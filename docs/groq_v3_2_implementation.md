# Groq Token-Efficiency Optimization (v3.2) Implementation Report

**Document Version**: 1.0  
**Date**: 2026-11-25  
**Target Component**: AI Tagging Pipeline v3.2 (`engine/prompts/tagger_v3_2.md`, `engine/tagger.py`, `tests/test_groq_v3_2.py`)  
**Status**: Implemented, Fully Tested, Ready for Verification  

---

## 1. Executive Summary

Following the empirical token-efficiency audit documented in `docs/groq_token_efficiency_audit.md`, this implementation establishes an experimental, token-optimized version of the tagging pipeline designated **v3.2**. 

The goal of v3.2 is to dramatically reduce prompt and reasoning token overhead for the Groq provider (`openai/gpt-oss-120b`) without altering, weakening, or omitting a single classification rule, schema constraint, privacy directive, or review queue routing trigger.

### Key Deliverables Implemented
1. **Consolidated Prompt (`engine/prompts/tagger_v3_2.md`)**:
   - Stripped cross-section triple redundancy and eliminated the 1,000-character mock JSON template block.
   - Reduced prompt size from **11,858 characters (202 lines, 1,603 words)** to **8,871 characters (140 lines, 1,192 words)**—a 25.2% character reduction (~750 estimated tokens saved per request).
   - Preserved 100% of calibration policies from Decisions 007, 008, 010, and 011.
2. **Explicit Version Selection (`--version v3_2`)**:
   - Added `v3_2` as an explicitly selectable version across `GroqLLMClient`, `GeminiLLMClient`, `MockLLMClient`, and the CLI.
   - Default outputs route cleanly to `data/tagged/tagged_reviews_v3_2.jsonl` and `data/tagged/review_queue_v3_2.jsonl`.
   - Existing Gemini and mock provider defaults remain strictly unchanged.
3. **Completion Token Bounding (`max_completion_tokens`)**:
   - Added `max_completion_tokens: Optional[int] = 1000` to `GroqLLMClient`, configurable via CLI (`--max-completion-tokens`).
   - Bounds unbounded reasoning generation while preserving >5x headroom for the ~160-token output JSON.
4. **Enhanced Retry Pacing and Quota Window Protection**:
   - Adjusted `GroqLLMClient` defaults to `initial_backoff=3.0s` and `max_backoff=35.0s`.
   - Enhanced header parsing to respect `retry-after`, `x-ratelimit-reset-requests`, and `x-ratelimit-reset-tokens` without premature truncation below header-specified reset durations, preventing retries before the rolling 60-second quota window replenishes.
5. **Comprehensive Testing and Verification**:
   - Added 25 unit and regression tests in `tests/test_groq_v3_2.py`.
   - Full test suite passed: **181 tests passed, 0 failures, 0 errors**.
   - Verified that all six baseline dataset SHA-256 checksums remain strictly unchanged.
   - Preserved `tagger_v3_1.md` and all prior evaluation outputs untouched.
   - **Zero live API calls** were executed.

---

## 2. Prompt Consolidation (`engine/prompts/tagger_v3_2.md`)

### Structural Refactoring
In `tagger_v3_1.md`, instructions were fragmented across three competing sections:
1. Section 1 ("Core Directives"): Defined grounding, low-information handling, and general negative constraints.
2. Section 2 ("16-Field Tagging Schema"): Defined enum values and reiterated rules for categories, rebook signals, and post-service expectations.
3. Section 3 ("Output Schema"): Re-defined the schema keys and included a 1,000-character synthetic JSON example demonstrating dummy classifications.

In `tagger_v3_2.md`, these were unified into a streamlined 3-part structure:
1. **Section 1: Global Operating Directives**: Grounding, verbatim quotes, non-inference of demographics/channels, low-info review triggers (<20 chars or generic praise), and JSON-only return.
2. **Section 2: 16-Field Authoritative Schema & Calibration Policies**: Single authoritative field-by-field specification defining enums, nullability, and disambiguation rules.
3. **Section 3: Required JSON Structure**: Clean, compact JSON contract template.

### Comparative Footprint
| Metric | `tagger_v3_1.md` | `tagger_v3_2.md` | Reduction | % Reduction |
| :--- | :---: | :---: | :---: | :---: |
| **Total Lines** | 202 lines | 140 lines | -62 lines | -30.7% |
| **Total Words** | 1,603 words | 1,192 words | -411 words | -25.6% |
| **Total Characters** | 11,858 characters | 8,871 characters | -2,987 characters | -25.2% |
| **Estimated Prompt Tokens** | ~3,285 tokens | ~2,535 tokens | ~750 tokens | ~22.8% |

> [!NOTE]
> Per project directives, token savings are reported as conservative estimates based on character/word ratios. Exact token counts will be empirically measured during live pilot execution.

### Policy Preservation Audit Matrix
Every single policy and schema rule from previous project decisions was meticulously preserved:

