"""Unit tests for engine-app data loading, metrics, filtering, and live tagging."""

from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_REPO_ROOT = Path(__file__).resolve().parent.parent
_APP_DIR = _REPO_ROOT / "engine-app"
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

from data_loader import (  # noqa: E402
    compute_overview_metrics,
    filter_opportunity_evidence,
    load_engine_bundle,
    sanitize_display_text,
    search_customer_voice,
    tag_live_review_groq_v3_2,
)


class TestEngineAppDataAndMetrics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = load_engine_bundle()
        cls.metrics = compute_overview_metrics(cls.bundle)

    def test_overview_metrics_match_repository_counts(self):
        self.assertEqual(self.metrics["total_evidence"], 1522)
        self.assertEqual(self.metrics["core_eligible"], 1378)
        self.assertEqual(self.metrics["instahelp_count"], 144)
        self.assertEqual(self.metrics["baseline_tagged_count"], 184)
        self.assertEqual(self.metrics["golden_count"], 30)
        self.assertEqual(self.metrics["baseline_nothing_went_wrong_true"], 0)
        self.assertEqual(self.metrics["baseline_recall_gap_true"], 0)
        self.assertAlmostEqual(self.metrics["sample_avg_rating_core"], 3.59, places=2)
        self.assertEqual(
            self.metrics["core_eligible"] + self.metrics["instahelp_count"],
            self.metrics["total_evidence"],
        )

    def test_filter_opportunity_excludes_instahelp_and_filters_rating(self):
        matches = filter_opportunity_evidence(
            records=self.bundle["normalized_records"],
            pain_key="warranty_and_post_service_gap",
            source_filter="Play Store",
            rating_filter="1-2 Stars",
            exclude_instahelp=True,
        )
        self.assertGreater(len(matches), 0)
        for item in matches:
            self.assertFalse(item.get("is_instahelp"))
            self.assertEqual(item.get("source"), "Play Store")
            self.assertIn(item.get("rating"), (1, 2))

    def test_search_customer_voice_preserves_untagged_honesty(self):
        untagged = search_customer_voice(
            records=self.bundle["normalized_records"],
            tagged_by_id=self.bundle["tagged_by_id"],
            golden_by_id=self.bundle["golden_by_id"],
            tag_status_filter="Untagged",
            include_instahelp=False,
        )
        self.assertGreater(len(untagged), 0)
        self.assertFalse(untagged[0]["is_tagged"])
        self.assertIsNone(untagged[0]["tags"])

        tagged = search_customer_voice(
            records=self.bundle["normalized_records"],
            tagged_by_id=self.bundle["tagged_by_id"],
            golden_by_id=self.bundle["golden_by_id"],
            tag_status_filter="Tagged (LLM)",
            include_instahelp=False,
        )
        self.assertGreaterEqual(len(tagged), 184)
        self.assertTrue(tagged[0]["is_tagged"])
        self.assertIn("category", tagged[0]["tags"])

    def test_sanitize_display_text_redacts_pii(self):
        scrubbed = sanitize_display_text("Call 9876543210 or email test@example.com")
        self.assertIn("[PHONE_REDACTED]", scrubbed)
        self.assertIn("[EMAIL_REDACTED]", scrubbed)

    def test_live_tagging_handles_missing_credentials_gracefully(self):
        with patch.dict(os.environ, {}, clear=True):
            res = tag_live_review_groq_v3_2(
                text="AC service was good and technician arrived on time.",
                secrets_dict={},
            )
            self.assertEqual(res["status"], "error")
            self.assertEqual(res["error_type"], "missing_credentials")

    def test_live_tagging_rejects_oversized_input(self):
        res = tag_live_review_groq_v3_2(
            text="a" * 2001,
            secrets_dict={"GROQ_API_KEY": "dummy_key"},
        )
        self.assertEqual(res["status"], "error")
        self.assertEqual(res["error_type"], "input_too_long")

    def test_live_tagging_blocks_address_pii(self):
        res = tag_live_review_groq_v3_2(
            text="Technician came to Flat 402, Sector 62, pincode 201301.",
            secrets_dict={"GROQ_API_KEY": "dummy_key"},
        )
        self.assertEqual(res["status"], "blocked_privacy")

    @patch("data_loader.GroqLLMClient")
    def test_live_tagging_success_with_mocked_groq_v3_2(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.model_name = "openai/gpt-oss-120b"
        mock_client.version = "v3_2"
        mock_client.tag_review.return_value = {
            "tags": {
                "source": "Play Store",
                "date": "2026-11-25",
                "city": None,
                "category": "AC",
                "experience_type": "positive",
                "nothing_went_wrong": None,
                "rebook_signal": "unclear",
                "need_trigger": None,
                "recall_gap": None,
                "alternative_used": "unclear",
                "post_service_expectation": "unclear",
                "discovery_channel": "unclear",
                "household_type": "unclear",
                "unmet_need": None,
                "evidence_quote": "AC service was good",
                "confidence": "medium",
            },
            "tag_evidence": {},
        }
        mock_client_cls.return_value = mock_client

        res = tag_live_review_groq_v3_2(
            text="AC service was good and technician was polite.",
            source="Play Store",
            rating=5,
            secrets_dict={"GROQ_API_KEY": "dummy_key"},
        )
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["result"]["tags"]["category"], "AC")
        self.assertEqual(res["result"]["metadata"]["prompt_version"], "tagger_v3_2")


if __name__ == "__main__":
    unittest.main()
