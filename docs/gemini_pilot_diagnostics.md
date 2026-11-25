# Gemini API 10-Review Pilot Diagnostic Report

**Date**: 2026-11-24  
**Pipeline Version**: v2  
**Target Pilot Input**: `data/tagged/pilot/pilot_input.jsonl` (10 records)  
**Execution Reference**: Task `task-2132` (Log: `.system_generated/tasks/task-2132.log`)  

---

## 1. Executive Summary

During the 10-review live tagging pilot with `gemini-3.5-flash-lite`:
- **Attempted**: 10 reviews (28 total API requests across attempts).
- **Succeeded**: 3 reviews (2 written to `tagged_reviews_pilot.jsonl`, 1 written to `review_queue_pilot.jsonl` due to low model confidence).
- **Failed**: 7 reviews failed after exhausting their bounded retries (3 attempts per review).
- **Total API Requests**: 28 total HTTP requests (3 succeeded with HTTP 200, 18 failed with HTTP 503 Service Unavailable, 7 failed with HTTP 504 Gateway Timeout).
- **Client Reliability**: The client correctly handled bounded retries, prevented cascading SDK retry loops, avoided crashing on per-review failure, logged duration/status safely without leaking review text or API keys, and maintained complete integrity of all immutable datasets.

---

## 2. Request Configuration Inspection

The request was executed with the following configuration:

| Configuration Parameter | Value | Source / Implementation |
| :--- | :--- | :--- |
| **Model ID** | `gemini-3.5-flash-lite` | `GeminiLLMClient._model_name` in `engine/tagger.py` |
| **API Endpoint / Version** | `https://generativelanguage.googleapis.com/v1/models/gemini-3.5-flash-lite:generateContent` (`v1`) | Default client endpoint in `google.genai.Client` |
| **System Instruction** | `engine/prompts/tagger_v2.md` | Configured via `config.system_instruction` in `GenerateContentConfig` |
| **Input Token Count (System)** | 8,899 characters, 1,197 words (~1,556 tokens) | Markdown classification prompt with 16-field schema |
| **Input Token Count (Per Review)** | 79 to 492 characters (~20 to 100 tokens) | Normalized review JSON passed in `contents` |
| **Total Input Tokens Per Request** | ~1,576 to 1,656 tokens | System instruction + single review payload |
| **Response MIME Type** | `application/json` | Enforced structured JSON output mode |
| **Temperature** | `0.0` | Deterministic sampling |
| **Max Output Tokens** | *Unset / Default* (~8,192 default) | Not explicitly capped in `types.GenerateContentConfig` |
| **Request Timeout** | `20.0` seconds | Passed as `types.HttpOptions(timeout=20000)` |
| **SDK Built-in Retry** | `attempts=1` (Disabled) | `retry_options=types.HttpRetryOptions(attempts=1)` |
| **Application Retry Policy** | `max_retries=3`, `initial_backoff=2.0s`, `multiplier=2.0`, `max_backoff=10.0s`, jitter `[0.1, 0.4]s` | Custom application loop in `GeminiLLMClient._call_model_with_retries` |
| **Inter-Review Delay** | `1.0` second | CLI parameter `--delay 1.0` |

---

## 3. Log Extraction for All 7 Failed Reviews

Across the 7 failed reviews, exactly 21 API requests were attempted (3 attempts per review). All 21 attempts failed upstream.

### Detailed Request-Level Breakdown

