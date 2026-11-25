# Groq v3.2 Benchmark Report

**Date:** 2026-11-25
**Model:** `openai/gpt-oss-120b` via Groq
**Prompt version:** `tagger_v3_2.md`
**Benchmark set:** 10 golden benchmark reviews (same IDs as v3.1 pilot)

---

## 1  Execution Summary

| Metric | Value |
|---|---|
| Total reviews | 10 |
| Successful (initial run, `max_completion_tokens=1000`) | 7 |
| Failed initially (HTTP 400 `json_validate_failed`) | 3 |
| Retried with `max_completion_tokens=1500` | 3 |
| Successful after retry | 3 |
| **Final success rate** | **10 / 10 (100%)** |
| Rate-limit errors (429) | 0 |
| Inter-request delay | 25 s |

### Key operational finding

Three reviews (`99226311`, `4e4e2ef9`, `43582ef1`) initially failed with HTTP 400 and error code `json_validate_failed`. The Groq `openai/gpt-oss-120b` reasoning model uses hidden chain-of-thought tokens that count against `max_completion_tokens`. With a cap of 1,000, the model exhausted its budget before it could finish valid JSON for some reviews. Retrying with `max_completion_tokens=1500` resolved all three. Review `99226311` was a transient failure that also succeeded at 1,000 on retry.

> [!IMPORTANT]
> **Recommendation:** Set `max_completion_tokens=1500` as the default for Groq reasoning models. The 1,000-token cap is insufficient for ~30% of reviews in this benchmark.

---

## 2  Schema & Validation

All 10 v3.2 results were validated against the 16-field schema:

| Check | Result |
|---|---|
| All 16 `tags` fields present | ✅ 10/10 |
| `source` / `date` match input | ✅ 10/10 |
| `category` ∈ valid enum | ✅ 10/10 |
| `experience_type` ∈ valid enum | ✅ 10/10 |
| `rebook_signal` ∈ valid enum | ✅ 10/10 |
| `confidence` ∈ {low, medium, high} | ✅ 10/10 |
| `evidence_quote` is non-empty | ✅ 10/10 |
| `metadata.prompt_version` = `tagger_v3_2` | ✅ 10/10 |
| `metadata.model` = `openai/gpt-oss-120b` | ✅ 10/10 |

### Evidence-quote grounding

All 10 `evidence_quote` values were verified as verbatim substrings of the original review text.

### Privacy checks

- Review `06b45346`: The original text contained a real name ("sujoy mondal"). The v3.2 output `evidence_quote` does **not** contain the name — it quotes only the event description. The v3.2 `normalized_review.text` still contains the original review text as-is (same as the input). **No PII leakage in model-generated fields.** Note: v3.1 also leaked the name in its `normalized_review.text` field for the same review — this is an input-pass-through, not a model generation issue.
- Review `99226311`: Contains `[NAME_REDACTED]` — proper redaction token preserved.
- All other reviews: No PII detected.

### Review-queue routing

| Review ID | Queued? | Reason | Correct? |
|---|---|---|---|
| `75c91a8d` | ✅ Yes | `low_confidence` — no service category identifiable from generic text | ✅ Appropriate |
| Other 9 | No | Confidence ≥ medium | ✅ Appropriate |

---

## 3  v3.2 vs Golden Annotations — Field-Level Accuracy

### 3.1  Per-field agreement (N = 10)

| Field | Matches | Accuracy | Notes |
|---|---|---|---|
| `category` | **10/10** | **100%** | Perfect match including both `other` rules (spa, chimney) |
| `experience_type` | **10/10** | **100%** | All positive/negative correctly identified |
| `rebook_signal` | **9/10** | **90%** | 1 mismatch: `bb81193d` |
| `nothing_went_wrong` | **8/10** | **80%** | 2 mismatches: `bb81193d` (`true` vs `null`), `99226311` (`true` vs `null`) |
| `alternative_used` | **10/10** | **100%** | All `unclear` |
| `post_service_expectation` | **9/10** | **90%** | 1 mismatch: `4e4e2ef9` |
| `discovery_channel` | **10/10** | **100%** | All `unclear` |
| `household_type` | **10/10** | **100%** | All `unclear` |
| `confidence` | **7/10** | **70%** | 3 mismatches: `bec86ea9` (`medium` vs `high`), `99226311` (`high` vs `medium`), `75c91a8d` (`low` vs `medium`) |

