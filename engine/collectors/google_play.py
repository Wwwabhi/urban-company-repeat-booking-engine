"""Google Play Store reviews collector for Urban Company customer app.

Uses `google-play-scraper` to pull public reviews, verify the official
app listing, strip usernames and user images, redact phone and email patterns,
run a pre-storage privacy-audit step to exclude reviews with potential addresses or pincodes,
and de-duplicate reviews into `data/raw/google_play_reviews.jsonl`.

Privacy & Exclusion Policy:
1. Usernames and user images are stripped at collection time.
2. Phone numbers and email patterns are redacted via regex.
3. Reviews containing unresolved potential addresses or postal pincodes are
   strictly excluded from `data/raw` storage.
4. Excluded review text is never persisted to any secondary or temporary file.
5. The collector logs the number of excluded reviews and reasons without logging
   any personal text.
6. Raw reviews from all services (including InstaHelp) that pass privacy checks
   are retained in raw data; InstaHelp exclusions apply downstream during core-metric analysis.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

try:
    from google_play_scraper import Sort, app, reviews
    from google_play_scraper.exceptions import NotFoundError
except ImportError as err:
    sys.exit(
        f"Missing dependency: {err}. Please install via: pip install google-play-scraper"
    )

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Verified official customer app ID
OFFICIAL_APP_ID = "com.urbanclap.urbanclap"
EXPECTED_TITLE_KEYWORD = "Urban Company"

# Regex patterns for redaction and privacy exclusion auditing
PHONE_PATTERN = re.compile(
    r"(?:\+?91[\s.-]?|\(?\+91\)?[\s.-]?|0)?[6-9](?:[\s.-]?\d){9}\b"
)
EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@{1,2}(?:\.[A-Za-z]{2,}|[A-Za-z0-9.-]+(?:\.[A-Za-z]{2,})?)\b"
)
EXPLICIT_PINCODE_PATTERN = re.compile(
    r"\b(?:pin|pincode|pin\s*code|postal\s*code|post\s*code|zip|zipcode|zip\s*code|area\s*code)\s*(?:is|:|-)?\s*[1-9][0-9]{2}\s?[0-9]{3}\b",
    re.IGNORECASE,
)
PINCODE_PATTERN = re.compile(r"\b[1-9][0-9]{2}\s?[0-9]{3}\b")

# Common adjectives, determiners, or modifiers that precede ordinary non-address nouns
COMMON_ROAD_ADJECTIVES = (
    r"(?:the|a|an|this|that|my|our|any|bad|new|rough|off|down|hit|one|same|whole|smooth|bumpy|long|busy|narrow|dirty|open|main|cross|local|private|public|good|best|toll|service|bypass|dirt|mud)"
)
COMMON_COLONY_ADJECTIVES = (
    r"(?:ant|termite|bee|bacterial|microbial|new|our|my|a|the|this|that|any|gated|residential|old|small|large|nearby|whole|same)"
)

# Regex pattern for identifying residential, apartment, and street address indicators
ADDRESS_CUE_PATTERN = re.compile(
    # Apartment / Flat / House / Plot / Building specific identifier
    r"\b(?:flat|apt|apartment|house|h\.?\s*no|plot|villa|tower|block|bldg|building)\s*(?:no\.?|number)?\s*[:#-]?\s*[\w\d/-]+"
    # Numbered street / cross / main
    r"|\b(?:\d+[a-zA-Z]?(?:st|nd|rd|th)?|\d+)\s+(?:main|cross|street|road|lane|ave|avenue|gali)\b"
    # Road / Street number (e.g. Road no 4)
    r"|\b(?:road|street|gali|lane)\s*(?:no\.?|number)?\s*[:#-]?\s*\d+\b"
    # Named Road / Street (excluding common descriptive adjectives)
    r"|\b(?!" + COMMON_ROAD_ADJECTIVES + r"\s+)[A-Za-z0-9_-]+\s+(?:street|road|marg|avenue)\b"
    # Sector or Phase number (e.g. Sector 62, Phase 2)
    r"|\b(?:sector|phase)\s*\d+\b"
    # Named Colony / Nagar / Layout / Enclave / Vihar / Puram (excluding biological or generic colony)
    r"|\b(?!" + COMMON_COLONY_ADJECTIVES + r"\s+)[A-Za-z0-9_-]+\s+(?:nagar|colony|layout|enclave|vihar|puram)\b",
    re.IGNORECASE,
)


def has_potential_pincode(text: str) -> bool:
    """Detects whether text contains a 6-digit postal pincode, filtering out order IDs, references, and monetary amounts."""
    if not text:
        return False

    if EXPLICIT_PINCODE_PATTERN.search(text):
        return True

    matches = list(re.finditer(r"\b([1-9][0-9]{2}\s?[0-9]{3})\b", text))
    if not matches:
        return False

    for m in matches:
        start, end = m.start(), m.end()
        surrounding_start = max(0, start - 25)
        surrounding_end = min(len(text), end + 25)
        before = text[surrounding_start:start]
        after = text[end:surrounding_end]

        # Preceded by reference, ID, transaction or price indicators
        if re.search(
            r"\b(?:booking|order|complaint|ticket|ref|reference|txn|transaction|job|crn|invoice|sr|id|coupon|promo)\s*(?:id|no\.?|number|#|code)?\s*[:#-]?\s*$",
            before,
            re.IGNORECASE,
        ):
            continue
        if re.search(
            r"(?:rs\.?|inr|₹|paid|cost|price|amount|fee|charges?)\s*(?:of|is|:)?\s*$",
            before,
            re.IGNORECASE,
        ):
            continue
        if re.search(r"\b(?:over|nearly|approx|about)\s+$", before, re.IGNORECASE):
            continue

        # Followed by metric, count, or currency indicators
        if re.search(
            r"^\s*(?:\+|plus\b|rupees\b|rs\b|inr\b|bucks\b|users\b|customers\b|downloads\b|people\b|reviews\b)",
            after,
            re.IGNORECASE,
        ):
            continue

        return True

    return False


# Common stop words/verbs/modifiers that must not be swallowed as the second word of a person name
PERSON_NAME_STOP_WORDS = {
    "is", "was", "are", "were", "has", "have", "had", "did", "does", "do",
    "and", "but", "or", "so", "very", "came", "visited", "arrived", "called",
    "fixed", "repaired", "done", "cleaned", "left", "great", "good", "nice",
    "punctual", "polite", "professional", "on", "in", "at", "for", "with",
    "by", "to", "also", "then", "just", "really", "always", "never",
}

# Whitelist of brand, platform, product, and category terms that must NEVER be redacted as person names
PERSON_NAME_WHITELIST = {
    "urban", "company", "urban company", "uc", "urbanclap",
    "instahelp", "insta help", "insta", "help",
    "ikea", "native", "native m1", "native m1 pro", "m1 pro",
    "kanpeki", "o3", "kenpeki", "ac", "ai", "sop", "ro", "water", "purifier",
    "spa", "salon", "app", "google", "apple", "play", "store",
    "play store", "app store", "service", "services", "cleaning",
}


def clean_name_tokens(name: str) -> str:
    """Strips trailing stop words/verbs from two-word matched name strings."""
    tokens = name.split()
    if len(tokens) == 2 and tokens[1].lower() in PERSON_NAME_STOP_WORDS:
        return tokens[0]
    return name


def redact_person_names(text: str) -> str:
    """Contextually redacts identifiable third-party personal names in review text.

    Applies contextual detection around:
    1. Worker enumeration cues (e.g. 'Whether it is Ramprit, Mohammad').
    2. Honorifics (Mr., Ms., Mrs., Dr., Mohd., Shri, etc.).
    3. Explicit service worker role prefixes (technician Ramesh, beautician Priya).
    4. Attribution prepositions (done by Ramesh, visited by Suresh).
    5. Commendation / gratitude cues (thanks to Ramesh, kudos to Priya).

    Preserves platform, brand, category, and product names via PERSON_NAME_WHITELIST.
    """
    if not text:
        return ""

    # 1. Partner enumeration cue (e.g. "whether it is Ramprit, Mohammad")
    def _sub_enum(m):
        prefix = m.group(1)
        names_str = m.group(2)
        parts = [p.strip() for p in names_str.split(",")]
        redacted_parts = []
        for p in parts:
            if p.lower() not in PERSON_NAME_WHITELIST and re.match(r"^[A-Z][a-z]+$", p):
                redacted_parts.append("[NAME_REDACTED]")
            else:
                redacted_parts.append(p)
        return f"{prefix} " + ", ".join(redacted_parts)

    text = re.sub(
        r"(?i:\b(whether\s+it\s+is|namely|specifically)\s+)([A-Z][a-z]+(?:\s*,\s*[A-Z][a-z]+)*)",
        _sub_enum,
        text,
    )

    # 2. Honorifics: Mr. / Ms. / Mrs. / Dr. / Mohd. / Shri
    def _sub_honorific(m):
        full_match = m.group(0)
        prefix = m.group(1)
        raw_name = m.group(2)
        name = clean_name_tokens(raw_name)
        if name.lower() in PERSON_NAME_WHITELIST:
            return full_match
        remainder = raw_name[len(name):]
        return f"{prefix}[NAME_REDACTED]{remainder}"

    text = re.sub(
        r"(?i:\b((?:mr|mrs|ms|dr|shri|smt|mohd)\.?\s+))([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        _sub_honorific,
        text,
    )

    # 3. Explicit role prefix: technician Ramesh, cleaner Priya, etc.
    def _sub_role(m):
        full_match = m.group(0)
        prefix = m.group(1)
        raw_name = m.group(2)
        name = clean_name_tokens(raw_name)
        if name.lower() in PERSON_NAME_WHITELIST:
            return full_match
        remainder = raw_name[len(name):]
        return f"{prefix}[NAME_REDACTED]{remainder}"

    text = re.sub(
        r"(?i:\b((?:technician|professional|server|pro|staff|mechanic|plumber|electrician|carpenter|beautician|cleaner|agent|rep|representative|person|guy|girl|boy)\s+(?:named|called|is|was)?\s*))([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        _sub_role,
        text,
    )

    # 4. Attribution prepositions: done by, serviced by, attended by, etc.
    def _sub_attribution(m):
        full_match = m.group(0)
        prefix = m.group(1)
        raw_name = m.group(2)
        name = clean_name_tokens(raw_name)
        if name.lower() in PERSON_NAME_WHITELIST:
            return full_match
        remainder = raw_name[len(name):]
        return f"{prefix}[NAME_REDACTED]{remainder}"

    text = re.sub(
        r"(?i:\b((?:served|attended|visited|serviced|done|repaired)\s+by\s+))([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        _sub_attribution,
        text,
    )

    # 5. Gratitude cues: thanks to, kudos to, etc.
    def _sub_gratitude(m):
        full_match = m.group(0)
        prefix = m.group(1)
        raw_name = m.group(2)
        name = clean_name_tokens(raw_name)
        if name.lower() in PERSON_NAME_WHITELIST:
            return full_match
        remainder = raw_name[len(name):]
        return f"{prefix}[NAME_REDACTED]{remainder}"

    text = re.sub(
        r"(?i:\b((?:thanks|kudos|shoutout|gratitude)\s+(?:to|for)\s+))([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        _sub_gratitude,
        text,
    )

    return text


def redact_pii(text: str) -> str:
    """Redacts standard phone numbers, email addresses, and contextual third-party personal names."""
    if not text:
        return ""
    text = PHONE_PATTERN.sub("[PHONE_REDACTED]", text)
    text = EMAIL_PATTERN.sub("[EMAIL_REDACTED]", text)
    text = redact_person_names(text)
    return text.strip()


def sanitize_text(text: str) -> str:
    """Alias for redact_pii for backward compatibility."""
    return redact_pii(text)


def audit_privacy(text: str) -> List[str]:
    """Privacy-audit step: inspects text for unresolved potential addresses, pincodes, or residual PII.

    Returns a list of exclusion reasons if any sensitive items are detected.
    Reviews with any returned flags MUST be excluded from storage.
    """
    flags: List[str] = []
    if not text:
        return flags

    # Check for residual contact information not caught by redaction
    if PHONE_PATTERN.search(text):
        flags.append("residual_phone_number")
    if EMAIL_PATTERN.search(text):
        flags.append("residual_email_address")

    # Check for postal pincodes (differentiating from order IDs / monetary amounts)
    if has_potential_pincode(text):
        flags.append("potential_postal_pincode")

    # Check for residential or street address indicators
    if ADDRESS_CUE_PATTERN.search(text):
        flags.append("potential_address_cue")

    return flags


def verify_app_listing(app_id: str) -> Dict[str, Any]:
    """Verifies that the target app ID belongs to the official Urban Company customer app."""
    logger.info(f"Verifying official Google Play app listing for package: '{app_id}'...")
    try:
        app_details = app(app_id, lang="en", country="in")
    except NotFoundError:
        raise ValueError(f"App package ID '{app_id}' was not found on Google Play Store.")
    except Exception as e:
        raise RuntimeError(f"Error communicating with Google Play Store: {e}")

    title = app_details.get("title", "")
    developer = app_details.get("developer", "")

    logger.info(f"Verified app listing: Title='{title}', Developer='{developer}', AppId='{app_id}'")

    if EXPECTED_TITLE_KEYWORD.lower() not in title.lower() and EXPECTED_TITLE_KEYWORD.lower() not in developer.lower():
        raise ValueError(
            f"Listing mismatch: expected '{EXPECTED_TITLE_KEYWORD}' in title or developer, but found Title='{title}', Developer='{developer}'"
        )

    return app_details


def load_existing_review_ids(output_file: Path) -> Set[str]:
    """Reads existing review IDs from the JSONL file to prevent duplicates."""
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


def collect_reviews(
    app_id: str = OFFICIAL_APP_ID,
    target_count: int = 20,
    output_path: Path = Path("data/raw/google_play_reviews.jsonl"),
    lang: str = "en",
    country: str = "in",
    request_delay: float = 1.0,
    dedupe_paths: Optional[List[Path]] = None,
) -> int:
    """Collects public reviews, strips PII, and appends unique records to JSONL.

    Persists each successfully processed batch immediately to disk to guarantee
    fault tolerance and prevent data loss if an unexpected error or interruption occurs.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    existing_ids = load_existing_review_ids(output_path)
    for extra_path in dedupe_paths or []:
        if extra_path != output_path:
            existing_ids.update(load_existing_review_ids(extra_path))

    collected_records: List[Dict[str, Any]] = []
    seen_in_batch: Set[str] = set()
    continuation_token: Optional[Any] = None
    batch_size = min(max(target_count, 10), 100)
    excluded_count = 0
    exclusion_reasons: Dict[str, int] = {}
    batch_idx = 1

    logger.info(
        f"Starting review collection for '{app_id}' (target: {target_count} reviews, "
        f"batch size: {batch_size}, delay: {request_delay}s)..."
    )

    try:
        while len(collected_records) < target_count:
            fetch_count = min(batch_size, target_count - len(collected_records) + 10)
            logger.info(f"Fetching reviews batch {batch_idx} from Google Play...")
            try:
                rvs, continuation_token = reviews(
                    app_id,
                    lang=lang,
                    country=country,
                    sort=Sort.NEWEST,
                    count=fetch_count,
                    continuation_token=continuation_token,
                )
            except Exception as e:
                logger.error(
                    f"Unexpected fetch failure on batch {batch_idx} ({len(collected_records)}/{target_count} collected): {e}"
                )
                raise RuntimeError(
                    f"Google Play collection failed on batch {batch_idx} after collecting {len(collected_records)} reviews: {e}"
                ) from e

            if not rvs:
                logger.info(f"No more reviews returned by the scraper at batch {batch_idx} (end of feed).")
                break

            batch_records: List[Dict[str, Any]] = []
            for r in rvs:
                review_id = str(r.get("reviewId"))
                if not review_id or review_id in existing_ids or review_id in seen_in_batch:
                    continue

                raw_text = r.get("content") or ""
                cleaned_text = redact_pii(raw_text)

                # Skip completely empty reviews if any
                if not cleaned_text:
                    continue

                # Privacy-audit step: exclude reviews with unresolved potential addresses or pincodes
                privacy_flags = audit_privacy(cleaned_text)
                if privacy_flags:
                    excluded_count += 1
                    for flag in privacy_flags:
                        exclusion_reasons[flag] = exclusion_reasons.get(flag, 0) + 1
                    continue  # Discarded immediately; never stored in data/raw or any secondary file

                # Note: Retain all services including InstaHelp in raw data;
                # InstaHelp exclusions are strictly applied downstream during core-metric analysis.

                review_date = r.get("at")
                date_str = review_date.strftime("%Y-%m-%d") if isinstance(review_date, datetime) else None

                # Strictly strip usernames, userImage, and personal account metadata
                record = {
                    "id": review_id,
                    "source": "Play Store",
                    "date": date_str,
                    "score": int(r.get("score")) if r.get("score") is not None else None,
                    "text": cleaned_text,
                    "thumbs_up": int(r.get("thumbsUpCount") or 0),
                    "app_version": r.get("appVersion"),
                    "review_created_version": r.get("reviewCreatedVersion"),
                    "collected_at": datetime.now(timezone.utc).isoformat(),
                }

                batch_records.append(record)
                seen_in_batch.add(review_id)

                if len(collected_records) + len(batch_records) >= target_count:
                    break

            # Persist valid records from this batch immediately to preserve progress
            if batch_records:
                with output_path.open("a", encoding="utf-8") as f:
                    for rec in batch_records:
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                existing_ids.update(r["id"] for r in batch_records)
                collected_records.extend(batch_records)

            logger.info(
                f"Batch {batch_idx}: {len(rvs)} items processed, {len(batch_records)} new valid records persisted "
                f"(total this run: {len(collected_records)}/{target_count})"
            )

            batch_idx += 1
            if not continuation_token or len(rvs) == 0:
                break

            if len(collected_records) < target_count and request_delay > 0:
                time.sleep(request_delay)

    finally:
        # Log aggregate privacy exclusion summary (counts and reason categories only)
        if excluded_count > 0:
            logger.info(
                f"Privacy exclusion summary: {excluded_count} reviews were excluded from storage. Breakdown: {dict(exclusion_reasons)}"
            )

    if collected_records:
        logger.info(
            f"Successfully saved {len(collected_records)} reviews to {output_path}"
        )
    else:
        logger.warning("No new reviews were collected.")

    return len(collected_records)


def main():
    parser = argparse.ArgumentParser(
        description="Collect public Google Play reviews for Urban Company customer app."
    )
    parser.add_argument(
        "--app-id",
        type=str,
        default=OFFICIAL_APP_ID,
        help=f"Google Play package ID (default: {OFFICIAL_APP_ID})",
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
        default=Path("data/raw/google_play_reviews.jsonl"),
        help="Output JSONL path (default: data/raw/google_play_reviews.jsonl)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay in seconds between paginated review requests (default: 1.0)",
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
        verify_app_listing(args.app_id)

        # Step 2: Collect reviews
        collected = collect_reviews(
            app_id=args.app_id,
            target_count=args.count,
            output_path=args.output,
            request_delay=args.delay,
            dedupe_paths=args.dedupe_from,
        )
        print(f"\n[DONE] Collected {collected} records into {args.output}")
    except Exception as e:
        logger.error(f"Collector failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
