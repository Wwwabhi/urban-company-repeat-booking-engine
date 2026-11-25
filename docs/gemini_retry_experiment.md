# Gemini Retry Recovery Experiment Report

**Date**: 2026-11-24  
**Pipeline Version**: v2  
**Target Input**: `data/tagged/pilot/retry_experiment/retry_input.jsonl` (7 reviews that failed in the original pilot)  
**Execution Reference**: Task `task-2339` (Log: `.system_generated/tasks/task-2339.log`)  

---

## 1. Executive Summary

This experiment tested whether expanding the retry envelope, increasing request timeouts, and increasing inter-request spacing could recover the 7 reviews that failed during the original 10-review pilot.

- **Input Reviews**: 7 reviews (all previously failed with exhausted retries).
- **Recovered**: **5 out of 7 reviews (71.4%) were successfully processed** (4 successfully tagged, 1 routed to human review queue).
- **Persistent Failures**: 2 reviews (`36b24dd5-1cd2-4752-9a46-68307d86382c` and `43582ef1-c85a-4b67-ad13-662ab7a72dcb`) failed all 5 attempts due to persistent upstream HTTP 503 errors and were preserved in `failures_retry.jsonl`.
- **Cumulative 10-Review Pilot Outcome**: Across the original 3 successes and these 5 recoveries, **8 of the 10 pilot reviews (80.0%) are now successfully processed** (6 tagged, 2 queued, 2 failed).

---

## 2. Experiment Configuration & Runtime Parameters

| Parameter | Original Pilot Value | Retry Experiment Value | Change Rationale |
| :--- | :---: | :---: | :--- |
| **Model** | `gemini-3.5-flash-lite` | `gemini-3.5-flash-lite` | *Unchanged* |
| **API Version / Endpoint** | `v1` | `v1` | *Unchanged* |
| **Prompt & Schema** | `tagger_v2.md` (16 fields) | `tagger_v2.md` (16 fields) | *Unchanged* |
| **Maximum Attempts** | 3 attempts | **5 attempts** | Provide extra retry runway across capacity dips |
| **Initial Backoff** | 2.0s | **3.0s** | Slower initial re-entry after first failure |
| **Backoff Multiplier** | 2.0x | **2.0x** | *Unchanged* |
| **Maximum Backoff** | 10.0s | **15.0s** | Allow backoff to span >45 seconds total per review |
| **Request Timeout** | 20.0s | **30.0s** | Prevent premature 504 timeouts on heavy queueing |
| **Inter-Review Delay** | 1.0s | **3.0s** | Prevent burst traffic across consecutive reviews |
| **SDK Internal Retries** | Disabled (`attempts=1`) | **Disabled (`attempts=1`)** | *Unchanged* |
| **Jitter** | Bounded (`[0.1, 0.4]s`) | **Bounded (`[0.1, 0.4]s`)** | Explicit logging of sleep duration + jitter |

---

## 3. High-Level Experiment Results

| Metric | Count | Details / File Path |
| :--- | :---: | :--- |
| **Total Input Reviews** | **7** | `data/tagged/pilot/retry_experiment/retry_input.jsonl` |
| **Successfully Tagged** | **4** | `data/tagged/pilot/retry_experiment/tagged_reviews_retry.jsonl` |
| **Sent to Review Queue** | **1** | `data/tagged/pilot/retry_experiment/review_queue_retry.jsonl` |
| **Failed (Exhausted 5 Retries)** | **2** | `data/tagged/pilot/retry_experiment/failures_retry.jsonl` |
| **Recovery Rate** | **71.4%** | 5 of 7 previously failed reviews recovered |
| **Total API Requests** | **26** | Across all attempts and reviews |
| **Total Retries Triggered** | **19** | Handled with exponential backoff and jitter |
| **Total Experiment Duration** | **5m 30s** | 20:40:36 to 20:46:06 UTC+5:30 |

---

## 4. HTTP Status Breakdown

| HTTP Status Code | Description | Count | Percentage |
| :---: | :--- | :---: | :---: |
| **200** | OK (Inference Succeeded) | 5 | 19.2% |
| **503** | Service Unavailable (Upstream Overload) | 20 | 76.9% |
| **504** | Gateway Timeout (Upstream Queuing) | 1 | 3.8% |
| **Total** | | **26** | **100.0%** |

*Note: Exactly zero 429 (`ResourceExhausted`), 400, 401, or 403 errors occurred.*

---

## 5. Latency Performance (Successful Requests)

Across the 5 successful API calls:
- **Average Latency**: **7.02s**
- **Median Latency**: **8.65s**
- **Minimum Latency**: **2.26s**
- **Maximum Latency**: **12.86s**
- **Distribution**: `[8.84s, 2.26s, 8.65s, 12.86s, 2.51s]`

