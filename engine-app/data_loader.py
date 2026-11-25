"""Data loading, metric calculation, filtering, and live Groq v3.2 tagging helpers
for the Urban Company Repeat-Booking Discovery Engine (`engine-app/`).

Kept free of Streamlit UI imports so all data/metric logic is unit-testable.
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from engine.analyze_evidence import CATEGORY_PATTERNS, PAIN_POINT_PATTERNS
from engine.collectors.google_play import audit_privacy, redact_pii
from engine.tagger import GroqLLMClient, tag_single_review

MAX_LIVE_INPUT_CHARS = 2000
UC_REPORTED_PLATFORM_AVG_RATING = 4.79

DEFAULT_DATA_PATHS = {
    "normalized_v2": _REPO_ROOT / "data/processed/normalized_evidence_v2.jsonl",
    "norm_report_v2": _REPO_ROOT / "data/processed/normalization_v2_report.json",
    "analysis_summary": _REPO_ROOT / "data/processed/analysis_summary.json",
    "tagged_v1": _REPO_ROOT / "data/tagged/tagged_reviews.jsonl",
    "queue_v1": _REPO_ROOT / "data/tagged/review_queue.jsonl",
    "tagged_v3_1": _REPO_ROOT / "data/tagged/tagged_reviews_v3_1.jsonl",
    "queue_v3_1": _REPO_ROOT / "data/tagged/review_queue_v3_1.jsonl",
    "tagged_groq_v3_2": _REPO_ROOT / "data/tagged/groq_pilot_v3_2/tagged_reviews_groq_v3_2.jsonl",
    "queue_groq_v3_2": _REPO_ROOT / "data/tagged/groq_pilot_v3_2/review_queue_groq_v3_2.jsonl",
    "golden_set": _REPO_ROOT / "data/golden/golden_set.jsonl",
}

OPPORTUNITY_THEMES: List[Dict[str, Any]] = [
    {
        "rank": 1,
        "theme": "Post-service continuity, maintenance timeline & warranty clarity",
        "pain_key": "warranty_and_post_service_gap",
        "evidence_summary": "22 warranty/post-service gap mentions (1,248 core); 14 high-rating (4-5★) delay/expectation frictions; 2 golden cases (4e4e2ef9, 1876c25b)",
        "categories": ["other (appliance/spa/carpentry/painting)", "AC", "deep clean", "pest control"],
        "impact": "High",
        "confidence": "Medium",
        "customer_side_influence": "Direct — post-job maintenance schedule & warranty checklist",
        "rationale": "Customers finish a one-off job without clear maintenance intervals, care guidelines, or warranty clarity, weakening 90-day recall.",
    },
    {
        "rank": 2,
        "theme": "Moment-of-need triage & category discovery (bridging offline default)",
        "pain_key": "offline_alternative_or_churn_signal",
        "evidence_summary": "11 explicit local-provider/churn mentions (1,248 core); 1 golden local-provider switch (14816200493); 0/184 recall_gap visible in app-store tags",
        "categories": ["plumber", "electrician", "AC", "other (appliance/spa/carpentry/painting)"],
        "impact": "High",
        "confidence": "Low-Medium",
        "customer_side_influence": "Direct — customer-side triage & prep companion",
        "rationale": "When a new household need arises, uncertain customers default to local technicians or society WhatsApp groups; requires interview validation.",
    },
    {
        "rank": 3,
        "theme": "Pre-booking expectation setting & cancellation/slot clarity",
        "pain_key": "cancellation_and_no_show",
        "evidence_summary": "82 cancellation/no-show mentions + 63 pricing/fee opacity mentions (10 in 4-5★); golden cases 36b24dd5, 06b45346, 14800891393",
        "categories": ["unspecified", "plumber", "deep clean", "other (appliance/spa/carpentry/painting)"],
        "impact": "Medium-High",
        "confidence": "Medium-High",
        "customer_side_influence": "Partial — pre-booking expectation & policy clarity checklist",
        "rationale": "Avoidable cancellation fee disputes and slot misunderstandings erode trust even among regular customers.",
    },
    {
        "rank": 4,
        "theme": "Customer support & escalation readiness",
        "pain_key": "customer_support_failure",
        "evidence_summary": "103 customer support failure mentions (94 in 1-2★) across 1,248 core consumer reviews",
        "categories": ["unspecified", "other (appliance/spa/carpentry/painting)"],
        "impact": "Medium (Retention floor)",
        "confidence": "High (pain point) / Low (customer-side tool)",
        "customer_side_influence": "Out of MVP scope — requires internal UC support workflows",
        "rationale": "Automated support loops block issue recovery, but internal support operations cannot be changed from a customer-side tool.",
    },
    {
        "rank": 5,
        "theme": "Technician skill & quality consistency",
        "pain_key": "technician_quality_and_behavior",
        "evidence_summary": "40 quality/behavior mentions (38 in 1-2★); corroborated by UC Q3 FY26 Shareholder Letter (ir_454a3734c3ecd554)",
        "categories": ["AC", "plumber", "electrician", "other (appliance/spa/carpentry/painting)"],
        "impact": "Medium",
        "confidence": "High (pain point) / Low (customer-side tool)",
        "customer_side_influence": "Out of MVP scope — no changes to professionals allowed",
        "rationale": "Quality consistency drives repeat usage per management disclosures, but partner training is outside project constraints.",
    },
]


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def sanitize_display_text(text: Optional[str]) -> str:
    """Applies defense-in-depth PII redaction before rendering any text in UI."""
    if not text:
        return ""
    return redact_pii(text)


def load_engine_bundle(paths: Optional[Dict[str, Path]] = None) -> Dict[str, Any]:
    """Loads all repository evidence, tagged outputs, golden records, and summaries."""
    p = paths or DEFAULT_DATA_PATHS
    norm_records = load_jsonl(p["normalized_v2"])
    norm_report = load_json(p["norm_report_v2"])
    analysis_summary = load_json(p["analysis_summary"])
    golden_records = load_jsonl(p["golden_set"])

    # Build lookup of existing LLM tags by review_id (latest version wins if multiple)
    tagged_by_id: Dict[str, Dict[str, Any]] = {}
    for key in ("tagged_v1", "queue_v1", "tagged_v3_1", "queue_v3_1", "tagged_groq_v3_2", "queue_groq_v3_2"):
        for rec in load_jsonl(p[key]):
            rid = str(rec.get("review_id", "")).strip()
            if rid:
                tagged_by_id[rid] = rec

    baseline_records = load_jsonl(p["tagged_v1"]) + load_jsonl(p["queue_v1"])
    baseline_by_id = {
        str(r.get("review_id", "")).strip(): r
        for r in baseline_records
        if r.get("review_id")
    }
    baseline_tagged_ids = set(baseline_by_id.keys())

    golden_by_id = {
        str(r.get("review_id", "")).strip(): r for r in golden_records if r.get("review_id")
    }

    return {
        "normalized_records": norm_records,
        "norm_report": norm_report,
        "analysis_summary": analysis_summary,
        "tagged_by_id": tagged_by_id,
        "baseline_by_id": baseline_by_id,
        "baseline_tagged_ids": baseline_tagged_ids,
        "golden_by_id": golden_by_id,
        "golden_records": golden_records,
    }


def compute_overview_metrics(bundle: Dict[str, Any]) -> Dict[str, Any]:
    """Computes exact, reproducible counts for the Overview page."""
    records = bundle["normalized_records"]
    tagged_by_id = bundle["tagged_by_id"]
    baseline_ids = bundle["baseline_tagged_ids"]

    total_evidence = len(records)
    instahelp_count = sum(1 for r in records if r.get("is_instahelp"))
    core_records = [r for r in records if not r.get("is_instahelp")]
    core_eligible = len(core_records)

    consumer_sources = {"Play Store", "App Store"}
    consumer_all = [r for r in records if r.get("source") in consumer_sources]
    consumer_core = [r for r in core_records if r.get("source") in consumer_sources]
    ir_core = [r for r in core_records if r.get("source") not in consumer_sources]

    tagged_in_dataset = sum(1 for r in core_records if r.get("review_id") in tagged_by_id)
    untagged_in_dataset = core_eligible - tagged_in_dataset
    untagged_consumer_core = sum(1 for r in consumer_core if r.get("review_id") not in tagged_by_id)

    source_counts = Counter(r.get("source", "Unknown") for r in records)
    core_rating_counts = Counter(
        str(int(r["rating"])) for r in consumer_core if r.get("rating") is not None
    )

    core_ratings = [float(r["rating"]) for r in consumer_core if r.get("rating") is not None]
    all_ratings = [float(r["rating"]) for r in consumer_all if r.get("rating") is not None]
    sample_avg_rating_core = round(sum(core_ratings) / len(core_ratings), 2) if core_ratings else None
    sample_avg_rating_all = round(sum(all_ratings) / len(all_ratings), 2) if all_ratings else None

    # Baseline 184 tagged sample headline stats (computed strictly from baseline 184, never overwritten by v3_2)
    baseline_by_id = bundle.get("baseline_by_id") or {}
    nww_true_baseline = 0
    recall_gap_true_baseline = 0
    for rid in baseline_ids:
        t_rec = baseline_by_id.get(rid) or tagged_by_id.get(rid) or {}
        tags = t_rec.get("tags") or {}
        if tags.get("nothing_went_wrong") is True:
            nww_true_baseline += 1
        if tags.get("recall_gap") is True:
            recall_gap_true_baseline += 1

    app_store_combined_count = source_counts.get("Play Store", 0) + source_counts.get("App Store", 0)

    return {
        "total_evidence": total_evidence,
        "core_eligible": core_eligible,
        "instahelp_count": instahelp_count,
        "consumer_all_count": len(consumer_all),
        "consumer_core_count": len(consumer_core),
        "ir_core_count": len(ir_core),
        "baseline_tagged_count": len(baseline_ids),
        "tagged_in_dataset": tagged_in_dataset,
        "untagged_in_dataset": untagged_in_dataset,
        "untagged_consumer_core": untagged_consumer_core,
        "golden_count": len(bundle["golden_records"]),
        "source_counts": dict(source_counts),
        "app_store_combined_count": app_store_combined_count,
        "core_rating_counts": dict(sorted(core_rating_counts.items())),
        "sample_avg_rating_core": sample_avg_rating_core,
        "sample_avg_rating_all": sample_avg_rating_all,
        "uc_platform_avg_rating": UC_REPORTED_PLATFORM_AVG_RATING,
        "baseline_nothing_went_wrong_true": nww_true_baseline,
        "baseline_recall_gap_true": recall_gap_true_baseline,
    }


def detect_directional_categories(text: str) -> List[str]:
    """Deterministic keyword match for filtering; never presented as an LLM tag."""
    cats = [cat for cat, pat in CATEGORY_PATTERNS.items() if pat.search(text)]
    return cats or ["unspecified"]


def filter_opportunity_evidence(
    records: List[Dict[str, Any]],
    pain_key: str,
    source_filter: str = "All",
    category_filter: str = "All",
    rating_filter: str = "All",
    exclude_instahelp: bool = True,
) -> List[Dict[str, Any]]:
    """Filters core evidence records matching a pain-point keyword pattern."""
    pattern = PAIN_POINT_PATTERNS.get(pain_key)
    if pattern is None:
        return []

    matches: List[Dict[str, Any]] = []
    for r in records:
        if exclude_instahelp and r.get("is_instahelp"):
            continue
        if source_filter != "All" and r.get("source") != source_filter:
            continue

        rating = r.get("rating")
        if rating_filter == "1-2 Stars" and rating not in (1, 2):
            continue
        if rating_filter == "3 Stars" and rating != 3:
            continue
        if rating_filter == "4-5 Stars" and rating not in (4, 5):
            continue
        if rating_filter == "No Rating (IR)" and rating is not None:
            continue

        combined = f"{r.get('title') or ''} {r.get('text') or ''}"
        if not pattern.search(combined):
            continue

        matched_cats = detect_directional_categories(combined)
        if category_filter != "All" and category_filter not in matched_cats:
            continue

        item = dict(r)
        item["matched_categories_keyword"] = matched_cats
        item["safe_text"] = sanitize_display_text(r.get("text"))
        item["safe_title"] = sanitize_display_text(r.get("title"))
        matches.append(item)

    return matches


def search_customer_voice(
    records: List[Dict[str, Any]],
    tagged_by_id: Dict[str, Dict[str, Any]],
    golden_by_id: Dict[str, Dict[str, Any]],
    query: str = "",
    source_filter: str = "All",
    tag_status_filter: str = "All",
    include_instahelp: bool = False,
) -> List[Dict[str, Any]]:
    """Searches evidence records and attaches existing LLM tags & review status."""
    q = query.strip().lower()
    results: List[Dict[str, Any]] = []

    for r in records:
        if not include_instahelp and r.get("is_instahelp"):
            continue
        if source_filter != "All" and r.get("source") != source_filter:
            continue

        rid = str(r.get("review_id", "")).strip()
        tagged_rec = tagged_by_id.get(rid)
        is_tagged = tagged_rec is not None
        meta = (tagged_rec or {}).get("metadata", {})
        requires_review = bool(meta.get("requires_human_review", False))

        if tag_status_filter == "Tagged (LLM)" and not is_tagged:
            continue
        if tag_status_filter == "Untagged" and is_tagged:
            continue
        if tag_status_filter == "Flagged for Human Review" and not requires_review:
            continue
        if tag_status_filter == "Golden Annotated" and rid not in golden_by_id:
            continue

        safe_text = sanitize_display_text(r.get("text"))
        safe_title = sanitize_display_text(r.get("title"))
        if q and q not in safe_text.lower() and q not in safe_title.lower() and q not in rid.lower():
            continue

        results.append(
            {
                "review_id": rid,
                "source": r.get("source"),
                "date": r.get("date"),
                "rating": r.get("rating"),
                "is_instahelp": bool(r.get("is_instahelp")),
                "safe_title": safe_title,
                "safe_text": safe_text,
                "source_url": r.get("source_url"),
                "is_tagged": is_tagged,
                "tags": (tagged_rec or {}).get("tags"),
                "tag_evidence": (tagged_rec or {}).get("tag_evidence"),
                "metadata": meta if is_tagged else None,
                "golden": golden_by_id.get(rid),
            }
        )

    return results


def resolve_groq_api_key(secrets_dict: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Resolves GROQ_API_KEY from Streamlit secrets or environment variables."""
    if secrets_dict:
        val = secrets_dict.get("GROQ_API_KEY")
        if val and str(val).strip():
            return str(val).strip()
    env_val = os.environ.get("GROQ_API_KEY")
    if env_val and env_val.strip():
        return env_val.strip()
    return None


