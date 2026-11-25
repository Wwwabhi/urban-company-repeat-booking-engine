# Groq Token Efficiency Audit: Tagging Pipeline v3.1

**Date**: 2026-11-25  
**Model Audited**: `openai/gpt-oss-120b` (Groq API)  
**Prompt Audited**: `engine/prompts/tagger_v3_1.md`  
**Execution Context**: 10-review live Groq pilot (`data/tagged/groq_pilot/`)

---

## 1. Executive Summary

This audit investigates per-review token consumption for the Groq review-tagging pipeline to identify optimization opportunities that reduce rate-limit saturation and token overhead while strictly preserving qualitative classification accuracy, privacy controls, evidence grounding, and review-queue routing.

### Key Empirical Findings
1. **Massive Prompt Overhead (75.0% of request)**: The input prompt consumes an average of **3,054 tokens per review**, of which **~2,964 tokens (97.1%)** represent static system instructions and only **~90 tokens (2.9%)** represent the actual customer review payload.
2. **Three-Tier Redundancy in `tagger_v3_1.md`**: Schema enumerations and policy rules are duplicated across three separate sections:
   - *Core Directives & Hard Policy Rules* (lines 7–66; 6,143 chars, ~1,536 tokens)
   - *16-Field Tagging Schema* (lines 69–167; 3,556 chars, ~889 tokens)
   - *Output JSON Structure* (lines 170–201; 994 chars, ~248 tokens)
3. **Reasoning Token Dominance (80–85% of completion)**: For each review, the model emits an average of **1,016 completion tokens**, yet the final structured JSON artifact requires only **~130–190 tokens**. The model consumes **~800–1,050 hidden reasoning tokens** per call.
4. **TPM Bucket Saturation & Rate-Limiting**: Because total tokens per review average **4,070 tokens**, two consecutive requests consume over **8,100 tokens**, immediately exhausting Groq's Tokens-Per-Minute (TPM) allocation on tier-1 accounts and triggering `HTTP 429 RateLimitError` (which caused 17 rate-limit retries and 4 exhausted failures during the 10-review pilot).
5. **Projected Savings**: Consolidating prompt redundancies and streamlining request formatting can reduce prompt consumption by **~1,450 tokens/review (~47.5% reduction in prompt tokens)**, decreasing total token usage per call from **4,070 to ~2,600 tokens (~36.1% overall reduction)** without altering any classification logic.

---

## 2. Baseline Token Footprint & Pilot Metrics

