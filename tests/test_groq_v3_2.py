"""Unit and regression tests for Groq token-efficiency optimization v3_2.

Verifies:
1. Version v3_2 prompt resolution and metadata in GroqLLMClient, GeminiLLMClient, and CLI.
2. Groq max_completion_tokens parameter handling and configurable limits.
3. Enhanced Groq retry pacing:
   - Respecting Retry-After and rate-limit reset headers.
   - Bounded exponential backoff.
   - Avoiding premature retries before quota window resets.
   - Configurable request delay.
4. Regression tests preserving every critical v3.1 policy under v3.2:
   - Spa & wellness mapping to 'other' (Decision 008).
   - Appliance cleaning/repair mapping to 'other' (Decision 007).
   - Explicit future booking intent mapping to 'rebooked'.
   - Historical repeat usage without future intent mapping to 'unclear'.
   - Negative complaints/cancellations alone never mapping to 'will_not_rebook'.
   - Explicit refusal mapping to 'will_not_rebook'.
   - General satisfaction/praise mapping to 'unclear'.
   - Evidence grounding and review queue routing.
"""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
from groq import (
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    RateLimitError,
)

from engine.tagger import (
    DEFAULT_PROMPT_PATH_V3_1,
    DEFAULT_PROMPT_PATH_V3_2,
    DEFAULT_QUEUE_OUTPUT_V3_2,
    DEFAULT_TAGGED_OUTPUT_V3_2,
    GeminiLLMClient,
    GroqLLMClient,
    MockLLMClient,
    PipelineStatistics,
    main,
    parse_retry_after,
    run_tagging_pipeline,
    tag_single_review,
)


class MockChatCompletionMessage:
    def __init__(self, content: str):
        self.content = content


class MockChatCompletionChoice:
    def __init__(self, content: str):
        self.message = MockChatCompletionMessage(content)


class MockCompletionUsage:
    def __init__(
        self,
        prompt_tokens: int = 120,
        completion_tokens: int = 70,
        total_tokens: int = 190,
    ):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens


class MockChatCompletion:
    """Mock Groq ChatCompletion response object."""

    def __init__(
        self,
        content: str,
        id: str = "chatcmpl-test-groq-v32-12345",
        prompt_tokens: int = 120,
        completion_tokens: int = 70,
    ):
        self.id = id
        self.choices = [MockChatCompletionChoice(content)]
        self.usage = MockCompletionUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )


def make_sample_tag_response(
    category: str = "AC",
    experience_type: str = "positive",
    rebook_signal: str = "rebooked",
    confidence: str = "high",
    evidence_quote: str = "Great AC service done quickly",
) -> str:
    """Helper creating valid JSON model response."""
    payload = {
        "tags": {
            "source": "Play Store",
            "date": "2026-11-20",
            "city": None,
            "category": category,
            "experience_type": experience_type,
            "nothing_went_wrong": None,
            "rebook_signal": rebook_signal,
            "need_trigger": None,
            "recall_gap": None,
            "alternative_used": "unclear",
            "post_service_expectation": "unclear",
            "discovery_channel": "unclear",
            "household_type": "unclear",
            "unmet_need": None,
            "evidence_quote": evidence_quote,
            "confidence": confidence,
        },
        "tag_evidence": {
            "category": {"quote": evidence_quote, "confidence": confidence},
            "experience_type": {"quote": evidence_quote, "confidence": confidence},
            "rebook_signal": {"quote": evidence_quote, "confidence": confidence},
        },
        "review_metadata": {
            "requires_human_review": False,
            "review_reasons": [],
        },
    }
    return json.dumps(payload)


