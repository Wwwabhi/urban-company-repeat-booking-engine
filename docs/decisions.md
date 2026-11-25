# AI Decision & Correction Log

This running log documents every instance where AI output (from taggers, summarizers, synthesis agents, or code generators) was corrected or rejected, including the root cause, discovery method, and resolution. This document directly feeds Level 10: The AI Evidence Log.

---

## Log Template

Each entry should follow this structure:

```markdown
### Decision [ID]: [Short Summary]
- **Date**: YYYY-MM-DD
- **Component / Phase**: (e.g., Tagging prompt v1, Data Cleaning, Analysis clustering)
- **What the AI Proposed / Generated**:
  > Verbatim or concise snippet of the faulty AI output
- **What Was Wrong / Rejected**:
  Explanation of the error, hallucination, or misalignment with brief rules.
- **How It Was Caught**:
  (e.g., Golden-set disagreement, human spot-check, automated assertion)
- **What Was Changed**:
  Action taken (e.g., prompt refinement, schema constraint, manual override).
- **Prompt / Code Diff Reference**:
  Link or diff to updated prompt or code.
```

---

## Decision Log Entries

### Decision 001: Contextual Third-Party Personal Name Redaction vs. Naive Capitalization Masking
- **Date**: 2026-11-23
- **Component / Phase**: Privacy & Data Ingestion (`engine/collectors`)
- **What the AI Proposed / Generated**:
  > Pre-collection privacy audits handled author metadata (stripped at source), phone numbers (redacted), emails (redacted), and physical addresses/pincodes (excluded). However, third-party personal names appearing inside review text (specifically service professionals and technicians named in customer reviews, such as "Ramprit" and "Mohammad" in Apple review ID `14816172315`) were initially left unredacted.
- **What Was Wrong / Rejected**:
  A naive rule of automatically redacting all capitalized words was rejected. Customer reviews in home services are dense with critical capitalized tokens:
  1. Platform/Brand names: "Urban Company", "UC", "UrbanClap", "Ikea"
  2. Proprietary products/services: "Native M1 Pro", "InstaHelp", "Spa", "Salon", "Purifier"
  3. Cosmetic treatments/brands: "Kanpeki", "O3"
  4. Technical/industry terms: "AC", "AI", "SOP", "INR"
  5. Sentence starters and category nouns: "Cleaning", "Good", "Surge Charge", "Price hikes"
  Blindly masking all capitalized words would destroy the semantic signals needed for category tagging, journey mapping, and repeat-booking frequency discovery. Blanket exclusion of reviews mentioning partner names was also rejected as disproportionate, as it would discard valuable service quality and operational feedback (e.g. cleaning skills, training gaps).
- **How It Was Caught**:
  Human privacy audit of the 20-review Apple App Store pilot dataset (`data/raw/app_store_reviews.jsonl`), where review ID `14816172315` contained explicit technician names: *"Whether it is Ramprit, Mohammad they are very professional."*
- **What Was Changed**:
  Implemented targeted contextual name detection and redaction (`redact_person_names()`) integrated into `redact_pii()` in `engine/collectors/google_play.py`. The rule matches names only when accompanied by explicit personal attribution cues:
  1. **Honorifics**: `Mr.`, `Mrs.`, `Ms.`, `Dr.`, `Mohd.`, `Shri`, `Smt.` followed by title-cased name tokens.
  2. **Worker Role Indicators**: `technician`, `beautician`, `pro`, `plumber`, `cleaner`, `mechanic`, `server`, etc., followed by `named`/`called` or title-cased names.
  3. **Attribution Prepositions**: `done by`, `serviced by`, `attended by`, `visited by`.
  4. **Commendation / Gratitude Cues**: `thanks to`, `kudos to`, `shoutout to`.
  5. **Partner Enumeration Cues**: `whether it is <Name>, <Name>`.
  
  A strict `PERSON_NAME_WHITELIST` ensures platform, brand, and service names ("Urban Company", "UC", "InstaHelp", "Ikea", "Native M1", "AC", "AI", "Kanpeki", "O3", etc.) are protected from redaction.
  Matched personal names are replaced with `[NAME_REDACTED]`.
  
  **Pilot Dataset Sanitization**:
  The existing 20-record Apple App Store pilot dataset (`data/raw/app_store_reviews.jsonl`) was sanitized using the agreed `redact_person_names()` rule. Specifically, in review ID `14816172315`, partner names `Ramprit` and `Mohammad` were replaced with `[NAME_REDACTED]`. All other review text, IDs, dates, scores, and metadata were strictly preserved across all 20 records.
  Consequently, the file's SHA-256 hash changed:
  - Previous SHA-256: `dc2c65b90ba4b14fe4a49d46194d99a351d6dff252574149fb21201ab6509b04`
  - Sanitized SHA-256: `7d7d5fb227b2bd3b25249ac1b7657c53bfc97acc2f195c5e249bfc118e63b778`
  The Google Play dataset (`data/raw/google_play_reviews.jsonl`) was not modified (SHA-256 remains `0204998ba0a405d5cda5ee3f75237c47887ddb32a720b78ccd2297eb14730597`).
