# Sampling Manifest: 30-Review Golden Dataset

This manifest documents the selection methodology, stratification rationale, and record-by-record provenance for the 30-review golden dataset (`data/golden/golden_set.jsonl`).

---

## 1. Population and Sampling Methodology

- **Total Ingested Reviews**: 200 (100 Google Play, 100 Apple App Store)
- **InstaHelp Exclusions**: 16 quick-housekeeping records excluded per project brief rules (Decision 005)
- **Eligible Core Pool**: 184 reviews (94 Google Play, 90 Apple App Store)
- **Target Golden Set Size**: Exactly 30 reviews
- **Platform Stratification**: Exactly 15 Google Play reviews (50%) and 15 Apple App Store reviews (50%)

### Selection Principles
1. **Semantic Stratification**: Selected to represent five distinct review types: Substantive Positive, Substantive Negative, Neutral / Mixed, Ambiguous / Edge Cases, and Low-Information.
2. **Category Diversity**: Ensures representation across all detectable core categories (AC, deep clean, plumber, salon, pest control, other/appliances, and unknown).
3. **Rating Independence**: Selection was based on text inspection rather than star scores alone, intentionally including severe rating-polarity conflicts (e.g. 4-star reviews complaining of no-shows or looting).
4. **Regression Edge Cases**: Incorporated key audit cases from `docs/decisions.md` (e.g. regular customer in churn context, washing machine pipe vs plumber, warning against engineer advice, warranty expiration disputes) to ensure the golden dataset tests model boundary conditions.
5. **Privacy Redaction Compliance**: All personal names of service professionals appearing in review text or titles are sanitized using `[NAME_REDACTED]` in accordance with Decision 001.

---

## 2. Stratification Summary Statistics

### By Platform & Stratum
| Stratum | Google Play | Apple App Store | Total |
|---|---|---|---|
| Substantive Positive | 3 | 3 | 6 |
| Substantive Negative | 5 | 4 | 9 |
| Neutral / Mixed | 1 | 2 | 3 |
| Ambiguous / Edge Case | 3 | 4 | 7 |
| Low-Information | 3 | 2 | 5 |
| **Total** | **15** | **15** | **30** |

### By Star Rating
| Star Rating | Count | Percentage |
|---|---|---|
| ★ 5 | 10 | 33.3% |
| ★ 4 | 4 | 13.3% |
| ★ 3 | 4 | 13.3% |
| ★ 2 | 1 | 3.3% |
| ★ 1 | 11 | 36.7% |
| **Total** | **30** | **100.0%** |

### By Target Service Category
| Service Category | Count | Percentage |
|---|---|---|
| `unknown` | 13 | 43.3% |
| `salon` | 5 | 16.7% |
| `deep clean` | 4 | 13.3% |
| `other` | 4 | 13.3% |
| `AC` | 2 | 6.7% |
| `plumber` | 1 | 3.3% |
| `pest control` | 1 | 3.3% |
| **Total** | **30** | **100.0%** |

---

## 3. Complete Review Inventory and Selection Rationale