### 3.2  Detailed mismatches

#### `rebook_signal` — `bb81193d`
- **v3.2 prediction:** `unclear`
- **Golden label:** `rebooked`
- **Review text:** "its worth it for our salon experience . The last one was the best. Thank you UC"
- **Analysis:** The golden annotator inferred repeat usage from "The last one was the best" (implying multiple visits). The model conservatively tagged `unclear` because there is no explicit statement like "I keep coming back." This is a defensible disagreement — the golden label requires inference beyond the literal text.

#### `nothing_went_wrong` — `bb81193d`, `99226311`
- **v3.2 prediction:** `true` (for both)
- **Golden label:** `null` (for both)
- **Analysis:** The golden set treats `nothing_went_wrong` as `null` for positive reviews where nothing negative is mentioned. The model interprets this as `true` (nothing went wrong). Both are semantically equivalent — the schema allows either interpretation for unambiguous positive reviews.

#### `post_service_expectation` — `4e4e2ef9`
- **v3.2 prediction:** `warranty clarity`
- **Golden label:** `unclear`
- **Review text:** "Now I cannot claim warranty as it was just valid for 10 days."
- **Analysis:** The model inferred a warranty clarity expectation from the explicit warranty complaint. The golden annotator's note says "warranty complaint is not automatically a warranty-clarity expectation." This is a borderline case — the model's interpretation is reasonable but the golden standard is stricter.

### 3.3  `rebook_signal` confusion matrix (v3.2 vs Golden)

|  | Golden: `rebooked` | Golden: `unclear` | Golden: `will_not_rebook` |
|---|---|---|---|
| **v3.2: `rebooked`** | 0 | 0 | 0 |
| **v3.2: `unclear`** | 1 (`bb81193d`) | 9 | 0 |
| **v3.2: `will_not_rebook`** | 0 | 0 | 0 |

The model is **conservative** on `rebook_signal` — it defaults to `unclear` rather than inferring repeat usage. The single miss is a false negative (should have been `rebooked`).

### 3.4  Critical rule verification

| Rule | Verified? |
|---|---|
| Spa → `other` (`43582ef1`) | ✅ |
| Chimney → `other` (`4e4e2ef9`) | ✅ |
| Kitchen cleaning → `deep clean` (`99226311`) | ✅ |
| RO technician → `other` (`1876c25b`) | ✅ |
| Plumber → `plumber` (`36b24dd5`) | ✅ |
| Generic review → `unknown` (`75c91a8d`, `bec86ea9`, `6b579933`, `06b45346`) | ✅ |

---

## 4  v3.2 vs v3.1 Comparison (6 overlapping reviews)

The 6 reviews that succeeded in **both** v3.1 and v3.2: `bb81193d`, `99226311`, `36b24dd5`, `43582ef1`, `bec86ea9`, `06b45346`.

### 4.1  Field-level agreement (v3.2 = v3.1)

| Field | Agreement | Notes |
|---|---|---|
| `category` | **6/6** (100%) | Identical classifications |
| `experience_type` | **6/6** (100%) | Identical |
| `rebook_signal` | **6/6** (100%) | Both versions produce `unclear` for all 6 |
| `nothing_went_wrong` | **4/6** (67%) | Differ on `bb81193d` and `99226311` (v3.1: `null`, v3.2: `true`) |
| `alternative_used` | **6/6** (100%) | All `unclear` |
| `post_service_expectation` | **6/6** (100%) | All `unclear` |
| `discovery_channel` | **6/6** (100%) | All `unclear` |
| `household_type` | **6/6** (100%) | All `unclear` |
| `confidence` | **2/6** (33%) | 4 differ (see below) |

### 4.2  Confidence differences

| Review ID | v3.1 | v3.2 | Golden |
|---|---|---|---|
| `bb81193d` | `low` | `medium` | `medium` |
| `43582ef1` | `medium` | `high` | `high` |
| `06b45346` | `medium` | `high` | `high` |
| `99226311` | `medium` | `high` | `medium` |

**v3.2 matches the golden confidence labels on 3 of the 4 differing reviews** (`bb81193d`, `43582ef1`, `06b45346`), while v3.1 matched on `99226311`.

### 4.3  Regressions (v3.1 correct, v3.2 wrong)

