# Urban Company Repeat-Booking Discovery Engine (`engine-app/`)

Interactive Streamlit front end for Level 1, Step 1.9 of the Urban Company Repeat-Booking Discovery Engine.

## Pages
1. **Overview** — Evidence totals (`1,522` total, `1,378` core-eligible, `144` InstaHelp excluded, `184` LLM-tagged, `30` golden), source/rating distributions, and ranked opportunity themes.
2. **Opportunity Explorer** — Ranked opportunities with evidence counts, confidence/impact ratings, and filters by source, keyword category, and rating tier.
3. **Customer Voice** — Searchable, PII-scrubbed review explorer showing original text, existing LLM tags, human-review status, and explicit `"Not yet tagged by LLM"` indicators.
4. **Bias Analysis** — App-store bimodal skew vs UC's 4.79/5.0 rating base rate, missing silent non-returners (`0/184` `nothing_went_wrong`), category/city/household sparsity, and collection blockers.
5. **Live AI Tagging** — Interactive Groq `openai/gpt-oss-120b` (`tagger_v3_2`) tagging with pre-tagging PII redaction and graceful handling when `GROQ_API_KEY` is absent.
6. **Methodology** — Collection, cleaning/deduplication, privacy filtering, schema/golden evaluation, and known limitations.

## Run Locally

From the repository root:

```bash
.venv/bin/pip install -r engine-app/requirements.txt
.venv/bin/streamlit run engine-app/app.py
```

All pages except **Live AI Tagging** work without any API keys. To enable **Live AI Tagging** locally, set `GROQ_API_KEY` in your shell or `.streamlit/secrets.toml`:

```bash
export GROQ_API_KEY="your_groq_api_key_here"
```

## Deploy to Streamlit Community Cloud

### 1. Push `engine-app/` to GitHub

From the repository root, run:

```bash
git add .gitignore requirements.txt engine-app/ tests/test_engine_app.py
git commit -m "Add Streamlit Discovery Engine (Level 1 Step 1.9)"
git push origin main
```

Verify `.env` and `.streamlit/secrets.toml` are **not** tracked (`git status` should not list them).

### 2. Configure Streamlit Community Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io/) and click **New app**.
2. Set the deployment parameters:
   - **Repository:** `Wwwabhi/urban-company-repeat-booking-engine`
   - **Branch:** `main`
   - **Main file path:** `engine-app/app.py`
   - **Python version (Advanced settings):** `3.12` (or `3.11`)
3. Under **Advanced settings → Secrets**, add:
   ```toml
   GROQ_API_KEY = "your_groq_api_key_here"
   ```
   *(If omitted, the app still loads cleanly; only the **Live AI Tagging** page remains inactive until `GROQ_API_KEY` is added.)*
4. Click **Deploy**. Streamlit Community Cloud installs dependencies from `requirements.txt` / `engine-app/requirements.txt` and launches `engine-app/app.py`.
