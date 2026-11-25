"""Reproducible bias and opportunity analysis script for Urban Company Repeat-Booking Engine.

Reads normalized evidence (v2), existing tagged datasets, golden annotations, and
Investor Relations excerpts to produce reproducible counts for:
1. Bias analysis (star-rating skew, source/category imbalance, city/demographic gaps,
   silent non-returner visibility).
2. Opportunity analysis (recurring pain points, repeat-booking barriers,
   nothing_went_wrong slice, category/source splits, and ranked opportunity table).

Outputs structured JSON to `data/processed/analysis_summary.json`.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_NORMALIZED_V2 = Path("data/processed/normalized_evidence_v2.jsonl")
DEFAULT_TAGGED_V1 = Path("data/tagged/tagged_reviews.jsonl")
DEFAULT_QUEUE_V1 = Path("data/tagged/review_queue.jsonl")
DEFAULT_GOLDEN = Path("data/golden/golden_set.jsonl")
DEFAULT_IR = Path("data/raw/investor_relations_excerpts.jsonl")
DEFAULT_OUTPUT = Path("data/processed/analysis_summary.json")

# Deterministic keyword patterns for directional theme & category scanning across all 1,500+ items
CATEGORY_PATTERNS = {
    "AC": re.compile(r"\b(?:ac|air\s*conditioner|split\s*ac|window\s*ac|ac\s*service|ac\s*repair|gas\s*fill)\b", re.I),
    "salon": re.compile(r"\b(?:salon|haircut|hair\s*cut|waxing|facial|manicure|pedicure|threading|beautician|grooming)\b", re.I),
    "deep clean": re.compile(r"\b(?:deep\s*clean|home\s*clean|bathroom\s*clean|kitchen\s*clean|sofa\s*clean|carpet\s*clean|house\s*clean)\b", re.I),
    "plumber": re.compile(r"\b(?:plumb(?:er|ing)|tap|leak|pipe|sink|flush|drain)\b", re.I),
    "electrician": re.compile(r"\b(?:electrician|electrical|wiring|switch|socket|fan|mcb|geyser)\b", re.I),
    "pest control": re.compile(r"\b(?:pest\s*control|cockroach|termite|bed\s*bug|ant\s*control|rodent)\b", re.I),
    "other (appliance/spa/carpentry/painting)": re.compile(r"\b(?:spa|massage|washing\s*machine|refrigerator|fridge|chimney|ro\s*(?:purifier|technician|service)|water\s*purifier|native|carpenter|carpentry|painting|waterproofing|microwave)\b", re.I),
}

PAIN_POINT_PATTERNS = {
    "cancellation_and_no_show": re.compile(r"\b(?:cancel(?:led|lation)?|no[\s-]*show|didn'?t\s*(?:turn\s*up|show\s*up|arrive)|never\s*arrived|reschedul(?:e|ed|ing)|ghost(?:ed|ing))\b", re.I),
    "customer_support_failure": re.compile(r"\b(?:customer\s*(?:care|support|service)|support\s*team|no\s*response|unresponsive|helpless|hopeless|bot|automated\s*reply|grievance|escalat)\b", re.I),
    "pricing_and_fee_opacity": re.compile(r"\b(?:expensive|overcharg|surge\s*charge|price\s*hike|hidden\s*charge|cancellation\s*(?:fee|charge)|looting|loot|cheating|cheat|refund|money\s*back|wallet)\b", re.I),
    "technician_quality_and_behavior": re.compile(r"\b(?:rude|attitude|unprofessional|untrained|incompetent|damaged|broken|spilled|misbehav|impolite|sloppy|incomplete)\b", re.I),
    "delay_and_punctuality": re.compile(r"\b(?:late|delay(?:ed)?|waiting|slot|hours?\s*late|punctual)\b", re.I),
    "warranty_and_post_service_gap": re.compile(r"\b(?:warranty|guarantee|revisit|redo|follow[\s-]*up|complaint\s*window|expired)\b", re.I),
    "app_and_booking_ux": re.compile(r"\b(?:app\s*(?:crash|bug|not\s*working|hang|slow|freeze)|unable\s*to\s*book|status|tracking|ui|interface)\b", re.I),
    "offline_alternative_or_churn_signal": re.compile(r"\b(?:local\s*(?:technician|plumber|electrician|provider|guy|vendor)|urban\s*clap\s*was\s*better|never\s*(?:book|use)\s*again|uninstall(?:ed|ing)?|stopped\s*using|switched\s*to|another\s*app|think\s*twice)\b", re.I),
}

CITY_PATTERN = re.compile(
    r"\b(?:delhi|ncr|gurgaon|gurugram|noida|mumbai|bengaluru|bangalore|hyderabad|chennai|pune|kolkata|ahmedabad|jaipur|chandigarh|lucknow|kochi|indore|bhopal|surat|nagpur|dubai|singapore|abu\s*dhabi)\b",
    re.I,
)

HOUSEHOLD_PATTERN = re.compile(
    r"\b(?:living\s*alone|bachelor|flatmate|roommate|family|wife|husband|kids|children|parents|elderly|senior\s*citizen|tenant|renter|landlord|homeowner)\b",
    re.I,
)


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def run_analysis(
    normalized_v2_path: Path = DEFAULT_NORMALIZED_V2,
    tagged_v1_path: Path = DEFAULT_TAGGED_V1,
    queue_v1_path: Path = DEFAULT_QUEUE_V1,
    golden_path: Path = DEFAULT_GOLDEN,
    ir_path: Path = DEFAULT_IR,
    output_path: Path = DEFAULT_OUTPUT,
) -> Dict[str, Any]:
    norm_records = load_jsonl(normalized_v2_path)
    tagged_v1 = load_jsonl(tagged_v1_path)
    queue_v1 = load_jsonl(queue_v1_path)
    golden = load_jsonl(golden_path)
    ir_records = load_jsonl(ir_path)

    source_counts = Counter(r["source"] for r in norm_records)
    instahelp_by_source = Counter(r["source"] for r in norm_records if r.get("is_instahelp"))

    # Core consumer reviews (excluding IR corporate disclosures and InstaHelp)
    consumer_sources = {"Play Store", "App Store"}
    consumer_core = [
        r for r in norm_records
        if r["source"] in consumer_sources and not r.get("is_instahelp")
    ]
    consumer_all = [r for r in norm_records if r["source"] in consumer_sources]

    rating_dist_all = Counter(str(r.get("rating")) for r in consumer_all)
    rating_dist_by_source: Dict[str, Dict[str, int]] = {}
    for src in consumer_sources:
        sub = [r for r in consumer_all if r["source"] == src]
        rating_dist_by_source[src] = dict(sorted(Counter(str(r.get("rating")) for r in sub).items()))

    date_ranges: Dict[str, Dict[str, Any]] = {}
    for src in sorted(source_counts.keys()):
        dates = sorted(r["date"] for r in norm_records if r["source"] == src and r.get("date"))
        date_ranges[src] = {
            "count": source_counts[src],
            "min_date": dates[0] if dates else None,
            "max_date": dates[-1] if dates else None,
        }

    # Short / low-info review rate (<20 chars)
    short_reviews = sum(1 for r in consumer_core if len((r.get("text") or "").strip()) < 20)
    city_mentions = sum(1 for r in consumer_core if CITY_PATTERN.search(r.get("text") or ""))
    household_mentions = sum(1 for r in consumer_core if HOUSEHOLD_PATTERN.search(r.get("text") or ""))

    # Category and pain-point directional scan across consumer_core
    cat_counts = Counter()
    pain_counts_all = Counter()
    pain_counts_low_rating = Counter()  # 1-2 stars
    pain_counts_high_rating = Counter()  # 4-5 stars
    pain_by_category: Dict[str, Counter] = defaultdict(Counter)

    for r in consumer_core:
        text = f"{r.get('title') or ''} {r.get('text') or ''}"
        matched_cats = [cat for cat, pat in CATEGORY_PATTERNS.items() if pat.search(text)]
        if not matched_cats:
            matched_cats = ["unspecified"]
        for cat in matched_cats:
            cat_counts[cat] += 1

        rating = r.get("rating")
        for pain, pat in PAIN_POINT_PATTERNS.items():
            if pat.search(text):
                pain_counts_all[pain] += 1
                if rating in (1, 2):
                    pain_counts_low_rating[pain] += 1
                elif rating in (4, 5):
                    pain_counts_high_rating[pain] += 1
                for cat in matched_cats:
                    pain_by_category[cat][pain] += 1

    # Tagged v1+queue analysis (184 core reviews from baseline)
    all_tagged_184 = tagged_v1 + queue_v1
    tagged_exp = Counter(r["tags"]["experience_type"] for r in all_tagged_184)
    tagged_rebook = Counter(r["tags"]["rebook_signal"] for r in all_tagged_184)
    tagged_cat = Counter(r["tags"]["category"] for r in all_tagged_184)
    tagged_nww_true = sum(1 for r in all_tagged_184 if r["tags"].get("nothing_went_wrong") is True)
    tagged_recall_gap = sum(1 for r in all_tagged_184 if r["tags"].get("recall_gap") is True)
    tagged_alt = Counter(r["tags"]["alternative_used"] for r in all_tagged_184)
    tagged_city = sum(1 for r in all_tagged_184 if r["tags"].get("city"))
    tagged_household = Counter(r["tags"]["household_type"] for r in all_tagged_184)

    # Golden set (30 reviews)
    golden_exp = Counter(r["human_tags"]["experience_type"] for r in golden)
    golden_rebook = Counter(r["human_tags"]["rebook_signal"] for r in golden)
    golden_cat = Counter(r["human_tags"]["category"] for r in golden)
    golden_alt = Counter(r["human_tags"]["alternative_used"] for r in golden)
    golden_city = sum(1 for r in golden if r["human_tags"].get("city"))
    golden_household = Counter(r["human_tags"]["household_type"] for r in golden)

    # IR key excerpts (repeat/retention/frequency/cross-category)
    ir_repeat_excerpts = []
    for r in ir_records:
        txt = r.get("text") or ""
        if any(k in txt.lower() for k in ("repeat", "retention", "cohort", "cross-category", "annual transacting")):
            ir_repeat_excerpts.append({
                "id": r["id"],
                "source": r["source"],
                "title": r.get("title"),
                "date": r.get("date"),
                "snippet": txt[:450],
            })

    summary = {
        "normalized_v2_totals": {
            "total_records": len(norm_records),
            "by_source": dict(source_counts),
            "instahelp_total": sum(instahelp_by_source.values()),
            "instahelp_by_source": dict(instahelp_by_source),
            "consumer_all": len(consumer_all),
            "consumer_core_excl_instahelp": len(consumer_core),
            "date_ranges": date_ranges,
        },
        "bias_metrics": {
            "rating_distribution_all_consumer": dict(sorted(rating_dist_all.items())),
            "rating_distribution_by_source": rating_dist_by_source,
            "short_low_info_reviews_lt20_chars": short_reviews,
            "short_low_info_pct": round(100 * short_reviews / max(len(consumer_core), 1), 1),
            "explicit_city_mentions_in_consumer_core": city_mentions,
            "explicit_city_pct": round(100 * city_mentions / max(len(consumer_core), 1), 1),
            "explicit_household_mentions_in_consumer_core": household_mentions,
            "explicit_household_pct": round(100 * household_mentions / max(len(consumer_core), 1), 1),
        },
        "directional_category_counts_consumer_core": dict(cat_counts.most_common()),
        "directional_pain_points_consumer_core": {
            "all": dict(pain_counts_all.most_common()),
            "low_rating_1_2_stars": dict(pain_counts_low_rating.most_common()),
            "high_rating_4_5_stars": dict(pain_counts_high_rating.most_common()),
            "by_category": {k: dict(v.most_common()) for k, v in pain_by_category.items()},
        },
        "baseline_tagged_184": {
            "total": len(all_tagged_184),
            "experience_type": dict(tagged_exp),
            "rebook_signal": dict(tagged_rebook),
            "category": dict(tagged_cat),
            "nothing_went_wrong_true": tagged_nww_true,
            "recall_gap_true": tagged_recall_gap,
            "alternative_used": dict(tagged_alt),
            "explicit_city_count": tagged_city,
            "household_type": dict(tagged_household),
        },
        "golden_set_30": {
            "total": len(golden),
            "experience_type": dict(golden_exp),
            "rebook_signal": dict(golden_rebook),
            "category": dict(golden_cat),
            "alternative_used": dict(golden_alt),
            "explicit_city_count": golden_city,
            "household_type": dict(golden_household),
        },
        "ir_repeat_excerpt_count": len(ir_repeat_excerpts),
        "ir_repeat_excerpts_sample": ir_repeat_excerpts[:12],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate reproducible bias & opportunity summary.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    summary = run_analysis(output_path=args.output)
    print(f"Analysis summary written to {args.output} (total_records={summary['normalized_v2_totals']['total_records']})")


if __name__ == "__main__":
    main()