| # | Review ID | Platform | Rating | Date | Category | Stratum | Excerpt | Selection Rationale |
|---|---|---|---|---|---|---|---|---|
| 1 | `bb81193d-cf36-41b3-abce-4d201b3c4a59` | Play Store | ★5 | 2026-11-22 | `salon` | Substantive Positive | "its worth it for our salon experience . The last one was the best..." | Explicit repeat booking signal in salon category with positive customer sentiment ('its worth it for our salon experience . The last one was the best'). Tests detection of repeat usage and positive experience type. |
| 2 | `99226311-a2f2-4ecf-b1ed-7d28518cd95e` | Play Store | ★5 | 2026-11-21 | `deep clean` | Substantive Positive | "Very good kitchen cleaning done by [NAME_REDACTED]. Very polite, ..." | Detailed positive kitchen cleaning review containing sanitized service provider token ([NAME_REDACTED]). Tests deep clean category recognition and validation of privacy redaction tokens in ground truth. |
| 3 | `75c91a8d-c132-48e2-a420-ea4221bb6059` | Play Store | ★5 | 2026-11-22 | `unknown` | Substantive Positive | "Great experience at Urban Company! Professional, well-mannered an..." | High-satisfaction general home services review expressing staff punctuality and strong recommendation intent. Tests general praise without explicit service category identification. |
| 4 | `36b24dd5-1cd2-4752-9a46-68307d86382c` | Play Store | ★1 | 2026-11-22 | `plumber` | Substantive Negative | "This rating is for the Company and the way they cheat people whil..." | Detailed plumbing booking grievance involving urgent cancellation within 5 minutes and unjustified fee imposition. Critical test for plumber category and cancellation fee unmet need. |
| 5 | `4e4e2ef9-6dd6-40cc-a65b-a3f327daf7f0` | Play Store | ★1 | 2026-11-22 | `other` | Substantive Negative | "Recently I have availed Chimney deep clean service from UC on Nov..." | Chimney deep clean review with oil leakage after 15 days and 10-day warranty expiration dispute. Tests appliance classification (other, not deep clean alone) and warranty grievance handling (Decision 008). |
| 6 | `43582ef1-c85a-4b67-ad13-662ab7a72dcb` | Play Store | ★1 | 2026-11-22 | `salon` | Substantive Negative | "Stay away from their Spa sessions , they are just going to treat ..." | Strong negative warning regarding Spa sessions ('treat you as their ginni pig'). Tests negative sentiment within salon/spa category and strong negative churn advice. |
| 7 | `1876c25b-b9ea-4720-9fcd-d11a7caa4bf1` | Play Store | ★1 | 2026-11-22 | `other` | Substantive Negative | "‼️Third class customer care support. They don't provide any RO te..." | Detailed operational failure regarding RO water purifier technician unavailability and support unresponsiveness. Tests RO/appliance category and customer support failure friction. |
| 8 | `6b579933-e83a-459c-b7c7-73f83b669c16` | Play Store | ★2 | 2026-11-21 | `unknown` | Substantive Negative | "For the last few months, the app has not been very responding. Su..." | Sole 2-star review in Play Store dataset. Describes severe app unresponsiveness and freezing during ongoing bookings, preventing visibility into active service status. Reclassified to Substantive Negative because textual content describes purely negative technical failure without neutral or mixed elements. |
| 9 | `bec86ea9-9a8f-495d-a091-1e4ec7843980` | Play Store | ★3 | 2026-11-22 | `unknown` | Neutral / Mixed | "At UC instead of 1 hr standard service, you provide only 45 minut..." | Sole 3-star review in Play Store dataset. Explicit complaint about duration shortening (45 minutes delivered vs 1 hour standard promised). Tests duration unmet need and neutral rating. |
| 10 | `06b45346-6f25-4d49-9b01-13d980482c2c` | Play Store | ★1 | 2026-11-22 | `unknown` | Ambiguous / Edge Case | "I had been a regular customer of urban company but due to one per..." | Decision 008 Audit Case 1: Customer states past tenure as 'regular customer' but gives 1 star due to partner cancellation and churn. Sanitized per privacy policy with [NAME_REDACTED] for partner name. Crucial test that past tenure is not falsely tagged as rebooked. |
| 11 | `b04a772a-f857-4356-ae3d-fa83612fdb90` | Play Store | ★4 | 2026-11-22 | `unknown` | Ambiguous / Edge Case | "after booking cancellation from UC and not arriving at the opted ..." | Severe rating-polarity conflict: 4-star rating awarded, but text reports booking cancellation and failure to arrive at scheduled time slot. Tests annotator discipline in prioritizing text over stars. |
| 12 | `372c9648-73fe-4245-8121-a8f198701159` | Play Store | ★1 | 2026-11-22 | `deep clean` | Ambiguous / Edge Case | "Pathetic Warranty Service. Good for low level cleaning jobs. Do N..." | Decision 008 Audit Case 5: Nuanced comparative review stating UC is 'good for low level cleaning jobs' but warning against expensive painting or repairs due to pathetic warranty. Tests cross-category distinction. |
| 13 | `bbf12112-379a-4f54-9112-99d788cb9d2e` | Play Store | ★5 | 2026-11-22 | `unknown` | Low-Information | "good work" | Terse 5-star review ('good work', 9 characters). Tests low-information review policy (confidence: low, rebook_signal: unclear, category: unknown, non-inference of rebooking). |
| 14 | `b31f176a-29af-4454-bf5d-4eacf25b7a38` | Play Store | ★4 | 2026-11-22 | `unknown` | Low-Information | "ok ok" | Terse 4-star review ('ok ok', 5 characters). Tests ambiguous/tepid sentiment evaluation on extremely short text. |
| 15 | `83ea578e-2a5e-41fc-a0b7-6b542aa3953e` | Play Store | ★1 | 2026-11-22 | `unknown` | Low-Information | "lut rahe hai" | Terse 1-star review in Hindi vernacular slang ('lut rahe hai', 12 characters). Tests non-English colloquial slang handling for overcharging/pricing dissatisfaction. |
| 16 | `14815231009` | App Store | ★5 | 2026-11-20 | `AC` | Substantive Positive | "Service par excellence. I have been using urban company for AC se..." | Detailed 5-year repeat usage review specifically evaluating AC services. Directly compares UC technicians favorably against brand competitors ('500% better than incompetent AC company technicians'). |
| 17 | `14805610926` | App Store | ★5 | 2026-11-18 | `deep clean` | Substantive Positive | "Professional and very co-operative. Had booked for deep cleaning ..." | Exemplary 1,196-character end-to-end positive journey review for home deep cleaning (kitchen and washrooms). Sanitized per privacy redaction policy with [NAME_REDACTED] for lead service professionals. Covers app booking, prompt arrival, and thorough execution. |
| 18 | `14809078193` | App Store | ★5 | 2026-11-19 | `salon` | Substantive Positive | "Incredible Experience with Body Spa – Ask for [NAME_REDACTED]!. [..." | Substantive positive spa/salon review detailing deep tissue massage and exceptional satisfaction with specific service professional. Sanitized per privacy redaction policy with [NAME_REDACTED] in title and body. Tests salon subcategory and provider commendation. |
| 19 | `14816200493` | App Store | ★1 | 2026-11-21 | `other` | Substantive Negative | "Misleading UC Technicians - Fraud attempts. Extremely Poor Experi..." | Decision 008 Audit Cases 2 & 3: 1,792-character review detailing washing machine repair, inlet pipe misdiagnosis, fraud attempts, and customer peer advice ('My advice to other customers'). Tests appliance vs plumber and advice directionality. |
| 20 | `14811772838` | App Store | ★1 | 2026-11-20 | `deep clean` | Substantive Negative | "Unethical service. The cleaning person spilled over excess cleani..." | Severe property damage review in bathroom cleaning where technician spilled excess cleaning acid, damaging the entire tile floor with zero compensation. Tests property damage friction. |
| 21 | `14813121635` | App Store | ★1 | 2026-11-20 | `other` | Substantive Negative | "Selling faulty Native M1 Pro Purifier with no return/refund optio..." | Extensive 1,010-character grievance regarding proprietary Native M1 Pro Water Purifier defects, leakage, and refund refusal. Tests proprietary appliance classification (other) and refund friction. |
| 22 | `14800891393` | App Store | ★1 | 2026-11-17 | `unknown` | Substantive Negative | "Unreliable bookings, ghosting, and arbitrary job refusals. Urban ..." | Substantive breakdown of platform reliability deterioration, consecutive technician reassignments, ghosting, and arbitrary job refusals. Tests platform operational breakdown and partner fulfillment friction. |
| 23 | `14819013371` | App Store | ★3 | 2026-11-21 | `salon` | Neutral / Mixed | "Price hikes. I have been regularly using UC for salon services fo..." | 3-star review from 6-year regular salon customer balancing acceptable service quality against steep price hikes and platform fees. Tests long-term tenure, price sensitivity, and neutral sentiment. |
| 24 | `14787997500` | App Store | ★3 | 2026-11-13 | `unknown` | Neutral / Mixed | "Review. The service providers are good but the app is no longer a..." | 3-star review presenting mixed evaluation: compliments offline service providers while criticizing app usability degradation, selection glitches, and poor UI. Tests provider vs app separation. |
| 25 | `14784151525` | App Store | ★5 | 2026-11-12 | `AC` | Ambiguous / Edge Case | "Made our life very easy. We are UC customers since many years now..." | Multi-category long-term customer review with 5 stars overall, but an explicit negative callout on AC servicing quality ('Ac servicing quality wasn’t good. Rest all the services are amazing'). Tests multi-category nuance. |
| 26 | `14811553737` | App Store | ★4 | 2026-11-19 | `unknown` | Ambiguous / Edge Case | "Looting customers. They are looting people with their services. T..." | Rating-polarity conflict: 4-star rating awarded despite Title 'Looting customers' and text detailing hidden plan details and pre-emptive plan cancellations. Tests text primacy over stars. |
| 27 | `14792849957` | App Store | ★5 | 2026-11-15 | `pest control` | Ambiguous / Edge Case | "Excellent app for all and everyday needs. I have been using Urban..." | Broad multi-category umbrella review citing repeat usage since 'Urban Clap' era across salon, spa, carpentry, pest control, and UC-help. One of very few explicit pest control mentions in corpus. |
| 28 | `14793598838` | App Store | ★4 | 2026-11-15 | `salon` | Ambiguous / Edge Case | "Pedicure. Therapist not reported" | Rating-polarity conflict: 4-star rating with title 'Pedicure' and text 'Therapist not reported'. Tests salon category detection on short text and partner no-show classification under high star rating. |
| 29 | `14807881351` | App Store | ★5 | 2026-11-19 | `unknown` | Low-Information | "Good" | Ultra-terse 4-character 5-star review (Title: 'Good', Text: 'Good'). Tests low-information non-inference rules on Apple App Store platform. |
| 30 | `14812347184` | App Store | ★3 | 2026-11-20 | `unknown` | Low-Information | "Surge Charge. Very expensive." | Short 3-star review (Title: 'Surge Charge', Text: 'Surge Charge. Very expensive.'). Tests brief pricing friction identification without service category or journey context. |

