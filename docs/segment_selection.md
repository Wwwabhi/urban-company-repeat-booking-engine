# Level 3: Segment Selection

**Project:** Urban Company Repeat-Booking Discovery Engine  
**Constraint Check:** No solution or product feature is proposed in this document. All segment criteria are designed for direct recruitment via a one-line screener in Level 4 interviews.

---

## 1. Evidence Reality Check Before Segmentation

Repository data (`data/processed/analysis_summary.json`) shows severe demographic and behavioral sparsity in public reviews:
- Explicit **city** is stated in only **9 / 1,248 (`0.7%`)** core consumer reviews (`3/184` baseline tagged; `0/30` golden).
- Explicit **household type** is stated in only **4 / 1,248 (`0.3%`)** core consumer reviews (`2/184` baseline tagged; `0/30` golden).
- Specific **service category** is missing in **90.4% (`1,128/1,248`)** of core consumer reviews (`155/184` `unknown` in baseline tagged).
- `nothing_went_wrong = true` is **0 / 184** and `recall_gap = true` is **0 / 184** in baseline tags (`docs/bias_analysis.md`).

**Implication:** Public evidence identifies *candidate categories and friction patterns*, while **household composition, city, and silent non-return behavior** must be captured directly through the Level 4 interview screener rather than inferred from app-store text.

---

## 2. Candidate Customer Segments

1. **Segment A — Urban Renters / Flatmates / Adults Living Alone with Single-Category Anchor Booking**
   - *Profile:* Metro residents (`22–38` yrs) living alone or with flatmates, whose anchor UC booking was a single category (e.g., `deep clean`, `AC`, or `salon`) and who have had other household needs (`plumber`, `electrician`, `appliance`, `cleaning`) in the past 90 days.
   - *Why relevant:* Lack inherited family vendor networks, rely heavily on society guards, WhatsApp groups, or quick local fixes when something breaks.

2. **Segment B — Episodic Appliance / Deep-Clean Households**
   - *Profile:* Metro households whose anchor UC booking was an episodic maintenance/repair job (`AC`, `deep clean`, or appliance repair like `chimney`/`RO`/`washing machine`—`77` `other` + `9` `AC` + `1` `deep clean` in core sample).
   - *Why relevant:* High concentration of post-service expectation/warranty friction (`22` mentions in `1,248` core; golden `4e4e2ef9`, `1876c25b`) and long inter-service intervals where UC recall decays before the next 90-day need.

3. **Segment C — Routine Salon-at-Home Users**
   - *Profile:* Repeat grooming customers (`13` `salon` in `1,248` core; `11/184` baseline; golden `bb81193d`, `14819013371`).
   - *Why relevant:* High natural repeat cadence, but price-hike complaints (`14819013371`) and single-category lock-in (using UC for salon without considering UC for home repairs).

4. **Segment D — Urgent Breakdown Users (Plumbing / Electrical)**
   - *Profile:* Households booking emergency fixes (`17` `plumber`, `14` `electrician` in `1,248` core; `2` explicit offline-alternative mentions in `plumber`).
   - *Why relevant:* Urgency favors immediate local/society technicians over app slot scheduling.

---

## 3. Segment Comparison Matrix

| Criterion | Segment A: Metro Adults Living Alone / Flatmates (Single-Category Anchor) | Segment B: Episodic Appliance / Deep-Clean Households | Segment C: Routine Salon-at-Home Users | Segment D: Urgent Breakdown Users (Plumber / Electrician) |
|---|---|---|---|---|
| **Repository Evidence** | Indirect only (`0.3%` household tags in app stores; `11` offline-switch mentions) | **Strongest category-level friction** (`77` `other` + `9` `AC`; `22` warranty/post-service gaps; `4e4e2ef9`, `1876c25b`) | Moderate (`13` core, `11` baseline; `14819013371` price sensitivity) | Small (`31` combined; `2` offline-switch in `plumber`) |
| **90-Day Opportunity Size** | **High** — frequent new household needs, no entrenched family vendor | **High** — cross-category expansion opportunity after episodic anchor | **Medium** — already repeat within salon; pricing sensitivity limits non-discount levers | **Low–Medium** — emergency urgency hard to shift customer-side |
| **Interview Accessibility** | **High** — easy to recruit 5–6 metro adults via personal/alumni/peer networks | **Medium–High** — common, though fewer people did appliance repair in last 90 days | **Medium** — skews to specific demographic; harder to separate price-driven churn | **Medium** — sporadic emergency events |
| **Alignment with Core Question** *(why non-return when nothing went wrong)* | **Very High** — directly tests `recall_gap` and offline defaults after a fine anchor booking | **High** — tests post-service continuity & category-blindness | **Medium** — salon churn is often price/beautician-driven rather than recall-driven | **Low–Medium** — urgency & slot availability dominate |

---

## 4. Selected Primary Segment

**Selected Segment:**  
> **Metro adults living alone or with flatmates who completed at least one Urban Company booking in a core category in the last 6 months, had zero major operational complaints on that booking, and have since encountered other household service needs.**

### One-Line Recruitment Screener
> *"Do you live alone or with flatmates in a metro city, have you completed an Urban Company home service booking (excluding daily maid/InstaHelp) in the last 6 months, and have you had any other home repair, cleaning, or maintenance need since then?"*

### Why This Segment
1. **Directly isolates the brief's core question:** By filtering for completed bookings without major operational failures, we avoid re-discovering 1★ cancellation/support complaints (`103` support + `82` cancellation mentions already well-documented in `docs/opportunity_analysis.md`) and focus squarely on **silent non-return**.
2. **Maximizes cross-category & recall-gap signal:** Adults living alone or with flatmates manage home tasks themselves without inherited family contractors, making their moment-of-need decision loop (`UC` vs `society group` vs `local technician` vs `DIY`) observable in a 30-minute interview.
3. **High recruitment feasibility:** Easily screened and mixed across `rebooked within 90 days` vs `did not rebook within 90 days` and across multiple anchor categories (`AC`, `deep clean`, `salon`, `plumber`).
