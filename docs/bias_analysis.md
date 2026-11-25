# Bias Analysis: Urban Company Repeat-Booking Discovery Engine

**Generated from:** `engine/analyze_evidence.py` → `data/processed/analysis_summary.json`  
**Dataset:** `data/processed/normalized_evidence_v2.jsonl` (`N = 1,522` total items; `1,378` core-eligible excluding `144` InstaHelp items)

---

## 1. Executive Summary

Public app-store reviews and corporate disclosures provide directional evidence on **acute service failures** and **macro platform retention**, but they are **severely biased against the core research question**: *why customers do not rebook within 90 days even when nothing went wrong.* Relying on raw app-store counts without bias correction will over-index on 1-star operational complaints and miss silent non-returners.

---

## 2. Quantified Biases in the Repository Dataset

### 2.1 App-Store Bimodal Selection Bias (Complainers & Terse Praise Over-Represented)

Across all `1,300` consumer reviews (`1,200` Play Store + `100` App Store), ratings are heavily U-shaped (bimodal):

| Star Rating | Play Store (`n=1,200`) | App Store (`n=100`) | Combined (`n=1,300`) | Share of Consumer Reviews |
|---|---|---|---|---|
| **1 ★** | 368 (30.7%) | 34 (34.0%) | **402** | **30.9%** |
| **2 ★** | 28 (2.3%) | 5 (5.0%) | **33** | **2.5%** |
| **3 ★** | 50 (4.2%) | 7 (7.0%) | **57** | **4.4%** |
| **4 ★** | 87 (7.3%) | 6 (6.0%) | **93** | **7.2%** |
| **5 ★** | 667 (55.6%) | 48 (48.0%) | **715** | **55.0%** |

**Comparison against platform base rate:**  
In Urban Company's public **Q3 FY26 Shareholder Letter** (`data/raw/investor_relations_excerpts.jsonl`, `ir_87ca9260e8dc17ac`), management reports an average in-app service rating of **4.79 / 5.0** across India Consumer Services (Ex InstaHelp), and **4.80 / 5.0** in Q2 FY26 (`ir_8eec0a189753932a`). By contrast, **30.9%** of collected app-store reviews are 1-star, while only **14.1%** (`183/1,300`) are 2–4 stars. Furthermore, **33.7% (`420/1,248`)** of core consumer reviews are under 20 characters (e.g., `"Good"`, `"Nice"`), yielding zero diagnostic signal.

- **Impact on repeat-booking conclusions:** Negative operational themes (cancellations, support failures, fee disputes) appear far more prevalent in app-store text than in typical completed bookings, while moderately satisfied 3–4 star users who simply drift away are almost absent (`6.9%` combined for 2–3 stars).

### 2.2 Missing Silent Non-Returners (Zero Direct Trace in Baseline Tags)

Customers who complete an acceptable booking, have no complaint, and later default to an offline habit or forget Urban Company rarely write an app-store review.

- In `data/tagged/tagged_reviews.jsonl` + `data/tagged/review_queue.jsonl` (`N = 184` baseline core reviews):
  - `nothing_went_wrong = true`: **0 / 184 (0.0%)**
  - `recall_gap = true`: **0 / 184 (0.0%)**
  - `rebook_signal = unclear`: **182 / 184 (98.9%)** (`rebooked`: 1, `will_not_rebook`: 1, `did_not_rebook`: 0)
  - `alternative_used = unclear`: **183 / 184 (99.5%)** (`local provider`: 1)
- In `data/golden/golden_set.jsonl` (`N = 30` manually annotated reviews):
  - `rebook_signal = unclear`: **23 / 30 (76.7%)** (`rebooked`: 6, `will_not_rebook`: 1, `did_not_rebook`: 0)
  - `alternative_used = unclear`: **29 / 30 (96.7%)** (`local provider`: 1)
- Across all `1,248` core consumer reviews, only **11 (`0.9%`)** contain explicit keywords for offline alternatives or churn intent (`offline_alternative_or_churn_signal`).
- **Collection blocker compounding this gap:** Community forums where indirect traces live ("who do you use for AC service?") could not be collected in this run—Reddit returned HTTP `403` without OAuth credentials (`REDDIT_CLIENT_ID` unset) and YouTube Data API v3 requires `YOUTUBE_API_KEY` (unset).

