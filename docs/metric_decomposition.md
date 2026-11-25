# Level 2: Business Metric Decomposition

**Project:** Urban Company Repeat-Booking Discovery Engine  
**Evidence Base:** `data/processed/analysis_summary.json` (`1,522` total items; `1,378` core-eligible; `184` baseline LLM-tagged; `30` golden; `222` IR excerpts)  
**Epistemic Rule:** Every figure below distinguishes **measured repository evidence** from **structural assumptions** that require Urban Company internal data or Level 4 interviews to quantify.

---

## 1. Exact Business Metric Definition

Per Section 1 of the project brief:

> **Strategic Goal:** Increase the percentage of customers who book another service within 90 days of a completed booking.

**Formal cohort definition:**
1. Pick a calendar month $M$. Every customer whose **first completed booking** in month $M$ is in a **core category** (`AC`, `deep clean`, `plumber`, `salon`, `electrician`, `pest control`, or `other` core services) is counted once. That booking is the **anchor booking**.
2. **Exclusions:** Quick-service housekeeping (**InstaHelp**) is excluded (`144` of `1,522` collected items are flagged as InstaHelp and excluded from core analysis).
3. **Conversion event:** A customer counts as **returning** if they complete **any later booking**, in **any core category**, within **90 days** of the anchor booking.
4. **Quality filter:** Redos, warranty claims, and bookings ending in a refund do **not** count as returning bookings.
5. **Commercial context:** Repeat customers account for ~84% of Urban Company's net transaction value (brief Section 1), and UC's Q3 FY26 Shareholder Letter (`ir_587032c9807572c1`) reports `7.826M` Annual Transacting Users across `51+` cities with `4.79 / 5.0` average rating (`ir_87ca9260e8dc17ac`).

---

## 2. Complete Metric Decomposition Tree

$$\text{Rebook Rate}_{90\text{d}} = P(\text{Need arises}_{90\text{d}}) \times P(\text{Thinks of UC} \mid \text{Need}) \times P(\text{Picks UC over alternatives} \mid \text{Considers UC}) \times P(\text{Booking completed} \mid \text{Attempts}) \times P(\text{Booking counts} \mid \text{Completed})$$

```
90-Day Repeat-Booking Rate
├── 1. P(Need arises within 90 days)
│      ├── Seasonal / weather triggers (e.g., summer AC, monsoon pest control)
│      ├── Episodic / life-event triggers (move-in, guests, festival cleaning)
│      └── Routine / recurring triggers (salon grooming, appliance upkeep)
├── 2. P(Customer thinks of UC when need arises)
│      ├── App & brand recall (remembers UC at the moment of need vs offline habit)
│      ├── Category awareness (knows UC covers plumber/electrician/appliance, not just anchor category)
│      └── Use-case clarity (knows whether need warrants a pro vs DIY vs waiting)
├── 3. P(Customer picks UC over alternatives)
│      ├── Perceived price / fee predictability vs local provider or society group
│      ├── Trust & quality expectation from anchor experience
│      └── Slot convenience & urgency fit (immediate breakdown vs scheduled)
├── 4. P(Booking is completed)
│      ├── App UX & service-selection friction
│      ├── Partner availability & slot adherence (no last-minute cancellation/no-show)
│      └── Customer-side readiness (clarity on scope, prep, eligibility)
└── 5. P(Booking counts — no redo, warranty claim, or refund)
       ├── First-time-right execution quality
       └── Post-service care, usage guidance & warranty clarity
```

---

## 3. Branch-by-Branch Explanation & Evidence Mapping

| Branch | Mechanism & Link to 90-Day Rebooking | Measured Repository Evidence | Assumption / Blind Spot |
|---|---|---|---|
| **1. $P(\text{Need arises}_{90\text{d}})$** | No household or personal need within 90 days → zero opportunity to rebook, regardless of satisfaction. | **Directional:** Core categories differ in cadence (`salon` routine vs `AC` seasonal vs `deep clean` episodic). `1,248` core consumer reviews span only 23 days in Nov 2026 (`2026-11-02`–`24`), missing summer peaks. | **Assumption:** Urban multi-category households experience multiple home/personal needs within 90 days, but true 90-day need incidence requires Level 4 interviews / internal UC cohort data. |
| **2. $P(\text{Thinks of UC} \mid \text{Need})$** | Even satisfied customers fail to return if they default to a local technician, society WhatsApp group, or forget UC covers the new category. | **Measured gap / blind spot:** `recall_gap = true` is **0/184** and `nothing_went_wrong = true` is **0/184** in baseline app-store tags; `11/1,248` (`0.9%`) core reviews explicitly mention offline alternatives/churn; `1/30` golden (`14816200493`) switched to `local provider`. | **Assumption:** Silent non-returners leave no app-store trace (`docs/bias_analysis.md`). High-frequency recall and cross-category awareness are major unmeasured leaks. |
| **3. $P(\text{Picks UC} \mid \text{Considers UC})$** | Customer remembers UC, compares it against local provider / DIY / another app, and chooses whether to book. | **Measured:** `63/1,248` (`5.0%`) core reviews flag pricing/surge/cancellation fee opacity (`10` in 4–5★); `14` high-rating reviews flag delays; golden `14819013371` (6-yr salon user) cites price hikes. | **Assumption:** Price sensitivity vs convenience trade-off for routine/minor jobs (`plumber`, `electrician`) cannot be quantified from 1★-skewed reviews alone. |
| **4. $P(\text{Booking completed})$** | Customer attempts to book on UC, but drops off due to app UX, slot unavailability, or partner cancellation. | **Measured:** `82/1,248` (`6.6%`) core reviews cite cancellations/no-shows (`72` in 1–2★); `42/1,248` (`3.4%`) cite delays; `2/1,248` cite app tracking bugs (`6b579933`). | **Operational constraint:** Partner supply and dispatch reliability are outside customer-side MVP scope. |
| **5. $P(\text{Booking counts})$** | Completed booking turns into a redo, warranty dispute, or refund—disqualifying it from the metric and damaging future trust. | **Measured:** `103/1,248` (`8.3%`) cite support/grievance failures; `40/1,248` (`3.2%`) cite technician quality/damage; `22/1,248` (`1.8%`) cite warranty/post-service gaps (e.g., golden `4e4e2ef9`, `1876c25b`). | **Assumption:** Clearer post-service usage guidance and warranty expectations reduce avoidable disputes, though actual execution quality depends on UC operations. |

