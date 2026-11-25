"""Unit tests for production-safe GroqLLMClient and provider selection.

All tests use mocked Groq responses and mock clients. No live API calls are made.
"""

import json
import logging
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
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
    DEFAULT_QUEUE_OUTPUT_V3_1,
    DEFAULT_TAGGED_OUTPUT_V3_1,
    GroqLLMClient,
    PipelineStatistics,
    is_retryable_groq_error,
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
        prompt_tokens: int = 150,
        completion_tokens: int = 80,
        total_tokens: int = 230,
    ):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens


class MockChatCompletion:
    """Mock Groq ChatCompletion response object."""

    def __init__(
        self,
        content: str,
        id: str = "chatcmpl-test-groq-12345",
        prompt_tokens: int = 150,
        completion_tokens: int = 80,
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


class TestGroqClientInitialization(unittest.TestCase):
    """Test client initialization, secure key resolution, and repr formatting."""

    def test_missing_api_key_raises_value_error(self):
        """Verify initializing without GROQ_API_KEY environment variable raises ValueError."""
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError) as ctx:
                GroqLLMClient(client=None, api_key=None, load_env=False)
            self.assertIn("GROQ_API_KEY environment variable is not set", str(ctx.exception))

    def test_explicit_api_key_or_env_var_initialization(self):
        """Verify explicit api_key or GROQ_API_KEY initializes client with default model."""
        with patch.dict(os.environ, {"GROQ_API_KEY": "gsk_fake_test_key_12345"}):
            with patch("groq.Groq") as mock_groq_cls:
                client = GroqLLMClient()
                self.assertEqual(client.model_name, "openai/gpt-oss-120b")
                self.assertEqual(client.version, "v3_1")
                self.assertTrue(mock_groq_cls.called)
                _, kwargs = mock_groq_cls.call_args
                self.assertEqual(kwargs.get("api_key"), "gsk_fake_test_key_12345")
                self.assertEqual(kwargs.get("max_retries"), 0)

    def test_injected_mock_client_bypasses_api_key_requirement(self):
        """Verify injecting client object allows testing without any API key present."""
        mock_raw_client = MagicMock()
        with patch.dict(os.environ, {}, clear=True):
            client = GroqLLMClient(client=mock_raw_client)
            self.assertIs(client._client, mock_raw_client)
            self.assertEqual(client.model_name, "openai/gpt-oss-120b")

    def test_client_repr_does_not_expose_api_key(self):
        """Verify client __repr__ never leaks credentials or sensitive information."""
        mock_raw_client = MagicMock()
        client = GroqLLMClient(
            model_name="openai/gpt-oss-120b",
            api_key="gsk_super_secret_groq_key_abc123",
            client=mock_raw_client,
        )
        repr_str = repr(client)
        self.assertIn("openai/gpt-oss-120b", repr_str)
        self.assertIn("v3_1", repr_str)
        self.assertNotIn("gsk_super_secret_groq_key_abc123", repr_str)
        self.assertNotIn("api_key", repr_str.lower())

    def test_default_model_and_v3_1_prompt_selected(self):
        """Verify GroqLLMClient defaults to openai/gpt-oss-120b and loads v3_1 prompt."""
        mock_raw_client = MagicMock()
        client = GroqLLMClient(client=mock_raw_client)
        self.assertEqual(client.model_name, "openai/gpt-oss-120b")
        self.assertEqual(client.version, "v3_1")
        self.assertIn("v3.1", client.system_prompt)