- **Limitations**:
  Regex-based contextual matching cannot identify standalone person names in arbitrary, non-standard grammar lacking contextual cues (e.g. "Suresh broke the pipe" without "technician" or attribution marker). Comprehensive name masking at scale across millions of informal reviews will require secondary NER (e.g. spaCy / transformer-based entity recognition) or downstream LLM privacy filtering during tagging.
- **Prompt / Code Diff Reference**:
  `engine/collectors/google_play.py` (`redact_person_names()`, `redact_pii()`), `tests/test_privacy.py` (`TestPersonNameRedaction`), `tests/test_app_store.py` (`TestAppleAppStoreDatasetSanitized`), `data/raw/app_store_reviews.jsonl`.


---

### Decision 002: Nullable Tri-State Representation for `nothing_went_wrong` and `recall_gap`
- **Date**: 2026-11-23
- **Component / Phase**: Tagging Schema & AI Pipeline (`engine/tagger.py`, `docs/schema.md`)
- **What the AI Proposed / Generated**:
  > Binary boolean fields (`true` or `false`) for `nothing_went_wrong` and `recall_gap`, where reviews that did not mention rebooking friction or subsequent household needs defaulted to `false`.
- **What Was Wrong / Rejected**:
  Defaulting missing evidence to `false` is methodologically invalid. In customer reviews, absence of discussion does not equal negation:
  1. Defaulting `nothing_went_wrong` to `false` on a satisfied review falsely asserts that an operational failure occurred ("something went wrong").
  2. Defaulting `recall_gap` to `false` falsely asserts that the customer actively remembered Urban Company at the moment of subsequent need.
- **How It Was Caught**:
  Schema design review against project brief requirement: *"For recall_gap and nothing_went_wrong, use null/unknown when the review does not provide enough evidence. Do not interpret missing evidence as false."*
- **What Was Changed**:
  Enforced nullable tri-state boolean (`true`, `false`, `null`) in `engine/tagger.py`:
  - `nothing_went_wrong`: `true` ONLY when review describes a satisfactory/fine service but mentions not rebooking or switching; `false` ONLY when operational failure is explicitly described; otherwise `null`.
  - `recall_gap`: `true` ONLY when customer explicitly notes forgetting UC existed or defaulting offline; `false` ONLY when customer explicitly notes immediately remembering UC; otherwise `null`.
- **Prompt / Code Diff Reference**:
  `engine/tagger.py` (`validate_16_schema_fields()`, `MockLLMClient.tag_review()`), `engine/prompts/tagger_v1.md`, `tests/test_tagger.py` (`test_nothing_went_wrong_and_recall_gap_are_nullable_tri_state`).

---

### Decision 003: Low-Information Review Interception and Routing to Human Review Queue
- **Date**: 2026-11-23
- **Component / Phase**: AI Tagging Pipeline & Data Quality (`engine/tagger.py`)
- **What the AI Proposed / Generated**:
  > LLMs frequently over-interpret terse 5-star reviews (e.g. "good", "nice", "ok ok", "super") as positive evidence of successful repeat booking (`rebook_signal: "rebooked"`, `confidence: "high"`).
- **What Was Wrong / Rejected**:
  Generic 1-word or 2-word reviews carry zero signal regarding customer journey, category context, or repeat booking behavior. Treating them as rebooked or assigning high confidence skews the repeat rate and fabricates evidence.
- **How It Was Caught**:
  Data quality audit of normalized dataset revealing 37 reviews under 20 characters in the eligible core set.
- **What Was Changed**:
  Implemented `is_low_information_review()` heuristic intercepting reviews under 20 characters or containing generic boilerplate.
  - Tagged with `confidence: "low"`, `rebook_signal: "unclear"`, `category: "unknown"`, `nothing_went_wrong: null`, `recall_gap: null`.
  - Automatically flagged with `requires_human_review: true` and routed to `data/tagged/review_queue.jsonl` with reason `low_information`.
  - Only substantive reviews with grounded evidence and medium/high confidence are persisted to `data/tagged/tagged_reviews.jsonl`.
- **Prompt / Code Diff Reference**:
  `engine/tagger.py` (`is_low_information_review()`, `evaluate_review_queue_triggers()`), `tests/test_tagger.py` (`TestLowInformationAndReviewQueueRouting`).

