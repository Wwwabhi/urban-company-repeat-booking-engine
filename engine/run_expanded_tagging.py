"""Resumable expanded tagging runner (v3_2) for untagged core consumer reviews.

Selects untagged core consumer reviews (Play Store + App Store, is_instahelp=False)
excluding baseline-tagged (184) and golden-set (30) records, runs the validated
v3_2 prompt/schema via Groq or Gemini, validates 16 fields, evidence grounding,
privacy, and human-review routing, and persists resumable outputs into an
isolated directory (`data/tagged/expanded_v2_pilot/` by default).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Set

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from engine.collectors.google_play import audit_privacy, redact_pii
from engine.tagger import (
    GeminiLLMClient,
    GroqLLMClient,
    tag_single_review,
    validate_16_schema_fields,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

DEFAULT_NORMALIZED_V2 = Path("data/processed/normalized_evidence_v2.jsonl")
DEFAULT_BASELINE_FILES = [
    Path("data/tagged/tagged_reviews.jsonl"),
    Path("data/tagged/review_queue.jsonl"),
    Path("data/golden/golden_set.jsonl"),
]
DEFAULT_OUTPUT_DIR = Path("data/tagged/expanded_v2_pilot")


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def collect_excluded_ids(paths: List[Path]) -> Set[str]:
    ids: Set[str] = set()
    for p in paths:
        for rec in load_jsonl(p):
            rid = str(rec.get("review_id", "")).strip()
            if rid:
                ids.add(rid)
    return ids


def select_untagged_core_consumer_reviews(
    normalized_path: Path = DEFAULT_NORMALIZED_V2,
    exclude_paths: List[Path] = DEFAULT_BASELINE_FILES,
) -> List[Dict[str, Any]]:
    excluded = collect_excluded_ids(exclude_paths)
    selected: List[Dict[str, Any]] = []
    for rec in load_jsonl(normalized_path):
        if rec.get("source") not in ("Play Store", "App Store"):
            continue
        if rec.get("is_instahelp"):
            continue
        rid = str(rec.get("review_id", "")).strip()
        if not rid or rid in excluded:
            continue
        selected.append(rec)
    return selected


def run_expanded_tagging(
    provider: str = "groq",
    version: str = "v3_2",
    limit: int = 20,
    delay: float = 20.0,
    max_completion_tokens: int = 1500,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    exclude_files: List[Path] | None = None,
    resume: bool = True,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    tagged_path = output_dir / "tagged_reviews_expanded.jsonl"
    queue_path = output_dir / "review_queue_expanded.jsonl"
    failed_path = output_dir / "failed_reviews_expanded.jsonl"
    metrics_path = output_dir / "metrics_expanded.json"

    already_done: Set[str] = set()
    if resume:
        already_done = collect_excluded_ids([tagged_path, queue_path])

    all_excludes = list(DEFAULT_BASELINE_FILES) + list(exclude_files or [])
    candidates = select_untagged_core_consumer_reviews(exclude_paths=all_excludes)
    pending = [r for r in candidates if r["review_id"] not in already_done]
    if limit > 0:
        pending = pending[:limit]

    if provider == "groq":
        client = GroqLLMClient(
            model_name="openai/gpt-oss-120b",
            version=version,
            max_completion_tokens=max_completion_tokens,
            request_delay=0.0,
            initial_backoff=3.0,
            max_backoff=35.0,
            max_retries=3,
        )
    elif provider == "gemini":
        client = GeminiLLMClient(
            version=version,
            request_delay=0.0,
            max_retries=3,
        )
    else:
        raise ValueError(f"Unsupported provider: {provider}")

    all_metrics: List[Dict[str, Any]] = []
    if resume and metrics_path.exists():
        try:
            all_metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        except Exception:
            all_metrics = []

    succeeded = 0
    queued = 0
    failed = 0

    for idx, raw_rec in enumerate(pending, start=1):
        rid = raw_rec["review_id"]
        # Defense-in-depth PII redaction before sending to model
        clean_rec = dict(raw_rec)
        clean_rec["text"] = redact_pii(raw_rec.get("text") or "")
        if audit_privacy(clean_rec["text"]):
            logger.warning(f"[{idx}/{len(pending)}] {rid[:8]} skipped by privacy audit")
            continue

        t0 = time.monotonic()
        try:
            packaged = tag_single_review(
                normalized_review=clean_rec,
                client=client,
                prompt_version=f"tagger_{version}",
            )
            elapsed = round(time.monotonic() - t0, 3)

            # Validate 16 fields and verbatim quote grounding
            validate_16_schema_fields(packaged["tags"])
            quote = packaged["tags"].get("evidence_quote") or ""
            grounded = quote in clean_rec["text"] if quote else False

            target_file = queue_path if packaged["metadata"]["requires_human_review"] else tagged_path
            with target_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(packaged, ensure_ascii=False) + "\n")

            if packaged["metadata"]["requires_human_review"]:
                queued += 1
            else:
                succeeded += 1

            # Capture client call metrics if recorded
            last_call = getattr(client, "call_metrics", [])[-1:] or [{}]
            m_entry = dict(last_call[0])
            m_entry.update(
                {
                    "review_id": rid,
                    "provider": provider,
                    "status": "ok",
                    "wall_latency_s": elapsed,
                    "grounded_quote": grounded,
                    "requires_human_review": packaged["metadata"]["requires_human_review"],
                }
            )
            all_metrics.append(m_entry)
            logger.info(
                f"[{idx}/{len(pending)}] {rid[:8]} OK ({elapsed}s, "
                f"queued={packaged['metadata']['requires_human_review']}, grounded={grounded})"
            )
        except Exception as exc:
            elapsed = round(time.monotonic() - t0, 3)
            failed += 1
            with failed_path.open("a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {"review_id": rid, "error_type": type(exc).__name__, "error": str(exc)},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            all_metrics.append(
                {
                    "review_id": rid,
                    "provider": provider,
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "wall_latency_s": elapsed,
                }
            )
            logger.error(f"[{idx}/{len(pending)}] {rid[:8]} FAILED ({type(exc).__name__})")

        metrics_path.write_text(json.dumps(all_metrics, indent=2), encoding="utf-8")
        if idx < len(pending) and delay > 0:
            time.sleep(delay)

    summary = {
        "provider": provider,
        "version": version,
        "total_candidates_available": len(candidates),
        "processed_this_run": len(pending),
        "tagged_direct": succeeded,
        "routed_to_queue": queued,
        "failed": failed,
        "output_dir": str(output_dir),
    }
    logger.info(f"Expanded tagging run summary: {summary}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run resumable expanded tagging (v3_2).")
    parser.add_argument("--provider", choices=["groq", "gemini"], default="groq")
    parser.add_argument("--version", default="v3_2")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--delay", type=float, default=20.0)
    parser.add_argument("--max-completion-tokens", type=int, default=1500)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--exclude-files", type=Path, nargs="*", default=[])
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()

    run_expanded_tagging(
        provider=args.provider,
        version=args.version,
        limit=args.limit,
        delay=args.delay,
        max_completion_tokens=args.max_completion_tokens,
        output_dir=args.output_dir,
        exclude_files=args.exclude_files,
        resume=not args.no_resume,
    )


if __name__ == "__main__":
    main()
