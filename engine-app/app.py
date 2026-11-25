"""Urban Company Repeat-Booking Discovery Engine — Streamlit Application."""

from __future__ import annotations

import os
from pathlib import Path
import sys

import pandas as pd
import streamlit as st

_APP_DIR = Path(__file__).resolve().parent
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

from data_loader import (
    OPPORTUNITY_THEMES,
    compute_overview_metrics,
    filter_opportunity_evidence,
    load_engine_bundle,
    resolve_groq_api_key,
    search_customer_voice,
    tag_live_review_groq_v3_2,
)

st.set_page_config(
    page_title="UC Repeat-Booking Discovery Engine",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container { padding-top: 2rem; padding-bottom: 2.5rem; max-width: 1180px; }
    div[data-testid="stMetric"] {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 12px 16px;
    }
    .quote-card {
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-left: 4px solid #0F172A;
        border-radius: 6px;
        padding: 12px 16px;
        margin-bottom: 10px;
    }
    .muted-meta { color: #475569; font-size: 0.85rem; margin-bottom: 6px; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def get_bundle():
    return load_engine_bundle()


bundle = get_bundle()
metrics = compute_overview_metrics(bundle)
summary = bundle["analysis_summary"]
norm_report = bundle["norm_report"]

PAGES = [
    "Overview",
    "Opportunity Explorer",
    "Customer Voice",
    "Bias Analysis",
    "Live AI Tagging",
    "Methodology",
]

with st.sidebar:
    st.title("UC Discovery Engine")
    st.caption("90-Day Repeat-Booking Discovery (Level 1)")
    page = st.radio("Navigation", PAGES, label_visibility="collapsed")
    st.divider()
    st.markdown(
        f"**Dataset Snapshot**\n"
        f"- Total items: **{metrics['total_evidence']:,}**\n"
        f"- Core eligible: **{metrics['core_eligible']:,}**\n"
        f"- InstaHelp (excluded): **{metrics['instahelp_count']}**\n"
        f"- LLM-tagged (baseline): **{metrics['baseline_tagged_count']}**\n"
        f"- Golden set: **{metrics['golden_count']}**"
    )
    st.caption("All metrics are computed directly from repository JSONL/JSON files.")


def render_overview() -> None:
    st.header("Overview")
    st.write(
        "Evidence base exploring why Urban Company customers do or do not book another "
        "core home service within 90 days—separating operational failures from silent non-return."
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Evidence Items", f"{metrics['total_evidence']:,}")
    c2.metric("Core Eligible (Excl. InstaHelp)", f"{metrics['core_eligible']:,}", f"-{metrics['instahelp_count']} InstaHelp")
    c3.metric("LLM-Tagged (Baseline)", f"{metrics['baseline_tagged_count']}", f"{metrics['untagged_in_dataset']:,} core untagged")
    c4.metric("Human Golden Set", f"{metrics['golden_count']}")

    st.subheader("Source & Rating Distributions")
    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("**Evidence by Source (All 1,522 items)**")
        src_df = pd.DataFrame(
            [{"Source": k, "Items": v} for k, v in metrics["source_counts"].items()]
        ).sort_values("Items", ascending=False)
        st.bar_chart(src_df.set_index("Source"), height=260)
        st.dataframe(src_df, width="stretch", hide_index=True)

    with col_right:
        st.markdown("**Star Rating Distribution (Core Consumer Reviews, n=1,248)**")
        rat_df = pd.DataFrame(
            [{"Rating": f"{k} ★", "Reviews": v} for k, v in metrics["core_rating_counts"].items()]
        )
        st.bar_chart(rat_df.set_index("Rating"), height=260)
        st.caption(
            "Note: U-shaped distribution (heavy 1★ and 5★) reflects app-store selection bias, "
            "compared to UC's reported 4.79/5.0 platform average (Q3 FY26 Shareholder Letter)."
        )

    st.subheader("Key Opportunity Themes (Directional Ranking)")
    opp_df = pd.DataFrame(
        [
            {
                "Rank": t["rank"],
                "Theme": t["theme"],
                "Potential Impact": t["impact"],
                "Confidence": t["confidence"],
                "Customer-Side Influence": t["customer_side_influence"],
            }
            for t in OPPORTUNITY_THEMES
        ]
    )
    st.dataframe(opp_df, width="stretch", hide_index=True)


def render_opportunity_explorer() -> None:
    st.header("Opportunity Explorer")
    st.caption(
        "Core evidence only (InstaHelp excluded). Counts below use deterministic keyword matching "
        "on the 1,378 core-eligible items and are explicitly directional—not LLM-inferred tags."
    )

    theme_labels = {f"#{t['rank']} — {t['theme']}": t for t in OPPORTUNITY_THEMES}
    selected_label = st.selectbox("Select Opportunity Theme", list(theme_labels.keys()))
    selected_theme = theme_labels[selected_label]

    c1, c2, c3 = st.columns(3)
    c1.metric("Potential 90-Day Impact", selected_theme["impact"])
    c2.metric("Evidence Confidence", selected_theme["confidence"])
    c3.metric("Categories Most Affected", ", ".join(selected_theme["categories"][:2]))

    st.info(
        f"**Evidence Summary:** {selected_theme['evidence_summary']}\n\n"
        f"**Customer-Side Product Influence:** {selected_theme['customer_side_influence']}\n\n"
        f"**Rationale:** {selected_theme['rationale']}"
    )

    st.subheader("Filter Supporting Evidence Quotes")
    f1, f2, f3 = st.columns(3)
    sources = ["All"] + sorted(metrics["source_counts"].keys())
    categories = [
        "All",
        "unspecified",
        "other (appliance/spa/carpentry/painting)",
        "plumber",
        "electrician",
        "salon",
        "AC",
        "pest control",
        "deep clean",
    ]
    ratings = ["All", "1-2 Stars", "3 Stars", "4-5 Stars", "No Rating (IR)"]

    src_val = f1.selectbox("Source", sources, key="opp_src")
    cat_val = f2.selectbox("Category (Keyword Match)", categories, key="opp_cat")
    rat_val = f3.selectbox("Rating Tier", ratings, key="opp_rat")

    matches = filter_opportunity_evidence(
        records=bundle["normalized_records"],
        pain_key=selected_theme["pain_key"],
        source_filter=src_val,
        category_filter=cat_val,
        rating_filter=rat_val,
        exclude_instahelp=True,
    )

    st.write(f"Showing **{min(len(matches), 25)}** of **{len(matches)}** matching core items:")
    if not matches:
        st.warning("No core items match the selected filter combination.")
        return

    for item in matches[:25]:
        rating_str = f"{item['rating']}★" if item.get("rating") is not None else "N/A (IR)"
        cats_str = ", ".join(item["matched_categories_keyword"])
        title_html = f"<strong>{item['safe_title']}</strong> — " if item["safe_title"] else ""
        st.markdown(
            f"<div class='quote-card'>"
            f"<div class='muted-meta'>ID: <code>{item['review_id']}</code> | Source: <b>{item['source']}</b> | "
            f"Date: {item.get('date') or 'N/A'} | Rating: {rating_str} | Keyword Category: {cats_str}</div>"
            f"<div>{title_html}{item['safe_text']}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )


def render_customer_voice() -> None:
    st.header("Customer Voice")
    st.write(
        "Searchable explorer across all repository records. Displays PII-scrubbed original text, "
        "existing LLM tags (where available), and human-review status."
    )

    c1, c2, c3, c4 = st.columns([2, 1, 1.3, 1])
    query = c1.text_input("Search text, title, or review ID", placeholder="e.g., warranty, chimney, salon, 4e4e2ef9")
    src_val = c2.selectbox("Source", ["All"] + sorted(metrics["source_counts"].keys()), key="cv_src")
    tag_status = c3.selectbox(
        "Tagging Status",
        ["All", "Tagged (LLM)", "Untagged", "Flagged for Human Review", "Golden Annotated"],
        key="cv_tag",
    )
    include_ih = c4.checkbox("Include InstaHelp", value=False)

    results = search_customer_voice(
        records=bundle["normalized_records"],
        tagged_by_id=bundle["tagged_by_id"],
        golden_by_id=bundle["golden_by_id"],
        query=query,
        source_filter=src_val,
        tag_status_filter=tag_status,
        include_instahelp=include_ih,
    )

    st.write(f"Found **{len(results)}** matching records (displaying up to 30).")
    for rec in results[:30]:
        badge = "🏷️ LLM Tagged" if rec["is_tagged"] else "⏳ Not yet tagged by LLM"
        if rec["golden"]:
            badge += " | ⭐ Golden Set"
        if rec["is_instahelp"]:
            badge += " | 🧹 InstaHelp"

        rating_str = f"{rec['rating']}★" if rec["rating"] is not None else "N/A"
        header = f"[{rec['source']}] {rating_str} | {rec['date'] or 'N/A'} | {rec['review_id'][:12]} — {badge}"
        with st.expander(header):
            if rec["safe_title"]:
                st.markdown(f"**{rec['safe_title']}**")
            st.write(rec["safe_text"])
            if rec.get("source_url"):
                st.caption(f"Source URL: {rec['source_url']}")

            if rec["is_tagged"]:
                meta = rec["metadata"] or {}
                st.markdown(
                    f"**AI Tags** (`{meta.get('prompt_version', 'unknown')}` / `{meta.get('model', 'unknown')}`)"
                )
                st.json(rec["tags"])
                if meta.get("requires_human_review"):
                    st.warning(f"Human Review Required: {', '.join(meta.get('review_reasons', []))}")
                else:
                    st.success("Human Review Status: Passed automatic quality checks")
            else:
                st.info("This record has not been tagged by the LLM yet. No AI tags are fabricated.")

            if rec["golden"]:
                st.markdown("**Human Golden Annotation**")
                st.json(rec["golden"].get("human_tags"))


def render_bias_analysis() -> None:
    st.header("Bias Analysis")
    st.write(
        "Explicit audit of why raw app-store counts cannot be treated as representative of "
        "Urban Company's overall customer base or silent non-returners."
    )

    bias = summary.get("bias_metrics", {})
    base_184 = summary.get("baseline_tagged_184", {})
    totals = summary.get("normalized_v2_totals", {})

    b1, b2, b3, b4 = st.columns(4)
    b1.metric("1★ Share (Consumer)", "30.9%", "vs 4.79/5.0 UC avg rating")
    b2.metric("Short Reviews (<20 chars)", f"{bias.get('short_low_info_pct', 0)}%", f"{bias.get('short_low_info_reviews_lt20_chars', 0)} / 1,248 core")
    b3.metric("Explicit City Mention", f"{bias.get('explicit_city_pct', 0)}%", f"{bias.get('explicit_city_mentions_in_consumer_core', 0)} / 1,248 core")
    b4.metric("Explicit Household Mention", f"{bias.get('explicit_household_pct', 0)}%", f"{bias.get('explicit_household_mentions_in_consumer_core', 0)} / 1,248 core")

    st.subheader("1. Missing Silent Non-Returners")
    st.warning(
        f"Across the **184** baseline LLM-tagged reviews:\n"
        f"- `nothing_went_wrong = true`: **{base_184.get('nothing_went_wrong_true', 0)} / 184**\n"
        f"- `recall_gap = true`: **{base_184.get('recall_gap_true', 0)} / 184**\n"
        f"- `rebook_signal = unclear`: **{base_184.get('rebook_signal', {}).get('unclear', 0)} / 184 (98.9%)**\n\n"
        "Customers who had an acceptable booking and later drifted to an offline habit rarely leave app-store reviews. "
        "Discovery interviews (Level 4) are required to observe this silent cohort."
    )

    st.subheader("2. Category & Source Coverage Gaps")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Category Sparsity (1,248 Core Consumer Reviews)**")
        cat_counts = summary.get("directional_category_counts_consumer_core", {})
        cat_df = pd.DataFrame([{"Category": k, "Count": v} for k, v in cat_counts.items()])
        st.dataframe(cat_df, width="stretch", hide_index=True)

    with col2:
        st.markdown("**Source Coverage & Access Blockers**")
        st.markdown(
            "- **Play Store (`1,200`) & App Store (`100`):** 92.3% Android skew; narrow Nov 2026 recency window.\n"
            "- **Investor Relations (`222`):** Corporate perspective, not individual customer journeys.\n"
            "- **Reddit (`0`):** Blocked (HTTP `403` without OAuth; `REDDIT_CLIENT_ID` unset).\n"
            "- **YouTube (`0`):** Blocked (`YOUTUBE_API_KEY` unset).\n"
            "- **Trustpilot / MouthShut (`0`):** Automated scraping skipped per ToS."
        )

    st.subheader("3. Evidence Limitations")
    st.markdown(
        "- Counts are directional indicators from a 23-day November window (`2026-11-02` to `2026-11-24` for Play Store), missing summer AC peaks.\n"
        "- `144` InstaHelp quick-housekeeping items are excluded from core repeat-booking metrics.\n"
        "- Strict non-inference rules mean `city` and `household_type` remain `null`/`unclear` in >99% of reviews."
    )


def get_safe_secrets() -> dict:
    try:
        return dict(st.secrets)
    except Exception:
        return {}


def render_live_tagging() -> None:
    st.header("Live AI Tagging (Groq v3.2)")
    st.write(
        "Paste any public home-service review to run the existing **Groq `openai/gpt-oss-120b` (`tagger_v3_2`)** "
        "pipeline with pre-tagging PII redaction and privacy checks."
    )

    secrets_dict = get_safe_secrets()
    has_key = resolve_groq_api_key(secrets_dict=secrets_dict) is not None
    if not has_key:
        st.warning(
            "**Live tagging is currently inactive:** `GROQ_API_KEY` is not set in environment variables or "
            "Streamlit Secrets. All other discovery engine pages work without API credentials."
        )
    else:
        st.success("`GROQ_API_KEY` detected. Ready for live tagging with `tagger_v3_2`.")

    sample_text = (
        "Booked UC chimney deep clean last month. The cleaning was fine, but 2 weeks later oil "
        "started dripping and warranty was only 10 days. Next time I might just call my local guy."
    )
    with st.form("live_tag_form"):
        review_text = st.text_area("Review Text", value=sample_text, height=130)
        c1, c2 = st.columns(2)
        src = c1.selectbox("Source", ["Play Store", "App Store", "Reddit", "Trustpilot", "Other"])
        rat = c2.selectbox("Star Rating (optional)", [None, 1, 2, 3, 4, 5], index=2)
        submitted = st.form_submit_button("Run Groq v3.2 Tagger")

    if submitted:
        with st.spinner("Running privacy checks and Groq v3.2 tagger..."):
            resp = tag_live_review_groq_v3_2(
                text=review_text,
                source=src,
                rating=rat,
                secrets_dict=secrets_dict,
            )
        if resp["status"] == "ok":
            res = resp["result"]
            tags = res["tags"]
            meta = res["metadata"]

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Category", tags.get("category", "unknown"))
            m2.metric("Experience", tags.get("experience_type", "unclear"))
            m3.metric("Rebook Signal", tags.get("rebook_signal", "unclear"))
            m4.metric("Confidence", tags.get("confidence", "low"))

            st.markdown(f"**Verbatim Evidence Quote:** `{tags.get('evidence_quote')}`")
            if meta.get("requires_human_review"):
                st.warning(f"Human Review Flagged: {', '.join(meta.get('review_reasons', []))}")
            st.subheader("Structured 16-Field Output")
            st.json(tags)
            with st.expander("Per-Field Evidence & Metadata"):
                st.json({"tag_evidence": res.get("tag_evidence"), "metadata": meta})
        elif resp["status"] == "blocked_privacy":
            st.error(resp["message"])
        else:
            st.error(resp["message"])


def render_methodology() -> None:
    st.header("Methodology")
    st.markdown(
        """
        ### 1. Data Collection (`engine/collectors/`)
        - **Google Play (`google_play.py`):** Public `google-play-scraper` (`com.urbanclap.urbanclap`) — `100` baseline + `1,100` v2 deduplicated reviews (`1,200` total).
        - **Apple App Store (`app_store.py`):** Public iTunes RSS feed (`1032480595`, India) — `100` baseline reviews.
        - **Investor Relations (`investor_relations.py`):** Public PDFs from `investorrelations.urbancompany.com/financials` (`14` PDFs across Q2 FY26–Q2 FY27) — `222` excerpts.
        - **Compliance:** No login bypass, no private Urban Company APIs, and automated scraping of Trustpilot/MouthShut avoided per ToS.

        ### 2. Cleaning & Deduplication (`engine/normalizer_v2.py`)
        - Cross-source deduplication by `(source, review_id)` and normalized text SHA-256 hash.
        - `InstaHelp` (quick-service housekeeping) records (`144` items) are flagged (`is_instahelp = true`) and excluded from core repeat-booking analysis.

        ### 3. Privacy Filtering (`engine/collectors/google_play.py`)
        - Usernames, profile URLs, and account metadata are stripped at collection time.
        - Phone numbers, emails, and contextual third-party names are regex-redacted (`[PHONE_REDACTED]`, `[EMAIL_REDACTED]`, `[NAME_REDACTED]`).
        - Reviews with unresolved street/apartment address cues or postal pincodes are discarded pre-storage without secondary persistence (`48` excluded in v2 runs).

        ### 4. AI Tagging & Golden Evaluation (`engine/tagger.py`)
        - **16-Field Schema (`docs/schema.md`):** Strict non-inference for `city`, `household_type`, `rebook_signal`, `nothing_went_wrong`, and `recall_gap`, with verbatim `evidence_quote` grounding.
        - **Human Review Queue:** Low-information (`<20` chars) and low-confidence items are routed to `review_queue` rather than treated as high-confidence signals.
        - **Golden Set (`30` reviews) & Groq v3.2 Benchmark (`10` reviews):** Verified `10/10` category and `10/10` experience_type agreement, `-21.2%` prompt token reduction (`3,054` → `2,407` tokens), and `185` passing unit tests.

        ### 5. Known Limitations
        - Only `184` baseline core reviews have full LLM tags; the remaining `1,064` core consumer reviews in v2 are analyzed via reproducible keyword matching (`engine/analyze_evidence.py`) until batch LLM tagging is run.
        - Silent non-returners (`nothing_went_wrong = true`) are `0/184` in app-store reviews and require Level 4 discovery interviews.
        """
    )


if page == "Overview":
    render_overview()
elif page == "Opportunity Explorer":
    render_opportunity_explorer()
elif page == "Customer Voice":
    render_customer_voice()
elif page == "Bias Analysis":
    render_bias_analysis()
elif page == "Live AI Tagging":
    render_live_tagging()
elif page == "Methodology":
    render_methodology()