| Review ID | Attempt | HTTP Status | Duration | Sanitized Error Type | Google Request ID | Retry-After Header | Failure Classification |
| :--- | :---: | :---: | :---: | :--- | :---: | :---: | :--- |
| `99226311-a2f2-4ecf-b1ed-7d28518cd95e` | 1 | 503 | 2.09s | `ServerError (HTTP 503)` | *Not emitted in body* | *None* | Upstream Service Unavailable |
| `99226311-a2f2-4ecf-b1ed-7d28518cd95e` | 2 | 504 | 19.83s | `ServerError (HTTP 504)` | *Not emitted in body* | *None* | Upstream Gateway Timeout |
| `99226311-a2f2-4ecf-b1ed-7d28518cd95e` | 3 | 503 | 1.54s | `ServerError (HTTP 503)` | *Not emitted in body* | *None* | Upstream Service Unavailable |
| `75c91a8d-c132-48e2-a420-ea4221bb6059` | 1 | 504 | 19.82s | `ServerError (HTTP 504)` | *Not emitted in body* | *None* | Upstream Gateway Timeout |
| `75c91a8d-c132-48e2-a420-ea4221bb6059` | 2 | 504 | 19.75s | `ServerError (HTTP 504)` | *Not emitted in body* | *None* | Upstream Gateway Timeout |
| `75c91a8d-c132-48e2-a420-ea4221bb6059` | 3 | 504 | 19.86s | `ServerError (HTTP 504)` | *Not emitted in body* | *None* | Upstream Gateway Timeout |
| `36b24dd5-1cd2-4752-9a46-68307d86382c` | 1 | 504 | 19.26s | `ServerError (HTTP 504)` | *Not emitted in body* | *None* | Upstream Gateway Timeout |
| `36b24dd5-1cd2-4752-9a46-68307d86382c` | 2 | 504 | 18.46s | `ServerError (HTTP 504)` | *Not emitted in body* | *None* | Upstream Gateway Timeout |
| `36b24dd5-1cd2-4752-9a46-68307d86382c` | 3 | 503 | 2.09s | `ServerError (HTTP 503)` | *Not emitted in body* | *None* | Upstream Service Unavailable |
| `43582ef1-c85a-4b67-ad13-662ab7a72dcb` | 1 | 503 | 2.08s | `ServerError (HTTP 503)` | *Not emitted in body* | *None* | Upstream Service Unavailable |
| `43582ef1-c85a-4b67-ad13-662ab7a72dcb` | 2 | 503 | 2.26s | `ServerError (HTTP 503)` | *Not emitted in body* | *None* | Upstream Service Unavailable |
| `43582ef1-c85a-4b67-ad13-662ab7a72dcb` | 3 | 503 | 1.69s | `ServerError (HTTP 503)` | *Not emitted in body* | *None* | Upstream Service Unavailable |
| `bec86ea9-9a8f-495d-a091-1e4ec7843980` | 1 | 503 | 3.87s | `ServerError (HTTP 503)` | *Not emitted in body* | *None* | Upstream Service Unavailable |
| `bec86ea9-9a8f-495d-a091-1e4ec7843980` | 2 | 503 | 1.35s | `ServerError (HTTP 503)` | *Not emitted in body* | *None* | Upstream Service Unavailable |
| `bec86ea9-9a8f-495d-a091-1e4ec7843980` | 3 | 503 | 1.67s | `ServerError (HTTP 503)` | *Not emitted in body* | *None* | Upstream Service Unavailable |
| `6b579933-e83a-459c-b7c7-73f83b669c16` | 1 | 503 | 1.21s | `ServerError (HTTP 503)` | *Not emitted in body* | *None* | Upstream Service Unavailable |
| `6b579933-e83a-459c-b7c7-73f83b669c16` | 2 | 503 | 1.47s | `ServerError (HTTP 503)` | *Not emitted in body* | *None* | Upstream Service Unavailable |
| `6b579933-e83a-459c-b7c7-73f83b669c16` | 3 | 503 | 1.33s | `ServerError (HTTP 503)` | *Not emitted in body* | *None* | Upstream Service Unavailable |
| `06b45346-6f25-4d49-9b01-13d980482c2c` | 1 | 503 | 1.18s | `ServerError (HTTP 503)` | *Not emitted in body* | *None* | Upstream Service Unavailable |
| `06b45346-6f25-4d49-9b01-13d980482c2c` | 2 | 503 | 1.46s | `ServerError (HTTP 503)` | *Not emitted in body* | *None* | Upstream Service Unavailable |
| `06b45346-6f25-4d49-9b01-13d980482c2c` | 3 | 503 | 1.24s | `ServerError (HTTP 503)` | *Not emitted in body* | *None* | Upstream Service Unavailable |

*(Note: In the 3 successful reviews, Review 1 also encountered two 503 errors before succeeding on attempt 3; Review 7 encountered a 504 and a 503 before succeeding on attempt 3; and Review 5 succeeded on attempt 1).*

---

## 4. Analysis of Potential Causes & Correlation Tests

### A. Request Payload Size / Token Count Correlation
We analyzed whether larger reviews failed more frequently than shorter reviews:
- **Review 1** (79 chars, 17 words): **Succeeded** on attempt 3.
- **Review 2** (101 chars, 16 words): **Failed** (503, 504, 503).
- **Review 3** (155 chars, 18 words): **Failed** (504, 504, 504).
- **Review 4** (472 chars, 84 words): **Failed** (504, 504, 503).
- **Review 5** (492 chars, 84 words — *longest review in pilot*): **Succeeded on attempt 1** (1.95s)!
- **Review 6** (116 chars, 22 words): **Failed** (503, 503, 503).
- **Review 7** (441 chars, 79 words — *3rd longest review*): **Succeeded on attempt 3** (1.88s)!
- **Review 8** (86 chars, 15 words): **Failed** (503, 503, 503).
- **Review 9** (166 chars, 30 words): **Failed** (503, 503, 503).
- **Review 10** (248 chars, 45 words): **Failed** (503, 503, 503).

**Finding**: There is **no correlation** between review length/token count and failure rate. The longest review in the entire pilot (Review 5, 492 chars) completed in under 2 seconds on its first attempt, while short reviews (86 and 101 chars) failed repeatedly.

