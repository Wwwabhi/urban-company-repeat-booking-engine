# Evaluation Report: Gemini v2 Predictions vs. Human-Annotated Golden Set

**Date**: 2026-11-24  
**Evaluator**: Automated Ground-Truth Comparative Harness  
**Model**: `gemini-3.5-flash-lite` (Pipeline Version: `v2`)  
**Golden Dataset**: `data/golden/golden_set.jsonl` (30 human-annotated records)  
**Machine-Readable Evaluation Artifact**: `evals/gemini_pilot_vs_golden.json`  

---

## 1. Executive Summary & Overlapping Sample

This evaluation benchmarks the real LLM predictions from the 10-review Gemini pilot (including the recovery experiment) against human-annotated ground-truth labels in the 30-record golden set.

- **Overlapping Records Evaluated**: **8 records** (all 8 successfully processed pilot reviews overlap with annotated golden records).
  - 6 records from the tagged output streams (`data/tagged/pilot/tagged_reviews_pilot.jsonl`, `data/tagged/pilot/retry_experiment/tagged_reviews_retry.jsonl`).
  - 2 records from the review queue output streams (`data/tagged/pilot/review_queue_pilot.jsonl`, `data/tagged/pilot/retry_experiment/review_queue_retry.jsonl`).
- **Excluded Records**: Exactly 2 reviews (`36b24dd5-1cd2-4752-9a46-68307d86382c` and `43582ef1-c85a-4b67-ad13-662ab7a72dcb`) failed upstream API calls and were excluded from model prediction evaluations per task instructions.
- **Overall Field Agreement**: Across all 72 evaluated field instances (8 records × 9 evaluated fields):
  - **Exact Field Matches**: **62 / 72 (86.1%)**
  - **Field Mismatches**: **10 / 72 (13.9%)**
- **Sample Size Consideration**: With $N = 8$, metric percentages represent directional trends and exact error categorization rather than definitive population statistics.

---

## 2. Field-by-Field Evaluation Metrics

Each of the 9 core fields was evaluated independently against the human ground-truth labels, respecting nullability and enum definitions:

| Field Name | Type / Values | Comparable Records ($N$) | Exact Matches | Mismatches | Accuracy | Key Observations |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| **`experience_type`** | Enum (`positive`, `negative`, `neutral`, `unclear`) | 8 | 8 | 0 | **100.0%** | Perfect alignment across 5 negative and 3 positive reviews ($F_1 = 1.0$). |
| **`nothing_went_wrong`** | Tri-state boolean (`True`, `False`, `None`) | 8 | 8 | 0 | **100.0%** | Perfect alignment: all 5 negative reviews tagged `False`, all 3 positive tagged `None` ($F_1 = 1.0$). |
| **`need_trigger`** | Enum (breakdown, season, move, etc., or `None`) | 8 | 8 | 0 | **100.0%** | Perfect alignment: all 8 correctly identified as `None` (no explicit trigger). |
| **`recall_gap`** | Tri-state boolean (`True`, `False`, `None`) | 8 | 8 | 0 | **100.0%** | Perfect alignment: all 8 correctly identified as `None` (no recall gap mentioned). |
| **`alternative_used`** | Enum (competitor, local, DIY, none, `unclear`) | 8 | 8 | 0 | **100.0%** | Perfect alignment: all 8 correctly identified as `unclear` (no alternative named). |
| **`post_service_expectation`**| Enum (revisit, warranty, tip, none, `unclear`) | 8 | 8 | 0 | **100.0%** | Perfect alignment: all 8 correctly identified as `unclear` (no follow-up expectation). |
| **`category`** | Enum (AC, salon, deep clean, plumber, etc., `other`, `unknown`) | 8 | 7 | 1 | **87.5%** | High accuracy. Single mismatch on Chimney cleaning (`other` vs `deep clean`). |
| **`rebook_signal`** | Enum (`rebooked`, `will_not_rebook`, `did_not_rebook`, `unclear`) | 8 | 4 | 4 | **50.0%** | **Primary weakness**: Model frequently over-predicts `will_not_rebook` for negative reviews. |
| **`unmet_need`** | Free-form String / `None` | 8 | 3 | 5 | **37.5%*** | *37.5% exact string match. **100.0% nullity agreement** (3/3 nulls matched; all 5 non-nulls captured identical latent friction).* |

---

## 3. Per-Class Precision, Recall, and F1 Breakdown

Where the sample supports meaningful calculation:

### A. `experience_type` (Accuracy: 100%)
- **`negative`** (Support = 5): TP = 5, FP = 0, FN = 0 → **Precision: 1.000, Recall: 1.000, F1: 1.000**
- **`positive`** (Support = 3): TP = 3, FP = 0, FN = 0 → **Precision: 1.000, Recall: 1.000, F1: 1.000**

