"""Diagnostic script: probe HTTP 400 errors on 3 failed Groq v3.2 reviews."""
import json
import os
import time
from pathlib import Path
from groq import Groq

# Load key
key = None
for line in Path('.env').read_text().splitlines():
    line = line.strip()
    if not line or line.startswith('#'):
        continue
    if 'GROQ_API_KEY' in line:
        sep = '=' if '=' in line else ':'
        key = line.split(sep, 1)[1].strip().strip('"').strip("'")
        break

prompt = Path('engine/prompts/tagger_v3_2.md').read_text(encoding='utf-8')
client = Groq(api_key=key, timeout=30.0, max_retries=0)

failed_ids = [
    '99226311-a2f2-4ecf-b1ed-7d28518cd95e',
    '4e4e2ef9-6dd6-40cc-a65b-a3f327daf7f0',
    '43582ef1-c85a-4b67-ad13-662ab7a72dcb',
]

with open('data/tagged/groq_pilot_v3_2/groq_pilot_v3_2_input.jsonl') as f:
    all_records = {json.loads(l)['review_id']: json.loads(l) for l in f if l.strip()}

for rid in failed_ids:
    review = all_records[rid]
    payload = {
        "review_id": review["review_id"],
        "source": review.get("source"),
        "date": review.get("date"),
        "rating": review.get("rating"),
        "title": review.get("title"),
        "text": review.get("text"),
    }
    user_prompt = (
        "Analyze and tag the following customer review according to the 16-field schema "
        "and strict policy rules provided in the system instructions. "
        "Return ONLY a single valid JSON object adhering strictly to the schema.\n\n"
        f"```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```"
    )

    print(f"\n=== Testing {rid} ===")
    try:
        resp = client.chat.completions.create(
            model='openai/gpt-oss-120b',
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_completion_tokens=1000,
        )
        print(f"SUCCESS: {resp.id}")
        print(f"Usage: prompt={resp.usage.prompt_tokens} completion={resp.usage.completion_tokens} total={resp.usage.total_tokens}")
        content = resp.choices[0].message.content
        print(f"Content (first 200): {content[:200]}")
    except Exception as e:
        print(f"ERROR: {type(e).__name__}")
        print(f"Status: {getattr(e, 'status_code', 'N/A')}")
        body = getattr(e, 'body', None)
        if body:
            print(f"Body: {body}")
        msg = getattr(e, 'message', str(e))
        print(f"Message: {msg}")
        if hasattr(e, 'response') and e.response is not None:
            hdrs = dict(e.response.headers)
            print(f"Content-Type: {hdrs.get('content-type')}")

    time.sleep(25)
