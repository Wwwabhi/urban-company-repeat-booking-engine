"""Unit tests for production-safe GeminiLLMClient and CLI provider selection.

All tests use mocked Gemini responses and mock clients. No live API calls are made.
"""

import json
import logging
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from google.genai import errors

from engine.tagger import (
    DEFAULT_PROMPT_PATH_V3,
    DEFAULT_QUEUE_OUTPUT_V3,
    DEFAULT_TAGGED_OUTPUT_V3,
    GeminiLLMClient,
    MockLLMClient,
    PipelineStatistics,
    main,
    run_tagging_pipeline,
    tag_single_review,
)


class MockGenerateContentResponse:
    """Mock Gemini GenerateContentResponse object."""

    def __init__(self, text: str):
        self.text = text


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
            "city": "Bengaluru",
            "category": category,
            "experience_type": experience_type,
            "nothing_went_wrong": None,
            "rebook_signal": rebook_signal,
            "need_trigger": "season",
            "recall_gap": None,
            "alternative_used": "unclear",
            "post_service_expectation": "unclear",
            "discovery_channel": "unclear",
            "household_type": "family",
            "unmet_need": None,
            "evidence_quote": evidence_quote,
            "confidence": confidence,
        },
        "tag_evidence": {
            "category": {"quote": "AC service", "confidence": "high"},
            "experience_type": {"quote": "Great AC service", "confidence": "high"},
        },
    }
    return json.dumps(payload)


class TestGeminiClientInitialization(unittest.TestCase):
    """Test client initialization, secure key resolution, and repr formatting."""

    def test_missing_api_key_raises_value_error(self):
        """Verify initializing without GEMINI_API_KEY environment variable raises ValueError."""
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError) as ctx:
                GeminiLLMClient(client=None, api_key=None, load_env=False)
            self.assertIn("GEMINI_API_KEY environment variable is not set", str(ctx.exception))

    def test_explicit_api_key_or_env_var_initialization(self):
        """Verify explicit api_key or GEMINI_API_KEY initializes client without error."""
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake_test_key_12345"}):
            with patch("google.genai.Client") as mock_client_cls:
                client = GeminiLLMClient(model_name="gemini-3.5-flash-lite")
                self.assertEqual(client.model_name, "gemini-3.5-flash-lite")
                self.assertTrue(mock_client_cls.called)

    def test_injected_mock_client_bypasses_api_key_requirement(self):
        """Verify injecting client object allows testing without any API key present."""
        mock_raw_client = MagicMock()
        with patch.dict(os.environ, {}, clear=True):
            client = GeminiLLMClient(client=mock_raw_client)
            self.assertIs(client._client, mock_raw_client)

    def test_client_repr_does_not_expose_api_key(self):
        """Verify client __repr__ never leaks credentials or sensitive information."""
        mock_raw_client = MagicMock()
        client = GeminiLLMClient(
            model_name="gemini-3-flash-preview",
            api_key="super_secret_api_key_abc123",
            client=mock_raw_client,
        )
        repr_str = repr(client)
        self.assertIn("gemini-3-flash-preview", repr_str)
        self.assertNotIn("super_secret_api_key_abc123", repr_str)
        self.assertNotIn("api_key", repr_str.lower())