class TestGroqClientTagging(unittest.TestCase):
    """Test response parsing, schema validation, and grounding for GroqLLMClient."""

    def setUp(self):
        self.mock_raw_client = MagicMock()
        self.client = GroqLLMClient(
            model_name="openai/gpt-oss-120b",
            version="v3_1",
            client=self.mock_raw_client,
        )
        self.sample_review = {
            "review_id": "test-rev-groq-001",
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
        self.mock_raw_client.chat.completions.create.return_value = MockChatCompletion(json_resp)

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

    def test_markdown_code_fencing_handled_cleanly(self):
        """Verify model output wrapped in markdown code fence blocks is stripped and parsed."""
        raw_json = make_sample_tag_response()
        fenced_output = f"```json\n{raw_json}\n```"
        self.mock_raw_client.chat.completions.create.return_value = MockChatCompletion(fenced_output)

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
        self.mock_raw_client.chat.completions.create.return_value = MockChatCompletion(
            json.dumps(flat_payload)
        )
        result = self.client.tag_review(self.sample_review)
        self.assertEqual(result["tags"]["category"], "AC")
        self.assertEqual(result["tags"]["rebook_signal"], "rebooked")

    def test_malformed_json_response_raises_value_error(self):
        """Verify unparseable or corrupted JSON response raises ValueError."""
        self.mock_raw_client.chat.completions.create.return_value = MockChatCompletion(
            "This is not JSON at all: {broken"
        )
        with self.assertRaises(ValueError) as ctx:
            self.client.tag_review(self.sample_review)
        self.assertIn("Malformed JSON", str(ctx.exception))

    def test_missing_required_fields_raises_value_error(self):
        """Verify response missing core schema fields raises schema validation ValueError."""
        bad_payload = {
            "tags": {
                "source": "Play Store",
                "date": "2026-11-20",
                "experience_type": "positive",
                "nothing_went_wrong": None,
                "confidence": "high",
            }
        }
        self.mock_raw_client.chat.completions.create.return_value = MockChatCompletion(
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
                "category": "invalid_category_xyz",
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
                "evidence_quote": "Great AC service",
                "confidence": "high",
            }
        }
        self.mock_raw_client.chat.completions.create.return_value = MockChatCompletion(
            json.dumps(bad_payload)
        )
        with self.assertRaises(ValueError) as ctx:
            self.client.tag_review(self.sample_review)
        self.assertIn("Invalid category 'invalid_category_xyz'", str(ctx.exception))

    def test_boolean_strings_normalized(self):
        """Verify string 'true' and 'false' for boolean fields are cast cleanly."""
        payload = {
            "tags": {
                "source": "Play Store",
                "date": "2026-11-20",
                "city": None,
                "category": "AC",
                "experience_type": "positive",
                "nothing_went_wrong": "true",
                "rebook_signal": "unclear",
                "need_trigger": None,
                "recall_gap": "false",
                "alternative_used": "unclear",
                "post_service_expectation": "unclear",
                "discovery_channel": "unclear",
                "household_type": "unclear",
                "unmet_need": None,
                "evidence_quote": "Great AC service",
                "confidence": "high",
            }
        }
        self.mock_raw_client.chat.completions.create.return_value = MockChatCompletion(
            json.dumps(payload)
        )
        result = self.client.tag_review(self.sample_review)
        self.assertIs(result["tags"]["nothing_went_wrong"], True)
        self.assertIs(result["tags"]["recall_gap"], False)


