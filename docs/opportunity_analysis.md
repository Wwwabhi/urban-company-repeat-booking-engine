# Opportunity Analysis: Urban Company Repeat-Booking Discovery Engine

**Generated from:** `engine/analyze_evidence.py` → `data/processed/analysis_summary.json`  
**Evidence base:** `1,522` total normalized items (`1,248` core consumer reviews excl. InstaHelp, `130` non-InstaHelp IR excerpts, `184` baseline LLM-tagged reviews, `30` golden-set reviews)

---

## 1. Analytical Guardrails

Per the project brief:
1. **Operational pain points ≠ repeat-booking barriers:** A 1-star complaint about a cancellation fee or rude technician explains *dissatisfaction*, not why a satisfied customer (`nothing_went_wrong = true`) fails to book again within 90 days.
2. **Historical repeat usage ≠ future intent:** Phrases like *"I have been using UC for 5 years"* (`rebooked`) do not guarantee future retention if a recent failure occurred, nor does a complaint prove `will_not_rebook` unless explicitly stated.
3. **Directional counts only:** Because **90.4% (`1,128/1,248`)** of core consumer reviews do not name a category and **98.9% (`182/184`)** of baseline tagged reviews have `rebook_signal = unclear`, all counts below are directional indicators paired with sample sizes.

---

## 2. Major Recurring Customer Pain Points (Core Consumer Reviews, `N = 1,248`)

To avoid pooling biased ratings, pain-point frequencies are split by rating tier (`1–2★` vs `4–5★`):

| Pain Point Theme | Total (`N=1,248`) | Low Rating `1–2★` | High Rating `4–5★` | Primary Nature |
|---|---|---|---|---|
| **Customer support & grievance failure** | **103 (8.3%)** | 94 | 4 | Post-issue recovery failure (bot loops, unresponsive escalation) |
| **Booking cancellations & no-shows** | **82 (6.6%)** | 72 | 4 | Fulfilment reliability (partner last-minute cancel, slot miss) |
| **Pricing, surge & cancellation fee opacity** | **63 (5.0%)** | 49 | 10 | Price hikes, unexpected cancellation/surge fees, wallet refunds |
| **Delay & punctuality issues** | **42 (3.4%)** | 26 | 14 | Late arrival or slot shifts (notably appears in 14 high-star reviews too) |
| **Technician quality, behavior & damage** | **40 (3.2%)** | 38 | 1 | Rudeness, incomplete work, property/appliance damage |
| **Warranty & post-service follow-up gap** | **22 (1.8%)** | 18 | 0 | Short warranty windows (e.g., 10 days), expired claim support |
| **Explicit offline alternative / churn signal** | **11 (0.9%)** | 11 | 0 | Named switch to local technician, competitor, or app uninstall |
| **App & booking-tracking UX** | **2 (0.2%)** | 2 | 0 | App unresponsiveness, inability to track ongoing booking |

### Category & Source Differences (Where Sample Size Permits)
- **Unspecified category (`n=1,128`):** Dominated by platform-level trust frictions—support (`72`), cancellations (`65`), and pricing/fees (`46`).
- **`other` — Appliance repair / Spa / Carpentry / Painting (`n=77`):** High concentration of support failures (`23/77`, `29.9%`), cancellations (`11`), pricing (`9`), and warranty/post-service disputes (`5`, e.g., Native RO purifier, chimney reinstallation leakage in golden set `4e4e2ef9`, washing machine misdiagnosis `14816200493`).
- **`plumber` (`n=17`) & `electrician` (`n=14`):** Small samples, but `plumber` shows pricing/fee friction (`4`), quality (`3`), support (`3`), and explicit offline-alternative mentions (`2`).
- **`AC` (`n=9`) & `salon` (`n=13`):** Sample sizes are too small (`n < 15`) for reliable cross-category generalization in November; `AC` shows technician quality mentions (`4/9`), while `salon` shows support (`3`) and pricing (`3`).
- **Source differences:** `App Store` (`n=100`, 34% 1-star) contains longer narrative reviews (e.g., multi-paragraph appliance repair and warranty disputes in the golden set) than `Play Store` (`n=1,200`, 30.7% 1-star, 33.7% `<20` chars).
- **Corporate disclosures (`N=222` IR excerpts):** In Q3 FY26 Shareholder Letter (`ir_454a3734c3ecd554`), UC leadership explicitly links *"Faster service fulfilment, consistent quality, and fair pricing"* to *"repeat usage"*, and notes rapid growth in `InstaHelp` (`1.61M` orders in Q3 FY26) alongside `7.8M+` Annual Transacting Users across India Consumer Services.

---

## 3. Repeat-Booking Barriers vs. Service Failures

Separating what stops repeat booking when **nothing went wrong** vs. when **something broke**:

1. **Silent / Low-Friction Non-Return (`nothing_went_wrong = true`, `recall_gap = true`):**
   - **Observed count in baseline tagged (`184`):** **0 / 184**.
   - **Implication:** App-store reviews do not capture customers who had a fine experience and simply forgot UC or called a local provider next time. Only **1 review** in the golden set (`14816200493`, `alternative_used = "local provider"`) explicitly named an offline substitute—and that was triggered by a ₹2,500 vs ₹300 repair quote dispute, not a smooth experience.