### B. `nothing_went_wrong` (Accuracy: 100%)
- **`False`** (Support = 5): TP = 5, FP = 0, FN = 0 → **Precision: 1.000, Recall: 1.000, F1: 1.000**
- **`None`** (Support = 3): TP = 3, FP = 0, FN = 0 → **Precision: 1.000, Recall: 1.000, F1: 1.000**

### C. `category` (Accuracy: 87.5%)
- **`unknown`** (Support = 4): TP = 4, FP = 0, FN = 0 → **Precision: 1.000, Recall: 1.000, F1: 1.000**
- **`salon`** (Support = 1): TP = 1, FP = 0, FN = 0 → **Precision: 1.000, Recall: 1.000, F1: 1.000**
- **`deep clean`** (Support = 1): TP = 1, FP = 1, FN = 0 → **Precision: 0.500, Recall: 1.000, F1: 0.667**
- **`other`** (Support = 2): TP = 1, FP = 0, FN = 1 → **Precision: 1.000, Recall: 0.500, F1: 0.667**

### D. `rebook_signal` (Accuracy: 50.0%)
- **`unclear`** (Support = 7): TP = 4, FP = 1, FN = 3 → **Precision: 0.800, Recall: 0.571, F1: 0.667**
- **`will_not_rebook`** (Support = 0): TP = 0, FP = 3, FN = 0 → **Precision: 0.000, Recall: 0.000, F1: 0.000**
- **`rebooked`** (Support = 1): TP = 0, FP = 0, FN = 1 → **Precision: 0.000, Recall: 0.000, F1: 0.000**

---

## 4. Comprehensive Mismatch Table & Error Analysis

The 10 mismatches fall into three specific error patterns:

| Review ID | Field | Human Label | Gemini Label | Error Category | Root Cause & Explanation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `4e4e2ef9-6dd6-40cc-a65b-a3f327daf7f0` | `category` | `other` | `deep clean` | **Taxonomy Boundary Ambiguity** | Review states: *"Recently I have availed Chimney deep clean service..."*. Gemini matched verbatim phrase *"deep clean"*, but UC taxonomy maps appliance services (Chimney) to `other`. |
| `4e4e2ef9-6dd6-40cc-a65b-a3f327daf7f0` | `rebook_signal` | `unclear` | `will_not_rebook` | **Dissatisfaction-to-Churn Leakage** | Review expresses strong dissatisfaction (*"I'm extremely unhappy as I already paid almost Rs 1400 and expected to book another paid service"*), but does not explicitly state future refusal to rebook. Gemini over-inferred churn. |
| `4e4e2ef9-6dd6-40cc-a65b-a3f327daf7f0` | `unmet_need` | `reliable post-service installation` | `proper chimney reinstallation without post-service leaks and reasonable warranty coverage` | **Free-Text Phrasing Divergence** | Semantically aligned: both human and Gemini correctly identify that the chimney leaked after reinstallation and warranty coverage was inadequate. |
| `1876c25b-b9ea-4720-9fcd-d11a7caa4bf1` | `rebook_signal` | `unclear` | `will_not_rebook` | **Dissatisfaction-to-Churn Leakage** | Review states: *"‼️Third class customer care support... I wanna give -5 star review."* Severe dissatisfaction was treated by Gemini as `will_not_rebook` without an explicit churn phrase like *"never book again"*. |
| `1876c25b-b9ea-4720-9fcd-d11a7caa4bf1` | `unmet_need` | `responsive customer care and punctual technician arrival` | `professional behavior and proper service guidelines from technicians` | **Free-Text Phrasing Divergence** | Both capture technician operational failure (rude conduct, 4.5h delay, lack of guidelines). |
| `bb81193d-cf36-41b3-abce-4d201b3c4a59` | `rebook_signal` | `rebooked` | `unclear` | **Conservative Rebooking Invalidation** | Review states: *"The last one was the best."* Human inferred repeat booking from *"The last one"*. Gemini followed prompt rule *"do not infer repeat usage without explicit booking statement"*, flagged confidence as `low`, and sent to Review Queue. |
| `bec86ea9-9a8f-495d-a091-1e4ec7843980` | `unmet_need` | `full promised service duration` | `full standard service duration as promised` | **Free-Text Phrasing Divergence** | Verbatim semantic equivalent regarding 45 min provided instead of 1 hour standard service. |
| `6b579933-e83a-459c-b7c7-73f83b669c16` | `unmet_need` | `reliable app booking tracking` | `stable app functionality to view ongoing booking status and details` | **Free-Text Phrasing Divergence** | Both capture app crash preventing user from seeing booking status. |
| `06b45346-6f25-4d49-9b01-13d980482c2c` | `rebook_signal` | `unclear` | `will_not_rebook` | **Dissatisfaction-to-Churn Leakage** | Customer states: *"I had been a regular customer... he cancelled booking exact half hour before... customer service seems to be hopeless."* Human rules specify that regular customer tenure overridden by cancellation is `unclear`; Gemini over-inferred `will_not_rebook`. |
| `06b45346-6f25-4d49-9b01-13d980482c2c` | `unmet_need` | `protection against partner cancellations` | `reliable technician arrival without cancellations and responsive customer service` | **Free-Text Phrasing Divergence** | Both capture partner last-minute cancellation and customer support helplessness. |