---

### Decision 004: Strict Non-Inference Grounding for Geographic and Demographic Fields
- **Date**: 2026-11-23
- **Component / Phase**: AI Prompt & Pipeline (`engine/prompts/tagger_v1.md`, `engine/tagger.py`)
- **What the AI Proposed / Generated**:
  > Unconstrained LLMs infer `city` based on corporate headquarters (assuming Delhi/Gurgaon or Bangalore) or infer `household_type` based on service category (e.g., assuming AC service implies a "family" or "homeowner").
- **What Was Wrong / Rejected**:
  Violates core project rule: *"Never infer city, household type, alternative used, need trigger, or customer intent without explicit evidence."* Hallucinated demographics distort customer segment analysis and interview screener design.
- **What Was Changed**:
  Enforced strict grounding in prompt and client:
  - `city`: Restricted to explicit mentions of known metropolitan areas; defaults to `null`.
  - `household_type`: Defaults to `"unclear"` unless explicit words like "bachelor", "living alone", "my wife", "my kids" appear.
  - `alternative_used`: Defaults to `"unclear"` unless offline providers, WhatsApp groups, or competitors are explicitly named.
  - `need_trigger`: Defaults to `null` unless breakdown, season, festival, moving, or guests are explicitly described.
- **Prompt / Code Diff Reference**:
  `engine/prompts/tagger_v1.md`, `engine/tagger.py` (`MockLLMClient.tag_review()`), `tests/test_tagger.py` (`TestGroundingAndStrictNonInference`).

---

### Decision 005: Exclusion of InstaHelp Records from Core Tagging Pipeline
- **Date**: 2026-11-23
- **Component / Phase**: Pipeline Ingestion (`engine/tagger.py`)
- **What the AI Proposed / Generated**:
  > Tagging all 200 normalized records indiscriminately into the core dataset.
- **What Was Wrong / Rejected**:
  The project brief (Level 0/1) explicitly dictates: *"Quick-service housekeeping (InstaHelp) is excluded"* from the repeat-booking metric and core discovery engine. Daily maid attendance, maid cancellations, and hourly dishwashing dynamics are fundamentally distinct from core home services (cleaning, salon, plumbing, AC repair).
- **How It Was Caught**:
  Normalizer audit identifying 16 InstaHelp records in the raw dataset.
- **What Was Changed**:
  `engine/tagger.py` inspects `is_instahelp`. All 16 records with `is_instahelp: true` are filtered out before tagging. They are preserved intact in `data/processed/normalized_reviews.jsonl` for separate evaluation, leaving exactly 184 eligible core reviews for tagging.
- **Prompt / Code Diff Reference**:
  `engine/tagger.py` (`run_tagging_pipeline()`), `tests/test_tagger.py` (`TestPipelineEndToEndAndInstaHelpExclusion`).

---

### Decision 006: Separation of Source Metadata and Tagging Namespaces with Per-Tag Evidence Tracking
- **Date**: 2026-11-23
- **Component / Phase**: Data Architecture & Schema Packaging (`engine/tagger.py`)
- **What the AI Proposed / Generated**:
  > Flat record merging normalized review fields and tags into a single level, with only one global evidence quote.
- **What Was Wrong / Rejected**:
  Flattening collapses the distinction between raw platform provenance (review ID, app version, thumbs up, vote count) and inferential AI tags. Furthermore, a single string `evidence_quote` is insufficient when a review provides evidence for multiple disparate tags (e.g., category evidence vs. rebook signal evidence).
- **What Was Changed**:
  Adopted a modular schema layout:
  - `review_id`: Root identifier.
  - `normalized_review`: Complete normalized source record preserved untouched.
  - `tags`: Exact 16-field dictionary conforming to `docs/schema.md`.
  - `tag_evidence`: Per-tag dictionary mapping each attribute to its verbatim supporting excerpt and individual confidence rating.
  - `metadata`: Model name, prompt version, human review routing flag, and diagnostic reasons.
- **Prompt / Code Diff Reference**:
  `engine/tagger.py` (`tag_single_review()`), `tests/test_tagger.py` (`test_strict_separation_of_source_and_tagging_fields`).


---

### Decision 007: Resolution of Schema Ambiguities for `post_service_expectation`, `unmet_need`, and `alternative_used`
- **Date**: 2026-11-23
- **Component / Phase**: Tagging Schema & Policy Hardening (`docs/schema.md`, `engine/tagger.py`, `engine/prompts/tagger_v1.md`)
- **What the AI Proposed / Generated**:
  > 1. Defaulted `post_service_expectation` to `"nothing"` whenever customer reviews omitted post-service mentions.
  > 2. Defined `unmet_need` as a non-nullable string, synthesizing generic template strings (e.g., `"satisfactory home service execution"`) on negative reviews where no specific unmet need was articulated.
  > 3. Lacked an explicit enforcement boundary between `alternative_used="none"` and `alternative_used="unclear"`.