Data extracted from the 10-review live pilot ([groq_pilot_metrics.json](file:///Users/abhimanyusingh/Developer/Urban%20Company%20Repeat-Booking%20Project%20Build%20Brief/data/tagged/groq_pilot/groq_pilot_metrics.json)):

### Quantitative Summary (Successful Reviews)

| Review ID | Prompt Tokens | Completion Tokens | Total Tokens | Latency | Actual JSON Size | Estimated Reasoning Tokens |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `bb81193d` | 3,035 | 1,006 | 4,041 | 2.96s | ~180 tokens | ~826 tokens (82.1%) |
| `99226311` | 3,039 | 1,226 | 4,265 | 3.46s | ~188 tokens | ~1,038 tokens (84.7%) |
| `36b24dd5` | 3,111 | 1,072 | 4,183 | 2.80s | ~134 tokens | ~938 tokens (87.5%) |
| `43582ef1` | 3,038 | 979 | 4,017 | 2.35s | ~118 tokens | ~861 tokens (87.9%) |
| `bec86ea9` | 3,035 | 734 | 3,769 | 2.18s | ~188 tokens | ~546 tokens (74.4%) |
| `06b45346` | 3,066 | 1,081 | 4,147 | 3.03s | ~140 tokens | ~941 tokens (87.0%) |
| **Average** | **3,054.0** | **1,016.3** | **4,070.3** | **2.80s** | **~158 tokens** | **~858.3 tokens (84.5%)** |

### Breakdown by Token Category
```
Total Tokens per Request (Avg: 4,070.3 tokens)
├── Prompt Tokens: 3,054.0 tokens (75.0%)
│   ├── System Instructions (tagger_v3_1.md): ~2,964 tokens (72.8%)
│   └── Review Payload + User Prompt Wrapper: ~90 tokens (2.2%)
└── Completion Tokens: 1,016.3 tokens (25.0%)
    ├── Hidden Reasoning Tokens (Chain-of-Thought): ~858 tokens (21.1%)
    └── Emitted 16-Field JSON Output: ~158 tokens (3.9%)
```

---

## 3. In-Depth Audit Findings

### Finding 1: Triple Redundancy across System Prompt Sections
In `tagger_v3_1.md` (202 lines, 1,603 words, 11,858 characters), the same schema fields, enum options, and behavioral constraints are stated up to three times:

1. **Category Definition**:
   - *Section 2 (Lines 46–52)*: Explains appliance vs. premises cleaning, chimney deep clean mapping to `other`, and spa sessions mapping to `other` (670 chars).
   - *Section 3 (Lines 80–89)*: Repeats the 8 categories, and re-explains chimney deep clean, appliance repairs, spa sessions, and premises cleaning (981 chars).
   - *Section 4 (Lines 178, 193)*: Repeats category in mock output.
   - *Redundancy*: 981 chars are spent restating rules already established in Section 2.
2. **Rebook Signal Policy**:
   - *Section 2 (Lines 23–45)*: Comprehensive policy on `rebooked`, `will_not_rebook`, `unclear`, and past vs. future intent (1,500 chars).
   - *Section 3 (Lines 102–106)*: Repeats summaries of `rebooked`, `did_not_rebook`, `will_not_rebook`, and `unclear` (600 chars).
   - *Redundancy*: 600 chars of duplicated descriptions.
3. **Post-Service Expectation**:
   - *Section 2 (Lines 18–22)*: Detailed directives on `unclear`, `nothing`, warranty complaints, and advice context (553 chars).
   - *Section 3 (Lines 132–139)*: Re-lists the 6 enums and re-states the exact same inline rules (428 chars).
   - *Redundancy*: ~400 chars.
4. **Demographic / Channel Inferencing Constraints**:
   - *Section 2 (Lines 10–14)*: Directives forbidding inference of `city`, `household_type`, `discovery_channel`, and `need_trigger` (501 chars).
   - *Section 3 (Lines 77–79, 108–115, 140–146, 148–156)*: Separate entries for each field repeating the exact non-inference constraints and lists of enums (569 chars).
5. **Tri-State Logic (`nothing_went_wrong`, `recall_gap`)**:
   - *Section 2 (Lines 56–59)*: Explains tri-state rules (370 chars).
   - *Section 3 (Lines 97–100, 117–120)*: Repeats `true`/`false`/`null` definitions (385 chars).

### Finding 2: Verbose Formatting Instructions vs. Constrained Decoding
- The prompt includes a 994-character mock JSON template (`Output JSON Structure`, lines 170–201) along with formatting reminders:
  - `"Return ONLY a single valid JSON object adhering strictly to the schema."`
  - Inline reminders repeated in both system prompt and `engine/tagger.py` user prompt.
- Modern Groq SDK supports OpenAI-compatible **Structured Outputs (`response_format={"type": "json_schema", ...}`)**.
- In the current pipeline, `response_format={"type": "json_object"}` is used. While this guarantees JSON syntax, it does not constrain keys at the grammar level, forcing the prompt to provide excessive structural examples to prevent schema divergence.

### Finding 3: Unbounded Completion Token Limit
- In `engine/tagger.py`, `GroqLLMClient._call_model_with_retries()` does not pass `max_tokens` or `max_completion_tokens`.
- Default model behavior allows up to 4,096+ tokens.
- While the intended output is under 200 tokens, the unconstrained ceiling allows the model to expand its reasoning chain up to 1,226 tokens, accelerating TPM depletion.

### Finding 4: Reasoning Token Quota Depletion
- `openai/gpt-oss-120b` is an open-weights reasoning model that performs chain-of-thought processing before emitting final JSON.
- Groq counts these reasoning tokens against both per-minute rate limits (TPM) and billed/quota limits.
- On standard Groq tiers, the TPM ceiling is typically 6,000–15,000 TPM. A single call consuming 4,265 tokens exhausts between 30% and 70% of the account's total per-minute bandwidth.

---

## 4. Prompt & Request Optimization Plan

### Strategy Overview
Optimize token usage across three distinct dimensions without weakening any classification rule, removing fields, or touching v3.1 files:

```
┌────────────────────────────────────────────────────────────────────────┐
│                      OPTIMIZATION ARCHITECTURE                         │
├──────────────────────────┬───────────────────────┬─────────────────────┤
│ 1. Unified Prompt Spec   │ 2. Request Parameters │ 3. Rate Pacing      │
│ (v3_2 Streamlined)       │ & Structured Outputs  │ & Backoff Tuning    │
├──────────────────────────┼───────────────────────┼─────────────────────┤
│ - Unify Directives +     │ - Set max_completion_ │ - Increase delay    │
│   Schema into 1 section  │   tokens = 800        │   from 1.0s to 5.0s │
│ - Strip triple redundancy│ - Compact user prompt │ - Expand max_backoff│
│ - Eliminate 1,000-char   │   payload formatting  │   from 10s to 35s   │
│   mock JSON template     │ - Evaluate json_schema│   (safe 60s reset)  │
│ - Retain 100% of rules   │   constrained decoding│                     │
└──────────────────────────┴───────────────────────┴─────────────────────┘
```

### Component A: Unified Schema Specification (`tagger_v3_2.md` Candidate)
Instead of two competing sections ("Core Directives" and "16-Field Tagging Schema"), establish a single authoritative, field-by-field specification. Each field header defines:
- Exact enum values.
- Explicit non-inference / nullability requirements.
- Critical disambiguation rules (e.g. Under `category: "other"`, explicitly note: *Appliance cleaning (chimney, RO, fridge), appliance repair, and spa/massage belong to "other"*).
- The explicit future intent vs. historical repeat rule under `rebook_signal`.

**Impact**: Reduces prompt characters from **11,858 to ~5,800 characters (~1,450 tokens saved)**.

### Component B: Request Payload Compaction in Client
In `engine/tagger.py`, the user prompt currently sends:
```json
{
  "review_id": "99226311-a2f2-4ecf-b1ed-7d28518cd95e",
  "source": "Play Store",
  "date": "2026-11-21",
  "rating": 5,
  "title": null,
  "text": "..."
}
```
Along with a 180-character instruction string:
`"Analyze and tag the following customer review according to the 16-field schema and strict policy rules provided in the system instructions. Return ONLY a single valid JSON object adhering strictly to the schema."`

**Optimization**:
- Condense the wrapper text to: `"Tag review per schema:\n"`
- Strip `null` title and redundant keys when empty.
- **Impact**: Saves ~35 tokens per request.

### Component C: Completion Token Bounding
- Set `max_completion_tokens=800` (or `max_tokens=800`) in `chat.completions.create()`.
- **Headroom verification**: The maximum observed completion across the pilot was 1,226 tokens (with ~1,040 reasoning tokens). An 800-token cap encourages concise reasoning while providing 4x the headroom required for the 160-token JSON output.
- For high-complexity reviews requiring extensive reasoning, 900–1,000 tokens provides a conservative safety buffer.

### Component D: Rate-Pacing Calibration for Groq
- The pilot used `--delay 1.0` and `--max-backoff 10.0`.
- Because Groq rate limits reset over rolling 60-second windows, two calls at 4,000 tokens deplete the bucket.
- **Adjustment**:
  - Set default Groq request delay to `5.0s`.
  - Set `initial_backoff=5.0`, `max_backoff=35.0`, `backoff_multiplier=2.0`.
  - This ensures that if a 429 occurs, attempt 2 waits ~10s and attempt 3 waits ~25s, spanning past the 60-second rolling token bucket reset.

---

## 5. Quantitative Token Savings Projection

| Metric | Current v3.1 Baseline | Optimized Projection | Net Savings per Unit | % Reduction |
| :--- | :---: | :---: | :---: | :---: |
| **System Prompt Tokens** | 2,964 tokens | ~1,500 tokens | -1,464 tokens | -49.4% |
| **User Prompt / Payload Tokens** | 90 tokens | ~55 tokens | -35 tokens | -38.8% |
| **Total Prompt Tokens per Request** | **3,054 tokens** | **~1,555 tokens** | **-1,499 tokens** | **-49.1%** |
| **Completion Tokens (Reasoning + JSON)** | 1,016 tokens | ~900 tokens (capped) | -116 tokens | -11.4% |
| **Total Tokens Consumed per Review** | **4,070 tokens** | **~2,455 tokens** | **-1,615 tokens** | **-39.7%** |
| **10-Review Pilot Consumption** | 40,700 tokens | ~24,550 tokens | -16,150 tokens | -39.7% |
| **Full 154-Review Batch Consumption** | 626,780 tokens | ~378,070 tokens | **-248,710 tokens** | **-39.7%** |

### Projected Impact on Rate-Limiting & Throughput
- **Current throughput**: Saturation after 2 consecutive calls (~8,140 tokens).
- **Optimized throughput**: Up to 4 consecutive calls (~9,800 tokens) before saturation on a 10,000 TPM limit.
- **Batch stability**: Slashes 429 frequency by an estimated **60–75%**, reducing total retry delays and batch runtime.

---

## 6. Risk Assessment & Safety Controls

| Potential Risk | Severity | Mechanism / Impact | Mitigation Strategy |
| :--- | :---: | :--- | :--- |
| **Loss of Subtle Disambiguation** | **HIGH** | Over-condensing prompt rules could cause regression on nuanced policies (e.g. appliance cleaning $\to$ `other`, spa $\to$ `other`, future intent vs. historical repeat). | **Zero Rule Removal Policy**: Consolidate format and strip prose fluff, but preserve every positive/negative example, keyword trigger, and enum definition intact. Run full 30-record golden benchmark before deploying. |
| **Reasoning Truncation / Malformed JSON** | **HIGH** | Setting `max_completion_tokens` too low (e.g. 300) when model spends 350 tokens on reasoning would cut off JSON mid-stream, triggering `JSONDecodeError`. | **Generous Safety Ceiling**: Set cap at 900–1,000 tokens (5x the size of the required JSON payload). Never cap below 800 tokens for reasoning models. |
| **Grammar Schema Incompatibility** | **MEDIUM** | If switching to strict `json_schema` mode, complex nullable or union types (`string \| null`, `boolean \| null`) might be rejected by the API engine. | Retain existing `response_format={"type": "json_object"}` as the primary mode; benchmark `json_schema` in isolated tests before adopting in production. |
| **Degraded Evidence Grounding** | **LOW** | If prompt shortening makes grounding instructions less prominent, the model might paraphrase quotes. | Retain explicit verbatim grounding rule and `evidence_quote` instruction as a non-negotiable directive. |

---

## 7. Next Steps & Recommended Path

1. **Keep v3.1 Untouched**: Maintain [tagger_v3_1.md](file:///Users/abhimanyusingh/Developer/Urban%20Company%20Repeat-Booking%20Project%20Build%20Brief/engine/prompts/tagger_v3_1.md) as the frozen baseline.
2. **Draft `tagger_v3_2.md` Candidate**: Author a consolidated, non-redundant prompt preserving 100% of the calibration rules from Decisions 007 and 008.
3. **Benchmark in Sandbox**: Execute a controlled 10-record comparison of candidate `v3_2` against `v3_1` using the exact same golden inputs to verify identical categorical agreement (aiming for $\ge 97.9\%$) while validating a ~40% token reduction.
4. **Calibrate Client Defaults**: Update `GroqLLMClient` with bounded completion tokens (`max_completion_tokens=1000`) and tuned backoff parameters (`max_backoff=35.0s`, `delay=5.0s`).