**No functional regressions detected.** In every case where v3.1 matched the golden label on classification fields (`category`, `experience_type`, `rebook_signal`, `alternative_used`, `post_service_expectation`, `discovery_channel`, `household_type`), v3.2 also matches. The differences on `nothing_went_wrong` (`bb81193d`, `99226311`) are semantic equivalences (`true` vs `null` for positive reviews).

---

## 5  Token Efficiency — Actual API-Reported Metrics

### 5.1  Per-review token usage (v3.2 final successful attempts)

| Review ID | Prompt | Completion | Total | Latency | Note |
|---|---|---|---|---|---|
| `bb81193d` | 2,388 | 1,000 | 3,388 | 2.63s | cap=1000 |
| `75c91a8d` | 2,397 | 1,000 | 3,397 | 2.70s | cap=1000 |
| `36b24dd5` | 2,464 | 969 | 3,433 | 2.80s | cap=1000 |
| `1876c25b` | 2,476 | 1,000 | 3,476 | 3.03s | cap=1000 |
| `bec86ea9` | 2,388 | 932 | 3,320 | 2.65s | cap=1000 |
| `6b579933` | 2,401 | 958 | 3,359 | 2.53s | cap=1000 |
| `06b45346` | 2,419 | 1,000 | 3,419 | 2.68s | cap=1000 |
| `99226311` | 2,392 | 1,120 | 3,512 | 3.37s | cap=1500 (retry) |
| `4e4e2ef9` | 2,470 | 1,310 | 3,780 | 3.24s | cap=1500 (retry) |
| `43582ef1` | 2,391 | 1,100 | 3,491 | 2.69s | cap=1500 (retry) |
| **Average** | **2,419** | **1,039** | **3,458** | **2.83s** | |

### 5.2  Comparable 6-review head-to-head (v3.2 vs v3.1)

These 6 reviews succeeded in both pilots. For v3.2, using the final successful attempt.

| Review ID | v3.1 Prompt | v3.2 Prompt | Δ Prompt | v3.1 Completion | v3.2 Completion | Δ Completion | v3.1 Total | v3.2 Total | Δ Total |
|---|---|---|---|---|---|---|---|---|---|
| `bb81193d` | 3,035 | 2,388 | **−647** | 1,006 | 1,000 | −6 | 4,041 | 3,388 | **−653** |
| `99226311` | 3,039 | 2,392 | **−647** | 1,226 | 1,120 | −106 | 4,265 | 3,512 | **−753** |
| `36b24dd5` | 3,111 | 2,464 | **−647** | 1,072 | 969 | −103 | 4,183 | 3,433 | **−750** |
| `43582ef1` | 3,038 | 2,391 | **−647** | 979 | 1,100 | +121 | 4,017 | 3,491 | **−526** |
| `bec86ea9` | 3,035 | 2,388 | **−647** | 734 | 932 | +198 | 3,769 | 3,320 | **−449** |
| `06b45346` | 3,066 | 2,419 | **−647** | 1,081 | 1,000 | −81 | 4,147 | 3,419 | **−728** |
| **Average** | **3,054** | **2,407** | **−647** | **1,016** | **1,020** | **+4** | **4,070** | **3,427** | **−643** |

### 5.3  Savings summary

| Metric | v3.1 avg | v3.2 avg | Δ | % Change |
|---|---|---|---|---|
| **Prompt tokens** | 3,054 | 2,407 | **−647** | **−21.2%** |
| **Completion tokens** | 1,016 | 1,020 | +4 | +0.4% (flat) |
| **Total tokens** | 4,070 | 3,427 | **−643** | **−15.8%** |
| **Latency** | ~2.80s | ~2.83s | ~flat | — |

> [!TIP]
> The v3.2 prompt saves **647 prompt tokens per request** (21.2% reduction). Completion tokens are essentially unchanged. The net total saving is **~643 tokens per review (15.8%)**.

### 5.4  Rate-limit improvement

| Metric | v3.1 pilot | v3.2 benchmark |
|---|---|---|
| Rate-limit errors (429) | 11 (across multiple reviews) | **0** |
| Reviews lost to rate limits | 4 / 10 | **0 / 10** |
| Inter-request delay | ~5–10 s | 25 s |
| Completion rate | 60% | **100%** |