- **What Was Wrong / Rejected**:
  1. Defaulting `post_service_expectation` to `"nothing"` conflated an unmentioned post-service journey with an affirmative customer desire for zero contact or interaction.
  2. Forcing a non-nullable string for `unmet_need` fabricated customer intent and distorted JTBD analysis by populating generic placeholder complaints.
  3. Conflating `"none"` with `"unclear"` in `alternative_used` falsely assumed exclusive platform loyalty when the review merely omitted discussing substitutes.
- **How It Was Caught**:
  Methodological schema audit and empirical inspection of the 115 pilot tagged records.
- **What Was Changed**:
  1. **`post_service_expectation`**: Added `"unclear"` to the allowed enum values across `docs/schema.md`, `engine/tagger.py`, and `engine/prompts/tagger_v1.md`. Restricted `"nothing"` strictly to reviews where the customer explicitly indicates that no post-service follow-up, advice, or contact is wanted (e.g., "do not call me", "leave me alone").
  2. **`unmet_need`**: Made explicitly nullable (`str | None`). Set to `null` whenever the customer does not explicitly voice a concrete friction, unmet need, or missing capability.
  3. **`alternative_used`**: Enforced that `"none"` is used ONLY when the customer explicitly confirms no alternative was used (e.g., "I did not call anyone else", "only use UC"). When no alternative is mentioned, it defaults strictly to `"unclear"`.
  4. **Schema Fidelity**: Preserved all 16 original tagging fields in the core schema dictionary, retaining `tag_evidence` as an external extension for granular quote validation.
- **Prompt / Code Diff Reference**:
  `docs/schema.md`, `engine/tagger.py` (`POST_SERVICE_EXPECTATION_ENUM`, `validate_16_schema_fields()`, `MockLLMClient.tag_review()`), `engine/prompts/tagger_v1.md`, `tests/test_tagger.py`.


---

### Decision 008: AI Tagging Pipeline v2 Policy Hardening and Semantic Classification
- **Date**: 2026-11-23
- **Component / Phase**: AI Tagging Pipeline v2 (`engine/prompts/tagger_v2.md`, `engine/tagger.py`, `tests/test_tagger.py`)
- **What the AI Proposed / Generated**:
  > Empirical audit of the 115 pilot tagged records produced by tagger_v1 identified five recurring failure modes:
  > 1. In review ID `06b45346-6f25-4d49-9b01-13d980482c2c`, `"regular customer"` triggered `rebook_signal: "rebooked"`, despite the review describing an abrupt cancellation and churn.
  > 2. In review ID `14816200493`, a washing machine repair was misclassified as `category: "plumber"` due to incidental mention of a `"water inlet pipe"`.
  > 3. In review IDs `14816200493` and `8d00e9ce-01f8-4263-80f1-73d55a830fe7`, matching the token `"advice"` triggered `post_service_expectation: "next-service advice"` even though the text was peer advice to other consumers (*"My advice to other customers"*) or an explicit warning against upsell advice (*"don't ever take advice of their engineers"*).
  > 4. In review IDs `372c9648-73fe-4245-8121-a8f198701159` and `4e4e2ef9-6dd6-40cc-a65b-a3f327daf7f0`, complaints about warranty claim rejection and 10-day warranty expiration triggered `post_service_expectation: "warranty clarity"`.
  > 5. Across 43 negative reviews lacking concrete operational friction, `unmet_need` was populated with generic synthetic strings (`"satisfactory home service execution"`) rather than `null`.
- **What Was Wrong / Rejected**:
  - Conflating past tenure with present rebooking intent misrepresents churned users as active repeat customers.
  - Token-level keyword matching without semantic scoping assigns incorrect categories based on internal machine components.
  - Naive keyword matching on "advice" inverts or distorts customer intent.
  - Conflating warranty claim failure with post-service documentation expectations distorts JTBD analysis.
  - Fabricating generic unmet needs violates the non-inference requirement.
- **How It Was Caught**:
  - Deterministic audit and manual inspection of all 115 records in `data/tagged/tagged_reviews.jsonl`.