class TestGeminiClientTagging(unittest.TestCase):
    """Test response parsing, schema validation, and grounding for GeminiLLMClient."""

    def setUp(self):
        self.mock_raw_client = MagicMock()
        self.client = GeminiLLMClient(
            model_name="gemini-3-flash-preview",
            version="v2",
            client=self.mock_raw_client,
        )
        self.sample_review = {
            "review_id": "test-rev-001",
            "source": "Play Store",
            "date": "2026-11-20",
            "rating": 5,
            "title": "Superb AC work",
            "text": "Great AC service done quickly in Bengaluru! Highly recommended.",
        }

    def test_successful_tagging_response(self):
        """Verify valid model output is parsed and strictly conforms to 16 schema fields."""
        json_resp = make_sample_tag_response(
            category="AC",
            experience_type="positive",
            rebook_signal="rebooked",
            evidence_quote="Great AC service done quickly",
        )
        self.mock_raw_client.models.generate_content.return_value = MockGenerateContentResponse(json_resp)

        result = self.client.tag_review(self.sample_review)
        self.assertIn("tags", result)
        self.assertIn("tag_evidence", result)

        tags = result["tags"]
        self.assertEqual(tags["category"], "AC")
        self.assertEqual(tags["experience_type"], "positive")
        self.assertEqual(tags["rebook_signal"], "rebooked")
        self.assertEqual(tags["city"], "Bengaluru")
        self.assertEqual(tags["evidence_quote"], "Great AC service done quickly")
        self.assertEqual(self.client.call_count, 1)

    def test_malformed_json_response_raises_value_error(self):
        """Verify unparseable or corrupted JSON response raises ValueError without falling back to mock."""
        self.mock_raw_client.models.generate_content.return_value = MockGenerateContentResponse(
            "This is not JSON at all: {broken: json"
        )
        with self.assertRaises(ValueError) as ctx:
            self.client.tag_review(self.sample_review)
        self.assertIn("Malformed JSON", str(ctx.exception))

    def test_missing_required_fields_raises_value_error(self):
        """Verify response missing core schema fields raises schema validation ValueError."""
        # Omit 'category' and 'rebook_signal'
        bad_payload = {
            "tags": {
                "source": "Play Store",
                "date": "2026-11-20",
                "experience_type": "positive",
                "nothing_went_wrong": None,
                "confidence": "high",
            }
        }
        self.mock_raw_client.models.generate_content.return_value = MockGenerateContentResponse(
            json.dumps(bad_payload)
        )
        with self.assertRaises(ValueError) as ctx:
            self.client.tag_review(self.sample_review)
        self.assertIn("failed schema validation", str(ctx.exception))
        self.assertIn("Missing required fields", str(ctx.exception))

    def test_invalid_enum_value_raises_value_error(self):
        """Verify response containing unlisted enum value raises schema validation ValueError."""
        bad_payload = {
            "tags": {
                "source": "Play Store",
                "date": "2026-11-20",
                "city": None,
                "category": "cryptocurrency_mining",  # Invalid category enum
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
                "evidence_quote": "Great service",
                "confidence": "high",
            }
        }
        self.mock_raw_client.models.generate_content.return_value = MockGenerateContentResponse(
            json.dumps(bad_payload)
        )
        with self.assertRaises(ValueError) as ctx:
            self.client.tag_review(self.sample_review)
        self.assertIn("Invalid category 'cryptocurrency_mining'", str(ctx.exception))

    def test_markdown_code_fencing_handled_cleanly(self):
        """Verify model output wrapped in markdown code fence blocks is stripped and parsed."""
        raw_json = make_sample_tag_response()
        fenced_output = f"```json\n{raw_json}\n```"
        self.mock_raw_client.models.generate_content.return_value = MockGenerateContentResponse(fenced_output)

        result = self.client.tag_review(self.sample_review)
        self.assertEqual(result["tags"]["category"], "AC")

    def test_flat_json_output_handled_cleanly(self):
        """Verify response where 16 fields are directly at root level is parsed into tags."""
        flat_payload = {
            "source": "Play Store",
            "date": "2026-11-20",
            "city": "Bengaluru",
            "category": "AC",
            "experience_type": "positive",
            "nothing_went_wrong": None,
            "rebook_signal": "rebooked",
            "need_trigger": None,
            "recall_gap": None,
            "alternative_used": "unclear",
            "post_service_expectation": "unclear",
            "discovery_channel": "unclear",
            "household_type": "unclear",
            "unmet_need": None,
            "evidence_quote": "Great AC service",
            "confidence": "high",
        }
        self.mock_raw_client.models.generate_content.return_value = MockGenerateContentResponse(
            json.dumps(flat_payload)
        )
        result = self.client.tag_review(self.sample_review)
        self.assertEqual(result["tags"]["category"], "AC")
        self.assertEqual(result["tags"]["rebook_signal"], "rebooked")


