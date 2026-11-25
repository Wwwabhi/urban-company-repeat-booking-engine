"""Public Investor Relations PDF collector for Urban Company disclosures.

Discovers and downloads publicly accessible PDFs from Urban Company's Investor
Relations financials page (Shareholder Letters, Earnings Call Transcripts, and
Results Press Releases), extracts paragraphs relevant to repeat-booking behavior,
retention, cross-category adoption, customer cohorts, and service quality, applies
PII redaction, deduplicates by content hash, and writes JSONL records.

Compliance:
- Publicly accessible unauthenticated investor relations pages and PDFs only.
- Records exact source URL, document title, source type, and collection timestamp.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import re
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import requests
from pypdf import PdfReader

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from engine.collectors.google_play import load_existing_review_ids, redact_pii

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

IR_FINANCIALS_URL = "https://investorrelations.urbancompany.com/financials"
DEFAULT_IR_OUTPUT = Path("data/raw/investor_relations_excerpts.jsonl")

RELEVANCE_KEYWORDS = (
    "repeat",
    "retention",
    "cohort",
    "frequency",
    "cross-category",
    "cross category",
    "transacting",
    "customer",
    "consumer",
    "rebook",
    "churn",
    "salon",
    "cleaning",
    "ac ",
    "plumb",
    "electric",
    "pest",
    "instahelp",
    "native",
    "quality",
    "cancellation",
    "fulfilment",
    "fulfillment",
)

QUARTER_DATE_MAP = {
    "Q2 FY26": "2025-10-31",
    "Q3 FY26": "2026-01-31",
    "Q4 FY26": "2026-05-15",
    "Q1 FY27": "2026-08-15",
    "Q2 FY27": "2026-10-31",
}


def classify_ir_source(url: str) -> str:
    """Maps an Investor Relations PDF URL to a schema-aligned source label."""
    lower = url.lower()
    if "shareholder" in lower or "letter" in lower:
        return "Shareholder Letter"
    if "transcript" in lower or "earnings_call" in lower or "earnings%20call" in lower or "conference%20call" in lower:
        return "Earnings Call"
    return "Press Release"


def infer_document_title_and_date(url: str) -> tuple[str, Optional[str]]:
    """Derives a clean document title and approximate disclosure date from PDF URL."""
    filename = urllib.parse.unquote(url.rsplit("/", 1)[-1]).replace(".pdf", "")
    title = re.sub(r"[_+]+", " ", filename).strip()
    inferred_date: Optional[str] = None
    norm_title = title.upper().replace("_", " ")
    for q_key, q_date in QUARTER_DATE_MAP.items():
        if q_key in norm_title:
            inferred_date = q_date
            break
    if inferred_date is None and "31012026" in filename:
        inferred_date = "2026-01-31"
    return title, inferred_date


def discover_ir_pdf_urls(
    financials_url: str = IR_FINANCIALS_URL,
    timeout: int = 20,
) -> List[str]:
    """Fetches the public IR financials page and extracts unique PDF URLs."""
    resp = requests.get(
        financials_url,
        headers={"User-Agent": "UC-RepeatBooking-DiscoveryEngine/1.0"},
        timeout=timeout,
    )
    resp.raise_for_status()
    urls = sorted(set(re.findall(r'https?://[^\s"\'<>]+\.pdf', resp.text, re.I)))
    return urls


def extract_relevant_paragraphs_from_pdf_bytes(
    pdf_bytes: bytes,
    source_url: str,
    min_chars: int = 100,
    max_chars: int = 1800,
) -> List[Dict[str, Any]]:
    """Extracts relevant, PII-redacted paragraphs from PDF bytes."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    source_label = classify_ir_source(source_url)
    doc_title, doc_date = infer_document_title_and_date(source_url)
    collected_at = datetime.now(timezone.utc).isoformat()

    records: List[Dict[str, Any]] = []
    for page_idx, page in enumerate(reader.pages, start=1):
        raw_page_text = page.extract_text() or ""
        # Split on double newlines or bullet/section breaks; collapse internal newlines
        raw_blocks = re.split(r"\n\s*\n", raw_page_text)
        for block in raw_blocks:
            cleaned = re.sub(r"\s+", " ", block).strip()
            if len(cleaned) < min_chars or len(cleaned) > max_chars:
                continue
            lower = cleaned.lower()
            if not any(kw in lower for kw in RELEVANCE_KEYWORDS):
                continue

            redacted = redact_pii(cleaned)
            content_hash = hashlib.sha256(
                f"{source_url}|p{page_idx}|{redacted}".encode("utf-8")
            ).hexdigest()[:16]

            records.append(
                {
                    "id": f"ir_{content_hash}",
                    "source": source_label,
                    "date": doc_date,
                    "score": None,
                    "title": f"{doc_title} (p.{page_idx})",
                    "text": redacted,
                    "source_url": source_url,
                    "document_title": doc_title,
                    "page_number": page_idx,
                    "collected_at": collected_at,
                }
            )
    return records


def collect_ir_disclosures(
    output_path: Path = DEFAULT_IR_OUTPUT,
    financials_url: str = IR_FINANCIALS_URL,
    max_pdfs: Optional[int] = None,
    timeout: int = 30,
) -> int:
    """Discovers public IR PDFs, extracts relevant excerpts, and writes deduplicated JSONL."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    existing_ids = load_existing_review_ids(output_path)

    pdf_urls = discover_ir_pdf_urls(financials_url=financials_url, timeout=timeout)
    if max_pdfs is not None:
        pdf_urls = pdf_urls[:max_pdfs]

    logger.info(f"Discovered {len(pdf_urls)} public IR PDFs from {financials_url}")

    new_records: List[Dict[str, Any]] = []
    seen_ids = set(existing_ids)

    for url in pdf_urls:
        try:
            logger.info(f"Fetching IR PDF: {url}")
            resp = requests.get(
                url,
                headers={"User-Agent": "UC-RepeatBooking-DiscoveryEngine/1.0"},
                timeout=timeout,
            )
            resp.raise_for_status()
            extracted = extract_relevant_paragraphs_from_pdf_bytes(
                resp.content, source_url=url
            )
            added_from_pdf = 0
            for rec in extracted:
                if rec["id"] in seen_ids:
                    continue
                seen_ids.add(rec["id"])
                new_records.append(rec)
                added_from_pdf += 1
            logger.info(
                f"Extracted {len(extracted)} relevant excerpts ({added_from_pdf} new) from {url}"
            )
        except Exception as e:
            logger.warning(f"Failed to process IR PDF {url}: {e}")

    if new_records:
        with output_path.open("a", encoding="utf-8") as f:
            for rec in new_records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    logger.info(f"Saved {len(new_records)} new IR excerpts to {output_path}")
    return len(new_records)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect public Urban Company Investor Relations excerpts."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_IR_OUTPUT)
    parser.add_argument("--max-pdfs", type=int, default=None)
    args = parser.parse_args()
    count = collect_ir_disclosures(output_path=args.output, max_pdfs=args.max_pdfs)
    print(f"\n[DONE] Collected {count} IR excerpts into {args.output}")


if __name__ == "__main__":
    main()