class TestGroqV32PromptAndVersionSelection(unittest.TestCase):
    """Test v3_2 version selection, prompt resolution, and CLI integration."""

    def test_v3_2_prompt_file_exists_and_is_valid(self):
        """Verify engine/prompts/tagger_v3_2.md exists and contains required sections."""
        self.assertTrue(DEFAULT_PROMPT_PATH_V3_2.exists())
        content = DEFAULT_PROMPT_PATH_V3_2.read_text(encoding="utf-8")
        self.assertIn("Tagging Prompt v3.2 (Optimized)", content)
        self.assertIn("Global Operating Directives", content)
        self.assertIn("16-Field Authoritative Schema & Calibration Policies", content)
        self.assertIn("Spa & Wellness", content)
        self.assertIn("Appliances", content)
        self.assertIn("chimney deep clean", content)
        self.assertIn("will definitely book", content)
        self.assertIn("CRITICAL NEGATIVE TRIGGER RULE", content)
        self.assertIn("Required JSON Structure", content)

    def test_v3_1_prompt_remains_untouched(self):
        """Verify v3.1 prompt file is preserved unchanged."""
        self.assertTrue(DEFAULT_PROMPT_PATH_V3_1.exists())
        content = DEFAULT_PROMPT_PATH_V3_1.read_text(encoding="utf-8")
        self.assertIn("Tagging Prompt v3.1", content)

    def test_groq_client_loads_v3_2_prompt(self):
        """Verify GroqLLMClient(version='v3_2') resolves to tagger_v3_2.md."""
        mock_raw = MagicMock()
        client = GroqLLMClient(version="v3_2", client=mock_raw)
        self.assertEqual(client.version, "v3_2")
        self.assertIn("v3.2 (Optimized)", client.system_prompt)
        self.assertIn("GroqLLMClient(model='openai/gpt-oss-120b', version='v3_2')", repr(client))

    def test_gemini_client_loads_v3_2_prompt(self):
        """Verify GeminiLLMClient(version='v3_2') resolves to tagger_v3_2.md."""
        mock_raw = MagicMock()
        client = GeminiLLMClient(version="v3_2", client=mock_raw)
        self.assertEqual(client.version, "v3_2")
        self.assertIn("v3.2 (Optimized)", client.system_prompt)

    def test_tag_single_review_metadata_prompt_version_v3_2(self):
        """Verify tagged record metadata specifies prompt_version 'tagger_v3_2'."""
        mock_raw = MagicMock()
        mock_raw.chat.completions.create.return_value = MockChatCompletion(
            make_sample_tag_response()
        )
        client = GroqLLMClient(version="v3_2", client=mock_raw)
        rev = {
            "review_id": "rev-v32-meta-01",
            "source": "Play Store",
            "date": "2026-11-20",
            "rating": 5,
            "text": "Great AC service done quickly",
        }
        tagged_rec = tag_single_review(rev, client=client)
        self.assertEqual(tagged_rec["metadata"]["prompt_version"], "tagger_v3_2")
        self.assertEqual(client.version, "v3_2")

    def test_cli_version_v3_2_argument_parsing(self):
        """Verify CLI parses --version v3_2 and selects default v3_2 output paths."""
        test_args = ["engine.tagger", "--provider", "groq", "--version", "v3_2", "--limit", "1"]
        with patch("sys.argv", test_args):
            with patch.dict(os.environ, {"GROQ_API_KEY": "fake_key"}):
                with patch("engine.tagger.run_tagging_pipeline") as mock_pipeline:
                    with patch("groq.Groq"):
                        mock_pipeline.return_value = PipelineStatistics()
                        main()
                        self.assertTrue(mock_pipeline.called)
                        _, kwargs = mock_pipeline.call_args
                        self.assertEqual(kwargs.get("tagged_output_path"), DEFAULT_TAGGED_OUTPUT_V3_2)
                        self.assertEqual(kwargs.get("queue_output_path"), DEFAULT_QUEUE_OUTPUT_V3_2)
                        client = kwargs.get("client")
                        self.assertEqual(client.version, "v3_2")


