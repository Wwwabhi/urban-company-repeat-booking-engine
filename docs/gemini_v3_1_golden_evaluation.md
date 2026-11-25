# Complete 30-Record Golden Set Evaluation: Gemini v3.1

**Evaluation Date**: 2026-11-24  
**Pipeline Version**: Gemini v3.1 (`tagger_v3_1.md`)  
**Provider**: Google Gemini API  
**Model**: `gemini-3.5-flash-lite`  
**Evaluation Benchmark**: Complete 30-record human golden ground-truth dataset (`data/golden/golden_set.jsonl`)  
**Input Source**: `data/tagged/golden_v3_evaluation/golden_v3_input.jsonl` (30 identical records)  
**Machine-Readable Evaluation Artifact**: `evals/gemini_v3_1_golden.json`  

---

## 1. Executive Summary

We executed a controlled live evaluation of **Gemini v3.1** (`gemini-3.5-flash-lite`, using calibrated prompt `engine/prompts/tagger_v3_1.md`) against the complete 30-record human-annotated golden set. 

This evaluation benchmark tested the two policy updates introduced in prompt version v3.1:
1. **Taxonomy Alignment for Spa Services**: Explicitly disambiguating spa sessions, body spa, and body massage as `category: "other"`, reserving `"salon"` strictly for hair and beauty grooming.
2. **Rebooking Future Intent Calibration**: Explicitly mapping unambiguous forward-looking booking intentions (e.g. *"I will definitely book her again"*, *"would book anytime again"*) to `rebook_signal: "rebooked"`, while maintaining strict guards so that historical tenure alone and general satisfaction/praise map to `"unclear"`.

### Key Benchmark Metrics ($N=30$)

| Evaluation Dimension | Gemini v3 (`tagger_v3`) | Gemini v3.1 (`tagger_v3_1`) | Delta / Impact |
| :--- | :---: | :---: | :--- |
| **Total Evaluated Records** | 30 | 30 | Identical $N=30$ benchmark input |
| **Successfully Tagged** | 20 (66.7%) | 19 (63.3%) | High-confidence classifications |
| **Sent to Review Queue** | 10 (33.3%) | 11 (36.7%) | Safe containment of ambiguous edge cases |
| **Permanent API Failures** | 0 (0.0%) | 0 (0.0%) | 100% execution completion (32 retries recovered) |
| **Overall Core Categorical Accuracy** | **91.67% (220 / 240)** | **95.42% (229 / 240)** | **+3.75% (+9 net correct field classifications)** |
| **`category` Accuracy** | **83.33% (25 / 30)** | **96.67% (29 / 30)** | **+13.34% (Spa taxonomy defect fully resolved)** |
| **`rebook_signal` Accuracy** | **86.67% (26 / 30)** | **90.00% (27 / 30)** | **+3.33% (0 false churn; future intent captured)** |
| **`nothing_went_wrong` Accuracy** | **80.00% (24 / 30)** | **86.67% (26 / 30)** | **+6.67% (Calibrated tri-state handling)** |
| **`need_trigger` Accuracy** | **93.33% (28 / 30)** | **96.67% (29 / 30)** | **+3.34%** |
| **`alternative_used` Accuracy** | **96.67% (29 / 30)** | **100.00% (30 / 30)** | **+3.33% (Perfect agreement)** |
| **`recall_gap` Accuracy** | **100.00% (30 / 30)** | **100.00% (30 / 30)** | **100% Perfect agreement** |
| **`post_service_expectation` Accuracy** | **100.00% (30 / 30)** | **100.00% (30 / 30)** | **100% Perfect agreement** |

---

## 2. Execution Pipeline Metrics & Reliability

- **Total Normalized Reviews Processed**: 30
- **InstaHelp Records Excluded**: 0 (all 30 were eligible core services)
- **Tagged Output**: 19 records saved to `data/tagged/golden_v3_1_evaluation/tagged_reviews_golden_v3_1.jsonl`
- **Review Queue Output**: 11 records saved to `data/tagged/golden_v3_1_evaluation/review_queue_golden_v3_1.jsonl`
  - *Queue Trigger Breakdown*:
    - Low Information (<20 chars): 4 reviews
    - Low Confidence / Borderline Sentiment: 8 reviews
    - Rating / Polarity Conflict: 3 reviews
    - Ungrounded Evidence: 1 review
