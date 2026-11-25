# Gemini v3.2 Golden-Set Evaluation Report

**Date:** 2026-11-25  
**Model:** `gemini-3.5-flash-lite`  
**Prompt:** `engine/prompts/tagger_v3_2.md`  
**Golden Set:** `data/golden/golden_set.jsonl` (`30` human-annotated records)  
**Outputs:** `data/tagged/golden_v3_2_gemini/tagged_golden_gemini_v3_2.jsonl`

---

## 1. Execution, Latency & Reliability

| Metric | Value |
|---|---|
| Golden records attempted | `30` |
| Succeeded (`200 OK`) | **`29 / 30` (96.7%)** *(1 failed after 4/4 `503` attempts)* |
| Transient retries (`HTTP 503`) | `17` across 30 records (`0` `429` rate-limit errors) |
| Average wall latency (OK calls) | **`5.00s`** (min `1.85s`, max `21.23s` with backoff) |
| Evidence-quote grounding | **`28 / 29` (96.6%)** verbatim substring match |
| Privacy check (`audit_privacy`) | **`29 / 29` (100%)** passed |

---

## 2. Field-Level Agreement (`N = 29` Evaluated Records)

**Overall field-level agreement (11 categorical/boolean fields × 29 = 319):** **`293 / 319` (`91.8%`)**

| Field | Matches (`N=29`) | Accuracy | Mismatches |
|---|---|---|---|
| `alternative_used` | `29 / 29` | **100.0%** | — |
| `discovery_channel` | `29 / 29` | **100.0%** | — |
| `household_type` | `29 / 29` | **100.0%** | — |
| `experience_type` | `28 / 29` | **96.6%** | `14793598` (`negative` vs `unclear`) |
| `need_trigger` | `28 / 29` | **96.6%** | `14816200` (`breakdown` vs `null`) |
| `recall_gap` | `28 / 29` | **96.6%** | `14792849` (`false` vs `null`) |
| `rebook_signal` | `27 / 29` | **93.1%** | `bb81193d` (`unclear` vs `rebooked`), `14811553` (`unclear` vs `will_not_rebook`) |
| `category` | `26 / 29` | **89.7%** | `99226311` (`other` vs `deep clean`), `372c9648` (`other` vs `unknown`), `14784151` (`AC` vs `unknown`) |
| `post_service_expectation` | `26 / 29` | **89.7%** | `4e4e2ef9`, `1876c25b`, `372c9648` |
| `confidence` | `22 / 29` | **75.9%** | 7 calibration differences |
| `nothing_went_wrong` | `21 / 29` | **72.4%** | 6 positive reviews (`true` vs `null`), 2 (`false` vs `null`) |

---

## 3. `rebook_signal` Confusion Matrix (`N = 29`)

| Predicted \ Golden | `rebooked` | `unclear` | `will_not_rebook` |
|---|---|---|---|
| **`rebooked`** | **4** | 0 | 0 |
| **`unclear`** | 1 (`bb81193d`) | **23** | 1 (`14811553`) |
| **`will_not_rebook`** | 0 | 0 | **0** |

Gemini is conservative on `rebook_signal` (`93.1%` accuracy): zero false-positive `rebooked` or `will_not_rebook` predictions.

---

## 4. Confidence Calibration

Accuracy of **all 3 core fields matching simultaneously** (`category` + `experience_type` + `rebook_signal`) by predicted `confidence`:

| Predicted Confidence | Exact 3-Field Match | Accuracy |
|---|---|---|
| `high` | `14 / 17` | **82.4%** |
| `medium` | `2 / 3` | **66.7%** |
| `low` | `7 / 9` | **77.8%** |

---

## 5. Comparison: Gemini `v3_2` vs. Groq `v3_2`

> [!NOTE]
> **Methodology & Sample-Size Caveat:** Groq `v3_2` was benchmarked on a **10-record** Play Store subset (`docs/groq_v3_2_benchmark_report.md`), whereas Gemini `v3_2` was evaluated on **29/30** full golden records (including long multi-paragraph App Store reviews). Direct percentages are not apples-to-apples across `N=10` vs `N=29`.

| Metric | Gemini `v3_2` (`N=29/30`) | Groq `v3_2` (`N=10` subset) |
|---|---|---|
| `category` accuracy | `89.7%` (`26/29`) | `100.0%` (`10/10`) |
| `experience_type` accuracy | `96.6%` (`28/29`) | `100.0%` (`10/10`) |
| `rebook_signal` accuracy | `93.1%` (`27/29`) | `90.0%` (`9/10`) |
| `alternative_used` / `discovery_channel` / `household_type` | `100.0%` (`29/29`) | `100.0%` (`10/10`) |
| Rate-limit (`429`) errors | **0** | **0** (at 25s delay; hit TPD in 1,044-batch) |
| Transient `503` retries | `17` (`1` failed) | `0` (`3` initial `400` at 1k cap) |

---

## 6. Conclusion

Gemini (`gemini-3.5-flash-lite`) achieves **91.8% overall field-level agreement** (`96.6%` `experience_type`, `93.1%` `rebook_signal`, `89.7%` `category`) across the full golden set with **zero `429` rate-limit errors**, making it suitable for completing the remaining `939` untagged core consumer reviews with a single retry pass for any `~3–5%` transient `503` failures.
