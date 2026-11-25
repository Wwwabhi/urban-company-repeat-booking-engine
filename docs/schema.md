# Tagging Schema: Urban Company Repeat-Booking Discovery Engine

This document defines the 16 tagging fields for public conversation and review data collected for the Urban Company Repeat-Booking Discovery Engine, as specified in the project build brief (pages 4–5).

---

## Field Specifications

### 1. `source`
- **Field Name**: `source`
- **Data Type**: String
- **Allowed Values**: Public data source identifier (e.g., `Play Store`, `App Store`, `Reddit`, `YouTube`, `Trustpilot`, `MouthShut`, `Shareholder Letter`, `Earnings Call`)
- **Explanation**: The public platform or channel from which the raw text item was collected.
- **Example**: `"Play Store"`

---

### 2. `date`
- **Field Name**: `date`
- **Data Type**: String (Nullable)
- **Allowed Values**: Valid calendar date in `YYYY-MM-DD` format, or `null` when unavailable
- **Explanation**: The publication date of the review, comment, post, or document excerpt. Accepts `null` when unavailable.
- **Example**: `"2024-04-18"`

---

### 3. `city`
- **Field Name**: `city`
- **Data Type**: String (Nullable)
- **Allowed Values**: City name only when explicitly stated in the text; `null` if not explicitly stated.
- **Explanation**: The geographic city or metropolitan area where the service occurred. Recorded only when explicitly stated in the post, never inferred.
- **Example**: `"Bengaluru"`

---

### 4. `category`
- **Field Name**: `category`
- **Data Type**: String / Enum
- **Allowed Values**:
  - `AC`
  - `deep clean`
  - `plumber`
  - `salon`
  - `electrician`
  - `pest control`
  - `other`
  - `unknown`
- **Explanation**: The primary service category referenced in the customer feedback or post.
  - `salon`: Grooming and beauty services (haircut, styling, waxing, facial, manicure, pedicure, threading). Does NOT include spa or massage.
  - `other`: Specific services outside the core categories, including spa sessions, body massage, wellness treatments, appliance repair (washing machine, chimney deep clean, refrigerator, RO water purifier), carpentry, painting.
  - `deep clean`: Premises cleaning (home, kitchen, bathroom, sofa). Does NOT include appliance deep cleaning (e.g. chimney deep clean maps to `other`).
- **Example**: `"AC"`

---

### 5. `experience_type`
- **Field Name**: `experience_type`
- **Data Type**: String / Enum
- **Allowed Values**:
  - `positive`
  - `neutral`
  - `negative`
  - `unclear`
- **Explanation**: The customer's overall qualitative assessment of the service delivery and experience.
- **Example**: `"positive"`

---

### 6. `nothing_went_wrong`
- **Field Name**: `nothing_went_wrong`
- **Data Type**: Boolean
- **Allowed Values**: `true`, `false`
- **Explanation**: Flagged as `true` when the post describes a satisfactory, fine, or good service experience where no operational failure occurred, yet the customer still mentions not rebooking, using the service only once, or switching to an alternative.
- **Example**: `true`

---

### 7. `rebook_signal`
- **Field Name**: `rebook_signal`
- **Data Type**: String / Enum
- **Allowed Values**:
  - `rebooked`
  - `did_not_rebook`
  - `will_not_rebook`
  - `unclear`
- **Explanation**: Explicit indication of repeat booking behavior or intent expressed in the text.
  - `rebooked`: Explicit confirmation of repeat usage (e.g. "booked second time", "using for 5 years") OR explicit future intention to book again (e.g. "will definitely book her again", "would book anytime again").
  - `did_not_rebook`: Explicitly states they stopped using UC after a completed service.
  - `will_not_rebook`: Explicit refusal to return to UC (e.g. "will never book again", "uninstalled the app"). Never infer from dissatisfaction, cancellations, anger, or complaints alone.
  - `unclear`: Default when no explicit statement of repeat booking or future booking intent is present (general praise, historical usage alone, low ratings, cancellations, or complaints map to `unclear`).
- **Example**: `"did_not_rebook"`

---

### 8. `need_trigger`
- **Field Name**: `need_trigger`
- **Data Type**: String / Enum (Nullable)
- **Allowed Values**:
  - `breakdown`
  - `season`
  - `festival`
  - `move`
  - `guests`
  - `routine`
  - `null` (when the text does not establish a trigger)
- **Explanation**: The underlying catalyst or life event that prompted the customer to seek the service. Accepts `null` when the text does not establish a trigger.
- **Example**: `"season"`

---

### 9. `recall_gap`
- **Field Name**: `recall_gap`
- **Data Type**: Boolean
- **Allowed Values**: `true`, `false`
- **Explanation**: Flagged as `true` if the post indicates that the customer did not think of Urban Company when a household need subsequently arose (e.g., defaulted to offline habits or forgot the category existed on UC).
- **Example**: `true`

---