- **What Was Changed**:
  1. **Tagger Prompt v2**: Authored `engine/prompts/tagger_v2.md` codifying explicit negative constraints for historical tenure, peer advice, warranty grievances, and appliance service scoping.
  2. **Pipeline v2 Implementation**:
     - `rebook_signal`: Distinguishes historical status from current intent; `"regular customer"` alone never sets `rebooked`. Active cancellation/churn context yields `"unclear"` or `"will_not_rebook"`.
     - `category`: Classifies the anchor booked service. Appliance repair (washing machine, refrigerator, RO purifier) is routed to `"other"`, preventing incidental plumbing/electrical misclassification.
     - `post_service_expectation`: Contextual advice matching excludes peer advice and warnings. Warranty complaints are excluded from `"warranty clarity"`. Default is `"unclear"`.
     - `unmet_need`: Strictly `null` unless the customer articulates a concrete operational friction (cancellations, overcharging, property damage).
  3. **Dataset Protection**: Existing tagger_v1 datasets (`data/tagged/tagged_reviews.jsonl` and `data/tagged/review_queue.jsonl`) are preserved unchanged. Tagger v2 defaults to `data/tagged/tagged_reviews_v2.jsonl` and `data/tagged/review_queue_v2.jsonl`.
  4. **Regression Test Suite**: Added `TestTaggerV2AuditRegressions` in `tests/test_tagger.py` covering all six audit cases and backwards compatibility.
- **Prompt / Code Diff Reference**:
  `engine/prompts/tagger_v2.md`, `engine/tagger.py` (`MockLLMClient`, `run_tagging_pipeline()`), `tests/test_tagger.py` (`TestTaggerV2AuditRegressions`).


---

### Decision 009: Golden Set Annotator Note Consistency Correction for Review `43582ef1-c85a-4b67-ad13-662ab7a72dcb`
- **Date**: 2026-11-24
- **Component / Phase**: Golden Dataset Validation & Annotation Review (`data/golden/golden_set.jsonl`, `tests/test_golden_set.py`)
- **What the AI Proposed / Generated**:
  > Review `43582ef1-c85a-4b67-ad13-662ab7a72dcb` (`"Stay away from their Spa sessions , they are just going to treat you as their ginni pig ! horrible horrible support"`) had its ground-truth tag set to `rebook_signal: "unclear"`, but its persisted `annotator_notes` in `data/golden/golden_set.jsonl` stated: `"Spa sessions mapped to other category per approved decision; explicit churn warning."`
- **What Was Wrong / Rejected**:
  Describing the note as an `"explicit churn warning"` directly conflicted with the approved ground-truth label `rebook_signal="unclear"`. While the customer advised others to *"Stay away"*, this constitutes a warning to third-party prospective users rather than an explicit statement of personal churn or future rebooking intentions. Stating "explicit churn warning" in the note created cognitive dissonance and schema inconsistency with `rebook_signal="unclear"`.
- **How It Was Caught**:
  Rigorous review of `tests/test_golden_set.py` where exact equality between approved ground-truth expectations and golden dataset records was enforced without prefix-based bypasses.
- **What Was Changed**:
  Updated ONLY the `annotator_notes` field for review ID `43582ef1-c85a-4b67-ad13-662ab7a72dcb` in `data/golden/golden_set.jsonl` to:
  `"Spa sessions mapped to other category per approved decision; warning to other users does not establish personal rebooking intent, so rebook_signal is unclear."`
  All 16 `human_tags` fields and all other 29 records in the golden dataset remained strictly untouched.
- **Prompt / Code Diff Reference**:
  `data/golden/golden_set.jsonl` (line 6), `docs/decisions.md` (Decision 009), `tests/test_golden_set.py` (`test_annotated_records_ground_truth`, `test_record_43582ef1_consistency_and_approved_annotation`).

---

### Decision 010: Gemini Prompt Corrections v3: Eliminating Dissatisfaction-to-Churn Leakage and Disambiguating Appliance vs Premises Deep Clean
- **Date**: 2026-11-24
- **Component / Phase**: AI Prompt Calibration & Evaluation (`engine/prompts/tagger_v3.md`, `engine/tagger.py`, `tests/test_gemini_tagger.py`)
- **What the AI Proposed / Generated**:
  Evaluation of Gemini 3.5 Flash-Lite predictions against the 8 overlapping records in the human-annotated golden set (`evals/gemini_pilot_vs_golden.json`) revealed two systematic defects in `tagger_v2`:
  1. *Dissatisfaction-to-churn leakage in `rebook_signal`*: The model incorrectly predicted `will_not_rebook` for reviews with severe dissatisfaction, low ratings, or partner cancellations, even when the customer stated no explicit intent regarding future bookings (e.g., review `06b45346-6f25-4d49-9b01-13d980482c2c` where a cancellation caused a 1-star rating; review `4e4e2ef9-6dd6-40cc-a65b-a3f327daf7f0` regarding warranty expiration; review `1876c25b-ae08-413a-a1db-753bc635d070` regarding salon quality).
  2. *Overly broad category matching for deep clean*: In review `36b24dd5-1cd2-4752-9a46-68307d86382c` (*"Chimney deep clean service..."*), the model classified the review as `deep clean` instead of `other`, because the tokens "deep clean" overpowered the appliance context ("chimney").