### B. Rate Limits and Quota Restrictions
- **HTTP 429 Status**: Exactly **0** instances of HTTP 429 (`ResourceExhausted` / `RateLimitExceeded`) occurred during the entire pilot run.
- **Headers**: No `Retry-After` header was sent by the server.
- **Finding**: Failures were **not caused by quota exhaustion or per-minute rate limits**.

### C. Request Timeout Setting (20s)
- **HTTP 504 Gateway Timeout**: 7 requests failed with HTTP 504, each lasting between 18.46s and 19.86s (average: 19.53s).
- **Behavior**: When the backend inference engine was responsive, requests completed in ~1.9s. When the backend queue backed up, the client reached its 20-second deadline before the model generated a token, triggering an HTTP 504 Gateway Timeout from the Google frontend load balancer.
- **Finding**: The 20s timeout prevented the client from hanging indefinitely, but in congested intervals (such as Review 3's 3 consecutive attempts), 20 seconds was insufficient for the upstream queue to clear.

### D. Upstream Temporary Service Availability & Temporal Clustering
- **HTTP 503 Service Unavailable**: 18 requests failed with HTTP 503 in rapid succession (average latency: 1.82s).
- **Temporal Pattern**:
  - From 20:13:11 to 20:15:04 (Reviews 3 & 4), the upstream gateway exhibited extreme queuing latency (multiple 504 timeouts).
  - From 20:15:53 to 20:16:29 (Reviews 8, 9, 10), the upstream cluster immediately rejected **9 consecutive requests across all 3 reviews** with HTTP 503 within 36 seconds.
- **Finding**: Failures clustered tightly into two distinct upstream congestion windows: a high-latency queuing window followed by an immediate capacity-shedding (503) window.

### E. Bounded Retry Window Span
- Because `max_retries = 3` with backoffs of 2s and 4s:
  - For rapid 503 rejections (latency ~1.5s), a review exhausted all 3 attempts in only ~10 to 13 seconds total (`1.5s + 2.3s + 1.5s + 4.2s + 1.5s ≈ 11.0s`).
  - An upstream congestion episode lasting 40–60 seconds will cause any request that arrives during that window to exhaust all 3 attempts before the service recovers.
- **Finding**: 3 attempts over an 11-second retry window is too narrow to ride out short-term Google API free-tier capacity surges.

---

## 5. Confirmed Findings vs. Unconfirmed Hypotheses

### Confirmed Findings
1. **Upstream Server Errors Exclusively**: 100% of failed attempts were either HTTP 503 (`Service Unavailable`, 72%) or HTTP 504 (`Gateway Timeout`, 28%). Zero client errors (400, 401, 403, 422) and zero quota errors (429) occurred.
2. **Payload Size Independence**: Both successful reviews (e.g., Review 5 at 492 chars) and failed reviews (e.g., Review 8 at 86 chars) had similar prompt structures and varied lengths; failures did not track input size.
3. **Sub-2s Processing When Responsive**: When the upstream model served requests without congestion, latency was consistently ~1.9s (1.88s, 1.95s, 2.02s).
4. **Retry Window Exhaustion**: The current 3-attempt backoff envelope (~11s for 503s) expires before transient upstream cluster congestion resolves.
5. **No Client Crash / Clean Separation**: Pipeline error catching allowed partial successes to persist cleanly without crashing the process or corrupting baseline datasets.

### Unconfirmed Hypotheses
1. **Endpoint Routing (`v1` vs `v1beta`)**: The client currently queries `v1`. Whether `v1beta` routes to different backend capacity pools with higher stability for `gemini-3.5-flash-lite` is plausible but unconfirmed.
2. **Output Token Allocation**: `max_output_tokens` is currently unspecified in `GenerateContentConfig`. Specifying `max_output_tokens=1024` might reduce backend reservation overhead, but evidence that this impacts 503 rejection is unconfirmed.
3. **Pacing Delay**: The 1.0s delay between reviews may not give Google's front-end sufficient time to reset per-client burst detection when multiple retries are active.

---

## 6. Recommended Next Experiment

### Recommended Experiment: Pacing and Backoff Window Expansion
Run a controlled test on the **7 failed reviews only**, modifying only runtime retry parameters without altering prompts, schema, or golden annotations:
1. **Increase `max_retries` from 3 to 5**.
2. **Expand retry backoff**: Initial backoff = 3.0s, multiplier = 2.0, max backoff = 15.0s, giving a retry survival window of >45 seconds.
3. **Increase inter-review request delay to 3.0s** (`--delay 3.0`) to avoid triggering burst capacity sheds.
4. **Increase request timeout to 30.0s** (`timeout=30000`) so queuing requests have adequate headroom to finish before triggering 504.