class TestGroqClientRetriesAndHeaders(unittest.TestCase):
    """Test retry behavior, rate limits, Retry-After header parsing, and backoff."""

    def setUp(self):
        self.mock_raw_client = MagicMock()
        self.client = GroqLLMClient(
            model_name="openai/gpt-oss-120b",
            version="v3_1",
            max_retries=3,
            initial_backoff=0.01,
            max_backoff=0.05,
            client=self.mock_raw_client,
        )
        self.sample_review = {
            "review_id": "rev-groq-retry-01",
            "source": "Play Store",
            "date": "2026-11-20",
            "rating": 5,
            "text": "Great AC service done quickly",
        }
        self.dummy_req = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")

    def test_parse_retry_after_utility(self):
        """Verify parse_retry_after parses integer, decimal, seconds, ms, and invalid strings."""
        self.assertEqual(parse_retry_after("5"), 5.0)
        self.assertEqual(parse_retry_after("2.5"), 2.5)
        self.assertEqual(parse_retry_after("3s"), 3.0)
        self.assertEqual(parse_retry_after("500ms"), 0.5)
        self.assertIsNone(parse_retry_after(None))
        self.assertIsNone(parse_retry_after(""))
        self.assertIsNone(parse_retry_after("not-a-number"))

    def test_rate_limit_retry_and_recovery(self):
        """Verify HTTP 429 rate limit triggers retry and succeeds on attempt 2."""
        resp_429 = httpx.Response(status_code=429, headers={"x-request-id": "req-429-01"}, request=self.dummy_req)
        api_error_429 = RateLimitError("Rate limit reached", response=resp_429, body=None)
        valid_response = MockChatCompletion(make_sample_tag_response())

        self.mock_raw_client.chat.completions.create.side_effect = [api_error_429, valid_response]

        with patch("time.sleep") as mock_sleep:
            result = self.client.tag_review(self.sample_review)

        self.assertEqual(result["tags"]["category"], "AC")
        self.assertEqual(self.client.total_retries, 1)
        self.assertEqual(self.client.total_errors, 0)
        self.assertEqual(self.mock_raw_client.chat.completions.create.call_count, 2)
        mock_sleep.assert_called()

    def test_retry_after_header_respected(self):
        """Verify Retry-After header duration is used when computing backoff."""
        resp_429 = httpx.Response(
            status_code=429,
            headers={"retry-after": "0.02", "x-request-id": "req-retry-after"},
            request=self.dummy_req,
        )
        api_error_429 = RateLimitError("Rate limit reached", response=resp_429, body=None)
        valid_response = MockChatCompletion(make_sample_tag_response())

        self.mock_raw_client.chat.completions.create.side_effect = [api_error_429, valid_response]

        with patch("time.sleep") as mock_sleep:
            result = self.client.tag_review(self.sample_review)

        self.assertEqual(result["tags"]["category"], "AC")
        self.assertEqual(self.client.total_retries, 1)
        mock_sleep.assert_called()

    def test_rate_limit_exhausted_raises_error(self):
        """Verify exceeding max_retries on persistent rate limits raises exception and updates total_errors."""
        resp_429 = httpx.Response(status_code=429, headers={"x-request-id": "req-exhaust"}, request=self.dummy_req)
        api_error_429 = RateLimitError("Rate limit reached", response=resp_429, body=None)
        self.mock_raw_client.chat.completions.create.side_effect = api_error_429

        with patch("time.sleep"):
            with self.assertRaises(RateLimitError):
                self.client.tag_review(self.sample_review)

        self.assertEqual(self.client.total_retries, 2)
        self.assertEqual(self.client.total_errors, 1)
        self.assertEqual(self.mock_raw_client.chat.completions.create.call_count, 3)

    def test_transient_server_error_retry_and_recovery(self):
        """Verify transient HTTP 500/503 InternalServerError triggers retry and succeeds."""
        resp_500 = httpx.Response(status_code=500, headers={"x-request-id": "req-500-01"}, request=self.dummy_req)
        server_error = InternalServerError("Internal server error", response=resp_500, body=None)
        valid_response = MockChatCompletion(make_sample_tag_response())

        self.mock_raw_client.chat.completions.create.side_effect = [server_error, valid_response]

        with patch("time.sleep"):
            result = self.client.tag_review(self.sample_review)

        self.assertEqual(result["tags"]["category"], "AC")
        self.assertEqual(self.client.total_retries, 1)
        self.assertEqual(self.client.total_errors, 0)

    def test_non_retryable_client_error_fails_immediately(self):
        """Verify non-retryable 400 Bad Request error fails on attempt 1 without retrying."""
        resp_400 = httpx.Response(status_code=400, headers={"x-request-id": "req-400"}, request=self.dummy_req)
        bad_request = BadRequestError("Invalid parameter", response=resp_400, body=None)
        self.mock_raw_client.chat.completions.create.side_effect = bad_request

        with self.assertRaises(BadRequestError):
            self.client.tag_review(self.sample_review)

        self.assertEqual(self.client.total_retries, 0)
        self.assertEqual(self.client.total_errors, 1)
        self.assertEqual(self.mock_raw_client.chat.completions.create.call_count, 1)

    def test_non_retryable_auth_error_fails_immediately(self):
        """Verify non-retryable 401 AuthenticationError fails on attempt 1 without retrying."""
        resp_401 = httpx.Response(status_code=401, headers={"x-request-id": "req-401"}, request=self.dummy_req)
        auth_error = AuthenticationError("Invalid API Key", response=resp_401, body=None)
        self.mock_raw_client.chat.completions.create.side_effect = auth_error

        with self.assertRaises(AuthenticationError):
            self.client.tag_review(self.sample_review)

        self.assertEqual(self.client.total_retries, 0)
        self.assertEqual(self.client.total_errors, 1)
        self.assertEqual(self.mock_raw_client.chat.completions.create.call_count, 1)

    def test_request_delay_applied(self):
        """Verify configured request_delay invokes time.sleep before executing API call."""
        client_with_delay = GroqLLMClient(
            model_name="openai/gpt-oss-120b",
            request_delay=0.5,
            client=self.mock_raw_client,
        )
        self.mock_raw_client.chat.completions.create.return_value = MockChatCompletion(
            make_sample_tag_response()
        )

        with patch("time.sleep") as mock_sleep:
            client_with_delay.tag_review(self.sample_review)

        mock_sleep.assert_called_with(0.5)


