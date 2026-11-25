"""Generate docs/golden_set_manifest.md documenting the sampling manifest."""
import json
from collections import Counter


def main():
    with open("data/golden/golden_set.jsonl", "r", encoding="utf-8") as f:
        golden_records = [json.loads(line) for line in f]
        golden_map = {r["review_id"]: r for r in golden_records}

    manifest_entries = [
        # Google Play
        {
            "id": "bb81193d-cf36-41b3-abce-4d201b3c4a59",
            "stratum": "Substantive Positive",
            "category": "salon",
            "rationale": "Explicit repeat booking signal in salon category with positive customer sentiment ('its worth it for our salon experience . The last one was the best'). Tests detection of repeat usage and positive experience type."
        },
        {
            "id": "99226311-a2f2-4ecf-b1ed-7d28518cd95e",
            "stratum": "Substantive Positive",
            "category": "deep clean",
            "rationale": "Detailed positive kitchen cleaning review containing sanitized service provider token ([NAME_REDACTED]). Tests deep clean category recognition and validation of privacy redaction tokens in ground truth."
        },
        {
            "id": "75c91a8d-c132-48e2-a420-ea4221bb6059",
            "stratum": "Substantive Positive",
            "category": "unknown",
            "rationale": "High-satisfaction general home services review expressing staff punctuality and strong recommendation intent. Tests general praise without explicit service category identification."
        },
        {
            "id": "36b24dd5-1cd2-4752-9a46-68307d86382c",
            "stratum": "Substantive Negative",
            "category": "plumber",
            "rationale": "Detailed plumbing booking grievance involving urgent cancellation within 5 minutes and unjustified fee imposition. Critical test for plumber category and cancellation fee unmet need."
        },
        {
            "id": "4e4e2ef9-6dd6-40cc-a65b-a3f327daf7f0",
            "stratum": "Substantive Negative",
            "category": "other",
            "rationale": "Chimney deep clean review with oil leakage after 15 days and 10-day warranty expiration dispute. Tests appliance classification (other, not deep clean alone) and warranty grievance handling (Decision 008)."
        },
        {
            "id": "43582ef1-c85a-4b67-ad13-662ab7a72dcb",
            "stratum": "Substantive Negative",
            "category": "salon",
            "rationale": "Strong negative warning regarding Spa sessions ('treat you as their ginni pig'). Tests negative sentiment within salon/spa category and strong negative churn advice."
        },
        {
            "id": "1876c25b-b9ea-4720-9fcd-d11a7caa4bf1",
            "stratum": "Substantive Negative",
            "category": "other",
            "rationale": "Detailed operational failure regarding RO water purifier technician unavailability and support unresponsiveness. Tests RO/appliance category and customer support failure friction."
        },
        {
            "id": "6b579933-e83a-459c-b7c7-73f83b669c16",
            "stratum": "Substantive Negative",
            "category": "unknown",
            "rationale": "Sole 2-star review in Play Store dataset. Describes severe app unresponsiveness and freezing during ongoing bookings, preventing visibility into active service status. Reclassified to Substantive Negative because textual content describes purely negative technical failure without neutral or mixed elements."
        },
        {
            "id": "bec86ea9-9a8f-495d-a091-1e4ec7843980",
            "stratum": "Neutral / Mixed",
            "category": "unknown",
            "rationale": "Sole 3-star review in Play Store dataset. Explicit complaint about duration shortening (45 minutes delivered vs 1 hour standard promised). Tests duration unmet need and neutral rating."
        },
        {
            "id": "06b45346-6f25-4d49-9b01-13d980482c2c",
            "stratum": "Ambiguous / Edge Case",
            "category": "unknown",
            "rationale": "Decision 008 Audit Case 1: Customer states past tenure as 'regular customer' but gives 1 star due to partner cancellation and churn. Sanitized per privacy policy with [NAME_REDACTED] for partner name. Crucial test that past tenure is not falsely tagged as rebooked."
        },
        {
            "id": "b04a772a-f857-4356-ae3d-fa83612fdb90",
            "stratum": "Ambiguous / Edge Case",
            "category": "unknown",
            "rationale": "Severe rating-polarity conflict: 4-star rating awarded, but text reports booking cancellation and failure to arrive at scheduled time slot. Tests annotator discipline in prioritizing text over stars."
        },
        {
            "id": "372c9648-73fe-4245-8121-a8f198701159",
            "stratum": "Ambiguous / Edge Case",
            "category": "deep clean",
            "rationale": "Decision 008 Audit Case 5: Nuanced comparative review stating UC is 'good for low level cleaning jobs' but warning against expensive painting or repairs due to pathetic warranty. Tests cross-category distinction."
        },
        {
            "id": "bbf12112-379a-4f54-9112-99d788cb9d2e",
            "stratum": "Low-Information",
            "category": "unknown",
            "rationale": "Terse 5-star review ('good work', 9 characters). Tests low-information review policy (confidence: low, rebook_signal: unclear, category: unknown, non-inference of rebooking)."
        },
        {
            "id": "b31f176a-29af-4454-bf5d-4eacf25b7a38",
            "stratum": "Low-Information",
            "category": "unknown",
            "rationale": "Terse 4-star review ('ok ok', 5 characters). Tests ambiguous/tepid sentiment evaluation on extremely short text."
        },
        {
            "id": "83ea578e-2a5e-41fc-a0b7-6b542aa3953e",
            "stratum": "Low-Information",
            "category": "unknown",
            "rationale": "Terse 1-star review in Hindi vernacular slang ('lut rahe hai', 12 characters). Tests non-English colloquial slang handling for overcharging/pricing dissatisfaction."
        },

        # Apple App Store
        {
            "id": "14815231009",
            "stratum": "Substantive Positive",
            "category": "AC",
            "rationale": "Detailed 5-year repeat usage review specifically evaluating AC services. Directly compares UC technicians favorably against brand competitors ('500% better than incompetent AC company technicians')."
        },
        {
            "id": "14805610926",
            "stratum": "Substantive Positive",
            "category": "deep clean",
            "rationale": "Exemplary 1,196-character end-to-end positive journey review for home deep cleaning (kitchen and washrooms). Sanitized per privacy redaction policy with [NAME_REDACTED] for lead service professionals. Covers app booking, prompt arrival, and thorough execution."
        },
        {
            "id": "14809078193",
            "stratum": "Substantive Positive",
            "category": "salon",
            "rationale": "Substantive positive spa/salon review detailing deep tissue massage and exceptional satisfaction with specific service professional. Sanitized per privacy redaction policy with [NAME_REDACTED] in title and body. Tests salon subcategory and provider commendation."
        },
        {
            "id": "14816200493",
            "stratum": "Substantive Negative",
            "category": "other",
            "rationale": "Decision 008 Audit Cases 2 & 3: 1,792-character review detailing washing machine repair, inlet pipe misdiagnosis, fraud attempts, and customer peer advice ('My advice to other customers'). Tests appliance vs plumber and advice directionality."
        },
        {
            "id": "14811772838",
            "stratum": "Substantive Negative",
            "category": "deep clean",
            "rationale": "Severe property damage review in bathroom cleaning where technician spilled excess cleaning acid, damaging the entire tile floor with zero compensation. Tests property damage friction."
        },
        {
            "id": "14813121635",
            "stratum": "Substantive Negative",
            "category": "other",
            "rationale": "Extensive 1,010-character grievance regarding proprietary Native M1 Pro Water Purifier defects, leakage, and refund refusal. Tests proprietary appliance classification (other) and refund friction."
        },
        {
            "id": "14800891393",
            "stratum": "Substantive Negative",
            "category": "unknown",
            "rationale": "Substantive breakdown of platform reliability deterioration, consecutive technician reassignments, ghosting, and arbitrary job refusals. Tests platform operational breakdown and partner fulfillment friction."
        },
        {
            "id": "14819013371",
            "stratum": "Neutral / Mixed",
            "category": "salon",
            "rationale": "3-star review from 6-year regular salon customer balancing acceptable service quality against steep price hikes and platform fees. Tests long-term tenure, price sensitivity, and neutral sentiment."
        },
        {
            "id": "14787997500",
            "stratum": "Neutral / Mixed",
            "category": "unknown",
            "rationale": "3-star review presenting mixed evaluation: compliments offline service providers while criticizing app usability degradation, selection glitches, and poor UI. Tests provider vs app separation."
        },
        {
            "id": "14784151525",
            "stratum": "Ambiguous / Edge Case",
            "category": "AC",
            "rationale": "Multi-category long-term customer review with 5 stars overall, but an explicit negative callout on AC servicing quality ('Ac servicing quality wasn’t good. Rest all the services are amazing'). Tests multi-category nuance."
        },
        {
            "id": "14811553737",
            "stratum": "Ambiguous / Edge Case",
            "category": "unknown",
            "rationale": "Rating-polarity conflict: 4-star rating awarded despite Title 'Looting customers' and text detailing hidden plan details and pre-emptive plan cancellations. Tests text primacy over stars."
        },
        {
            "id": "14792849957",
            "stratum": "Ambiguous / Edge Case",
            "category": "pest control",
            "rationale": "Broad multi-category umbrella review citing repeat usage since 'Urban Clap' era across salon, spa, carpentry, pest control, and UC-help. One of very few explicit pest control mentions in corpus."
        },
        {
            "id": "14793598838",
            "stratum": "Ambiguous / Edge Case",
            "category": "salon",
            "rationale": "Rating-polarity conflict: 4-star rating with title 'Pedicure' and text 'Therapist not reported'. Tests salon category detection on short text and partner no-show classification under high star rating."
        },
        {
            "id": "14807881351",
            "stratum": "Low-Information",
            "category": "unknown",
            "rationale": "Ultra-terse 4-character 5-star review (Title: 'Good', Text: 'Good'). Tests low-information non-inference rules on Apple App Store platform."
        },
        {
            "id": "14812347184",
            "stratum": "Low-Information",
            "category": "unknown",
            "rationale": "Short 3-star review (Title: 'Surge Charge', Text: 'Surge Charge. Very expensive.'). Tests brief pricing friction identification without service category or journey context."
        },
    ]

    md = []
    md.append("# Sampling Manifest: 30-Review Golden Dataset")
    md.append("")
    md.append("This manifest documents the selection methodology, stratification rationale, and record-by-record provenance for the 30-review golden dataset (`data/golden/golden_set.jsonl`).")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 1. Population and Sampling Methodology")
    md.append("")
    md.append("- **Total Ingested Reviews**: 200 (100 Google Play, 100 Apple App Store)")
    md.append("- **InstaHelp Exclusions**: 16 quick-housekeeping records excluded per project brief rules (Decision 005)")
    md.append("- **Eligible Core Pool**: 184 reviews (94 Google Play, 90 Apple App Store)")
    md.append("- **Target Golden Set Size**: Exactly 30 reviews")
    md.append("- **Platform Stratification**: Exactly 15 Google Play reviews (50%) and 15 Apple App Store reviews (50%)")
    md.append("")
    md.append("### Selection Principles")
    md.append("1. **Semantic Stratification**: Selected to represent five distinct review types: Substantive Positive, Substantive Negative, Neutral / Mixed, Ambiguous / Edge Cases, and Low-Information.")
    md.append("2. **Category Diversity**: Ensures representation across all detectable core categories (AC, deep clean, plumber, salon, pest control, other/appliances, and unknown).")
    md.append("3. **Rating Independence**: Selection was based on text inspection rather than star scores alone, intentionally including severe rating-polarity conflicts (e.g. 4-star reviews complaining of no-shows or looting).")
    md.append("4. **Regression Edge Cases**: Incorporated key audit cases from `docs/decisions.md` (e.g. regular customer in churn context, washing machine pipe vs plumber, warning against engineer advice, warranty expiration disputes) to ensure the golden dataset tests model boundary conditions.")
    md.append("5. **Privacy Redaction Compliance**: All personal names of service professionals appearing in review text or titles are sanitized using `[NAME_REDACTED]` in accordance with Decision 001.")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 2. Stratification Summary Statistics")
    md.append("")
    md.append("### By Platform & Stratum")
    md.append("| Stratum | Google Play | Apple App Store | Total |")
    md.append("|---|---|---|---|")

    strata = [
        "Substantive Positive",
        "Substantive Negative",
        "Neutral / Mixed",
        "Ambiguous / Edge Case",
        "Low-Information",
    ]
    for s in strata:
        gp_c = sum(1 for e in manifest_entries if e["stratum"] == s and golden_map[e["id"]]["source"] == "Play Store")
        ap_c = sum(1 for e in manifest_entries if e["stratum"] == s and golden_map[e["id"]]["source"] == "App Store")
        md.append(f"| {s} | {gp_c} | {ap_c} | {gp_c + ap_c} |")
    md.append("| **Total** | **15** | **15** | **30** |")
    md.append("")

    md.append("### By Star Rating")
    ratings = Counter(golden_map[e["id"]]["rating"] for e in manifest_entries)
    md.append("| Star Rating | Count | Percentage |")
    md.append("|---|---|---|")
    for r in sorted(ratings.keys(), reverse=True):
        md.append(f"| ★ {r} | {ratings[r]} | {ratings[r]/30*100:.1f}% |")
    md.append("| **Total** | **30** | **100.0%** |")
    md.append("")

    md.append("### By Target Service Category")
    cats = Counter(e["category"] for e in manifest_entries)
    md.append("| Service Category | Count | Percentage |")
    md.append("|---|---|---|")
    for c, cnt in sorted(cats.items(), key=lambda x: -x[1]):
        md.append(f"| `{c}` | {cnt} | {cnt/30*100:.1f}% |")
    md.append("| **Total** | **30** | **100.0%** |")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 3. Complete Review Inventory and Selection Rationale")
    md.append("")
    md.append("| # | Review ID | Platform | Rating | Date | Category | Stratum | Excerpt | Selection Rationale |")
    md.append("|---|---|---|---|---|---|---|---|---|")

    for idx, entry in enumerate(manifest_entries, 1):
        rid = entry["id"]
        norm = golden_map[rid]
        src = norm["source"]
        star = f"★{norm.get('rating')}"
        dt = norm.get("date") or "N/A"
        cat = entry["category"]
        strat = entry["stratum"]
        txt = norm["review_text"].replace("\n", " ").replace("|", "\\|")
        excerpt = (txt[:65] + "...") if len(txt) > 65 else txt
        rat = entry["rationale"].replace("|", "\\|")
        md.append(f"| {idx} | `{rid}` | {src} | {star} | {dt} | `{cat}` | {strat} | \"{excerpt}\" | {rat} |")

    md.append("")
    content = "\n".join(md) + "\n"

    with open("docs/golden_set_manifest.md", "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Successfully generated docs/golden_set_manifest.md with {len(manifest_entries)} entries.")


if __name__ == "__main__":
    main()