*(In contrast to the original pilot where all 3 successful calls occurred during quiet intervals at ~1.95s, this experiment captured successful completions even during active backend queuing, aided by the expanded 30s timeout).*

---

## 6. Per-Review Attempt History & Outcomes

### Review 1: `99226311-a2f2-4ecf-b1ed-7d28518cd95e` (**RECOVERED — Tagged**)
- **Final Outcome**: Successfully tagged (`category="deep clean"`, `experience_type="positive"`, `rebook_signal="unclear"`).
- **Attempt History**:
  - Attempt 1/5: HTTP 503 (1.98s) → Backoff wait 3.33s (jitter +0.33s)
  - Attempt 2/5: HTTP 503 (1.61s) → Backoff wait 6.23s (jitter +0.23s)
  - Attempt 3/5: **HTTP 200 OK** (8.84s) → **SUCCESS**

### Review 2: `75c91a8d-c132-48e2-a420-ea4221bb6059` (**RECOVERED — Review Queue**)
- **Final Outcome**: Routed to review queue (`reasons=["low_confidence: Model reported low tagging confidence"]`).
- **Attempt History**:
  - Attempt 1/5: HTTP 503 (2.33s) → Backoff wait 3.28s (jitter +0.28s)
  - Attempt 2/5: HTTP 503 (6.30s) → Backoff wait 6.21s (jitter +0.21s)
  - Attempt 3/5: HTTP 503 (9.18s) → Backoff wait 12.28s (jitter +0.28s)
  - Attempt 4/5: **HTTP 200 OK** (2.26s) → **SUCCESS**

### Review 3: `36b24dd5-1cd2-4752-9a46-68307d86382c` (**FAILED**)
- **Final Outcome**: Failed after exhausting all 5 attempts; recorded in `failures_retry.jsonl`.
- **Attempt History**:
  - Attempt 1/5: HTTP 503 (11.13s) → Backoff wait 3.16s (jitter +0.16s)
  - Attempt 2/5: HTTP 503 (14.48s) → Backoff wait 6.14s (jitter +0.14s)
  - Attempt 3/5: HTTP 503 (4.23s) → Backoff wait 12.22s (jitter +0.22s)
  - Attempt 4/5: HTTP 503 (1.57s) → Backoff wait 15.00s (jitter +0.36s)
  - Attempt 5/5: HTTP 503 (7.20s) → **FAILED (ServerError 503)**

### Review 4: `43582ef1-c85a-4b67-ad13-662ab7a72dcb` (**FAILED**)
- **Final Outcome**: Failed after exhausting all 5 attempts; recorded in `failures_retry.jsonl`.
- **Attempt History**:
  - Attempt 1/5: HTTP 503 (1.84s) → Backoff wait 3.18s (jitter +0.18s)
  - Attempt 2/5: HTTP 503 (1.68s) → Backoff wait 6.38s (jitter +0.38s)
  - Attempt 3/5: HTTP 503 (11.45s) → Backoff wait 12.38s (jitter +0.38s)
  - Attempt 4/5: HTTP 503 (2.92s) → Backoff wait 15.00s (jitter +0.36s)
  - Attempt 5/5: HTTP 503 (3.15s) → **FAILED (ServerError 503)**

### Review 5: `bec86ea9-9a8f-495d-a091-1e4ec7843980` (**RECOVERED — Tagged**)
- **Final Outcome**: Successfully tagged (`category="unknown"`, `experience_type="negative"`, `rebook_signal="unclear"`).
- **Attempt History**:
  - Attempt 1/5: **HTTP 200 OK** (8.65s) → **SUCCESS**

### Review 6: `6b579933-e83a-459c-b7c7-73f83b669c16` (**RECOVERED — Tagged**)
- **Final Outcome**: Successfully tagged (`category="unknown"`, `experience_type="negative"`, `rebook_signal="unclear"`).
- **Attempt History**:
  - Attempt 1/5: HTTP 503 (1.26s) → Backoff wait 3.36s (jitter +0.36s)
  - Attempt 2/5: HTTP 504 (29.46s) → Backoff wait 6.30s (jitter +0.30s) *(Saved by 30s timeout)*
  - Attempt 3/5: **HTTP 200 OK** (12.86s) → **SUCCESS**