2. **Post-Service Expectation & Maintenance Continuity Gap (`22` warranty/follow-up mentions in `1,248`; `1/10` in Groq v3.2 golden pilot):**
   - Customers finish a one-off booking (e.g., chimney deep clean `4e4e2ef9`, RO purifier `1876c25b`) with unclear post-service maintenance expectations, warranty windows, or usage guidelines. Even without a catastrophic failure, lack of post-service continuity leaves no structured reason to return to UC before the next breakdown.
3. **Price & Cancellation-Fee Friction on Low-Urgency / Routine Needs (`63` mentions; `10` in 4–5★ reviews):**
   - Notably, **10 high-rating (4–5★) reviews** still flag pricing/surge fees and **14 high-rating reviews** flag delays—meaning even *satisfied* customers experience friction that can push routine or price-sensitive categories (e.g., salon price hikes in golden `14819013371`, plumber/electrician minor jobs) back to offline providers.
4. **Trust Spillover from Fulfilment & Support Failures (`103` support + `82` cancellation mentions):**
   - While these are service failures rather than "nothing went wrong" barriers, a single unresolved cancellation or support bot loop in one category can block cross-category trial within 90 days (e.g., golden `06b45346`: *"I had been a regular customer of urban company but... giving 1 star as he cancelled booking"*).

---

## 4. Ranked Opportunity Table (Customer-Side Product Lens)

All opportunities below respect the brief's constraints (**no discounts, coupons, memberships, pricing changes, or changes to professional earnings/management**; customer-side product only):

| Rank | Opportunity / Barrier Theme | Supporting Evidence (Actual Counts) | Categories Most Affected | Potential 90-Day Impact | Confidence | Rationale & Customer-Side Product Influence |
|---|---|---|---|---|---|---|
| **1** | **Post-service continuity, maintenance timeline & warranty clarity** | **22** warranty/post-service gap mentions (`1,248` core); **14** high-rating delay/expectation frictions; **2** detailed golden cases (`4e4e2ef9`, `1876c25b`) lacking usage guidelines/warranty clarity | `other` (appliances, RO, chimney), `AC`, `deep clean`, `pest control` | **High** | **Medium** | **Directly influenceable customer-side.** After a completed job, customers lack a personal maintenance schedule, clear warranty/care checklist, or "what to expect next" guide—weakening recall before the next 90-day need. |
| **2** | **Moment-of-need triage & category discovery (bridging offline default)** | **11** explicit local-provider/churn mentions (`1,248` core); **1** golden `local provider` switch (`14816200493`); **0/184** `recall_gap` visible in app-store tags (known blind spot) | `plumber`, `electrician`, `AC`, `other` (appliances) | **High** | **Low–Medium** *(requires interview validation)* | **Directly influenceable customer-side.** Customers default to local technicians or society WhatsApp groups when unsure if a problem needs a pro, DIY, or wait. A customer-side triage & prep companion addresses this without touching pricing. |
| **3** | **Pre-booking expectation setting & cancellation/slot clarity** | **82** cancellation/no-show mentions (`1,248` core); **63** pricing/cancellation-fee opacity mentions (`10` in 4–5★); golden `36b24dd5`, `06b45346`, `14800891393` | `unspecified` (all), `plumber`, `deep clean`, `other` | **Medium–High** | **Medium–High** | **Partly influenceable customer-side.** While partner supply and fee policies are outside scope, a customer-side prep checklist (what to verify, slot/cancellation policy clarity, when to book) reduces avoidable friction. |
| **4** | **Customer support & escalation readiness** | **103** customer support failure mentions (`1,248` core; `94` in 1–2★) | `unspecified` (all), `other` (appliances) | **Medium** *(retention floor)* | **High** *(as pain point)* / **Low** *(for customer-side tool)* | **Outside customer-side MVP scope.** Support bots and refund/grievance workflows require internal UC operations changes, not a standalone customer-side tool. |
| **5** | **Technician skill & quality consistency** | **40** quality/behavior mentions (`1,248` core); corroborated by UC Q3 FY26 Shareholder Letter (`ir_454a3734c3ecd554`) | `AC`, `plumber`, `electrician`, `other` | **Medium** | **High** *(as pain point)* / **Low** *(for customer-side tool)* | **Outside customer-side MVP scope.** Partner training and quality enforcement violate the "no changes to professionals" constraint. |

---

## 5. Key Unresolved Questions for Level 4 Interviews

1. Among customers whose last UC booking had **zero operational issues**, how many had another household need within 90 days—and what did they do instead (`local provider`, `WhatsApp/society group`, `DIY`, or `UC`)?
2. Does **category-blindness** (not realizing UC covers plumber/electrician/appliance repair after booking `salon` or `AC`) drive more non-returns than price or support friction?
3. Would a customer-side **post-service maintenance timeline + need triage** tool increase top-of-mind recall at the next household trigger?