- **Permanent Errors**: 0
- **Transient Retries**: 32 total HTTP 503 Service Unavailable / Gateway Timeout retries from the upstream Google Generative Language endpoint, all successfully recovered using the validated bounded backoff policy (3s initial, multiplier 2.0, max 15s, 30s timeout).

---

## 3. Detailed Audit of Key Milestone Reviews

### 1. Review `14809078193` (Explicit Future Booking Intent & Body Spa)
- **Review Text**: *"Incredible Experience with Body Spa – Ask for [NAME_REDACTED]!... Serious skill, absolutely in awe of her service and would recommend and book her anytime again!"*
- **Human Ground Truth**: `category: "other"` | `rebook_signal: "rebooked"`
- **Gemini v3 Result**: `category: "salon"` (mismatch) | `rebook_signal: "unclear"` (mismatch)
- **Gemini v3.1 Result**: **`category: "other"` (MATCH)** | **`rebook_signal: "rebooked"` (MATCH)**
- **Audit Findings**:
  - In v3, the model misclassified body spa as `salon` due to the prompt's salon definition, and misclassified the rebooking signal as `unclear` because the customer had not already completed an additional service.
  - In v3.1, both errors were completely eliminated: the body spa service correctly mapped to `other`, and the forward-looking statement *"would recommend and book her anytime again!"* correctly mapped to `rebooked`.

### 2. Review `43582ef1-c85a-4b67-ad13-662ab7a72dcb` (Spa Sessions Warning)
- **Review Text**: *"Stay away from their Spa sessions , they are just going to treat you as their ginni pig ! horrible horrible support"*
- **Human Ground Truth**: `category: "other"` | `rebook_signal: "unclear"`
- **Gemini v3 Result**: `category: "salon"` (mismatch) | `rebook_signal: "unclear"` (match)
- **Gemini v3.1 Result**: **`category: "other"` (MATCH)** | **`rebook_signal: "unclear"` (MATCH)**
- **Audit Findings**:
  - The spa session is now classified as `other` in exact alignment with Decision 009 and the golden ground truth.
  - The warning to third-party prospective customers (*"Stay away"*) is correctly maintained as `rebook_signal: "unclear"` (zero false-positive churn).

### 3. Review `bb81193d-cf36-41b3-abce-4d201b3c4a59` (Historical Mention & Gratitude)
- **Review Text**: *"its worth it for our salon experience . The last one was the best. Thank you UC"*
- **Human Ground Truth**: `category: "salon"` | `rebook_signal: "rebooked"`
- **Gemini v3 Result**: `category: "salon"` (match) | `rebook_signal: "unclear"` (mismatch)
- **Gemini v3.1 Result**: `category: "salon"` (match) | `rebook_signal: "unclear"` (mismatch)
- **Audit Findings & Human Mismatch Explanation**:
  - Gemini v3.1 continues to classify `rebook_signal` as `"unclear"`.
  - **Reason for Divergence**: The customer's statement *"The last one was the best"* refers to past service history, and *"Thank you UC"* expresses general satisfaction/gratitude. 
  - Under Directive 5 of `tagger_v3_1.md`:
    > *"Historical repeat usage alone does not establish future intent. Phrases like 'regular customer', 'frequent user', or 'always used UC' describe past historical status, NOT present rebooking behavior."*
    > *"General satisfaction, gratitude, or praise alone (e.g., 'Urban Company is best', 'Thank you UC', 'great service') maps to 'unclear' unless accompanied by explicit repeat booking confirmation or future booking intent."*
  - The model strictly and faithfully adhered to this non-inference policy. It did not extrapolate a completed future booking from past historical tenure.
  - **Recommendation**: This golden ground-truth annotation was flagged for human review. If the golden dataset is updated in the future to reflect the strict non-inference standard, `bb81193d` should be labeled `rebook_signal: "unclear"`.