- **What Was Wrong / Rejected**:
  1. Conflating strong negative sentiment, bad partner behavior, or poor ratings with churn violates the core repeat-booking schema requirement: `will_not_rebook` requires direct, unambiguous proof of future non-rebooking intent (e.g., "I will never book again"). Without explicit churn language, the intent is unknown and must be tagged `unclear`.
  2. Classifying appliance deep cleaning (such as chimney, washing machine, refrigerator) as `deep clean` corrupts category segmentation. `deep clean` is strictly reserved for premises cleaning (home, bathroom, kitchen, sofa). Appliance cleaning belongs to `other` (or `AC`).
- **How It Was Caught**:
  Rigorous golden-set evaluation across 8 overlapping records between Gemini v2 pilot/retry outputs and the ground-truth human annotations in `data/golden/golden_set.jsonl`, generating 50% accuracy on `rebook_signal` and 87.5% on `category`.
- **What Was Changed**:
  1. Authored `engine/prompts/tagger_v3.md`:
     - Added strict negative constraints for `rebook_signal`: `will_not_rebook` strictly requires direct unambiguous intent. Explicitly enumerates non-qualifying factors (low ratings, anger, complaints, technician misconduct, partner cancellations, refund requests, past regular status, general warnings to others) that must NEVER independently trigger `will_not_rebook`. Default is `unclear`.
     - Explicit category disambiguation: `deep clean` is strictly for premises. Appliance cleaning/repair (including chimney deep clean, washing machine, RO purifier, etc.) routes to `other`.
  2. Preserved backward compatibility:
     - `engine/prompts/tagger_v2.md` and `engine/prompts/tagger_v1.md` remain completely unmodified.
     - `engine/tagger.py` updated to support `v3` alongside `v1` and `v2`.
     - Output paths default to `data/tagged/tagged_reviews_v3.jsonl` and `data/tagged/review_queue_v3.jsonl`.
  3. Added comprehensive regression tests in `tests/test_gemini_tagger.py`:
     - 8 specific regression cases covering angry 1-star, technician complaints, partner cancellations, regular customer cancellations, explicit "never book again", explicit "will not use this app again", chimney deep clean (`other`), and home deep clean (`deep clean`).
- **Prompt / Code Diff Reference**:
  `engine/prompts/tagger_v3.md`, `engine/tagger.py` (`DEFAULT_PROMPT_PATH_V3`, `MockLLMClient`, `GeminiLLMClient`, `run_tagging_pipeline`, `main`), `tests/test_gemini_tagger.py` (`TestTaggerV3PromptRegressions`), `evals/gemini_pilot_vs_golden.json`, `docs/gemini_golden_evaluation.md`.

---

### Decision 011: Gemini Prompt v3.1 Taxonomy Alignment (Spa to Other) and Rebooking Future Intent Calibration
- **Date**: 2026-11-24
- **Component / Phase**: AI Prompt Calibration & Taxonomy Hardening (`engine/prompts/tagger_v3_1.md`, `engine/tagger.py`, `docs/schema.md`, `docs/golden_set_guidelines.md`, `tests/test_gemini_tagger.py`)
- **What the AI Proposed / Generated**:
  Comprehensive 30-record golden evaluation of Gemini v3 (`gemini-3.5-flash-lite`, `engine/prompts/tagger_v3.md`) revealed two remaining policy misalignments:
  1. *Spa Taxonomy Conflict*: In `engine/prompts/tagger_v3.md`, the definition of `salon` included `"spa"` and `"massage"`. However, human golden ground truth (`data/golden/golden_set.jsonl`, Decision 009) and the approved schema map Spa sessions and body massage to `other` (as distinct wellness therapy rather than grooming). Consequently, reviews `43582ef1-c85a-4b67-ad13-662ab7a72dcb` and `14809078193` were classified by Gemini v3 as `salon` instead of `other`.
  2. *Exclusion of Explicit Future Booking Intent from `rebook_signal`*: `tagger_v3` rule stated: `"Tag 'rebooked' ONLY when the customer explicitly confirms they booked another service or continue to rebook actively"`. This caused reviews with explicit, unambiguous future booking intent (such as `14809078193`: *"Will definitely book her again"*, *"would recommend and book her anytime again!"*) to be tagged as `unclear` instead of `rebooked`.
