"""Data normalization pipeline for Urban Company customer reviews.

Reads raw Google Play and Apple App Store reviews, maps them into a unified,
consistent intermediate schema, preserves source provenance and engagement metadata,
identifies InstaHelp reviews with a clear flag, performs intra-source deduplication,
and writes normalized records to `data/processed/normalized_reviews.jsonl`.

Raw files are strictly read-only and preserved untouched.
No LLM, intent inference, or category tagging is applied at this stage.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Ensure project root is in sys.path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Pattern to detect references to InstaHelp (quick-service maid / housekeeping)
INSTAHELP_PATTERN = re.compile(r"\binsta[-_\s]*(?:help|maids?)\b", re.IGNORECASE)

DEFAULT_GOOGLE_PLAY_RAW = Path("data/raw/google_play_reviews.jsonl")
DEFAULT_APP_STORE_RAW = Path("data/raw/app_store_reviews.jsonl")
DEFAULT_NORMALIZED_OUTPUT = Path("data/processed/normalized_reviews.jsonl")


def detect_instahelp(text: str, title: Optional[str] = None) -> bool:
    """Detects whether review text or title mentions Urban Company's InstaHelp service."""
    combined = f"{title or ''} {text or ''}"
    return bool(INSTAHELP_PATTERN.search(combined))


def normalize_google_play_record(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Maps a raw Google Play review record into the normalized intermediate schema."""
    text = (raw.get("text") or "").strip()
    title = None  # Google Play reviews do not have titles

    return {
        "review_id": str(raw.get("id", "")).strip(),
        "source": "Play Store",
        "date": raw.get("date"),
        "rating": raw.get("score"),
        "title": title,
        "text": text,
        "app_version": raw.get("app_version"),
        "review_created_version": raw.get("review_created_version"),
        "thumbs_up": raw.get("thumbs_up"),
        "vote_count": None,  # App Store specific
        "vote_sum": None,  # App Store specific
        "is_instahelp": detect_instahelp(text=text, title=title),
    }


def normalize_app_store_record(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Maps a raw Apple App Store review record into the normalized intermediate schema."""
    title = (raw.get("title") or "").strip() or None
    text = (raw.get("text") or "").strip()

    return {
        "review_id": str(raw.get("id", "")).strip(),
        "source": "App Store",
        "date": raw.get("date"),
        "rating": raw.get("score"),
        "title": title,
        "text": text,
        "app_version": raw.get("app_version"),
        "review_created_version": None,  # Play Store specific
        "thumbs_up": None,  # Play Store specific
        "vote_count": raw.get("vote_count"),
        "vote_sum": raw.get("vote_sum"),
        "is_instahelp": detect_instahelp(text=text, title=title),
    }


def normalize_dataset(
    file_path: Path, source_type: str
) -> Tuple[List[Dict[str, Any]], int]:
    """Reads a single raw dataset, deduplicates within the source, and normalizes records.

    Returns:
        Tuple of (normalized_records, duplicates_skipped)
    """
    if not file_path.exists():
        logger.warning(f"Raw source file does not exist: {file_path}")
        return [], 0

    normalized_records: List[Dict[str, Any]] = []
    seen_ids: Set[str] = set()
    duplicates_count = 0

    with file_path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                raw_record = json.loads(line)
            except json.JSONDecodeError as e:
                logger.warning(f"Malformed JSON on line {line_no} in {file_path}: {e}")
                continue

            review_id = str(raw_record.get("id", "")).strip()
            if not review_id:
                logger.warning(f"Missing review ID on line {line_no} in {file_path}; skipping.")
                continue

            # Intra-source deduplication: skip duplicates within the source
            if review_id in seen_ids:
                duplicates_count += 1
                logger.warning(
                    f"Duplicate review ID '{review_id}' encountered on line {line_no} in {file_path}; skipped."
                )
                continue

            seen_ids.add(review_id)

            if source_type == "Play Store":
                normalized = normalize_google_play_record(raw_record)
            elif source_type == "App Store":
                normalized = normalize_app_store_record(raw_record)
            else:
                raise ValueError(f"Unknown source type: '{source_type}'")

            normalized_records.append(normalized)

    logger.info(
        f"Normalized {len(normalized_records)} records from {file_path} "
        f"({duplicates_count} duplicates skipped)."
    )
    return normalized_records, duplicates_count


def run_normalization_pipeline(
    google_play_path: Path = DEFAULT_GOOGLE_PLAY_RAW,
    app_store_path: Path = DEFAULT_APP_STORE_RAW,
    output_path: Path = DEFAULT_NORMALIZED_OUTPUT,
) -> Dict[str, Any]:
    """Runs the full normalization pipeline across both raw datasets.

    Preserves raw files strictly unchanged, combines normalized records,
    and writes to the processed output path.
    """
    logger.info("Starting review normalization pipeline...")

    # 1. Normalize Google Play reviews
    gp_records, gp_dups = normalize_dataset(google_play_path, "Play Store")

    # 2. Normalize Apple App Store reviews
    as_records, as_dups = normalize_dataset(app_store_path, "App Store")

    # 3. Combine normalized records
    all_normalized = gp_records + as_records

    # 4. Write to processed output file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for rec in all_normalized:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    summary = {
        "total_normalized": len(all_normalized),
        "google_play_count": len(gp_records),
        "app_store_count": len(as_records),
        "google_play_duplicates_skipped": gp_dups,
        "app_store_duplicates_skipped": as_dups,
        "instahelp_count": sum(1 for r in all_normalized if r["is_instahelp"]),
        "core_uc_count": sum(1 for r in all_normalized if not r["is_instahelp"]),
        "output_path": str(output_path),
    }

    logger.info(
        f"Normalization complete: {summary['total_normalized']} total records written to {output_path} "
        f"({summary['core_uc_count']} core UC, {summary['instahelp_count']} InstaHelp)."
    )
    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Normalize Google Play and Apple App Store reviews into a unified schema."
    )
    parser.add_argument(
        "--google-play",
        type=Path,
        default=DEFAULT_GOOGLE_PLAY_RAW,
        help=f"Path to raw Google Play JSONL (default: {DEFAULT_GOOGLE_PLAY_RAW})",
    )
    parser.add_argument(
        "--app-store",
        type=Path,
        default=DEFAULT_APP_STORE_RAW,
        help=f"Path to raw Apple App Store JSONL (default: {DEFAULT_APP_STORE_RAW})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_NORMALIZED_OUTPUT,
        help=f"Path to output normalized JSONL (default: {DEFAULT_NORMALIZED_OUTPUT})",
    )
    args = parser.parse_args()

    try:
        summary = run_normalization_pipeline(
            google_play_path=args.google_play,
            app_store_path=args.app_store,
            output_path=args.output,
        )
        print("\n=== Normalization Summary ===")
        print(f"Total Normalized Records: {summary['total_normalized']}")
        print(f"  Play Store Records:     {summary['google_play_count']}")
        print(f"  App Store Records:      {summary['app_store_count']}")
        print(f"  Core UC Reviews:        {summary['core_uc_count']}")
        print(f"  InstaHelp Reviews:      {summary['instahelp_count']}")
        print(f"Saved to:                 {summary['output_path']}")
    except Exception as e:
        logger.error(f"Normalization pipeline failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