| Policy / Rule | Source Decision | Preserved in `tagger_v3_2.md` | Verification Reference |
| :--- | :--- | :---: | :--- |
| **Spa & Wellness $\to$ `other`** | Decision 008, 011 | Yes | Section 2, Field 4 (`category: "other"`) |
| **Appliance Cleaning/Repair $\to$ `other`** | Decision 007, 010 | Yes | Section 2, Field 4 (Chimney, RO, Fridge, Washing Machine) |
| **Premises Cleaning $\to$ `deep clean`** | Decision 007, 010 | Yes | Section 2, Field 4 (Home, bathroom, kitchen, sofa) |
| **Explicit Future Intent $\to$ `rebooked`** | Decision 011 | Yes | Section 2, Field 7 (`rebook_signal: "rebooked"`) |
| **Historical Tenure Alone $\to$ `unclear`** | Decision 008, 011 | Yes | Section 2, Field 7 (`rebook_signal: "unclear"`) |
| **General Praise Alone $\to$ `unclear`** | Decision 011 | Yes | Section 2, Field 7 (`rebook_signal: "unclear"`) |
| **Negative Triggers $\to$ `unclear` (Never Churn)**| Decision 010, 011 | Yes | Section 2, Field 7 (Explicit negative trigger list) |
| **Explicit Refusal $\to$ `will_not_rebook`** | Decision 010, 011 | Yes | Section 2, Field 7 ("never book again", "uninstalled") |
| **Warranty Grievances $\neq$ `warranty clarity`** | Decision 008 | Yes | Section 2, Field 11 (`post_service_expectation`) |
| **Customer Advice $\neq$ `next-service advice`** | Decision 008 | Yes | Section 2, Field 11 (`post_service_expectation`) |
| **Unmet Need Nullable (`str \| null`)** | Decision 007 | Yes | Section 2, Field 14 (`unmet_need: string \| null`) |
| **Exact 16 Fields Enforced** | Decision 007 | Yes | Section 2 & Section 3 |
| **Low-Info Reviews $\to$ Review Queue** | Decision 008 | Yes | Section 1, Directive 4 |
| **Verbatim Evidence Grounding** | Decision 007, 008 | Yes | Section 1, Directive 2 & Section 2, Field 15 |

---

## 3. Pipeline Updates (`engine/tagger.py`)

### 1. Versioning and Output Path Defaults
Added path constants and pipeline resolution for `v3_2`:
```python
DEFAULT_TAGGED_OUTPUT_V3_2 = Path("data/tagged/tagged_reviews_v3_2.jsonl")
DEFAULT_QUEUE_OUTPUT_V3_2 = Path("data/tagged/review_queue_v3_2.jsonl")
DEFAULT_PROMPT_PATH_V3_2 = Path("engine/prompts/tagger_v3_2.md")
```
When `--version v3_2` is specified:
- `DEFAULT_PROMPT_PATH_V3_2` is loaded by `GroqLLMClient`, `GeminiLLMClient`, and `MockLLMClient`.
- Output paths default to `tagged_reviews_v3_2.jsonl` and `review_queue_v3_2.jsonl`.
- Tagged review record metadata records `"prompt_version": "tagger_v3_2"`.

### 2. Provider Defaults Preserved
- `mock` remains the default provider.
- `gemini-3.5-flash-lite` remains the default Gemini model.
- `openai/gpt-oss-120b` remains the default Groq model.
- `v2` remains the default version for legacy commands.
- `tagger_v3_1.md` and all previous outputs are preserved unchanged.

### 3. Groq Completion Token Bounding
Added `max_completion_tokens` parameter:
```python
class GroqLLMClient(BaseLLMClient):
    def __init__(
        self,
        ...,
        max_completion_tokens: Optional[int] = 1000,
        ...
    ):
        self.max_completion_tokens = max_completion_tokens
```
During chat completion calls, `max_completion_tokens` is passed directly to `chat.completions.create(**create_kwargs)`. CLI option `--max-completion-tokens` allows runtime configuration (e.g. `--max-completion-tokens 800`).

### 4. Calibrated Retry Pacing and Quota Window Protection
To resolve the HTTP 429 rate limit issues identified during the 10-review Groq pilot:
- **Default Backoff**: `initial_backoff` increased to `3.0s`, `max_backoff` increased to `35.0s`.
- **Header Respect**: Parses `retry-after`, `x-ratelimit-reset-requests`, and `x-ratelimit-reset-tokens`.
- **Window Preservation**:
  ```python
  jitter = random.uniform(0.1, 0.4)
  if retry_after_val is not None and retry_after_val > 0:
      base_wait = max(retry_after_val, backoff)
      effective_max = max(self.max_backoff, retry_after_val + 1.0)
      sleep_duration = min(base_wait + jitter, effective_max)
  else:
      sleep_duration = min(backoff + jitter, self.max_backoff)
  ```
  This ensures that when Groq sends a reset header of e.g. 24.5 seconds, the client waits at least 24.5s (rather than truncating to a 10s ceiling), avoiding premature retries before quota replenishes.
- **Request Pacing**: Request delay remains configurable via `--delay` (e.g., `--delay 5.0`).

---

## 4. Test Suite and Regression Verification

A dedicated test suite was created in `tests/test_groq_v3_2.py` containing 25 unit and regression tests across four test classes:

