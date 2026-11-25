"""Apple App Store public customer reviews collector for Urban Company customer app.

Uses Apple's official public customer-reviews RSS feed (iTunes Store RSS),
verifies the official app listing via the iTunes lookup API, strips author/account
metadata, redacts phone/email patterns, excludes potential addresses and pincodes
before storage, and writes deduplicated reviews to `data/raw/app_store_reviews.jsonl`.

Privacy & Exclusion Policy:
1. Author names and account links are stripped at collection time and never stored.
2. Phone numbers and email patterns are redacted via regex.
3. Reviews containing unresolved potential addresses or postal pincodes are
   strictly excluded from `data/raw` storage.
4. Excluded review text is never persisted to any secondary or temporary file.
5. The collector logs the number of excluded reviews and reasons without logging
   any review IDs or personal text.
6. Public RSS feed only; no private, authenticated, or restricted endpoints accessed.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# Ensure project root is in sys.path for direct script execution
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from engine.collectors.google_play import audit_privacy, redact_pii

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Verified official Apple App Store identifiers for Urban Company India
OFFICIAL_APP_ID = "1032480595"
OFFICIAL_COUNTRY = "in"
EXPECTED_TITLE_KEYWORD = "Urban Company"
EXPECTED_DEVELOPER_KEYWORD = "Urban Company"

# Standard public User-Agent header for HTTP requests
HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def verify_app_store_listing(
    app_id: str = OFFICIAL_APP_ID, country: str = OFFICIAL_COUNTRY
) -> Dict[str, Any]:
    """Verifies official app listing via Apple's public iTunes Lookup API.

    Checks:
    1. App exists in target country storefront.
    2. Returned trackId matches the requested app_id.
    3. trackName contains the expected title keyword.
    4. artistName contains the expected developer keyword.
    """
    lookup_url = f"https://itunes.apple.com/lookup?id={app_id}&country={country}"
    logger.info(f"Verifying official App Store listing at: {lookup_url}")

    req = urllib.request.Request(lookup_url, headers=HTTP_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        raise RuntimeError(f"Failed to query iTunes lookup endpoint: {e}")

    results = data.get("results", [])
    if not results:
        raise ValueError(
            f"No App Store listing found for ID '{app_id}' in country '{country}'."
        )

    app_info = results[0]
    track_id = str(app_info.get("trackId", "")).strip()
    track_name = app_info.get("trackName", "").strip()
    artist_name = app_info.get("artistName", "").strip()
    bundle_id = app_info.get("bundleId", "").strip()

    logger.info(
        f"Verified App Store listing: Title='{track_name}', Developer='{artist_name}', "
        f"BundleId='{bundle_id}', TrackId='{track_id}'"
    )

    # 1. Verify track ID matches requested app ID
    if track_id != str(app_id).strip():
        raise ValueError(
            f"App Store ID mismatch: requested '{app_id}', received '{track_id}'."
        )

    # 2. Verify title contains expected keyword
    if EXPECTED_TITLE_KEYWORD.lower() not in track_name.lower():
        raise ValueError(
            f"Title mismatch: expected '{EXPECTED_TITLE_KEYWORD}' in title, found '{track_name}'."
        )

    # 3. Verify developer contains expected keyword
    if EXPECTED_DEVELOPER_KEYWORD.lower() not in artist_name.lower():
        raise ValueError(
            f"Developer mismatch: expected '{EXPECTED_DEVELOPER_KEYWORD}' in developer, found '{artist_name}'."
        )

    return app_info


def load_existing_review_ids(output_file: Path) -> Set[str]:
    """Loads existing review IDs from the JSONL output file to prevent duplicates."""
    seen_ids: Set[str] = set()
    if not output_file.exists():
        return seen_ids

    try:
        with output_file.open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if "id" in data:
                        seen_ids.add(str(data["id"]))
                except json.JSONDecodeError:
                    logger.warning(f"Malformed JSON on line {line_no} in {output_file}")
    except Exception as e:
        logger.warning(f"Could not read existing file {output_file}: {e}")

    logger.info(f"Loaded {len(seen_ids)} existing review IDs from {output_file}")
    return seen_ids


def fetch_review_page(
    app_id: str, page: int, country: str = OFFICIAL_COUNTRY
) -> List[Dict[str, Any]]:
    """Fetches a single page of customer reviews from Apple's public RSS feed."""
    feed_url = (
        f"https://itunes.apple.com/{country}/rss/customerreviews/"
        f"page={page}/id={app_id}/sortBy=mostRecent/json"
    )
    req = urllib.request.Request(feed_url, headers=HTTP_HEADERS)

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            logger.info(f"No further reviews available (page {page} returned 404).")
            return []
        raise RuntimeError(f"HTTP error {e.code} while fetching page {page}: {e}")
    except Exception as e:
        raise RuntimeError(f"Error fetching page {page} from Apple RSS feed: {e}")

    if not isinstance(data, dict):
        raise RuntimeError(
            f"Malformed response from Apple RSS feed: expected JSON object, got {type(data).__name__}"
        )

    feed = data.get("feed")
    if not isinstance(feed, dict):
        raise RuntimeError("Malformed response from Apple RSS feed: missing 'feed' object")

    entries = feed.get("entry", [])
    if isinstance(entries, dict):
        entries = [entries]
    elif not isinstance(entries, list):
        entries = []

    review_entries: List[Dict[str, Any]] = []
    for entry in entries:
        if isinstance(entry, dict) and "im:rating" in entry and "content" in entry:
            review_entries.append(entry)

    return review_entries


