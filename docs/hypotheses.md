# Level 3: Problem & Alternative Hypotheses

**Primary Segment:** Metro adults living alone or with flatmates who completed a core Urban Company booking in the last 6 months without major operational issues and have since had other household service needs.  
**Constraint Check:** These are falsifiable **problem hypotheses** to be tested in Level 4 interviews—no product solution is proposed or assumed.

---

## 1. Core Unmet Need (Hypothesis-Level, To Be Validated)

When a new household or maintenance need arises after a satisfactory Urban Company booking, customers lack **moment-of-need clarity and effortless recall**—specifically knowing *whether* the issue requires a professional (vs DIY/waiting), *whether* Urban Company covers that specific category reliably, and *what* to expect on scope and post-service care—causing them to default to familiar offline channels (local providers, society/WhatsApp referrals) or defer maintenance altogether.

---

## 2. Primary Problem Hypothesis (H1 — Recall Gap & Offline Default)

> **H1:** *Metro adults living alone or with flatmates who had a satisfactory first/anchor Urban Company booking do not rebook within 90 days because, when a subsequent household need arises, they default to a local provider, society/WhatsApp referral, or DIY instead of thinking of Urban Company as their go-to option for that category.*

### Evidence Supporting / Motivating H1 (Directional)
- `0 / 184` baseline tagged app-store reviews show `nothing_went_wrong = true` or `recall_gap = true` (`docs/bias_analysis.md`), indicating silent non-returners are invisible in app-store data.
- `11 / 1,248` core consumer reviews explicitly mention offline alternatives or switching, and golden review `14816200493` explicitly documents turning to a `local provider`.
- `90.4%` (`1,128 / 1,248`) of core reviews do not associate UC with a specific category, consistent with single-category mental framing.

### Falsification Criteria (What Would Support or Reject H1 in Level 4 Interviews)
- **Supports H1:** $\ge 3$ of 5–6 interviewees who did *not* rebook within 90 days report having subsequent household needs, had no complaint about their prior UC booking, and either forgot UC covered the new need or defaulted to a society guard / local technician / WhatsApp group without opening the UC app.
- **Rejects H1:** Interviewees *did* think of and open the UC app when the next need arose, but actively chose not to book for another reason (supporting H2, H3, or H4 instead).

---

## 3. Alternative (Rival) Hypotheses

### H2 — Category-Specific Price / Fee Friction Overcomes Habit
> **H2:** *Customers in this segment do think of Urban Company at the moment of need, but actively reject it for routine or minor jobs because perceived pricing, surge charges, or cancellation/inspection fees feel higher or less transparent than a local provider.*

- **Motivating evidence:** `63 / 1,248` (`5.0%`) core consumer reviews cite pricing, surge, or cancellation-fee opacity—including `10` high-rating (`4–5★`) reviews; golden `14819013371` (6-year salon user) and `36b24dd5` (cancellation fee) highlight fee friction.
- **Supports H2:** Interviewees report checking UC prices/fees at the moment of need and deliberately choosing a local provider because UC's total price or fee structure felt unjustified.
- **Rejects H2:** Interviewees never checked UC prices before calling an offline provider, or did not cite price as the deciding factor.

### H3 — Post-Service Continuity & Scope Uncertainty (No Maintenance Hook)
> **H3:** *Customers do not rebook within 90 days because, after a completed booking, they have no clear view of what maintenance is due next or what post-service care/warranty applies—so subsequent needs go unrecognized or are deferred until an urgent breakdown favors an immediate local fix.*

- **Motivating evidence:** `22 / 1,248` (`1.8%`) core reviews cite warranty or post-service follow-up gaps; golden `4e4e2ef9` (chimney reinstallation oil leak after 15 days vs 10-day warranty) and `1876c25b` (no usage guidelines/precautions) show missing post-service clarity.
- **Supports H3:** Interviewees report postponing routine upkeep because they did not know when service was next needed, or losing trust after unclear post-service care/warranty expectations.
- **Rejects H3:** Interviewees had clear, recognized household needs within 90 days and knew what to do, yet still skipped UC.

### H4 — Trust Spillover from Fulfilment / Support Friction (Even Without Personal Failure)
> **H4:** *Even when a customer's own anchor booking went fine, prior or peer experiences with partner cancellations, delays, or unresponsive support make them hesitant to rely on Urban Company for time-sensitive needs.*

- **Motivating evidence:** `103 / 1,248` (`8.3%`) customer support failures, `82 / 1,248` (`6.6%`) cancellations/no-shows, and `42 / 1,248` (`3.4%`) delays (`14` even in `4–5★` reviews); golden `06b45346` shows a regular customer churning after a single last-minute cancellation.
- **Supports H4:** Non-returners cite slot uncertainty, fear of last-minute cancellation, or peer horror stories as the reason they avoided UC on their next need.
- **Rejects H4:** Non-returners express high trust in UC's reliability and simply never thought of UC or had no urgent slot concern.

---

## 4. Summary Decision Matrix for Level 4 Interviews

| Hypothesis | Core Mechanism | Interview Signal to Watch | Primary Alternative if Disproved |
|---|---|---|---|
| **H1 (Primary)** | Moment-of-need recall gap & offline default | Did not open UC app; called local/society contact out of habit | H2 / H3 / H4 |
| **H2 (Rival)** | Deliberate price / fee rejection | Opened UC app, saw price/fee, chose local provider | H1 / H3 |
| **H3 (Rival)** | Unrecognized maintenance / post-service gap | Deferred need or lacked maintenance/warranty clarity | H1 / H4 |
| **H4 (Rival)** | Reliability / slot-trust hesitation | Avoided UC due to fear of cancellation/delay | H1 / H2 |