### 10. `alternative_used`
- **Field Name**: `alternative_used`
- **Data Type**: String / Enum
- **Allowed Values**:
  - `neighbour`
  - `family`
  - `local provider`
  - `WhatsApp or society group`
  - `another app`
  - `DIY`
  - `none`
  - `unclear`
- **Explanation**: The substitute solution, referral, or channel the customer turned to instead of booking via Urban Company. Keep `none` only when the customer explicitly confirms no alternative was used (e.g., "I did not call anyone else"). Use `unclear` when no alternative is mentioned.
- **Example**: `"local provider"`

---

### 11. `post_service_expectation`
- **Field Name**: `post_service_expectation`
- **Data Type**: String / Enum
- **Allowed Values**:
  - `follow-up`
  - `reminder`
  - `warranty clarity`
  - `next-service advice`
  - `nothing`
  - `unclear`
- **Explanation**: What the customer expected or wished would happen after the job was finished to support continued maintenance. Use `unclear` when the review does not mention post-service expectations. Use `nothing` only when the customer explicitly indicates no post-service expectation or contact is wanted (e.g., "do not call me").
- **Example**: `"reminder"`

---

### 12. `discovery_channel`
- **Field Name**: `discovery_channel`
- **Data Type**: String / Enum
- **Allowed Values**:
  - `search`
  - `ad`
  - `friend`
  - `society group`
  - `preinstalled habit`
  - `unclear`
- **Explanation**: How the customer initially discovered or came into contact with Urban Company or the specific service category.
- **Example**: `"society group"`

---

### 13. `household_type`
- **Field Name**: `household_type`
- **Data Type**: String / Enum
- **Allowed Values**:
  - `living alone`
  - `couple`
  - `family`
  - `elderly`
  - `renter`
  - `owner`
  - `unclear`
- **Explanation**: The customer's household composition or living arrangement if mentioned or clearly discernible.
- **Example**: `"living alone"`

---

### 14. `unmet_need`
- **Field Name**: `unmet_need`
- **Data Type**: String (Nullable)
- **Allowed Values**: Free text (one concise phrase), or `null` when no unmet need is explicitly expressed.
- **Explanation**: A short descriptive phrase summarizing the latent friction, unaddressed job-to-be-done, or missing experience from the customer's point of view. Use `null` when no unmet need is explicitly expressed.
- **Example**: `"predictable routine maintenance schedule"`

---

### 15. `evidence_quote`
- **Field Name**: `evidence_quote`
- **Data Type**: String
- **Allowed Values**: Free text (direct excerpt)
- **Explanation**: A short verbatim snippet extracted directly from the post supporting the assigned tags.
- **Example**: `"The cleaning was fine, but next time my society guard gave me the number of a local guy."`

---

### 16. `confidence`
- **Field Name**: `confidence`
- **Data Type**: String / Enum
- **Allowed Values**:
  - `low`
  - `medium`
  - `high`
- **Explanation**: The model's or human annotator's degree of certainty in the tags assigned to the item based on the clarity and completeness of the source text.
- **Example**: `"high"`

---

## Schema Overview Table

| # | Field Name | Data Type | Allowed Values |
|---|---|---|---|
| 1 | `source` | String | Platform names (e.g., `Play Store`, `App Store`, `Reddit`, `YouTube`, etc.) |
| 2 | `date` | String (Nullable) | `YYYY-MM-DD`, or `null` when unavailable |
| 3 | `city` | String (Nullable) | City name only when explicitly stated, else `null` (never inferred) |
| 4 | `category` | Enum | `AC`, `deep clean`, `plumber`, `salon`, `electrician`, `pest control`, `other`, `unknown` |
| 5 | `experience_type` | Enum | `positive`, `neutral`, `negative`, `unclear` |
| 6 | `nothing_went_wrong` | Boolean (Nullable) | `true`, `false`, or `null` (when missing evidence; never default to false) |
| 7 | `rebook_signal` | Enum | `rebooked`, `did_not_rebook`, `will_not_rebook`, `unclear` |
| 8 | `need_trigger` | Enum (Nullable) | `breakdown`, `season`, `festival`, `move`, `guests`, `routine`, or `null` |
| 9 | `recall_gap` | Boolean (Nullable) | `true`, `false`, or `null` (when missing evidence; never default to false) |
| 10 | `alternative_used` | Enum | `neighbour`, `family`, `local provider`, `WhatsApp or society group`, `another app`, `DIY`, `none` (explicit only), `unclear` |
| 11 | `post_service_expectation` | Enum | `follow-up`, `reminder`, `warranty clarity`, `next-service advice`, `nothing` (explicit only), `unclear` |
| 12 | `discovery_channel` | Enum | `search`, `ad`, `friend`, `society group`, `preinstalled habit`, `unclear` |
| 13 | `household_type` | Enum | `living alone`, `couple`, `family`, `elderly`, `renter`, `owner`, `unclear` |
| 14 | `unmet_need` | String (Nullable) | Short phrase, or `null` when no unmet need is explicitly expressed |
| 15 | `evidence_quote` | String | Short verbatim snippet |
| 16 | `confidence` | Enum | `low`, `medium`, `high` |