class TestGroqClientSafeLogging(unittest.TestCase):
    """Test that logger messages output metadata and never expose secrets or review text."""

    def test_safe_logging_never_exposes_api_key_or_review_text(self):
        """Verify logging outputs review ID and attempt, but NEVER full review text or secrets."""
        mock_raw_client = MagicMock()
        mock_raw_client.chat.completions.create.return_value = MockChatCompletion(
            make_sample_tag_response()
        )
        client = GroqLLMClient(
            model_name="openai/gpt-oss-120b",
            api_key="gsk_secret_token_xyz987",
            client=mock_raw_client,
        )

        sensitive_review = {
            "review_id": "rev-safe-log-01",
            "source": "Play Store",
            "date": "2026-11-20",
            "rating": 5,
            "text": "SENSITIVE_CUSTOMER_PII_AND_PRIVATE_NOTES_HERE_DO_NOT_LOG",
        }

        with self.assertLogs("engine.tagger", level="INFO") as log_capture:
            client.tag_review(sensitive_review)

        all_logs = " ".join(log_capture.output)
        self.assertIn("rev-safe-log-01", all_logs)
        self.assertNotIn("SENSITIVE_CUSTOMER_PII_AND_PRIVATE_NOTES_HERE_DO_NOT_LOG", all_logs)
        self.assertNotIn("gsk_secret_token_xyz987", all_logs)

    def test_token_usage_and_request_id_logged(self):
        """Verify request ID and token usage counts are captured in logs."""
        mock_raw_client = MagicMock()
        mock_raw_client.chat.completions.create.return_value = MockChatCompletion(
            make_sample_tag_response(),
            id="chatcmpl-custom-req-id-777",
            prompt_tokens=180,
            completion_tokens=65,
        )
        client = GroqLLMClient(
            model_name="openai/gpt-oss-120b",
            client=mock_raw_client,
        )

        sample_rev = {
            "review_id": "rev-token-log-02",
            "source": "Play Store",
            "date": "2026-11-20",
            "rating": 5,
            "text": "Great service done quickly",
        }

        with self.assertLogs("engine.tagger", level="INFO") as log_capture:
            client.tag_review(sample_rev)

        all_logs = " ".join(log_capture.output)
        self.assertIn("chatcmpl-custom-req-id-777", all_logs)
        self.assertIn("prompt_tokens: 180", all_logs)
        self.assertIn("completion_tokens: 65", all_logs)
        self.assertIn("total_tokens: 245", all_logs)