class TestGroqCompletionLimits(unittest.TestCase):
    """Test max_completion_tokens configuration and request parameter inclusion."""

    def setUp(self):
        self.mock_raw = MagicMock()
        self.mock_raw.chat.completions.create.return_value = MockChatCompletion(
            make_sample_tag_response()
        )
        self.sample_review = {
            "review_id": "rev-tokens-01",
            "source": "Play Store",
            "date": "2026-11-20",
            "rating": 5,
            "text": "Great AC service done quickly",
        }

    def test_default_max_completion_tokens_is_1000(self):
        """Verify GroqLLMClient defaults max_completion_tokens to 1000."""
        client = GroqLLMClient(version="v3_2", client=self.mock_raw)
        self.assertEqual(client.max_completion_tokens, 1000)

    def test_custom_max_completion_tokens_setting(self):
        """Verify max_completion_tokens can be configured via constructor."""
        client = GroqLLMClient(
            version="v3_2",
            max_completion_tokens=800,
            client=self.mock_raw,
        )
        self.assertEqual(client.max_completion_tokens, 800)

    def test_max_completion_tokens_passed_to_api_call(self):
        """Verify chat.completions.create receives max_completion_tokens kwarg."""
        client = GroqLLMClient(
            version="v3_2",
            max_completion_tokens=850,
            client=self.mock_raw,
        )
        client.tag_review(self.sample_review)
        self.assertEqual(self.mock_raw.chat.completions.create.call_count, 1)
        _, kwargs = self.mock_raw.chat.completions.create.call_args
        self.assertEqual(kwargs.get("max_completion_tokens"), 850)

    def test_none_max_completion_tokens_omitted_from_api_call(self):
        """Verify when max_completion_tokens=None it is omitted from create kwargs."""
        client = GroqLLMClient(
            version="v3_2",
            max_completion_tokens=None,
            client=self.mock_raw,
        )
        client.tag_review(self.sample_review)
        _, kwargs = self.mock_raw.chat.completions.create.call_args
        self.assertNotIn("max_completion_tokens", kwargs)

    def test_cli_max_completion_tokens_argument_parsing(self):
        """Verify CLI parses --max-completion-tokens and configures client."""
        test_args = [
            "engine.tagger",
            "--provider",
            "groq",
            "--version",
            "v3_2",
            "--max-completion-tokens",
            "750",
            "--limit",
            "1",
        ]
        with patch("sys.argv", test_args):
            with patch.dict(os.environ, {"GROQ_API_KEY": "fake_key"}):
                with patch("engine.tagger.run_tagging_pipeline") as mock_pipeline:
                    with patch("groq.Groq"):
                        mock_pipeline.return_value = PipelineStatistics()
                        main()
                        _, kwargs = mock_pipeline.call_args
                        client = kwargs.get("client")
                        self.assertEqual(client.max_completion_tokens, 750)


