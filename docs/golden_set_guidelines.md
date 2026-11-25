# Human Annotation Guidelines: 30-Review Golden Dataset

This document defines the official human annotation instructions for the **Urban Company Repeat-Booking Discovery Engine** 30-review golden ground-truth dataset (`data/golden/golden_set.jsonl`).

These guidelines ensure that human ground truth is objective, reproducible, strictly grounded in review text, and completely unpolluted by AI hallucinations or assumptions.

---

## 1. Ground Truth Principles

The golden dataset establishes the gold standard against which AI tagging pipelines (v1, v2, and downstream fine-tuned or LLM-prompted taggers) are benchmarked.

### Core Grounding Rule (Non-Inference)
- **Annotate what is written, never what you assume.**
- Never infer `city`, `household_type`, `alternative_used`, `need_trigger`, or `rebook_signal` without explicit textual evidence.
- If a review says *"Urban Company is great"*, do NOT infer that they rebooked, do NOT infer their city, and do NOT infer that they are a family or homeowner.

### Ground Truth Integrity Rule
- **Never populate AI predictions as ground truth.**
- All 16 schema fields in `data/golden/golden_set.jsonl` are initialized to `null`.
- Human annotators must read the review text independently and populate values strictly based on these guidelines.

### Star Rating vs. Written Review Text
- Customer star ratings frequently contradict written text (e.g., 4-star reviews complaining of no-shows or "looting", 1-star reviews expressing gratitude).
- **The written review text is always primary.** Tags must reflect the semantic meaning of the customer's written words, not an assumed sentiment derived solely from star score.

---

## 2. Dataset Structure & Annotation Workflow

### File Location
`data/golden/golden_set.jsonl`

### Record Format
Each line is a JSON object with the following schema:
```json
{
  "review_id": "bb81193d-cf36-41b3-abce-4d201b3c4a59",
  "source": "Play Store",
  "review_text": "its worth it for our salon experience . The last one was the best. Thank you UC",
  "text": "its worth it for our salon experience . The last one was the best. Thank you UC",
  "rating": 5,
  "date": "2024-04-18",
  "title": null,
  "annotation_status": "unannotated",
  "annotator_notes": null,
  "human_tags": {
    "source": null,
    "date": null,
    "city": null,
    "category": null,
    "experience_type": null,
    "nothing_went_wrong": null,
    "rebook_signal": null,
    "need_trigger": null,
    "recall_gap": null,
    "alternative_used": null,
    "post_service_expectation": null,
    "discovery_channel": null,
    "household_type": null,
    "unmet_need": null,
    "evidence_quote": null,
    "confidence": null
  }
}
```

### Annotation Lifecycle
1. **`unannotated`**: Initial state; all 16 `human_tags` are `null`.
2. **`in_progress`**: Annotator is reviewing and populating fields.
3. **`annotated`**: All 16 fields populated in accordance with this guideline.
4. **`verified`**: Second annotator or lead has verified agreement.

---

## 3. Field-by-Field Annotation Specifications

The 16 fields below conform to `docs/schema.md` and policy decisions in `docs/decisions.md`.

---

### Field 1: `source`
- **Type**: String
- **Allowed Values**: Exact data source identifier (`"Play Store"` or `"App Store"`).
- **Instruction**: Verifies provenance. In the golden set, copy the platform source directly from the record's top-level `source`.

---

### Field 2: `date`
- **Type**: String (Nullable)
- **Allowed Values**: `YYYY-MM-DD` formatted date string, or `null`.
- **Instruction**: Publication date of the review. Copy the review publication date from `normalized_date` / top-level `date`, or `null` if absent.

---

### Field 3: `city`
- **Type**: String (Nullable)
- **Allowed Values**: Explicit city name (e.g., `"Bengaluru"`, `"Delhi"`, `"Mumbai"`, `"Chennai"`, `"Khammam"`), or `null`.
- **Instruction**:
  - Record the city **only when explicitly named** in the text (e.g., *"in Bengaluru"*, *"expand to Khammam"*).
  - **Never infer** city from headquarters, pincodes, slang, or store country.
  - If no city is explicitly written, assign `null`.

---

### Field 4: `category`
- **Type**: String / Enum
- **Allowed Values**:
  - `"AC"`
  - `"deep clean"`
  - `"plumber"`
  - `"salon"`
  - `"electrician"`
  - `"pest control"`
  - `"other"`
  - `"unknown"`