class TestGroqPipelineAndCLI(unittest.TestCase):
    """Test tag_single_review, run_tagging_pipeline, and CLI integration with GroqLLMClient."""

    def test_tag_single_review_metadata_integration(self):
        """Verify tag_single_review integrates with GroqLLMClient and packages metadata."""
        mock_raw_client = MagicMock()
        mock_raw_client.chat.completions.create.return_value = MockChatCompletion(
            make_sample_tag_response(category="AC", experience_type="positive")
        )
        client = GroqLLMClient(
            model_name="openai/gpt-oss-120b",
            version="v3_1",
            client=mock_raw_client,
        )

        review = {
            "review_id": "rev-pipe-01",
            "source": "Play Store",
            "date": "2026-11-20",
            "rating": 5,
            "text": "Great AC service done quickly",
        }

        tagged_item = tag_single_review(review, client=client)
        self.assertEqual(tagged_item["review_id"], "rev-pipe-01")
        self.assertEqual(tagged_item["metadata"]["model"], "openai/gpt-oss-120b")
        self.assertEqual(tagged_item["metadata"]["prompt_version"], "tagger_v3_1")
        self.assertFalse(tagged_item["metadata"]["requires_human_review"])

    def test_run_tagging_pipeline_with_groq_client(self):
        """Verify run_tagging_pipeline runs with GroqLLMClient without live API calls."""
        mock_raw_client = MagicMock()
        mock_raw_client.chat.completions.create.return_value = MockChatCompletion(
            make_sample_tag_response(category="AC", experience_type="positive")
        )
        client = GroqLLMClient(
            model_name="openai/gpt-oss-120b",
            version="v3_1",
            client=mock_raw_client,
        )

        sample_reviews = [
            {
                "review_id": f"rev-groq-{i}",
                "source": "Play Store",
                "date": "2026-11-20",
                "rating": 5,
                "text": "Great AC service done quickly and professionally",
                "is_instahelp": False,
            }
            for i in range(2)
        ]

        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_file = tmp_path / "input.jsonl"
            tagged_file = tmp_path / "tagged.jsonl"
            queue_file = tmp_path / "queue.jsonl"

            with open(input_file, "w") as f:
                for r in sample_reviews:
                    f.write(json.dumps(r) + "\n")

            stats = run_tagging_pipeline(
                input_path=input_file,
                tagged_output_path=tagged_file,
                queue_output_path=queue_file,
                client=client,
                version="v3_1",
                resume=False,
            )

            self.assertEqual(stats.total_input_records, 2)
            self.assertEqual(stats.eligible_core_reviews, 2)
            self.assertEqual(stats.tagged_saved_count, 2)
            self.assertEqual(stats.review_queue_count, 0)
            self.assertEqual(stats.errors_count, 0)

            # Check output file on disk
            with open(tagged_file, "r") as f:
                lines = [json.loads(line) for line in f if line.strip()]
            self.assertEqual(len(lines), 2)
            self.assertEqual(lines[0]["metadata"]["model"], "openai/gpt-oss-120b")
            self.assertEqual(lines[0]["metadata"]["prompt_version"], "tagger_v3_1")

    def test_cli_provider_groq_argument_parsing(self):
        """Verify CLI parses --provider groq and defaults to openai/gpt-oss-120b."""
        test_args = ["engine.tagger", "--provider", "groq", "--limit", "1"]
        with patch("sys.argv", test_args):
            with patch.dict(os.environ, {"GROQ_API_KEY": "fake_gsk_key"}):
                with patch("engine.tagger.run_tagging_pipeline") as mock_pipeline:
                    with patch("groq.Groq"):
                        mock_pipeline.return_value = PipelineStatistics()
                        main()
                        self.assertTrue(mock_pipeline.called)
                        _, kwargs = mock_pipeline.call_args
                        client = kwargs.get("client")
                        self.assertIsInstance(client, GroqLLMClient)
                        self.assertEqual(client.model_name, "openai/gpt-oss-120b")


if __name__ == "__main__":
    unittest.main()