- **What Was Wrong / Rejected**:
  1. Grouping Spa/massage under `salon` conflates beauty and grooming services (haircuts, facial, waxing, threading, manicure) with full-body wellness/spa therapies, violating the approved category taxonomy established in the human golden set (where `43582ef1` and `14809078193` are tagged as `other`).
  2. Restricting `rebooked` solely to completed past bookings ignored strong, unprompted forward-looking intent statements (e.g. *"I will definitely book her again"*), which are prime repeat-booking signals. Conversely, treating historical repeat usage alone or general praise ("Thank you UC") as repeat booking was also rejected, as it falsely conflates past tenure or general satisfaction with active repeat intent.
- **How It Was Caught**:
  1. Complete 30-record golden benchmark evaluation (`evals/gemini_v3_full_golden.json`, `docs/gemini_v3_full_golden_evaluation.md`) where `category` mismatches were traced directly to `salon -> other` spa classifications.
  2. Audit of `14809078193` and `bb81193d` human annotations and confusion matrix analysis.
- **What Was Changed**:
  1. Authored `engine/prompts/tagger_v3_1.md`:
     - **Spa Taxonomy Rule**: Removed `spa` and `massage` from `salon`. Explicitly mapped spa sessions, body spa, and body massage to `other`. Clarified `salon` is strictly for beauty and grooming.
     - **Future Intent Rule**: Updated `rebook_signal` so explicit future booking intention (e.g., *"I will definitely book her again"*, *"would book anytime again"*) maps to `rebooked`.
     - **Historical Tenure & Praise Constraints**: Codified that historical repeat usage alone (e.g. *"regular customer"*, *"using UC for 5 years"*) without future intent maps to `unclear`. General satisfaction or praise alone ("Thank you UC") maps to `unclear`. Explicit refusal maps to `will_not_rebook`. Dissatisfaction, cancellations, or complaints alone never establish churn.
  2. Updated Documentation:
     - `docs/schema.md`: Clarified `category` (spa/massage $\rightarrow$ `other`) and `rebook_signal` (future intent $\rightarrow$ `rebooked`, general praise $\rightarrow$ `unclear`).
     - `docs/golden_set_guidelines.md`: Clarified Field 4 (Spa $\rightarrow$ `other`) and Field 7 (explicit future intent $\rightarrow$ `rebooked`).
  3. Preserved Artifacts & Pipeline Versioning:
     - `engine/prompts/tagger_v3.md` and all previous outputs preserved untouched.
     - `engine/tagger.py` updated to support `version="v3_1"` with default paths `tagged_reviews_v3_1.jsonl` and `review_queue_v3_1.jsonl`.
  4. Added Regression Tests in `tests/test_gemini_tagger.py`:
     - Added `TestTaggerV3_1PromptRegressions` covering explicit future intent (`rebooked`), historical usage alone (`unclear`), general praise alone (`unclear`), explicit refusal (`will_not_rebook`), and spa taxonomy (`other`).
- **Prompt / Code Diff Reference**:
  `engine/prompts/tagger_v3_1.md`, `engine/tagger.py`, `docs/schema.md`, `docs/golden_set_guidelines.md`, `docs/decisions.md` (Decision 011), `tests/test_gemini_tagger.py` (`TestTaggerV3_1PromptRegressions`).

---

### Decision 012: Experimental Groq Token-Efficiency Optimization v3_2: Prompt Consolidation, Max Completion Tokens, and Calibrated Rate-Limit Pacing
- **Date**: 2026-11-25
- **Component / Phase**: AI Tagging Pipeline Optimization (`engine/prompts/tagger_v3_2.md`, `engine/tagger.py`, `tests/test_groq_v3_2.py`, `docs/groq_v3_2_implementation.md`)
- **What the AI Proposed / Generated**:
  Empirical token-efficiency audit (`docs/groq_token_efficiency_audit.md`) based on the 10-review Groq pilot (`data/tagged/groq_pilot/groq_pilot_metrics.json`) revealed three optimization opportunities:
  1. *Prompt Redundancy*: `engine/prompts/tagger_v3_1.md` (11,858 characters, 1,603 words, ~3,285 prompt tokens) suffered from triple redundancy: rules were stated in Section 1 (Core Directives), restated under Section 2 (16-Field Schema), repeated in Section 3 (JSON schema comments), and demonstrated across a 1,000-character mock JSON template.
  2. *Unbounded Reasoning Tokens*: `openai/gpt-oss-120b` generated an average of 858 completion/reasoning tokens per call (peaking at 1,226 tokens) for a structured output JSON requiring only ~160 tokens. An unconstrained completion limit allowed runaway reasoning tokens to consume rate limits.
  3. *Rate-Limit Window Premature Retries*: Groq Tier-1 TPM limits operate on a rolling 60-second window. With `max_backoff=10.0s`, client retries fired before the 60-second window reset, causing successive HTTP 429 failures.