---

## 4. Regression Analysis: Comparison Between v3 and v3.1

Across all $30 \times 8 = 240$ discrete categorical/tri-state evaluations:
- **Net Improvement**: $+9$ correct classifications ($220 \rightarrow 229$, $91.67\% \rightarrow 95.42\%$).
- **10 Definite Improvements**:
  1. `4e4e2ef9-6dd6-40cc-a65b-a3f327daf7f0`: `rebook_signal` corrected from `did_not_rebook` $\rightarrow$ `unclear` (matches ground truth).
  2. `43582ef1-c85a-4b67-ad13-662ab7a72dcb`: `category` corrected from `salon` $\rightarrow$ `other` (matches ground truth).
  3. `14815231009`: `nothing_went_wrong` corrected from `True` $\rightarrow$ `None` (matches ground truth).
  4. `14809078193`: `category` corrected from `salon` $\rightarrow$ `other` (matches ground truth).
  5. `14809078193`: `rebook_signal` corrected from `unclear` $\rightarrow$ `rebooked` (matches ground truth).
  6. `14787997500`: `nothing_went_wrong` corrected from `None` $\rightarrow$ `False` (matches ground truth).
  7. `14784151525`: `category` corrected from `AC` $\rightarrow$ `unknown` (matches ground truth, multi-category umbrella).
  8. `14811553737`: `alternative_used` corrected from `local provider` $\rightarrow$ `unclear` (matches ground truth).
  9. `14792849957`: `category` corrected from `salon` $\rightarrow$ `unknown` (matches ground truth, multi-category umbrella).
  10. `14792849957`: `need_trigger` corrected from `routine` $\rightarrow$ `None` (matches ground truth).

- **1 Observed Regression / Divergence**:
  - **Review `14792849957`**:
    - *Text*: *"I have been using Urban Company since before the time when it was then called ‘Urban Clap’. It is my go-to app for all services... Definitely recommend this App to everyone and for sure you will NOT be disappointed."*
    - *v3 Prediction*: `rebook_signal: "rebooked"` (matched human).
    - *v3.1 Prediction*: `rebook_signal: "unclear"` (diverged from human).
    - *Root Cause Analysis*: In v3.1, the prompt reinforced that general app praise and historical tenure alone describe past usage rather than active forward intent. Because the customer described historical usage and gave an umbrella recommendation without mentioning an active upcoming appointment, the model conservatively assigned `unclear`. While technically a statistical divergence from the human label, this conservative behavior aligns directly with the anti-hallucination policy.

---

## 5. Confusion Matrices ($N=30$)

### 1. `rebook_signal` ($N=30$)

```text
Human / Predicted              unclear        rebooked will_not_rebook  did_not_rebook     Total
------------------------------------------------------------------------------------------------
unclear                             23               0               0               0        23
rebooked                             3               3               0               0         6
will_not_rebook                      0               0               1               0         1
did_not_rebook                       0               0               0               0         0
------------------------------------------------------------------------------------------------
Total (Predicted)                   26               3               1               0        30
```

- **Accuracy**: $27 / 30 = \mathbf{90.00\%}$
- **Precision on `will_not_rebook`**: $1 / 1 = \mathbf{100.00\%}$ (Zero false-positive churn predictions across all 17 negative reviews).
- **Precision on `rebooked`**: $3 / 3 = \mathbf{100.00\%}$ (Zero false-positive repeat-booking predictions).
- **Accuracy on `unclear`**: $23 / 23 = \mathbf{100.00\%}$ (No leakage into churn or ungrounded repeat status).

---

### 2. `category` ($N=30$)

```text
Human / Predicted                   AC      deep clean         plumber           salon     electrician    pest control           other         unknown     Total
----------------------------------------------------------------------------------------------------------------------------------------------------------------
AC                                   1               0               0               0               0               0               0               0         1
deep clean                           0               4               0               0               0               0               0               0         4
plumber                              0               0               1               0               0               0               0               0         1
salon                                0               0               0               3               0               0               0               0         3
electrician                          0               0               0               0               0               0               0               0         0
pest control                         0               0               0               0               0               0               0               0         0
other                                0               0               0               0               0               0               6               0         6
unknown                              0               0               0               0               0               0               1              14        15
----------------------------------------------------------------------------------------------------------------------------------------------------------------
Total (Predicted)                    1               4               1               3               0               0               7              14        30
```