class TestGroqRetryPacingAndQuotaWindow(unittest.TestCase):
    """Test enhanced retry pacing, rate-limit header respect, and quota window handling."""

    def setUp(self):
        self.mock_raw = MagicMock()
        self.dummy_req = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
        self.sample_review = {
            "review_id": "rev-pacing-01",
            "source": "Play Store",
            "date": "2026-11-20",
            "rating": 5,
            "text": "Great AC service done quickly",
        }

    def test_default_backoff_settings_for_groq(self):
        """Verify GroqLLMClient defaults initial_backoff to 3.0s and max_backoff to 35.0s."""
        client = GroqLLMClient(version="v3_2", client=self.mock_raw)
        self.assertEqual(client.initial_backoff, 3.0)
        self.assertEqual(client.max_backoff, 35.0)
        self.assertEqual(client.backoff_multiplier, 2.0)

    def test_rate_limit_reset_tokens_header_avoids_premature_retry(self):
        """Verify x-ratelimit-reset-tokens header duration is not truncated below quota window."""
        # Scenario: Groq returns x-ratelimit-reset-tokens: 24.5s
        resp_429 = httpx.Response(
            status_code=429,
            headers={"x-ratelimit-reset-tokens": "24.5s", "x-request-id": "req-reset-tokens-01"},
            request=self.dummy_req,
        )
        api_error_429 = RateLimitError("Rate limit reached", response=resp_429, body=None)
        valid_response = MockChatCompletion(make_sample_tag_response())

        self.mock_raw.chat.completions.create.side_effect = [api_error_429, valid_response]
        client = GroqLLMClient(version="v3_2", client=self.mock_raw)

        with patch("time.sleep") as mock_sleep:
            result = client.tag_review(self.sample_review)

        self.assertEqual(result["tags"]["category"], "AC")
        self.assertEqual(client.total_retries, 1)
        # Verify sleep duration was at least 24.5s (header specified), not truncated to 10s
        self.assertTrue(mock_sleep.called)
        sleep_arg = mock_sleep.call_args[0][0]
        self.assertGreaterEqual(sleep_arg, 24.5)
        self.assertLessEqual(sleep_arg, 36.0)

    def test_retry_after_header_duration_respected(self):
        """Verify Retry-After header duration is honored."""
        resp_429 = httpx.Response(
            status_code=429,
            headers={"retry-after": "15", "x-request-id": "req-retry-after-02"},
            request=self.dummy_req,
        )
        api_error_429 = RateLimitError("Rate limit reached", response=resp_429, body=None)
        valid_response = MockChatCompletion(make_sample_tag_response())

        self.mock_raw.chat.completions.create.side_effect = [api_error_429, valid_response]
        client = GroqLLMClient(version="v3_2", client=self.mock_raw)

        with patch("time.sleep") as mock_sleep:
            result = client.tag_review(self.sample_review)

        self.assertEqual(result["tags"]["category"], "AC")
        sleep_arg = mock_sleep.call_args[0][0]
        self.assertGreaterEqual(sleep_arg, 15.0)

    def test_exponential_backoff_without_headers(self):
        """Verify exponential backoff progression when no rate-limit headers are present."""
        resp_500 = httpx.Response(
            status_code=500,
            headers={"x-request-id": "req-500-progression"},
            request=self.dummy_req,
        )
        err_500 = InternalServerError("Server Error", response=resp_500, body=None)
        valid_response = MockChatCompletion(make_sample_tag_response())

        self.mock_raw.chat.completions.create.side_effect = [err_500, valid_response]
        client = GroqLLMClient(
            version="v3_2",
            initial_backoff=4.0,
            max_backoff=30.0,
            client=self.mock_raw,
        )

        with patch("time.sleep") as mock_sleep:
            client.tag_review(self.sample_review)

        self.assertTrue(mock_sleep.called)
        sleep_arg = mock_sleep.call_args[0][0]
        # Backoff 4.0 + jitter [0.1, 0.4] -> between 4.1 and 4.4
        self.assertGreaterEqual(sleep_arg, 4.0)
        self.assertLessEqual(sleep_arg, 5.0)

    def test_request_delay_applied_prior_to_call(self):
        """Verify configurable request delay is applied before invoking the API."""
        client = GroqLLMClient(
            version="v3_2",
            request_delay=3.5,
            client=self.mock_raw,
        )
        self.mock_raw.chat.completions.create.return_value = MockChatCompletion(
            make_sample_tag_response()
        )

        with patch("time.sleep") as mock_sleep:
            client.tag_review(self.sample_review)

        mock_sleep.assert_called_with(3.5)