def collect_reviews(
    app_id: str = OFFICIAL_APP_ID,
    target_count: int = 20,
    output_path: Path = Path("data/raw/app_store_reviews.jsonl"),
    country: str = OFFICIAL_COUNTRY,
    request_delay: float = 1.0,
    dedupe_paths: Optional[List[Path]] = None,
) -> int:
    """Collects public App Store reviews, applies privacy filters, and appends unique records."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    existing_ids = load_existing_review_ids(output_path)
    for extra_path in dedupe_paths or []:
        if extra_path != output_path:
            existing_ids.update(load_existing_review_ids(extra_path))

    collected_records: List[Dict[str, Any]] = []
    seen_in_batch: Set[str] = set()
    excluded_count = 0
    exclusion_reasons: Dict[str, int] = {}

    page = 1
    max_pages = 10  # Apple RSS feed hard limit is typically 10 pages (~500 reviews)

    logger.info(
        f"Starting Apple App Store collection for ID '{app_id}' (country: '{country}', "
        f"target: {target_count} reviews)..."
    )

    try:
        while len(collected_records) < target_count and page <= max_pages:
            logger.info(f"Fetching reviews page {page} from Apple RSS feed...")
            try:
                entries = fetch_review_page(app_id=app_id, page=page, country=country)
            except Exception as e:
                logger.error(
                    f"Unexpected fetch failure on page {page} ({len(collected_records)}/{target_count} collected): {e}"
                )
                raise RuntimeError(
                    f"Apple RSS collection failed on page {page} after collecting {len(collected_records)} reviews: {e}"
                ) from e

            if not entries:
                logger.info(f"No more reviews returned at page {page} (end of pagination).")
                break

            page_records: List[Dict[str, Any]] = []
            for entry in entries:
                review_id = str(entry.get("id", {}).get("label", "")).strip()
                if not review_id or review_id in existing_ids or review_id in seen_in_batch:
                    continue

                raw_title = entry.get("title", {}).get("label", "").strip()
                raw_content = entry.get("content", {}).get("label", "").strip()

                # Construct full review text, merging title if distinct
                if raw_title and not raw_content.startswith(raw_title):
                    raw_text = f"{raw_title}. {raw_content}"
                else:
                    raw_text = raw_content or raw_title

                if not raw_text:
                    continue

                # Redact phone numbers and email addresses
                cleaned_text = redact_pii(raw_text)

                # Privacy audit: check for unresolved addresses, pincodes, or residual PII
                privacy_flags = audit_privacy(cleaned_text)
                if privacy_flags:
                    excluded_count += 1
                    for flag in privacy_flags:
                        exclusion_reasons[flag] = exclusion_reasons.get(flag, 0) + 1
                    # Discard immediately; omit review ID and review text from logs
                    continue

                # Parse publication/update date
                updated_str = entry.get("updated", {}).get("label", "")
                date_str: Optional[str] = None
                if updated_str:
                    try:
                        dt = datetime.fromisoformat(updated_str)
                        date_str = dt.strftime("%Y-%m-%d")
                    except ValueError:
                        date_str = None

                # Parse score/rating (1-5)
                score: Optional[int] = None
                try:
                    score = int(entry.get("im:rating", {}).get("label", 0))
                except (ValueError, TypeError):
                    score = None

                app_version = entry.get("im:version", {}).get("label")

                vote_count = 0
                try:
                    vote_count = int(entry.get("im:voteCount", {}).get("label", 0))
                except (ValueError, TypeError):
                    vote_count = 0

                vote_sum = 0
                try:
                    vote_sum = int(entry.get("im:voteSum", {}).get("label", 0))
                except (ValueError, TypeError):
                    vote_sum = 0

                # Strict privacy: discard author/username metadata completely
                record = {
                    "id": review_id,
                    "source": "App Store",
                    "date": date_str,
                    "score": score,
                    "title": redact_pii(raw_title) if raw_title else None,
                    "text": cleaned_text,
                    "app_version": app_version,
                    "vote_count": vote_count,
                    "vote_sum": vote_sum,
                    "collected_at": datetime.now(timezone.utc).isoformat(),
                }

                page_records.append(record)
                seen_in_batch.add(review_id)

                if len(collected_records) + len(page_records) >= target_count:
                    break

            # Persist valid records from this page immediately to preserve progress
            if page_records:
                with output_path.open("a", encoding="utf-8") as f:
                    for rec in page_records:
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                existing_ids.update(r["id"] for r in page_records)
                collected_records.extend(page_records)

            logger.info(
                f"Page {page}: {len(entries)} items processed, {len(page_records)} new valid records persisted "
                f"(total this run: {len(collected_records)}/{target_count})"
            )

            page += 1
            if len(collected_records) < target_count and page <= max_pages:
                time.sleep(request_delay)

    finally:
        # Log aggregate privacy exclusion summary (counts and reason categories only)
        if excluded_count > 0:
            logger.info(
                f"Privacy exclusion summary: {excluded_count} reviews were excluded from storage. "
                f"Reasons: {dict(exclusion_reasons)}"
            )

    if collected_records:
        logger.info(
            f"Successfully saved {len(collected_records)} App Store reviews to {output_path}"
        )
    else:
        logger.warning("No new App Store reviews were collected.")

    return len(collected_records)


def main():
    parser = argparse.ArgumentParser(
        description="Collect public Apple App Store reviews for Urban Company customer app."
    )
    parser.add_argument(
        "--app-id",
        type=str,
        default=OFFICIAL_APP_ID,
        help=f"Apple App Store app track ID (default: {OFFICIAL_APP_ID})",
    )
    parser.add_argument(
        "--country",
        type=str,
        default=OFFICIAL_COUNTRY,
        help=f"Store country storefront (default: {OFFICIAL_COUNTRY})",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=20,
        help="Number of reviews to collect (default: 20)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/raw/app_store_reviews.jsonl"),
        help="Output JSONL path (default: data/raw/app_store_reviews.jsonl)",
    )
    parser.add_argument(
        "--dedupe-from",
        type=Path,
        nargs="*",
        default=[],
        help="Additional JSONL files whose review IDs should be excluded as duplicates",
    )
    args = parser.parse_args()

    try:
        # Step 1: Verify official app listing
        verify_app_store_listing(app_id=args.app_id, country=args.country)

        # Step 2: Collect reviews
        collected = collect_reviews(
            app_id=args.app_id,
            target_count=args.count,
            output_path=args.output,
            country=args.country,
            dedupe_paths=args.dedupe_from,
        )
        print(f"\n[DONE] Collected {collected} App Store reviews into {args.output}")
    except Exception as e:
        logger.error(f"Collector failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