- **Instruction**:
  - Classify the **primary service booked or evaluated**.
  - **Appliances & Hardware**: Washing machine repair, chimney service, refrigerator, microwave, and RO water purifiers belong to `"other"` (NOT plumber or electrician, even if water pipes or wiring are mentioned).
  - **Spa & Wellness**: Spa sessions, body massage, and wellness therapy belong to `"other"` (NOT `"salon"`, which is reserved strictly for grooming and beauty).
  - **Carpentry**: Belongs to `"other"`.
  - **General / Multi-Category**: If the review mentions multiple categories without a primary focus, or describes app/support issues without naming a service, use `"unknown"`.
  - **Incidental Words**: Do not classify based on incidental words (e.g., *"broke the water inlet pipe"* during washing machine repair is `"other"`, not `"plumber"`).

---

### Field 5: `experience_type`
- **Type**: String / Enum
- **Allowed Values**:
  - `"positive"`: Expresses satisfaction, praise, promptness, or good quality.
  - `"neutral"`: Balanced pros and cons, mild critiques, or neither positive nor negative.
  - `"negative"`: Expresses dissatisfaction, operational failure, damages, delays, or fraud.
  - `"unclear"`: Terse or uninterpretable text where sentiment cannot be determined.
- **Instruction**: Base this on the review text sentiment, not merely the star rating.

---

### Field 6: `nothing_went_wrong`
- **Type**: Boolean (Nullable Tri-State: `true`, `false`, `null`)
- **Allowed Values**: `true`, `false`, `null`
- **Instruction**:
  - `true`: Use **only** when the review explicitly confirms a fine, good, or satisfactory service where no failure occurred, **yet** the customer still mentions not rebooking, using only once, or switching to an alternative.
  - `false`: Use **only** when an operational, technical, or customer-service failure is explicitly described.
  - `null`: Use when the customer was satisfied and did not stop rebooking, or when there is insufficient evidence to determine whether friction occurred. **Never default to `false` when evidence is missing.**

---

### Field 7: `rebook_signal`
- **Type**: String / Enum
- **Allowed Values**:
  - `"rebooked"`: Explicit confirmation of repeat usage (e.g., *"using since 5 years"*, *"booked second time"*) OR explicit future intention to book again (e.g., *"will definitely book her again"*, *"would book anytime again"*).
  - `"did_not_rebook"`: Explicit statement that customer stopped using or switched away after previous bookings.
  - `"will_not_rebook"`: Explicit statement of intent never to book again (e.g., *"never booking again"*, *"will not use this app again"*, *"uninstalled app"*).
  - `"unclear"`: Review does not state whether customer rebooked or intends to rebook. General satisfaction, gratitude, or praise alone (e.g., *"great service"*, *"Thank you UC"*) maps to `"unclear"`.
- **Critical Policy (Decisions 008, 010, 011)**:
  - Mention of past tenure alone (e.g., *"I had been a regular customer"*) does **NOT** establish future intent. If contradicted by cancellations, disputes, or complaints, return `"unclear"`.
  - Dissatisfaction, cancellations, anger, support disputes, or 1-star ratings alone must **NEVER** establish `"will_not_rebook"`. If explicit future non-rebooking intent is absent, map to `"unclear"`.

---

### Field 8: `need_trigger`
- **Type**: String / Enum (Nullable)
- **Allowed Values**:
  - `"breakdown"`: Sudden failure (e.g., AC stopped cooling, water leak, appliance dead).
  - `"season"`: Seasonal prep (e.g., summer AC service).
  - `"festival"`: Holiday or festive preparation (e.g., Diwali cleaning).
  - `"move"`: Moving into or out of a home / tenant transition.
  - `"guests"`: Upcoming visitors or hosting event.
  - `"routine"`: Scheduled periodic maintenance.
  - `null`: No trigger explicitly mentioned. (Do not guess).

---

### Field 9: `recall_gap`
- **Type**: Boolean (Nullable Tri-State: `true`, `false`, `null`)
- **Allowed Values**: `true`, `false`, `null`
- **Instruction**:
  - `true`: Customer explicitly describes forgetting UC existed when a need arose, or defaulting to an offline habit before remembering UC.
  - `false`: Customer explicitly notes immediately remembering or defaulting to UC.
  - `null`: Review does not discuss whether UC was remembered at the trigger moment. **Never default to `false`.**

---

### Field 10: `alternative_used`
- **Type**: String / Enum
- **Allowed Values**:
  - `"neighbour"`
  - `"family"`
  - `"local provider"`
  - `"WhatsApp or society group"`
  - `"another app"`
  - `"DIY"`
  - `"none"`: **Explicit confirmation only** (e.g., *"I did not call anyone else"*, *"only use UC"*).
  - `"unclear"`: No alternative mentioned in the text (Default).

---