- **What Was Wrong / Rejected**:
  1. We rejected removing or simplifying any of the 16 schema fields, negative trigger constraints, evidence-grounding rules, or review-queue conditions. Classification fidelity cannot be sacrificed for token savings.
  2. We rejected modifying `tagger_v3_1.md` in-place, preserving `v3_1` as a frozen benchmark.
  3. We rejected unmeasured or speculative token savings claims; all prompt reductions are reported as character/word counts and estimated projections until empirical live measurement is conducted.
- **How It Was Caught**:
  Empirical audit of the 10-review Groq pilot metrics (`docs/groq_token_efficiency_audit.md`).
- **What Was Changed**:
  1. **Tagger Prompt v3.2**: Authored `engine/prompts/tagger_v3_2.md`, reducing character count from 11,858 to 8,871 (140 lines, 1,192 words, ~25% reduction in characters and ~750 estimated tokens) by eliminating duplicate descriptions and the verbose sample JSON block while preserving 100% of calibration rules, spa-to-other rule, appliance mappings, rebooking rules, negative triggers, evidence grounding, and review queue conditions.
  2. **Pipeline v3.2 Versioning**: Updated `engine/tagger.py` to support `version="v3_2"` across `GroqLLMClient`, `GeminiLLMClient`, `MockLLMClient`, and CLI (`--version v3_2`). Default outputs route to `data/tagged/tagged_reviews_v3_2.jsonl` and `data/tagged/review_queue_v3_2.jsonl`.
  3. **Completion Limits**: Added `max_completion_tokens` parameter (initially 1,000) in `GroqLLMClient` and CLI (`--max-completion-tokens`).
  4. **Pacing & Backoff Calibration**: Configured `GroqLLMClient` defaults to `initial_backoff=3.0s` and `max_backoff=35.0s`. Enforced that rate-limit reset headers (`retry-after`, `x-ratelimit-reset-requests`, `x-ratelimit-reset-tokens`) are honored without truncation below header duration, ensuring retries do not fire before rolling quota replenishment.
  5. **Unit & Regression Testing**: Added `tests/test_groq_v3_2.py` with 25 comprehensive tests (181 total suite tests passing) covering prompt loading, completion limits, header pacing, and regressions for all critical v3.1 policies under v3.2.
  6. **Dataset Protection**: Verified all six baseline datasets remain strictly unmodified.
- **Prompt / Code Diff Reference**:
  `engine/prompts/tagger_v3_2.md`, `engine/tagger.py`, `tests/test_groq_v3_2.py`, `docs/decisions.md` (Decision 012), `docs/groq_v3_2_implementation.md`.

---

### Decision 013: Versioned Level 1 Data Expansion, Compliance Blockers, and Silent Non-Returner Blind Spot
- **Date**: 2026-11-25
- **Component / Phase**: Level 1 Data Collection, Bias Analysis, and Opportunity Analysis (`engine/collectors/investor_relations.py`, `engine/normalizer_v2.py`, `engine/analyze_evidence.py`)
- **What Was Decided**:
  1. Preserved all 6 baseline files untouched (verified by SHA-256) and wrote expanded raw collections to separate versioned files (`data/raw/google_play_reviews_v2.jsonl` with `1,100` new reviews; `data/raw/investor_relations_excerpts.jsonl` with `222` excerpts from 14 public IR PDFs) and `data/processed/normalized_evidence_v2.jsonl` (`1,522` total items; `1,378` core-eligible).
  2. Documented external access blockers honestly rather than bypassing restrictions: Reddit returned HTTP `403` without OAuth (`REDDIT_CLIENT_ID` unset), YouTube Data API v3 lacked `YOUTUBE_API_KEY`, Apple RSS returned 0 entries on page 1 during v2 re-fetch, and Trustpilot/MouthShut automated scraping was skipped per ToS.
  3. Explicitly recorded in `docs/bias_analysis.md` and `docs/opportunity_analysis.md` that `nothing_went_wrong = true` is `0/184` in baseline tagged reviews—confirming app-store reviews cannot observe silent non-returners and requiring Level 4 interviews to test recall-gap hypotheses.
- **Prompt / Code Diff Reference**:
  `engine/collectors/investor_relations.py`, `engine/normalizer_v2.py`, `engine/analyze_evidence.py`, `docs/bias_analysis.md`, `docs/opportunity_analysis.md`, `docs/sources.md`, `tests/test_expanded_pipeline.py`.