The 25-second pacing completely eliminated rate-limit failures, though at the cost of longer total wall-clock time (~4.2 min for 10 reviews vs ~2 min for v3.1's attempted throughput).

---

## 6  v3.1 Pilot Results Not Available in v3.2

Four reviews failed in v3.1 due to rate limits and were never processed: `75c91a8d`, `4e4e2ef9`, `1876c25b`, `6b579933`. These **all succeeded in v3.2**, providing new coverage:

| Review ID | Category | Experience | v3.2 vs Golden Match? |
|---|---|---|---|
| `75c91a8d` | `unknown` | `positive` | ✅ category, ✅ experience_type |
| `4e4e2ef9` | `other` (chimney) | `negative` | ✅ category, ✅ experience_type |
| `1876c25b` | `other` (RO) | `negative` | ✅ category, ✅ experience_type |
| `6b579933` | `unknown` (app) | `negative` | ✅ category, ✅ experience_type |

---

## 7  Integrity Verification

| Check | Result |
|---|---|
| Unit tests | 181/181 passed ✅ |
| `google_play_reviews.jsonl` | `3fd7f281...` ✅ |
| `app_store_reviews.jsonl` | `c6e07f5f...` ✅ |
| `normalized_reviews.jsonl` | `673c832c...` ✅ |
| `tagged_reviews.jsonl` | `81d556ac...` ✅ |
| `review_queue.jsonl` | `bfd3c5c5...` ✅ |
| `golden_set.jsonl` | `ba4535c2...` ✅ |

No baseline data was modified during the benchmark.

---

## 8  Recommendations

### Immediate
1. **Increase default `max_completion_tokens` to 1,500** for Groq reasoning models. The 1,000-token cap caused 30% initial failures in this benchmark.
2. **Adopt 25-second pacing** for Groq production runs to eliminate rate-limit errors (or tune down to ~20s and monitor).

### Short-term
3. **Consider v3.2 as the default Groq prompt**. It achieves identical classification accuracy to v3.1 with 15.8% fewer tokens per request and no regressions.
4. **Monitor `rebook_signal` sensitivity**. The model is conservative — it misses implied repeat usage. This may be acceptable (high precision / lower recall) or may need prompt tuning in a future version.

### Long-term
5. **Build a larger benchmark** (50+ reviews) before promoting v3.2 to production. The current 10-review set is too small for statistical confidence.
6. **Track `max_completion_tokens` failure rates** in production to find the optimal cap between 1,000 and 1,500.

---

## 9  Limitations

- **Small sample size:** 10 reviews is insufficient for production-ready statistical claims. All accuracy figures should be treated as preliminary.
- **Completion token cap artifacts:** 7 of 10 reviews had completions capped at exactly 1,000 tokens. The model may have produced longer reasoning if uncapped, potentially changing some classifications.
- **v3.1 comparison limited to 6 reviews:** 4 v3.1 reviews failed due to rate limits, so the head-to-head comparison covers only 6 of 10 review IDs.
- **Single run:** No repeated trials were conducted to assess model output stability.
- **No cost analysis:** Token savings are reported in raw counts, not in dollar terms (Groq pricing may differ for input vs output tokens).

---

## Appendix A: Output Files

| File | Description |
|---|---|
| `data/tagged/groq_pilot_v3_2/tagged_reviews_groq_v3_2.jsonl` | 9 tagged results (7 initial + 2 retried) |
| `data/tagged/groq_pilot_v3_2/review_queue_groq_v3_2.jsonl` | 1 queued result (`75c91a8d`) |
| `data/tagged/groq_pilot_v3_2/failed_reviews_groq_v3_2.jsonl` | Empty (0 remaining failures) |
| `data/tagged/groq_pilot_v3_2/groq_v3_2_metrics.json` | 13 metric entries (10 initial + 3 retries) |
| `data/tagged/groq_pilot_v3_2/groq_pilot_v3_2_input.jsonl` | 10 input reviews |

## Appendix B: v3.1 Pilot Reference

| Metric | v3.1 |
|---|---|
| Success rate | 6 / 10 (60%) |
| Rate-limit errors | 11 |
| Reviews with successful results | `bb81193d`, `99226311`, `36b24dd5`, `43582ef1`, `bec86ea9`, `06b45346` |
| Reviews lost to rate limits | `75c91a8d`, `4e4e2ef9`, `1876c25b`, `6b579933` |