def tag_live_review_groq_v3_2(
    text: str,
    source: str = "Play Store",
    rating: Optional[int] = None,
    date_str: str = "2026-11-25",
    secrets_dict: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Tags a user-supplied review using the existing Groq v3.2 pipeline."""
    cleaned_input = (text or "").strip()
    if not cleaned_input:
        return {"status": "error", "error_type": "empty_input", "message": "Please enter review text to tag."}

    if len(cleaned_input) > MAX_LIVE_INPUT_CHARS:
        return {
            "status": "error",
            "error_type": "input_too_long",
            "message": (
                f"Input exceeds the {MAX_LIVE_INPUT_CHARS}-character limit "
                f"({len(cleaned_input)} chars). Please shorten the review text."
            ),
        }

    # Always redact PII before privacy audit or sending text to the model
    redacted = redact_pii(cleaned_input)
    privacy_flags = audit_privacy(redacted)
    if privacy_flags:
        return {
            "status": "blocked_privacy",
            "error_type": "privacy_exclusion",
            "privacy_flags": privacy_flags,
            "message": (
                "Input was blocked by the pre-tagging privacy filter because it contains "
                f"potential address or pincode cues ({', '.join(privacy_flags)}). "
                "Remove personal location details and try again."
            ),
        }

    api_key = resolve_groq_api_key(secrets_dict=secrets_dict)
    if not api_key:
        return {
            "status": "error",
            "error_type": "missing_credentials",
            "message": (
                "GROQ_API_KEY is not configured. Set GROQ_API_KEY in your environment "
                "or Streamlit Secrets (.streamlit/secrets.toml) to enable live tagging."
            ),
        }

    normalized_review = {
        "review_id": "live_demo_input",
        "source": source,
        "date": date_str,
        "rating": rating,
        "title": None,
        "text": redacted,
        "app_version": None,
        "review_created_version": None,
        "thumbs_up": None,
        "vote_count": None,
        "vote_sum": None,
        "is_instahelp": False,
    }

    try:
        client = GroqLLMClient(
            model_name="openai/gpt-oss-120b",
            api_key=api_key,
            prompt_path=_REPO_ROOT / "engine/prompts/tagger_v3_2.md",
            version="v3_2",
            max_completion_tokens=1500,
            max_retries=2,
            load_env=False,
        )
        result = tag_single_review(
            normalized_review=normalized_review,
            client=client,
            prompt_version="tagger_v3_2",
        )
        return {"status": "ok", "result": result, "redacted_text": redacted}
    except Exception as exc:
        err_name = type(exc).__name__
        err_lower = str(exc).lower()
        if "429" in err_lower or "rate" in err_lower or "quota" in err_lower or "limit" in err_lower:
            safe_msg = "Groq API rate limit or quota reached. Please wait ~60 seconds and try again."
        elif "401" in err_lower or "403" in err_lower or "auth" in err_lower or "api_key" in err_lower:
            safe_msg = "Groq API authentication failed. Please check your GROQ_API_KEY configuration."
        else:
            safe_msg = f"Groq v3.2 tagging could not complete ({err_name}). Please try again."
        return {
            "status": "error",
            "error_type": err_name,
            "message": safe_msg,
        }