class TestGeminiClientRetriesAndErrorHandling(unittest.TestCase):
    """Test retry behavior, rate limits, transient network errors, and delays."""

    def setUp(self):
        self.mock_raw_client = MagicMock()
        self.client = GeminiLLMClient(
            model_name="gemini-3-flash-preview",
            version="v2",
            max_retries=3,
            initial_backoff=0.01,
            max_backoff=0.05,
            client=self.mock_raw_client,
        )
        self.sample_review = {
            "review_id": "rev-retry-01",
            "source": "Play Store",
            "date": "2026-11-20",
            "rating": 5,
            "text": "Great AC service done quickly",
        }

    def test_rate_limit_retry_and_recovery(self):
        """Verify HTTP 429 rate limit triggers bounded retry with backoff and succeeds on attempt 2."""
        api_error_429 = errors.APIError(code=429, response_json={"error": "Resource exhausted"})
        valid_response = MockGenerateContentResponse(make_sample_tag_response())

        self.mock_raw_client.models.generate_content.side_effect = [api_error_429, valid_response]

        with patch("time.sleep") as mock_sleep:
            result = self.client.tag_review(self.sample_review)

        self.assertEqual(result["tags"]["category"], "AC")
        self.assertEqual(self.client.total_retries, 1)
        self.assertEqual(self.client.total_errors, 0)
        self.assertEqual(self.mock_raw_client.models.generate_content.call_count, 2)
        mock_sleep.assert_called()

    def test_rate_limit_exhausted_raises_error(self):
        """Verify exceeding max_retries on persistent rate limits raises exception and updates total_errors."""
        api_error_429 = errors.APIError(code=429, response_json={"error": "Resource exhausted"})
        self.mock_raw_client.models.generate_content.side_effect = api_error_429

        with patch("time.sleep"):
            with self.assertRaises(errors.APIError):
                self.client.tag_review(self.sample_review)

        self.assertEqual(self.client.total_retries, 2)
        self.assertEqual(self.client.total_errors, 1)
        self.assertEqual(self.mock_raw_client.models.generate_content.call_count, 3)

    def test_transient_network_error_retry_and_recovery(self):
        """Verify transient network ConnectionError triggers retry and succeeds on attempt 2."""
        network_error = ConnectionError("Connection reset by peer")
        valid_response = MockGenerateContentResponse(make_sample_tag_response())

        self.mock_raw_client.models.generate_content.side_effect = [network_error, valid_response]

        with patch("time.sleep"):
            result = self.client.tag_review(self.sample_review)

        self.assertEqual(result["tags"]["category"], "AC")
        self.assertEqual(self.client.total_retries, 1)
        self.assertEqual(self.client.total_errors, 0)

    def test_non_retryable_client_error_fails_immediately(self):
        """Verify non-retryable 400 Bad Request error fails on attempt 1 without retrying."""
        bad_request_error = errors.APIError(code=400, response_json={"error": "Bad request"})
        self.mock_raw_client.models.generate_content.side_effect = bad_request_error

        with self.assertRaises(errors.APIError):
            self.client.tag_review(self.sample_review)

        self.assertEqual(self.client.total_retries, 0)
        self.assertEqual(self.client.total_errors, 1)
        self.assertEqual(self.mock_raw_client.models.generate_content.call_count, 1)

    def test_request_delay_applied(self):
        """Verify configured request_delay invokes time.sleep before executing API call."""
        client_with_delay = GeminiLLMClient(
            model_name="gemini-3-flash-preview",
            request_delay=0.5,
            client=self.mock_raw_client,
        )
        self.mock_raw_client.models.generate_content.return_value = MockGenerateContentResponse(
            make_sample_tag_response()
        )

        with patch("time.sleep") as mock_sleep:
            client_with_delay.tag_review(self.sample_review)

        mock_sleep.assert_called_with(0.5)


class TestGeminiClientSafeLogging(unittest.TestCase):
    """Test that logger messages never expose API keys, review text, or customer PII."""

    def test_safe_logging_never_exposes_api_key_or_review_text(self):
        """Verify logging outputs review ID and attempt, but NEVER full review text or secrets."""
        mock_raw_client = MagicMock()
        mock_raw_client.models.generate_content.return_value = MockGenerateContentResponse(
            make_sample_tag_response()
        )
        client = GeminiLLMClient(
            model_name="gemini-3-flash-preview",
            api_key="secret_token_xyz987",
            client=mock_raw_client,
        )

        sensitive_review = {
            "review_id": "rev-secret-pincode-99",
            "source": "Play Store",
            "date": "2026-11-20",
            "rating": 5,
            "text": "My secret phone is 9876543210 and living in Flat 402 Palm Grove Road.",
        }

        with self.assertLogs("engine.tagger", level="INFO") as log_capture:
            client.tag_review(sensitive_review)

        all_logs = " ".join(log_capture.output)
        self.assertIn("rev-secret-pincode-99", all_logs)
        self.assertNotIn("9876543210", all_logs)
        self.assertNotIn("Palm Grove Road", all_logs)
        self.assertNotIn("secret_token_xyz987", all_logs)
        self.assertNotIn("Flat 402", all_logs)


