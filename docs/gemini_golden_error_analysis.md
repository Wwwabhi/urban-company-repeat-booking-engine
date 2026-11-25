# Gemini v3.2 Golden-Set Error Analysis

**Date:** 2026-11-25  
**Model:** `gemini-3.5-flash-lite` (`tagger_v3_2.md`)  
**Evaluated:** `29 / 30` golden records (`data/tagged/golden_v3_2_gemini/tagged_golden_gemini_v3_2.jsonl` vs `data/golden/golden_set.jsonl`)  
**Total Mismatches:** `26` field-level disagreements across `319` evaluated field-record pairs (`91.8%` agreement) + `1` evidence-grounding failure.

---

## 1. Summary by Disagreement Classification

| Classification | Count | Fields Affected |
|---|---|---|
| **Model error** | `8` | `category` (3), `post_service_expectation` (2), `rebook_signal` (1), `experience_type` (1), `nothing_went_wrong` (1) |
| **Ambiguous annotation guideline** | `17` | `nothing_went_wrong` (7), `confidence` (7), `post_service_expectation` (1), `rebook_signal` (1), `recall_gap` (1) |
| **Potential golden-set annotation error** | `1` | `need_trigger` (`14816200`) |
| **Insufficient evidence** | `0` | — |

---

## 2. Priority Field-by-Field Analysis

### 2.1 `nothing_went_wrong` (8 mismatches — `72.4%` accuracy)

| Review ID | Pred | Gold | Classification | Explanation |
|---|---|---|---|---|
| `bb81193d`, `99226311`, `14815231`, `14805610`, `14809078`, `14792849` (6 positive reviews) | `true` | `null` | **Ambiguous annotation guideline** | `docs/schema.md` defines `true` as *"no operational failure occurred, yet the customer still mentions not rebooking..."*, while human annotators use `null` for unambiguous positive reviews. Gemini interpreted "no failure occurred" literally as `true`. |
| `14812347` (`"Surge Charge. Very expensive."`) | `false` | `null` | **Ambiguous annotation guideline** | Pricing complaint without an explicit service-delivery failure; human annotator left `null`, Gemini treated price friction as `false`. |
| `14793598` (`"Pedicure. Therapist not reported"`) | `false` | `null` | **Model error** | Terse statement; Gemini inferred a failed appointment despite explicit non-inference rules. |

### 2.2 `confidence` (7 mismatches — `75.9%` accuracy)

| Review IDs | Pred vs Gold | Classification | Explanation |
|---|---|---|---|
| `bb81193d`, `75c91a8d`, `b04a772a` | `low` vs `medium` | **Ambiguous annotation guideline** | Gemini assigned `low` when `category` was `unknown` or rating conflicted with text; human annotator assigned `medium`. |
| `bec86ea9`, `14787997` | `medium` vs `high` | **Ambiguous annotation guideline** | Minor 1-tier calibration difference on clear negative/neutral reviews. |
| `14811553` | `medium` vs `high` | **Ambiguous annotation guideline** | Gemini missed `will_not_rebook` and rated confidence `medium`. |
| `99226311` | `high` vs `medium` | **Ambiguous annotation guideline** | Clear kitchen-cleaning review; human annotator conservatively rated `medium`. |

### 2.3 `category` (3 mismatches — `89.7%` accuracy)

| Review ID | Pred | Gold | Classification | Explanation |
|---|---|---|---|---|
| `99226311` (`"Very good kitchen cleaning"`) | `other` | `deep clean` | **Model error** | Failed to apply the `kitchen cleaning -> deep clean` rule in `tagger_v3_2.md`. |
| `372c9648` (`"Good for low level cleaning... Do NOT go for expensive painting"`) | `other` | `unknown` | **Model error** | Multi-category comparison should map to `unknown`, not `other`. |
| `14784151` (`"Ac servicing quality wasn't good. Rest all the services are amazing"`) | `AC` | `unknown` | **Model error** | Multi-category review ("used all categories multiple times") should map to `unknown`, not the single negative exception (`AC`). |

### 2.4 `post_service_expectation` (3 mismatches — `89.7%` accuracy)

| Review ID | Pred | Gold | Classification | Explanation |
|---|---|---|---|---|
| `4e4e2ef9` (chimney warranty expired) | `warranty clarity` | `unclear` | **Model error** | Violated rule: *"warranty complaint is not automatically a warranty-clarity expectation."* |
| `372c9648` (`"Pathetic Warranty Service"`) | `warranty clarity` | `unclear` | **Model error** | Same rule violation as `4e4e2ef9`. |
| `1876c25b` (`"didn't tell me how to use it, any guidelines & precautions"`) | `next-service advice` | `unclear` | **Ambiguous annotation guideline** | Missing usage guidelines for a newly serviced RO purifier sits on the boundary of `next-service advice` vs `unclear`. |

### 2.5 `rebook_signal` (2 mismatches — `93.1%` accuracy)

| Review ID | Pred | Gold | Classification | Explanation |
|---|---|---|---|---|
| `bb81193d` (`"The last one was the best"`) | `unclear` | `rebooked` | **Ambiguous annotation guideline** | Golden annotator inferred repeat usage from `"The last one"`; `v3_2` instructs `unclear` unless explicit. |
| `14811553` (`"Pay extra to anyone but not them. Don't trust this brand"`) | `unclear` | `will_not_rebook` | **Model error** | Explicit refusal/brand-avoidance statement should map to `will_not_rebook`. |

### 2.6 Other Fields (3 mismatches)

- `experience_type` (`14793598`: `"Pedicure. Therapist not reported"`): `negative` vs `unclear` — **Model error** (inferred failure from terse text).
- `need_trigger` (`14816200`: `"washing machine repair... because the drum was not rotating"`): `breakdown` vs `null` — **Potential golden-set annotation error** (`"drum was not rotating"` is an explicit appliance breakdown).
- `recall_gap` (`14792849`: `"It is my go-to app for all services"`): `false` vs `null` — **Ambiguous annotation guideline** (habitual use implies no recall gap, but golden defaults to `null`).

---

## 3. Failed Evidence-Grounding Case (1 / 29)

- **Review ID:** `14784151`
- **Gemini `evidence_quote`:** `"We are UC customers since many years now. ... Ac servicing quality wasn’t good."`
- **Root cause:** **Model error** — Gemini stitched two non-contiguous sentences using `" ... "`, breaking the exact verbatim substring check.

---

## 4. Recommended Actions (Only Where Justified)

1. **Do NOT silently alter golden labels.** Optionally review `14816200` (`need_trigger = null` vs `breakdown`) in the next human golden-set audit.
2. **Proceed with the 939-record Gemini `v3_2` batch without changing `tagger_v3_2.md` now:** `category` (`89.7%`), `experience_type` (`96.6%`), and `rebook_signal` (`93.1%`) are strong, and `nothing_went_wrong = true` on positive reviews is a benign schema-interpretation artifact (easily filtered downstream by checking `rebook_signal != "rebooked"` and `experience_type != "positive"`).
3. **If a future `v3_3` prompt is created:** Add one explicit line forbidding `"..."` ellipsis stitching in `evidence_quote` and one example showing `kitchen cleaning -> deep clean`.