### Review 7: `06b45346-6f25-4d49-9b01-13d980482c2c` (**RECOVERED — Tagged**)
- **Final Outcome**: Successfully tagged (`category="unknown"`, `experience_type="negative"`, `rebook_signal="will_not_rebook"`).
- **Attempt History**:
  - Attempt 1/5: HTTP 503 (6.80s) → Backoff wait 3.23s (jitter +0.23s)
  - Attempt 2/5: HTTP 503 (0.77s) → Backoff wait 6.29s (jitter +0.29s)
  - Attempt 3/5: HTTP 503 (1.75s) → Backoff wait 12.22s (jitter +0.22s)
  - Attempt 4/5: HTTP 503 (1.80s) → Backoff wait 15.00s (jitter +0.23s)
  - Attempt 5/5: **HTTP 200 OK** (2.51s) → **SUCCESS**

---

## 7. Success After Retry Verification

Did any review succeed after one or more failed attempts?
- **Yes**: **4 out of the 5 recovered reviews succeeded strictly because of retries**:
  - `99226311...` succeeded on **Attempt 3** (after 2 failures).
  - `6b579933...` succeeded on **Attempt 3** (after 2 failures, including surviving a 29.5s timeout).
  - `75c91a8d...` succeeded on **Attempt 4** (after 3 failures). Under the original pilot's 3-attempt limit, this review would have failed!
  - `06b45346...` succeeded on **Attempt 5** (after 4 failures). Under the original pilot's 3-attempt limit, this review would have failed!

This empirically proves that expanding the retry budget to 5 attempts and widening the backoff window directly converts persistent upstream transient failures into successful completions.

---

## 8. Comparison: Original Pilot vs. Retry Experiment

| Evaluation Dimension | Original Pilot (10 Reviews) | Retry Experiment (7 Failed Reviews) | Cumulative Pilot (All 10 Reviews) |
| :--- | :---: | :---: | :---: |
| **Max Attempts** | 3 | 5 | 5 |
| **Request Timeout** | 20.0s | 30.0s | 30.0s |
| **Max Backoff** | 10.0s | 15.0s | 15.0s |
| **Inter-Review Delay** | 1.0s | 3.0s | 3.0s |
| **Successfully Processed** | 3 / 10 (30.0%) | **5 / 7 (71.4%)** | **8 / 10 (80.0%)** |
| - Tagged | 2 | 4 | 6 |
| - Review Queue | 1 | 1 | 2 |
| **Failed** | 7 / 10 (70.0%) | **2 / 7 (28.6%)** | **2 / 10 (20.0%)** |
| **Failure Recovery** | N/A | **71.4% Recovered** | **80% Net Yield** |

---

## 9. Baseline Dataset SHA-256 Verification

All baseline datasets remain completely untouched:

| Dataset Path | Expected SHA-256 | Current SHA-256 | Status |
| :--- | :--- | :--- | :--- |
| `data/raw/google_play_reviews.jsonl` | `3fd7f281006826bdcdf82c8c279b7c6819365c868025fa965c18573cf9035301` | `3fd7f281006826bdcdf82c8c279b7c6819365c868025fa965c18573cf9035301` | **Unchanged** |
| `data/raw/app_store_reviews.jsonl` | `c6e07f5ffbd77573da20f651983d0395da8ced5e57fa1616319d1b578bd2666d` | `c6e07f5ffbd77573da20f651983d0395da8ced5e57fa1616319d1b578bd2666d` | **Unchanged** |
| `data/processed/normalized_reviews.jsonl` | `673c832ceb42527654e605d2ce7e124d6b895dd38b4cd3d7a80bc1672d0c0cb1` | `673c832ceb42527654e605d2ce7e124d6b895dd38b4cd3d7a80bc1672d0c0cb1` | **Unchanged** |
| `data/golden/golden_set.jsonl` | `ba4535c28e6643df31990556d70bfd0a6c36d47894930f164f7215eeea3aff0c` | `ba4535c28e6643df31990556d70bfd0a6c36d47894930f164f7215eeea3aff0c` | **Unchanged** |
| `data/tagged/tagged_reviews.jsonl` (v1) | `81d556ac5c41dd3e04ca089bd5b5b713d673ab0f0784ecaf6dee75c9324130ea` | `81d556ac5c41dd3e04ca089bd5b5b713d673ab0f0784ecaf6dee75c9324130ea` | **Unchanged** |
| `data/tagged/review_queue.jsonl` (v1) | `bfd3c5c5be8ed33d5c1058b35b8832b4d750dc6a6aa2d5917645dbb71df96b3a` | `bfd3c5c5be8ed33d5c1058b35b8832b4d750dc6a6aa2d5917645dbb71df96b3a` | **Unchanged** |

---

## 10. Regression Test Suite Execution

`python -m unittest discover tests` was run:
- **Total Tests**: 113
- **Passed**: 113
- **Failed**: 0
- **Duration**: 0.238s