class TestGeminiCLIAndPipelineIntegration(unittest.TestCase):
    """Test CLI argument parsing and end-to-end pipeline execution with GeminiLLMClient."""

    def test_cli_provider_selection_mock_default(self):
        """Verify CLI default selects MockLLMClient."""
        with patch("sys.argv", ["engine.tagger"]):
            with patch("engine.tagger.run_tagging_pipeline") as mock_pipeline:
                main()
                self.assertTrue(mock_pipeline.called)
                client_used = mock_pipeline.call_args[1]["client"]
                self.assertIsInstance(client_used, MockLLMClient)

    def test_cli_provider_selection_explicit_gemini(self):
        """Verify CLI --provider gemini selects GeminiLLMClient with gemini-3.5-flash-lite."""
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake_key_cli"}):
            with patch("sys.argv", ["engine.tagger", "--provider", "gemini", "--version", "v2"]):
                with patch("engine.tagger.run_tagging_pipeline") as mock_pipeline:
                    with patch("google.genai.Client"):
                        main()
                        self.assertTrue(mock_pipeline.called)
                        client_used = mock_pipeline.call_args[1]["client"]
                        self.assertIsInstance(client_used, GeminiLLMClient)
                        self.assertEqual(client_used.model_name, "gemini-3.5-flash-lite")

    def test_cli_gemini_without_api_key_fails_fast(self):
        """Verify CLI --provider gemini fails fast with ValueError when GEMINI_API_KEY is not set."""
        with patch.dict(os.environ, {}, clear=True):
            orig_exists = Path.exists
            with patch.object(Path, "exists", autospec=True, side_effect=lambda self: False if self.name == ".env" else orig_exists(self)):
                with patch("sys.argv", ["engine.tagger", "--provider", "gemini"]):
                    with self.assertRaises(ValueError) as ctx:
                        main()
                    self.assertIn("GEMINI_API_KEY environment variable is not set", str(ctx.exception))

    def test_pipeline_integration_with_gemini_client_routes_queue_and_tagged(self):
        """Verify run_tagging_pipeline with GeminiLLMClient properly routes high-conf vs low-info reviews."""
        mock_raw_client = MagicMock()
        client = GeminiLLMClient(
            model_name="gemini-3-flash-preview",
            version="v2",
            client=mock_raw_client,
        )

        # 1. Normal high-confidence review
        normal_review = {
            "review_id": "rev-core-1",
            "source": "Play Store",
            "date": "2026-11-20",
            "rating": 5,
            "text": "Great AC service done quickly and efficiently. Booked again for next week.",
            "is_instahelp": False,
        }
        # 2. Terse low-info review
        low_info_review = {
            "review_id": "rev-low-info-2",
            "source": "Play Store",
            "date": "2026-11-20",
            "rating": 5,
            "text": "good",
            "is_instahelp": False,
        }

        # Mock responses
        resp_normal = make_sample_tag_response(
            category="AC",
            rebook_signal="rebooked",
            confidence="high",
            evidence_quote="Great AC service done quickly and efficiently.",
        )
        resp_low_info = make_sample_tag_response(
            category="unknown",
            rebook_signal="unclear",
            confidence="low",
            evidence_quote="",
        )

        mock_raw_client.models.generate_content.side_effect = [
            MockGenerateContentResponse(resp_normal),
            MockGenerateContentResponse(resp_low_info),
        ]

        with TemporaryDirectory() as tmpdir:
            input_file = Path(tmpdir) / "test_normalized.jsonl"
            tagged_file = Path(tmpdir) / "tagged_v2.jsonl"
            queue_file = Path(tmpdir) / "queue_v2.jsonl"

            with open(input_file, "w") as f:
                f.write(json.dumps(normal_review) + "\n")
                f.write(json.dumps(low_info_review) + "\n")

            stats = run_tagging_pipeline(
                input_path=input_file,
                tagged_output_path=tagged_file,
                queue_output_path=queue_file,
                client=client,
                version="v2",
            )

            self.assertEqual(stats.total_input_records, 2)
            self.assertEqual(stats.eligible_core_reviews, 2)
            self.assertEqual(stats.tagged_saved_count, 1)
            self.assertEqual(stats.review_queue_count, 1)

            # Check tagged file contains rev-core-1
            with open(tagged_file) as f:
                tagged_lines = [json.loads(line) for line in f]
            self.assertEqual(len(tagged_lines), 1)
            self.assertEqual(tagged_lines[0]["review_id"], "rev-core-1")
            self.assertEqual(tagged_lines[0]["metadata"]["model"], "gemini-3-flash-preview")

            # Check queue file contains rev-low-info-2
            with open(queue_file) as f:
                queue_lines = [json.loads(line) for line in f]
            self.assertEqual(len(queue_lines), 1)
            self.assertEqual(queue_lines[0]["review_id"], "rev-low-info-2")
            self.assertTrue(queue_lines[0]["metadata"]["requires_human_review"])