class TestGroqV32PolicyRegressions(unittest.TestCase):
    """Regression tests verifying all critical v3.1 policies are preserved in v3.2."""

    def setUp(self):
        self.mock_client = MockLLMClient(version="v3_2")

    def test_spa_sessions_map_to_other_not_salon(self):
        """Decision 008: Spa / massage services must map to 'other', not 'salon'."""
        rev = {
            "review_id": "rev-spa-01",
            "source": "Play Store",
            "date": "2026-11-20",
            "rating": 5,
            "text": "Booked a relaxing body spa session and massage at home, very good therapist.",
        }
        res = self.mock_client.tag_review(rev)
        self.assertEqual(res["tags"]["category"], "other")
        self.assertIn("spa", res["tag_evidence"]["category"]["quote"].lower())

    def test_appliance_cleaning_and_repair_map_to_other(self):
        """Decision 007: Chimney cleaning and appliance repairs map to 'other', not 'deep clean' or 'plumber'."""
        chimney_rev = {
            "review_id": "rev-appliance-01",
            "source": "Play Store",
            "date": "2026-11-20",
            "rating": 5,
            "text": "Chimney deep clean service done on time and working well.",
        }
        res = self.mock_client.tag_review(chimney_rev)
        self.assertEqual(res["tags"]["category"], "other")

        purifier_rev = {
            "review_id": "rev-appliance-02",
            "source": "Play Store",
            "date": "2026-11-20",
            "rating": 4,
            "text": "RO water purifier pipe was leaking, repaired quickly.",
        }
        res_p = self.mock_client.tag_review(purifier_rev)
        self.assertEqual(res_p["tags"]["category"], "other")

    def test_explicit_future_booking_intent_maps_to_rebooked(self):
        """Explicit future booking intent ('I will definitely book her again') maps to 'rebooked'."""
        rev = {
            "review_id": "rev-future-rebook-01",
            "source": "Play Store",
            "date": "2026-11-20",
            "rating": 5,
            "text": "The beautician was polite and thorough. I will definitely book her again for my next facial.",
        }
        res = self.mock_client.tag_review(rev)
        self.assertEqual(res["tags"]["rebook_signal"], "rebooked")
        self.assertEqual(res["tags"]["category"], "salon")

    def test_historical_repeat_usage_alone_maps_to_unclear(self):
        """Historical repeat status ('regular customer') with complaint/cancellation maps to 'unclear'."""
        rev = {
            "review_id": "rev-hist-repeat-01",
            "source": "Play Store",
            "date": "2026-11-20",
            "rating": 1,
            "text": "I am a regular customer and frequent user of UC, but today partner cancelled.",
        }
        res = self.mock_client.tag_review(rev)
        self.assertEqual(res["tags"]["rebook_signal"], "unclear")
        self.assertNotEqual(res["tags"]["rebook_signal"], "rebooked")

    def test_general_satisfaction_alone_maps_to_unclear(self):
        """General satisfaction/praise alone without booking statement maps to 'unclear'."""
        rev = {
            "review_id": "rev-praise-01",
            "source": "Play Store",
            "date": "2026-11-20",
            "rating": 5,
            "text": "Urban Company is the best app for home services. Excellent work by technician.",
        }
        res = self.mock_client.tag_review(rev)
        self.assertEqual(res["tags"]["rebook_signal"], "unclear")

    def test_complaints_and_cancellations_never_establish_will_not_rebook(self):
        """Negative trigger rule: 1-star, dissatisfaction, cancellations alone must map to 'unclear'."""
        rev = {
            "review_id": "rev-neg-01",
            "source": "Play Store",
            "date": "2026-11-20",
            "rating": 1,
            "text": "Worst experience ever. The plumber did not show up and customer support was useless.",
        }
        res = self.mock_client.tag_review(rev)
        self.assertEqual(res["tags"]["experience_type"], "negative")
        self.assertEqual(res["tags"]["rebook_signal"], "unclear")
        self.assertNotEqual(res["tags"]["rebook_signal"], "will_not_rebook")

    def test_explicit_refusal_maps_to_will_not_rebook(self):
        """Explicit refusal ('will never book again', 'deleting app') maps to 'will_not_rebook'."""
        rev = {
            "review_id": "rev-refusal-01",
            "source": "Play Store",
            "date": "2026-11-20",
            "rating": 1,
            "text": "Cheated by technician. I will never book again and have uninstalled the app.",
        }
        res = self.mock_client.tag_review(rev)
        self.assertEqual(res["tags"]["rebook_signal"], "will_not_rebook")

    def test_warranty_complaint_does_not_imply_warranty_clarity(self):
        """Warranty complaints alone must NOT map post_service_expectation to 'warranty clarity'."""
        rev = {
            "review_id": "rev-warranty-01",
            "source": "Play Store",
            "date": "2026-11-20",
            "rating": 1,
            "text": "Pathetic warranty service. Cannot claim warranty when AC stopped working after 5 days.",
        }
        res = self.mock_client.tag_review(rev)
        self.assertNotEqual(res["tags"]["post_service_expectation"], "warranty clarity")
        self.assertEqual(res["tags"]["post_service_expectation"], "unclear")

    def test_review_queue_routing_for_low_information_reviews(self):
        """Low information reviews must be routed to human review queue."""
        rev = {
            "review_id": "rev-low-info-01",
            "source": "Play Store",
            "date": "2026-11-20",
            "rating": 5,
            "text": "Good",
        }
        tagged_rec = tag_single_review(rev, client=self.mock_client)
        self.assertTrue(tagged_rec["metadata"]["requires_human_review"])
        self.assertTrue(any("low_information" in r for r in tagged_rec["metadata"]["review_reasons"]))


if __name__ == "__main__":
    unittest.main()
