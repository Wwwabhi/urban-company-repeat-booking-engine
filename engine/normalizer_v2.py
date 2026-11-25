"""Expanded normalization and deduplication pipeline (v2) for all raw evidence sources.

Reads baseline raw files (read-only) plus expanded v2 raw files and Investor
Relations excerpts, deduplicates across all sources by (source, id) and exact
normalized text hash, flags InstaHelp records, logs cleaning statistics, and
writes to `data/processed/normalized_evidence_v2.jsonl` without modifying
`data/processed/normalized_reviews.jsonl`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from engine.normalizer import (
    detect_instahelp,
    normalize_app_store_record,
    normalize_google_play_record,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

DEFAULT_RAW_SOURCES = [
    ("Play Store", Path("data/raw/google_play_reviews.jsonl")),
    ("Play Store", Path("data/raw/google_play_reviews_v2.jsonl")),
    ("App Store", Path("data/raw/app_store_reviews.jsonl")),
    ("Investor Relations", Path("data/raw/investor_relations_excerpts.jsonl")),
]
DEFAULT_OUTPUT_V2 = Path("data/processed/normalized_evidence_v2.jsonl")
DEFAULT_REPORT_V2 = Path("data/processed/normalization_v2_report.json")


def normalize_ir_record(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Maps a raw Investor Relations excerpt into the unified normalized schema."""
    text = (raw.get("text") or "").strip()
    title = (raw.get("title") or "").strip() or None
    return {
        "review_id": str(raw.get("id", "")).strip(),
        "source": raw.get("source") or "Shareholder Letter",
        "date": raw.get("date"),
        "rating": None,
        "title": title,
        "text": text,
        "app_version": None,
        "review_created_version": None,
        "thumbs_up": None,
        "vote_count": None,
        "vote_sum": None,
        "source_url": raw.get("source_url"),
        "collected_at": raw.get("collected_at"),
        "is_instahelp": detect_instahelp(text=text, title=title),
    }


def normalize_record_by_source(raw: Dict[str, Any], source_group: str) -> Dict[str, Any]:
    """Dispatches normalization by source group while preserving provenance."""
    if source_group == "Play Store":
        rec = normalize_google_play_record(raw)
        rec["collected_at"] = raw.get("collected_at")
        return rec
    if source_group == "App Store":
        rec = normalize_app_store_record(raw)
        rec["collected_at"] = raw.get("collected_at")
        return rec
    return normalize_ir_record(raw)


def run_normalization_v2(
    sources: List[Tuple[str, Path]] = DEFAULT_RAW_SOURCES,
    output_path: Path = DEFAULT_OUTPUT_V2,
    report_path: Path = DEFAULT_REPORT_V2,
) -> Dict[str, Any]:
    """Normalizes and deduplicates all raw evidence sources into v2 output."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    seen_ids: Set[Tuple[str, str]] = set()
    seen_text_hashes: Set[str] = set()
    normalized: List[Dict[str, Any]] = []

    raw_counts_by_file: Dict[str, int] = {}
    removed_counts = Counter()
    kept_by_source = Counter()
    instahelp_count = 0

    for source_group, path in sources:
        if not path.exists():
            logger.warning(f"Source file not found, skipping: {path}")
            continue
        file_raw_count = 0
        with path.open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                file_raw_count += 1
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    removed_counts["malformed_json"] += 1
                    continue

                rec = normalize_record_by_source(raw, source_group)
                rid = rec["review_id"]
                text = rec["text"]

                if not rid:
                    removed_counts["missing_id"] += 1
                    continue
                if not text:
                    removed_counts["empty_text"] += 1
                    continue

                id_key = (rec["source"], rid)
                if id_key in seen_ids:
                    removed_counts["duplicate_id"] += 1
                    continue

                # Exact-text deduplication within same source
                norm_text_key = re.sub(r"\s+", " ", text.lower()).strip()
                text_hash = hashlib.sha256(
                    f"{rec['source']}|{norm_text_key}".encode("utf-8")
                ).hexdigest()
                if len(norm_text_key) >= 25 and text_hash in seen_text_hashes:
                    removed_counts["duplicate_text"] += 1
                    continue

                seen_ids.add(id_key)
                seen_text_hashes.add(text_hash)
                normalized.append(rec)
                kept_by_source[rec["source"]] += 1
                if rec["is_instahelp"]:
                    instahelp_count += 1

        raw_counts_by_file[str(path)] = file_raw_count

    with output_path.open("w", encoding="utf-8") as f:
        for rec in normalized:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    report = {
        "total_raw_read": sum(raw_counts_by_file.values()),
        "raw_counts_by_file": raw_counts_by_file,
        "total_normalized_kept": len(normalized),
        "kept_by_source": dict(kept_by_source),
        "removed_counts": dict(removed_counts),
        "instahelp_flagged": instahelp_count,
        "core_eligible": len(normalized) - instahelp_count,
        "output_path": str(output_path),
    }

    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    logger.info(
        f"Normalization v2 complete: {report['total_normalized_kept']} kept "
        f"({report['core_eligible']} core eligible, {instahelp_count} InstaHelp) "
        f"from {report['total_raw_read']} raw items."
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run expanded v2 normalization.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_V2)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_V2)
    args = parser.parse_args()
    run_normalization_v2(output_path=args.output, report_path=args.report)


if __name__ == "__main__":
    main()