---

## 4. Customer-Side Product Influence Classification

Per project constraints (**no discounts, coupons, memberships, pricing changes, or changes to professionals/UC internal ops; MVP acts only on the customer's side**):

| Branch | Customer-Side Product Influence | Measurable Proxy (Public / Customer-Reported Only) |
|---|---|---|
| **1. $P(\text{Need arises}_{90\text{d}})$** | **No** (external household/weather events) | Self-reported frequency of household tasks in interviews |
| **2. $P(\text{Thinks of UC} \mid \text{Need})$** | **Yes (High)** — recall, category discovery, maintenance timing, and triage clarity | Share of customers reporting UC as first option at moment of need; category-coverage awareness |
| **3. $P(\text{Picks UC} \mid \text{Considers UC})$** | **Partly** — cannot change UC prices, but can clarify scope, prep, and when a pro is vs isn't needed | Pre-booking confidence; perceived value vs offline alternatives without discounts |
| **4. $P(\text{Booking completed})$** | **Partly (Low)** — cannot control partner dispatch, but can reduce customer-side booking/prep misunderstandings | Self-reported readiness and expectation alignment before slot |
| **5. $P(\text{Booking counts})$** | **Partly (Low–Medium)** — cannot control technician skill, but can set post-service care/warranty expectations | Self-reported post-service clarity and avoidable warranty confusion |

---

## 5. Ranked Branches (Prioritization)

| Rank | Branch | Size of Gap (Engine + Hypothesis) | Customer-Side Influence | Interview Testability | Rationale |
|---|---|---|---|---|---|
| **1** | **$P(\text{Thinks of UC} \mid \text{Need})$** | **High** (suspected primary silent-churn driver; `0/184` visible in app stores due to selection bias) | **Yes (High)** | **High** ("Walk me through the last time something needed fixing") | Directly answers *"why people do not rebook even when nothing went wrong"* without touching pricing or partner ops. |
| **2** | **$P(\text{Picks UC} \mid \text{Considers UC})$** | **Medium–High** (`63` fee/pricing + `11` offline-switch mentions in `1,248` core) | **Partly** | **High** ("Who did you compare or consider calling, and why?") | Reveals whether non-price factors (prep uncertainty, scope ambiguity, habit) vs price drive offline switching. |
| **3** | **$P(\text{Booking counts})$** *(post-service clarity)* | **Medium** (`22` warranty/post-service gap mentions; `4e4e2ef9`, `1876c25b`) | **Partly (Low–Medium)** | **Medium** ("What happened after the job finished?") | Post-service expectation gaps weaken trust and leave no structured maintenance hook for the next 90 days. |
| **4** | **$P(\text{Booking completed})$** | **High in 1★ reviews** (`82` cancellations), **Low** customer-side control | **Partly (Low)** | Medium | Driven primarily by UC partner supply and dispatch, outside customer-side MVP scope. |
| **5** | **$P(\text{Need arises}_{90\text{d}})$** | External | **No** | High | Cannot be manufactured by product; varies naturally by category (`salon` vs `AC` vs `deep clean`). |

---

## 6. Leading & Lagging Metrics

- **Lagging Business Metric (North Star):** **90-Day Core Repeat-Booking Rate** — share of month-$M$ core anchor customers completing $\ge 1$ valid non-InstaHelp, non-redo/non-refund booking in any core category within 90 days. *(Requires UC internal cohort data; cannot be measured directly from public data.)*
- **Leading Customer-Side Indicators (Measurable in MVP / Interviews):**
  1. **Top-of-Mind Recall Rate:** Share of users who report thinking of Urban Company first when a new household need arises.
  2. **Category-Breadth Awareness:** Share of single-category anchor users who accurately identify $\ge 3$ other core UC categories for upcoming needs.
  3. **Actionable Next-Step Rate:** Share of triaged needs ending in a clear customer-confirmed decision (`book pro`, `DIY`, or `wait`).
  4. **30-Day Return / Artifact Save Rate:** Share of users who save/export a maintenance timeline or return to the tool within 30 days.
- **Guardrail Metrics:**
  1. **"No service needed" triage share** (must stay $> 0$ so the product does not over-nudge unnecessary bookings).
  2. **Pushiness / trust complaint rate** and **service-fact hallucination rate** (must remain near zero).