### Field 11: `post_service_expectation`
- **Type**: String / Enum
- **Allowed Values**:
  - `"follow-up"`: Customer wanted post-service check-in or health check.
  - `"reminder"`: Customer wanted future maintenance reminder.
  - `"warranty clarity"`: Customer explicitly wanted post-service documentation or clarity on warranty terms.
  - `"next-service advice"`: Customer explicitly wanted professional advice on subsequent care.
  - `"nothing"`: **Explicit confirmation only** (e.g., *"do not call me"*, *"no follow-up wanted"*).
  - `"unclear"`: Post-service expectations are not discussed (Default).
- **Critical Rules (Decisions 007 & 008)**:
  - Customer advice given to other consumers (*"My advice to other customers is..."*) or warnings against engineer advice is **NOT** `"next-service advice"`.
  - Disputing a denied warranty claim after breakdown is **NOT** a post-service documentation expectation.

---

### Field 12: `discovery_channel`
- **Type**: String / Enum
- **Allowed Values**:
  - `"search"`
  - `"ad"`
  - `"friend"`
  - `"society group"`
  - `"preinstalled habit"`
  - `"unclear"`: How customer discovered UC is not stated (Default).

---

### Field 13: `household_type`
- **Type**: String / Enum
- **Allowed Values**:
  - `"living alone"`
  - `"couple"`
  - `"family"`
  - `"elderly"`
  - `"renter"`
  - `"owner"`
  - `"unclear"`: Living arrangement is not stated (Default).
- **Instruction**: Do not infer household composition from the service category (e.g., AC cleaning does not imply `"family"`).

---

### Field 14: `unmet_need`
- **Type**: String (Nullable)
- **Allowed Values**: One concise descriptive phrase summarizing the latent friction or missing JTBD (e.g., `"transparent cancellation fee policy"`, `"competent appliance diagnostics"`), or `null`.
- **Instruction**:
  - Use `null` when no specific unmet need or friction is articulated.
  - Do **not** invent generic template phrases (e.g., do NOT synthesize "satisfactory service execution").

---

### Field 15: `evidence_quote`
- **Type**: String
- **Allowed Values**: Verbatim substring extracted directly from `review_text`.
- **Instruction**:
  - Must be an exact character-for-character substring of the review.
  - Must contain the specific clause or sentence that justifies the assigned tags (especially `rebook_signal`, `category`, and `unmet_need`).
  - For very short reviews (e.g., "good work"), the evidence quote is the entire text.

---

### Field 16: `confidence`
- **Type**: String / Enum
- **Allowed Values**:
  - `"high"`: Explicit, unambiguous text directly supporting all primary tags.
  - `"medium"`: Text clearly supports the classification, but some context is implicit or phrasing is colloquial.
  - `"low"`: Review is very short (< 20 characters), vague, contradictory, or low-information.

---

## 4. Special Annotation Scenarios

### 1. Low-Information Reviews (Terse Reviews)
For reviews such as *"good work"*, *"ok ok"*, *"lut rahe hai"*, *"Good"*, *"useful"*:
- `confidence`: `"low"`
- `category`: `"unknown"` (unless a specific service word is present)
- `rebook_signal`: `"unclear"`
- `nothing_went_wrong`: `null`
- `recall_gap`: `null`
- `unmet_need`: `null` (or short vernacular friction if explicit, e.g., "lut rahe hai" -> `"fair pricing"`)
- `evidence_quote`: Full text snippet

### 2. Rating-Polarity Conflicts
When a customer awards 4 or 5 stars but writes an accusatory or critical review (e.g., 4 stars with *"after booking cancellation from UC and not arriving at opted time slot"*):
- `experience_type`: `"negative"`
- `rebook_signal`: Based on written text, typically `"unclear"` or `"will_not_rebook"`
- `annotator_notes`: Note: *"Rating-polarity conflict: 4 stars awarded but review describes partner cancellation."*

### 3. Multi-Category and Brand Tenure Reviews
When a customer reviews Urban Company across multiple years and services (e.g., *"using since Urban Clap for salon, spa, carpentry, pest control"*):
- `category`: `"unknown"` or the primary category highlighted in the body.
- `rebook_signal`: `"rebooked"`
- `confidence`: `"high"`
- `evidence_quote`: Quote confirming multi-service repeat tenure.

---

## 5. Annotator Checklist Before Submitting

- [ ] Every field in `human_tags` is populated with an allowed value or appropriate `null`.
- [ ] No demographic or geographic field is inferred without explicit textual evidence.
- [ ] Tri-state booleans (`nothing_went_wrong`, `recall_gap`) are `null` unless explicit evidence warrants `true` or `false`.
- [ ] Defaults used properly: `post_service_expectation` is `"unclear"`, `alternative_used` is `"unclear"`.
- [ ] `evidence_quote` is an exact verbatim substring from `review_text`.
- [ ] `annotation_status` updated to `"annotated"`.
- [ ] Any ambiguities or judgment calls recorded in `annotator_notes`.
