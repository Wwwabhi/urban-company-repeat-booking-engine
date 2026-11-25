# Data Sources Tracking

This document records the provenance, access methods, status, and item counts for all public data sources utilized in the Urban Company Repeat-Booking Discovery Engine, adhering to compliance and terms-of-service guidelines.

## Source Tracking Table

| Source | Access Method | Collection Status | Item Count | Date Range | Notes |
|---|---|---|---|---|---|
| Google Play Store | Public scraper (`google-play-scraper` package via Python) | Expanded v2 Complete (`1,200` total: `100` baseline + `1,100` v2) | 1200 | 2026-11-02 to 2026-11-24 | Verified app `com.urbanclap.urbanclap` (Title: "Urban Company: Home Services", Developer: "Urban Company"). Baseline `100` reviews preserved untouched in `data/raw/google_play_reviews.jsonl`. Expanded `1,100` deduplicated reviews collected on 2026-11-25 into `data/raw/google_play_reviews_v2.jsonl` (`--dedupe-from data/raw/google_play_reviews.jsonl`) with `collected_at` UTC timestamps. `48` reviews were excluded pre-storage across the two v2 runs (`46` `potential_address_cue`, `2` `potential_postal_pincode`) without logging text. `42` InstaHelp reviews retained in raw data for downstream filtering. |
| Apple App Store | Apple Public Customer Review RSS Feed (`itunes.apple.com/in/rss/customerreviews`) | Baseline Complete (`100`); v2 RSS check returned `0` new items | 100 | 2026-11-12 to 2026-11-21 | Verified app ID `1032480595` (Bundle: `com.urbanclap.customer`, Title: "Urban Company: Home Services", Developer: "Urban Company Limited", Country: `in`). Baseline `100` reviews preserved untouched in `data/raw/app_store_reviews.jsonl`. On 2026-11-25, re-querying page 1 of the RSS feed returned 0 entries (feed empty/throttled at collection time), so no v2 records were added. Limitations: Apple RSS feed is capped at 10 pages (~500 recent reviews) and historical back-catalog is inaccessible. |
| Reddit | Official Reddit API (PRAW) / Public JSON | Blocked (No OAuth credentials; public JSON `403`) | 0 | N/A | Blocker verified 2026-11-25: `REDDIT_CLIENT_ID` is not configured in environment and unauthenticated `reddit.com/r/india/search.json` returned HTTP `403`. No login bypass or scraping attempted per compliance rules. |
| YouTube | YouTube Data API v3 (`commentThreads`) | Blocked (`YOUTUBE_API_KEY` not configured) | 0 | N/A | Blocker verified 2026-11-25: `YOUTUBE_API_KEY` is not set in environment. Requires official API key to query `commentThreads`. |
| Trustpilot | Manual copy of public pages | Skipped (automated scraping restricted by ToS) | 0 | N/A | Automated scraping avoided per ToS and project brief rules; no manual copy performed in this automated batch. |
| MouthShut | Manual copy of public pages | Skipped (automated scraping restricted by ToS) | 0 | N/A | Automated scraping avoided per ToS and project brief rules; no manual copy performed in this automated batch. |
| Shareholder Letters (Investor Relations) | Public PDFs via `engine/collectors/investor_relations.py` (`pypdf`) | Complete (`Q3 FY26`, `Q4 FY26`, `Q1 FY27`, `Q2 FY27`) | 213 | 2026-01-31 to 2026-10-31 | Discovered from `https://investorrelations.urbancompany.com/financials` on 2026-11-25. Extracted relevant paragraphs on repeat usage, retention, cohorts, ATUs, InstaHelp, and service quality into `data/raw/investor_relations_excerpts.jsonl` with `source_url`, `page_number`, and `collected_at`. |
| Earnings Calls & Press Releases (IR) | Public PDFs via `engine/collectors/investor_relations.py` (`pypdf`) | Complete (`Q2 FY26`–`Q2 FY27`) | 9 | 2025-10-31 to 2026-10-31 | `2` Earnings Call excerpts + `7` Results Press Release excerpts extracted from public IR PDFs into `data/raw/investor_relations_excerpts.jsonl`. Note: several transcript PDFs use single-newline formatting, limiting multi-paragraph block extraction (`0–1` excerpts per transcript). |

---

## Access & Ethics Rules
1. **No Logged-In Pages or Private APIs**: Never touch Urban Company's internal systems, private APIs, customer accounts, or logged-in portal views.
2. **Respect Robots.txt & Terms of Service**: Where automated scraping is restricted, limit extraction to small, manual public samples and record the specific source URL.
3. **Anonymization, Redaction & Privacy Exclusion Policy**:
   - **Stripping Metadata**: Usernames and profile images/avatars are stripped at collection time and never stored.
   - **Automated PII Redaction**: Phone numbers and email addresses are automatically redacted from review text using regex replacement (`[PHONE_REDACTED]`, `[EMAIL_REDACTED]`).
   - **Contextual Third-Party Name Redaction**: Identifiable third-party personal names (e.g., service professionals/technicians named in reviews) are contextually detected (via honorifics, role cues, attribution prepositions, commendation phrases, and worker enumerations) and redacted as `[NAME_REDACTED]`. Platform, brand, and proprietary product/service names ("Urban Company", "UC", "InstaHelp", "Ikea", "Native M1", "AC", "AI", "Kanpeki", "O3", etc.) are strictly protected via a whitelist to avoid over-redaction.
   - **Exclusion of Address/Pincode Data**: Reviews containing unresolved physical address indicators (e.g., flat, apartment, house numbers, street/colony/road cues) or 6-digit postal pincodes are strictly excluded from storage in `data/raw`.
   - **Zero Secondary Storage**: Excluded reviews are discarded immediately. Their text is never persisted to any quarantine, dead-letter, or secondary file.
   - **Safe Audit Logging**: The collector logs only aggregate exclusion counts and reason categories (e.g. `potential_address_cue`, `potential_postal_pincode`), completely omitting review IDs and all review text.
4. **InstaHelp Raw Retention**: Quick-service housekeeping (InstaHelp) posts are not filtered or deleted from raw collected data, ensuring full data provenance; they will be excluded strictly during downstream core-metric analysis.