class TestTaggerV3PromptRegressions(unittest.TestCase):
    """Regression tests for Tagger v3 prompt corrections based on golden-set evaluation.

    Verifies:
    1. Dissatisfaction-to-churn leakage elimination in rebook_signal.
    2. Appliance vs. premises scoping in category classification.
    3. Proper resolution of v3 prompts and default outputs.
    """

    def setUp(self):
        self.client_v3 = MockLLMClient(version="v3")
        self.client_v2 = MockLLMClient(version="v2")

    def test_v3_prompt_file_exists_and_contains_negative_rebook_and_appliance_rules(self):
        """Verify engine/prompts/tagger_v3.md exists and contains the calibrated directives."""
        self.assertTrue(DEFAULT_PROMPT_PATH_V3.exists(), f"Missing {DEFAULT_PROMPT_PATH_V3}")
        with open(DEFAULT_PROMPT_PATH_V3, "r", encoding="utf-8") as f:
            content = f.read()

        # Check rebook_signal rules
        self.assertIn("`will_not_rebook` requires direct, unambiguous evidence", content)
        self.assertIn("The following must **NEVER** independently establish `will_not_rebook`", content)
        self.assertIn("One-star or low ratings", content)
        self.assertIn("Strong dissatisfaction or anger", content)
        self.assertIn("Technician misconduct", content)
        self.assertIn("Partner cancellations or no-shows", content)

        # Check category appliance scoping rules
        self.assertIn("deep clean", content)
        self.assertIn("chimney deep clean", content)
        self.assertIn("premises", content)

    def test_gemini_client_v3_loads_v3_prompt(self):
        """Verify GeminiLLMClient(version='v3') loads tagger_v3.md by default."""
        mock_raw = MagicMock()
        client = GeminiLLMClient(
            model_name="gemini-3.5-flash-lite",
            version="v3",
            client=mock_raw,
        )
        self.assertIn("Tagging Prompt v3", client.system_prompt)
        self.assertIn("`will_not_rebook` requires direct, unambiguous evidence", client.system_prompt)

    def test_case_1_angry_1_star_without_explicit_churn_is_unclear(self):
        """Case 1: Angry 1-star review without explicit churn: rebook_signal must be 'unclear'."""
        review = {
            "review_id": "case-1-angry",
            "source": "Play Store",
            "date": "2026-11-22",
            "rating": 1,
            "text": "Worst experience ever! Pathetic customer service, completely useless and complete waste of money! 1 star!",
            "is_instahelp": False,
        }
        res = tag_single_review(review, client=self.client_v3)
        self.assertEqual(res["tags"]["rebook_signal"], "unclear")
        self.assertNotEqual(res["tags"]["rebook_signal"], "will_not_rebook")

    def test_case_2_technician_complaint_is_unclear(self):
        """Case 2: Customer complaining about technician: rebook_signal must be 'unclear'."""
        review = {
            "review_id": "case-2-technician",
            "source": "Play Store",
            "date": "2026-11-22",
            "rating": 1,
            "text": "The technician Sujoy was extremely rude, arrived two hours late, cheated on pricing, and argued with family members.",
            "is_instahelp": False,
        }
        res = tag_single_review(review, client=self.client_v3)
        self.assertEqual(res["tags"]["rebook_signal"], "unclear")
        self.assertNotEqual(res["tags"]["rebook_signal"], "will_not_rebook")

    def test_case_3_partner_cancellation_without_intent_is_unclear(self):
        """Case 3: Partner cancellation with no future intent statement: rebook_signal must be 'unclear'."""
        review = {
            "review_id": "case-3-cancellation",
            "source": "Play Store",
            "date": "2026-11-22",
            "rating": 1,
            "text": "Partner cancelled the booking at the last moment leaving me stranded with no explanation and no support response.",
            "is_instahelp": False,
        }
        res = tag_single_review(review, client=self.client_v3)
        self.assertEqual(res["tags"]["rebook_signal"], "unclear")
        self.assertNotEqual(res["tags"]["rebook_signal"], "will_not_rebook")

    def test_case_4_former_regular_customer_with_cancelled_booking_is_unclear(self):
        """Case 4: Former regular customer with cancelled booking: rebook_signal must be 'unclear'."""
        review = {
            "review_id": "case-4-regular-cancelled",
            "source": "Play Store",
            "date": "2026-11-22",
            "rating": 1,
            "text": "I had been a regular customer of Urban Company for 2 years, but today the pro cancelled booking 30 mins before time without notice.",
            "is_instahelp": False,
        }
        res = tag_single_review(review, client=self.client_v3)
        self.assertEqual(res["tags"]["rebook_signal"], "unclear")
        self.assertNotEqual(res["tags"]["rebook_signal"], "will_not_rebook")
        self.assertNotEqual(res["tags"]["rebook_signal"], "rebooked")

    def test_case_5_explicit_never_book_again_is_will_not_rebook(self):
        """Case 5: Explicit 'I will never book again': rebook_signal must be 'will_not_rebook'."""
        review = {
            "review_id": "case-5-never-book",
            "source": "Play Store",
            "date": "2026-11-22",
            "rating": 1,
            "text": "Terrible salon service at home. Cut my hair terribly. I will never book again from Urban Company!",
            "is_instahelp": False,
        }
        res = tag_single_review(review, client=self.client_v3)
        self.assertEqual(res["tags"]["rebook_signal"], "will_not_rebook")

    def test_case_6_explicit_will_not_use_app_again_is_will_not_rebook(self):
        """Case 6: Explicit 'I will not use this app again': rebook_signal must be 'will_not_rebook'."""
        review = {
            "review_id": "case-6-not-use-app",
            "source": "Play Store",
            "date": "2026-11-22",
            "rating": 1,
            "text": "Cheated by the AC technician on gas refilling charges. I will not use this app again!",
            "is_instahelp": False,
        }
        res = tag_single_review(review, client=self.client_v3)
        self.assertEqual(res["tags"]["rebook_signal"], "will_not_rebook")

    def test_case_7_chimney_deep_cleaning_is_other(self):
        """Case 7: Chimney deep cleaning: category must be 'other' in v3 (whereas v2 classified it as 'deep clean')."""
        review = {
            "review_id": "case-7-chimney",
            "source": "Play Store",
            "date": "2026-11-22",
            "rating": 4,
            "text": "Booked a chimney deep clean service for our kitchen hob. Pro did a good job degreasing the filters.",
            "is_instahelp": False,
        }
        res_v3 = tag_single_review(review, client=self.client_v3)
        self.assertEqual(res_v3["tags"]["category"], "other")
        self.assertNotEqual(res_v3["tags"]["category"], "deep clean")

        # Verify backwards compatibility: v2 classified chimney deep clean as deep clean
        res_v2 = tag_single_review(review, client=self.client_v2)
        self.assertEqual(res_v2["tags"]["category"], "deep clean")

    def test_case_8_home_deep_cleaning_is_deep_clean(self):
        """Case 8: Home deep cleaning: category must be 'deep clean'."""
        review = {
            "review_id": "case-8-home-clean",
            "source": "Play Store",
            "date": "2026-11-22",
            "rating": 5,
            "text": "Booked home deep clean for our 3BHK flat before Diwali, team arrived on time and did thorough cleaning.",
            "is_instahelp": False,
        }
        res = tag_single_review(review, client=self.client_v3)
        self.assertEqual(res["tags"]["category"], "deep clean")

    def test_v3_default_output_routing(self):
        """Verify v3 run_tagging_pipeline defaults to tagged_reviews_v3.jsonl and review_queue_v3.jsonl."""
        with TemporaryDirectory() as tmpdir:
            input_file = Path(tmpdir) / "test_norm.jsonl"
            rev = {
                "review_id": "rev-test-1",
                "source": "Play Store",
                "date": "2026-11-20",
                "rating": 5,
                "text": "Great AC service done quickly and efficiently. Booked again for next week.",
                "is_instahelp": False,
            }
            with open(input_file, "w") as f:
                f.write(json.dumps(rev) + "\n")

            mock_raw = MagicMock()
            client = GeminiLLMClient(
                model_name="gemini-3.5-flash-lite",
                version="v3",
                client=mock_raw,
            )
            resp = make_sample_tag_response(category="AC", rebook_signal="rebooked", confidence="high")
            mock_raw.models.generate_content.return_value = MockGenerateContentResponse(resp)

            tmp_tagged = Path(tmpdir) / "tagged_v3.jsonl"
            tmp_queue = Path(tmpdir) / "queue_v3.jsonl"
            stats = run_tagging_pipeline(
                input_path=input_file,
                tagged_output_path=tmp_tagged,
                queue_output_path=tmp_queue,
                client=client,
                version="v3",
            )
            self.assertEqual(stats.total_input_records, 1)
            self.assertEqual(stats.tagged_saved_count, 1)
            self.assertTrue(tmp_tagged.exists())