---

## 5. Detailed Qualitative Topic Analysis

### A. `rebook_signal` (The Critical Point of Failure)
- **Human Rule**: Rebooking intent requires explicit textual grounding. Severe dissatisfaction, 1-star ratings, rude technician behavior, or last-minute cancellations alone must **never** be labeled `will_not_rebook` unless the user explicitly declares future intent (e.g., *"will never use UC again"*, *"uninstalled the app"*, *"switching to competitor"*). If absent, the signal is `unclear`.
- **Gemini Behavior**: Gemini generated 3 false positives for `will_not_rebook` on reviews `4e4e2ef9`, `1876c25b`, and `06b45346`. In each case, it conflated severe negative sentiment with explicit future refusal to book.
- **Queue Fallback Performance**: For review `bb81193d` (*"The last one was the best"*), Gemini was uncertain, set confidence to `low`, and routed it to the review queue, preventing an ungrounded classification.

### B. `nothing_went_wrong` (100% Precision & Recall)
- **Human Rule**: Must only be `True` when service was positive AND rebook was `did_not_rebook` / `will_not_rebook` (the "unexplained churn" state). For ordinary positive reviews, it is `None`. For negative reviews with defects, it is `False`.
- **Gemini Behavior**: Gemini exhibited 100% adherence: all 5 negative reviews received `False`, and all 3 positive reviews received `None`. Zero hallucinations or false `True` classifications occurred.

### C. `post_service_expectation` & `alternative_used` (100% Precision & Recall)
- Gemini resisted hallucinating post-service expectations or competitor alternatives when not explicitly named in the text, assigning `unclear` to all 8 reviews in 100% agreement with ground truth.

### D. `unmet_need` (Semantic Alignment Analysis)
- In 100% of cases where human ground-truth was `None` (reviews `bb81193d`, `99226311`, `75c91a8d`), Gemini output `None`, demonstrating zero invented needs on satisfactory reviews.
- In all 5 non-null cases, while wording diverged (e.g., *"reliable post-service installation"* vs. *"proper chimney reinstallation without post-service leaks and reasonable warranty coverage"*), Gemini accurately captured the core friction mechanism without hallucinating outside context.

---

## 6. Golden Set Integrity & Regression Verification

- **Regression Test Suite**: `python -m unittest discover tests` executed cleanly (**113 tests passed in 0.238s**).
- **Golden Dataset SHA-256**: `ba4535c28e6643df31990556d70bfd0a6c36d47894930f164f7215eeea3aff0c` (Identical).
- **Baseline Raw / Normalized / v1 Hashes**: Completely identical; zero datasets modified.

---

## 7. Conclusion & Strategic Recommendation

### Conclusion: **In Need of Prompt Corrections** (Option 2)

Gemini v2 is **not ready for an unassisted full-scale run of 174 reviews** in its current configuration, nor is it unreliable or fundamentally flawed. Rather, it is **in need of targeted prompt corrections**:

1. **Root Cause**: The 50% accuracy on `rebook_signal` is caused by a systemic prompt vulnerability: **dissatisfaction-to-churn leakage**. Gemini treats intense anger and 1-star ratings as equivalent to `will_not_rebook`, whereas the repeat-booking project schema strictly demands explicit future non-rebooking declarations.
2. **Impact if Scaled Now**: Scaling to 184 reviews without correcting this prompt rule will artificially inflate `will_not_rebook` classifications by an estimated 60% across negative reviews, invalidating downstream repeat-booking opportunity sizing.
3. **Actionable Prompt Fix**:
   - Add an explicit negative constraint in `engine/prompts/tagger_v2.md`:
     > *"CRITICAL RULE: Anger, complaints, poor ratings, or partner cancellations do NOT equal `will_not_rebook`. You must ONLY tag `will_not_rebook` if the customer explicitly uses phrases like 'will never book again', 'never using again', 'deleted the app', or 'uninstalled'. If the customer is merely complaining without explicitly stating they will never book again, you MUST tag `unclear`."*
   - Add explicit guidance for appliance cleaning: Chimney cleaning and RO purifiers belong to `other`, not `deep clean`.