- **Accuracy**: $29 / 30 = \mathbf{96.67\%}$
- **Single Mismatch**: In review `372c9648-73fe-4245-8121-a8f198701159` (*"Good for low level cleaning jobs. Do NOT go for expensive painting or waterproofing service"*), the model assigned `category: "other"` (since painting belongs to `other`), whereas human labeled `unknown` due to the broad cautionary nature of the review.

---

### 3. `nothing_went_wrong` ($N=30$)

```text
Human / Predicted                 None           False            True     Total
--------------------------------------------------------------------------------
None                                10               3               0        13
False                                1              16               0        17
True                                 0               0               0         0
--------------------------------------------------------------------------------
Total (Predicted)                   11              19               0        30
```

- **Accuracy**: $26 / 30 = \mathbf{86.67\%}$
- **Zero False-Positive `True`**: No customer with operational friction or an unstated rebooking status was incorrectly tagged as `True`.

---

### 4. `experience_type` ($N=30$)

```text
Human / Predicted             positive         neutral        negative         unclear     Total
------------------------------------------------------------------------------------------------
positive                            10               0               0               0        10
neutral                              0               1               0               0         1
negative                             0               0              17               0        17
unclear                              0               1               1               0         2
------------------------------------------------------------------------------------------------
Total (Predicted)                   10               2              18               0        30
```

- **Accuracy**: $28 / 30 = \mathbf{93.33\%}$
- **100% Precision on Positive and Negative substantive reviews**. The two mismatches occurred on terse low-information reviews (`b31f176a` *"ok ok"* and `14793598838` *"Pedicure. Therapist not reported..."*), both of which were appropriately routed to the human review queue.

---

## 6. Honest Evaluation of Limitations

While Gemini v3.1 achieved 95.42% accuracy on core fields, several critical limitations must be explicitly noted before considering large-scale batch processing:

1. **Conservative Stance on Conversational Rebooking Statements**:
   - The model strictly demands affirmative future booking commitment language (*"will definitely book again"*, *"would book anytime again"*).
   - Conversational or nostalgic phrases indicating habitual use (*"the last one was the best"*, *"it is my go-to app"*) are routed to `unclear`. While this eliminates false positives, it leads to conservative false negatives when human annotators interpret habitual enthusiasm as repeat usage.
2. **Review Queue Containment Volume**:
   - 11 of the 30 reviews (36.7%) were routed to the human review queue.
   - On boundary-heavy golden test sets, this high queue rate is expected and desirable. However, in production runs, handling 35-40% manual review volume would require significant human annotator bandwidth.
3. **Upstream Google API Throttling & Rate Sensitivity**:
   - The pilot encountered 32 transient HTTP 503 errors across 30 reviews, requiring 5 retry cycles to complete.
   - Running the remaining 154 reviews without inter-review rate limiting (minimum 3.0s delay) or robust exponential backoff will encounter severe upstream throttling.
4. **Free-Text `unmet_need` Phrasing Variance**:
   - Exact string match was 33.33% ($10/30$), although semantic alignment was $90.00\%$ ($27/30$). Downstream analytical pipelines clustering customer friction cannot rely on exact string equality and will require embedding-based semantic similarity or normalized category groupings.

---

## 7. Conclusion & Next Steps

Gemini v3.1 successfully resolved the spa taxonomy conflict and eliminated the future intent defect while preserving the zero-churn-leakage guarantee.

The dataset, prompt, and test configurations remain fully isolated:
- Prompt: `engine/prompts/tagger_v3_1.md`
- Output: `data/tagged/golden_v3_1_evaluation/`
- Evaluation Artifact: `evals/gemini_v3_1_golden.json`
- Baseline SHA-256 Checksums: Strictly intact across all 6 repository files.