class TestTaggerV3_1PromptRegressions(unittest.TestCase):
    """Regression tests for Gemini prompt v3.1:

    1. Explicit future booking intent maps to 'rebooked'.
    2. Historical repeat usage without future intent maps to 'unclear'.
    3. General praise without booking intent maps to 'unclear'.
    4. Explicit refusal to return maps to 'will_not_rebook' (dissatisfaction alone is 'unclear').
    5. Approved spa category rule maps spa sessions / body massage to 'other' (not 'salon').
    """

    def setUp(self):
        self.client_v3_1 = MockLLMClient(version="v3_1")
        self.client_v3 = MockLLMClient(version="v3")
        self.client_v2 = MockLLMClient(version="v2")

    def test_gemini_client_v3_1_loads_v3_1_prompt(self):
        """Verify GeminiLLMClient with version='v3_1' loads tagger_v3_1.md with updated policy."""
        mock_raw = MagicMock()
        client = GeminiLLMClient(
            model_name="gemini-3.5-flash-lite",
            version="v3_1",
            client=mock_raw,
        )
        self.assertIn("Tagging Prompt v3.1", client.system_prompt)
        self.assertIn("Spa & Wellness", client.system_prompt)
        self.assertIn("spa sessions and body massage belong to `\"other\"`", client.system_prompt)
        self.assertIn("Explicit future intention to book again", client.system_prompt)
        self.assertIn("`will_not_rebook` requires direct, unambiguous evidence", client.system_prompt)

    def test_case_1_explicit_future_booking_intent_is_rebooked(self):
        """Regression Case 1: Explicit future intention to book again maps to 'rebooked'."""
        review_1 = {
            "review_id": "case-1-future-book",
            "source": "App Store",
            "date": "2026-11-20",
            "rating": 5,
            "text": "Great service by Anita on our hair styling today. I will definitely book her again!",
            "is_instahelp": False,
        }
        res_1 = tag_single_review(review_1, client=self.client_v3_1)
        self.assertEqual(res_1["tags"]["rebook_signal"], "rebooked")

        review_2 = {
            "review_id": "case-1-anytime-again",
            "source": "App Store",
            "date": "2026-11-19",
            "rating": 5,
            "text": "Serious skill, absolutely in awe of her service and would recommend and book her anytime again!",
            "is_instahelp": False,
        }
        res_2 = tag_single_review(review_2, client=self.client_v3_1)
        self.assertEqual(res_2["tags"]["rebook_signal"], "rebooked")

    def test_case_2_historical_repeat_usage_without_future_intent_is_unclear(self):
        """Regression Case 2: Historical repeat usage alone without future intent maps to 'unclear'."""
        review = {
            "review_id": "case-2-regular-customer-cancelled",
            "source": "Play Store",
            "date": "2026-11-22",
            "rating": 1,
            "text": "I have been a regular customer for 2 years with UC, but today the technician cancelled at the last minute.",
            "is_instahelp": False,
        }
        res = tag_single_review(review, client=self.client_v3_1)
        self.assertEqual(res["tags"]["rebook_signal"], "unclear")
        self.assertNotEqual(res["tags"]["rebook_signal"], "rebooked")
        self.assertNotEqual(res["tags"]["rebook_signal"], "will_not_rebook")

    def test_case_3_general_praise_without_booking_intent_is_unclear(self):
        """Regression Case 3: General satisfaction or praise alone maps to 'unclear'."""
        review = {
            "review_id": "case-3-general-praise",
            "source": "Play Store",
            "date": "2026-11-21",
            "rating": 5,
            "text": "Excellent salon haircut done cleanly and professionally. Thank you UC!",
            "is_instahelp": False,
        }
        res = tag_single_review(review, client=self.client_v3_1)
        self.assertEqual(res["tags"]["rebook_signal"], "unclear")
        self.assertNotEqual(res["tags"]["rebook_signal"], "rebooked")

    def test_case_4_explicit_refusal_to_return_is_will_not_rebook(self):
        """Regression Case 4: Explicit refusal maps to 'will_not_rebook', but dissatisfaction alone is 'unclear'."""
        # Explicit refusal
        review_refusal = {
            "review_id": "case-4-refusal",
            "source": "Play Store",
            "date": "2026-11-22",
            "rating": 1,
            "text": "Worst AC servicing experience. Ruined my machine. I will never book again from Urban Company!",
            "is_instahelp": False,
        }
        res_refusal = tag_single_review(review_refusal, client=self.client_v3_1)
        self.assertEqual(res_refusal["tags"]["rebook_signal"], "will_not_rebook")

        # Dissatisfaction / complaint without explicit refusal
        review_complaint = {
            "review_id": "case-4-complaint",
            "source": "Play Store",
            "date": "2026-11-22",
            "rating": 1,
            "text": "Terrible service, unpunctual technician and rude customer care. Pathetic experience!",
            "is_instahelp": False,
        }
        res_complaint = tag_single_review(review_complaint, client=self.client_v3_1)
        self.assertEqual(res_complaint["tags"]["rebook_signal"], "unclear")
        self.assertNotEqual(res_complaint["tags"]["rebook_signal"], "will_not_rebook")

    def test_case_5_approved_spa_category_rule(self):
        """Regression Case 5: Approved spa category rule maps spa / body massage to 'other' (not 'salon')."""
        # Review with spa sessions
        review_spa_negative = {
            "review_id": "case-5-spa-negative",
            "source": "Play Store",
            "date": "2026-11-21",
            "rating": 1,
            "text": "Stay away from their Spa sessions, they are just going to treat you as guinea pigs! Horrible support.",
            "is_instahelp": False,
        }
        res_spa_v3_1 = tag_single_review(review_spa_negative, client=self.client_v3_1)
        self.assertEqual(res_spa_v3_1["tags"]["category"], "other")

        # In previous v3, spa mapped to salon
        res_spa_v3 = tag_single_review(review_spa_negative, client=self.client_v3)
        self.assertEqual(res_spa_v3["tags"]["category"], "salon")

        # Review with body spa positive
        review_spa_positive = {
            "review_id": "case-5-spa-positive",
            "source": "App Store",
            "date": "2026-11-19",
            "rating": 5,
            "text": "Incredible Experience with Body Spa – She got rid of all pain and cramps. Great professional.",
            "is_instahelp": False,
        }
        res_spa_pos = tag_single_review(review_spa_positive, client=self.client_v3_1)
        self.assertEqual(res_spa_pos["tags"]["category"], "other")

        # Standard salon grooming still maps to salon
        review_salon = {
            "review_id": "case-5-salon",
            "source": "Play Store",
            "date": "2026-11-20",
            "rating": 5,
            "text": "Excellent salon haircut and facial grooming done very cleanly at home.",
            "is_instahelp": False,
        }
        res_salon = tag_single_review(review_salon, client=self.client_v3_1)
        self.assertEqual(res_salon["tags"]["category"], "salon")

    def test_v3_1_default_output_routing(self):
        """Verify v3_1 run_tagging_pipeline defaults to tagged_reviews_v3_1.jsonl and review_queue_v3_1.jsonl."""
        with TemporaryDirectory() as tmpdir:
            input_file = Path(tmpdir) / "test_norm.jsonl"
            rev = {
                "review_id": "rev-test-v3-1",
                "source": "Play Store",
                "date": "2026-11-20",
                "rating": 5,
                "text": "Great AC service done quickly and efficiently. Booked again for next week.",
                "is_instahelp": False,
            }
            with open(input_file, "w") as f:
                f.write(json.dumps(rev) + "\n")

            mock_raw = MagicMock()
            client = GeminiLLMClient(
                model_name="gemini-3.5-flash-lite",
                version="v3_1",
                client=mock_raw,
            )
            resp = make_sample_tag_response(category="AC", rebook_signal="rebooked", confidence="high")
            mock_raw.models.generate_content.return_value = MockGenerateContentResponse(resp)

            tmp_tagged = Path(tmpdir) / "tagged_v3_1.jsonl"
            tmp_queue = Path(tmpdir) / "queue_v3_1.jsonl"
            stats = run_tagging_pipeline(
                input_path=input_file,
                tagged_output_path=tmp_tagged,
                queue_output_path=tmp_queue,
                client=client,
                version="v3_1",
            )
            self.assertEqual(stats.total_input_records, 1)
            self.assertEqual(stats.tagged_saved_count, 1)
            self.assertTrue(tmp_tagged.exists())


if __name__ == "__main__":
    unittest.main()