- **Impact on repeat-booking conclusions:** The discovery engine cannot observe the "silent non-returner" cohort directly from app-store data. Any claim about *why* satisfied customers fail to return within 90 days remains a **hypothesis** until tested in Level 4 discovery interviews.

### 2.3 Source, Category, and Temporal Imbalance

- **Source skew (`N = 1,522`):**
  - `Play Store`: **1,200 (78.8%)**
  - `Shareholder Letter`: **213 (14.0%)**
  - `App Store`: **100 (6.6%)**
  - `Press Release`: **7 (0.5%)**
  - `Earnings Call`: **2 (0.1%)**
  - Missing consumer sources: Reddit (`0`), YouTube (`0`), Trustpilot (`0`), MouthShut (`0`).
- **Category sparsity (`N = 1,248` core consumer reviews):**
  - **90.4% (`1,128/1,248`)** do not mention a specific service category (`unspecified`) — reviewers complain or praise "the app" or "the service" generically.
  - Named categories in `1,248` core consumer reviews: `other` (appliance/spa/carpentry/painting) = **77**, `plumber` = **17**, `electrician` = **14**, `salon` = **13**, `AC` = **9**, `pest control` = **4**, `deep clean` = **1**.
  - Similarly, in the `184` baseline tagged reviews, **155 (`84.2%`)** are `category = unknown`.
- **Narrow recency window:**
  - `Play Store` (`n=1,200`) spans only **2026-11-02 to 2026-11-24** (23 days in November).
  - `App Store` (`n=100`) spans **2026-11-12 to 2026-11-21** (10 days).
  - Seasonal peaks (e.g., March–June AC servicing, pre-Diwali deep cleaning) are completely absent from consumer reviews.

- **Impact on repeat-booking conclusions:** Category-level comparisons (e.g., `AC` vs `salon` vs `deep clean`) have small cell sizes (`n = 1` to `77`) and November seasonal bias. Findings must be treated as directional, not statistically representative.

### 2.4 Missing City and Demographic Coverage

- **City coverage:** Explicit city names appear in only **9 / 1,248 (`0.7%`)** core consumer reviews (`3 / 184` in baseline tagged; `0 / 30` in golden set).
- **Household type coverage:** Explicit household cues (`living alone`, `family`, `renter`, etc.) appear in only **4 / 1,248 (`0.3%`)** core consumer reviews (`2 / 184` in baseline tagged; `0 / 30` in golden set).
- **Platform skew:** Android (`Play Store`) dominates iOS (`App Store`) 12:1 in our sample, and both skew toward digitally vocal users rather than silent household decision-makers.

- **Impact on repeat-booking conclusions:** We cannot segment repeat-booking barriers by Tier-1 vs Tier-2 city or by household type (`living alone` vs `family`) from public reviews alone.

---

## 3. Practical Mitigation Methods

| Bias | Mitigation Implemented / Planned |
|---|---|
| **App-store bimodal skew** | Never pool themes across ratings; report pain points separately for 1–2★ vs 4–5★ (`analysis_summary.json`) and anchor against UC's 4.79/5.0 in-app average rating. |
| **Low-information 5★ noise** | Filter/route `<20`-char reviews (`33.7%` of core consumer reviews) to `review_queue` (`low_information`) so they do not inflate positive or rebooking counts. |
| **Missing silent non-returners** | Explicitly mark `rebook_signal = unclear` when unstated (`98.9%` in baseline); use Level 4 interviews (5–6 users who completed a booking and did/did not rebook within 90 days) to test recall-gap and offline-habit hypotheses. |
| **InstaHelp contamination** | Flag and exclude `144` InstaHelp items (`42` Play Store, `10` App Store, `92` IR) from core-category analysis while retaining them in raw storage for provenance. |
| **Missing community forums** | Document Reddit/YouTube API blockers in `docs/sources.md`; configure `REDDIT_CLIENT_ID` / `YOUTUBE_API_KEY` when available to capture indirect "recommend a plumber/AC" threads. |
| **City/household sparsity** | Enforce strict non-inference (`city = null`, `household_type = unclear`) in tagging; capture city and household type directly in the Level 4 interview screener. |
