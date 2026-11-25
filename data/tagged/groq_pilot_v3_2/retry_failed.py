"""Retry the 3 failed Groq v3.2 reviews with increased max_completion_tokens.

Reviews 4e4e2ef9 and 43582ef1 failed with json_validate_failed because
max_completion_tokens=1000 was exhausted before the model could finish
generating valid JSON. Review 99226311 was a transient failure.

This script retries all 3 with max_completion_tokens=1500, appends
successful results to the existing tagged/queue output files, and
merges metrics into the existing metrics file.
"""
import json
import os
import re
import sys
import time
from pathlib import Path

# Ensure project root is on sys.path
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))
os.chdir(project_root)

from engine.tagger import (
    GroqLLMClient,
    tag_single_review,
    is_low_information_review,
    evaluate_review_queue_triggers,
    validate_evidence_quote,
    validate_16_schema_fields,
    EXACT_16_FIELDS,
)

FAILED_IDS = [
    "99226311-a2f2-4ecf-b1ed-7d28518cd95e",
    "4e4e2ef9-6dd6-40cc-a65b-a3f327daf7f0",
    "43582ef1-c85a-4b67-ad13-662ab7a72dcb",
]

INPUT_FILE = Path("data/tagged/groq_pilot_v3_2/groq_pilot_v3_2_input.jsonl")
TAGGED_FILE = Path("data/tagged/groq_pilot_v3_2/tagged_reviews_groq_v3_2.jsonl")
QUEUE_FILE = Path("data/tagged/groq_pilot_v3_2/review_queue_groq_v3_2.jsonl")
METRICS_FILE = Path("data/tagged/groq_pilot_v3_2/groq_v3_2_metrics.json")
FAILED_FILE = Path("data/tagged/groq_pilot_v3_2/failed_reviews_groq_v3_2.jsonl")

# Load input reviews
with open(INPUT_FILE) as f:
    all_records = {json.loads(l)["review_id"]: json.loads(l) for l in f if l.strip()}

failed_reviews = [all_records[rid] for rid in FAILED_IDS]

# Initialize client with max_completion_tokens=1500
client = GroqLLMClient(
    model_name="openai/gpt-oss-120b",
    version="v3_2",
    max_retries=4,
    request_timeout=30.0,
    initial_backoff=5.0,
    max_backoff=40.0,
    backoff_multiplier=2.0,
    request_delay=25.0,
    max_completion_tokens=1500,
)

# Load existing metrics
with open(METRICS_FILE) as f:
    existing_metrics = json.load(f)

retry_succeeded = []
retry_failed = []

for review in failed_reviews:
    rid = review["review_id"]
    print(f"\n=== Retrying {rid} (max_completion_tokens=1500) ===")
    try:
        tagged_rec = tag_single_review(review, client=client, prompt_version="tagger_v3_2")
        tagged_rec["metadata"]["retry_note"] = "Retried with max_completion_tokens=1500 after initial json_validate_failed"
        retry_succeeded.append(tagged_rec)
        print(f"  SUCCESS: category={tagged_rec['tags'].get('category')}, rebook={tagged_rec['tags'].get('rebook_signal')}")
    except Exception as e:
        print(f"  FAILED: {type(e).__name__}: {e}")
        retry_failed.append({
            "review_id": rid,
            "error_type": type(e).__name__,
            "status_code": getattr(e, "status_code", None),
            "message": str(getattr(e, "body", str(e)))[:200],
        })

# Append successful retries to tagged/queue files
for rec in retry_succeeded:
    requires_review = rec["metadata"].get("requires_human_review", False)
    if requires_review:
        with open(QUEUE_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"  -> Queued: {rec['review_id']}")
    else:
        with open(TAGGED_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"  -> Tagged: {rec['review_id']}")

# Merge retry metrics into existing metrics
retry_metrics = client.call_history
all_metrics = existing_metrics + retry_metrics
with open(METRICS_FILE, "w", encoding="utf-8") as f:
    json.dump(all_metrics, f, indent=2)

# Rewrite failed file with only still-failed reviews
with open(FAILED_FILE, "w", encoding="utf-8") as f:
    for rec in retry_failed:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

print(f"\n=== Retry Summary ===")
print(f"Retried:   {len(FAILED_IDS)}")
print(f"Succeeded: {len(retry_succeeded)}")
print(f"Failed:    {len(retry_failed)}")
print(f"Total metrics entries: {len(all_metrics)}")

for m in retry_metrics:
    if m.get("status_code") == 200:
        print(f"  {m['review_id']}: prompt={m.get('prompt_tokens')} completion={m.get('completion_tokens')} total={m.get('total_tokens')} latency={m.get('latency')}s")