### Test Classes Implemented
1. `TestGroqV32PromptAndVersionSelection`:
   - Verifies `tagger_v3_2.md` file existence, contents, and structure.
   - Verifies `tagger_v3_1.md` remains unmodified.
   - Verifies prompt loading in `GroqLLMClient` and `GeminiLLMClient`.
   - Verifies metadata generation (`prompt_version: "tagger_v3_2"`).
   - Verifies CLI argument parsing for `--version v3_2` and output path resolution.
2. `TestGroqCompletionLimits`:
   - Verifies default `max_completion_tokens=1000`.
   - Verifies custom parameter initialization.
   - Verifies inclusion in `chat.completions.create` keyword arguments.
   - Verifies clean omission when set to `None`.
   - Verifies CLI parsing for `--max-completion-tokens`.
3. `TestGroqRetryPacingAndQuotaWindow`:
   - Verifies default backoff settings (`initial_backoff=3.0`, `max_backoff=35.0`).
   - Verifies `x-ratelimit-reset-tokens` header durations are honored without premature truncation.
   - Verifies `Retry-After` header handling.
   - Verifies exponential backoff progression without headers.
   - Verifies configurable request delay (`request_delay`) is honored.
4. `TestGroqV32PolicyRegressions`:
   - Spa & wellness sessions map to `other`, not `salon` (Decision 008).
   - Chimney deep clean and RO water purifier repair map to `other`, not `deep clean` or `plumber` (Decision 007).
   - Explicit future booking intent maps to `rebooked` (Decision 011).
   - Historical repeat usage with complaint/cancellation maps to `unclear` (Decision 008, 011).
   - General praise alone maps to `unclear` (Decision 011).
   - Complaints and cancellations alone never establish `will_not_rebook` (Decision 010).
   - Explicit refusal maps to `will_not_rebook` (Decision 010).
   - Warranty complaints do not imply `warranty clarity` (Decision 008).
   - Low-information reviews are routed to the review queue (Decision 008).

### Test Suite Execution Result
```
.venv/bin/python -m unittest discover tests
Ran 181 tests in 0.316s
OK (All 181 tests passed, 0 failures, 0 errors)
```

---

## 5. Baseline Dataset Integrity Verification

All six baseline datasets were verified using SHA-256 cryptographic checksums immediately following implementation and test execution:

| Dataset Path | Expected SHA-256 Checksum | Verified Current SHA-256 Checksum | Status |
| :--- | :---: | :---: | :---: |
| `data/raw/google_play_reviews.jsonl` | `3fd7f281006826bdcdf82c8c279b7c6819365c868025fa965c18573cf9035301` | `3fd7f281006826bdcdf82c8c279b7c6819365c868025fa965c18573cf9035301` | **Unchanged** |
| `data/raw/app_store_reviews.jsonl` | `c6e07f5ffbd77573da20f651983d0395da8ced5e57fa1616319d1b578bd2666d` | `c6e07f5ffbd77573da20f651983d0395da8ced5e57fa1616319d1b578bd2666d` | **Unchanged** |
| `data/processed/normalized_reviews.jsonl` | `673c832ceb42527654e605d2ce7e124d6b895dd38b4cd3d7a80bc1672d0c0cb1` | `673c832ceb42527654e605d2ce7e124d6b895dd38b4cd3d7a80bc1672d0c0cb1` | **Unchanged** |
| `data/tagged/tagged_reviews.jsonl` | `81d556ac5c41dd3e04ca089bd5b5b713d673ab0f0784ecaf6dee75c9324130ea` | `81d556ac5c41dd3e04ca089bd5b5b713d673ab0f0784ecaf6dee75c9324130ea` | **Unchanged** |
| `data/tagged/review_queue.jsonl` | `bfd3c5c5be8ed33d5c1058b35b8832b4d750dc6a6aa2d5917645dbb71df96b3a` | `bfd3c5c5be8ed33d5c1058b35b8832b4d750dc6a6aa2d5917645dbb71df96b3a` | **Unchanged** |
| `data/golden/golden_set.jsonl` | `ba4535c28e6643df31990556d70bfd0a6c36d47894930f164f7215eeea3aff0c` | `ba4535c28e6643df31990556d70bfd0a6c36d47894930f164f7215eeea3aff0c` | **Unchanged** |

---

## 6. Next Steps & Recommended Usage

1. **Experimental Testing Only**:
   Version `v3_2` is ready for controlled live pilot testing against benchmark samples.
2. **Safe Execution Command**:
   When authorized to run a live test with Groq v3.2:
   ```bash
   python -m engine.tagger \
     --provider groq \
     --version v3_2 \
     --input data/tagged/golden_v3_evaluation/golden_v3_input.jsonl \
     --delay 5.0 \
     --max-completion-tokens 1000 \
     --tagged-output data/tagged/groq_pilot_v3_2/tagged.jsonl \
     --queue-output data/tagged/groq_pilot_v3_2/queue.jsonl \
     --metrics-output data/tagged/groq_pilot_v3_2/metrics.json
   ```
3. **No Speculative Token Claims**:
   Actual per-review token savings and throughput improvements will be measured directly from `metrics.json` after live execution.
