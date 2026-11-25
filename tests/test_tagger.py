"""Comprehensive unit and integration tests for AI Tagging Pipeline (engine/tagger.py).

Tests:
1. Exact 16-field tagging schema compliance and enum validations.
2. Separation of normalized source fields and tagging fields.
3. Grounding and strict non-inference rules (city, household_type, alternative_used, need_trigger).
4. Nullable tri-state representation for nothing_went_wrong and recall_gap (no false defaults).
5. Low-information handling for short reviews ('good', 'ok', 'nice').
6. Exclusion of InstaHelp records from core tagging runs.
7. Verification routing to review_queue.jsonl vs tagged_reviews.jsonl.
8. Storage of per-tag evidence quotes and confidence.
9. Pipeline execution with mocked LLM and raw/normalized dataset immutability.
"""

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict

from engine.tagger import (
    ALTERNATIVE_USED_ENUM,
    CATEGORY_ENUM,
    CONFIDENCE_ENUM,
    DISCOVERY_CHANNEL_ENUM,
    EXACT_16_FIELDS,
    EXPERIENCE_TYPE_ENUM,
    HOUSEHOLD_TYPE_ENUM,
    NEED_TRIGGER_ENUM,
    POST_SERVICE_EXPECTATION_ENUM,
    REBOOK_SIGNAL_ENUM,
    BaseLLMClient,
    MockLLMClient,
    evaluate_review_queue_triggers,
    is_low_information_review,
    run_tagging_pipeline,
    tag_single_review,
    validate_16_schema_fields,
    validate_evidence_quote,
)


def compute_sha256(file_path: Path) -> str:
    """Computes SHA-256 hash of a file."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class TestSchemaConformityAndSeparation(unittest.TestCase):
    """Verifies that tagging output strictly conforms to schema.md and separates namespaces."""

    def setUp(self):
        self.mock_client = MockLLMClient()

    def test_exact_16_fields_present_and_valid(self):
        """Verify that tagged output contains exactly the 16 schema fields with valid values."""
        sample_review = {
            "review_id": "rev-001",
            "source": "Play Store",
            "date": "2026-11-22",
            "rating": 5,
            "title": None,
            "text": "Booked AC service for summer cooling. Technician arrived on time and did great work. Will book again.",
            "app_version": "7.6.92",
            "review_created_version": "7.6.92",
            "thumbs_up": 0,
            "vote_count": None,
            "vote_sum": None,
            "is_instahelp": False,
        }

        tagged = tag_single_review(sample_review, client=self.mock_client)
        tags = tagged["tags"]

        # Check all 16 fields exist
        self.assertEqual(set(tags.keys()), set(EXACT_16_FIELDS))

        # Check validation passes
        errors = validate_16_schema_fields(tags)
        self.assertEqual(errors, [])

        # Check allowed enum values
        self.assertIn(tags["category"], CATEGORY_ENUM)
        self.assertIn(tags["experience_type"], EXPERIENCE_TYPE_ENUM)
        self.assertIn(tags["rebook_signal"], REBOOK_SIGNAL_ENUM)
        self.assertIn(tags["need_trigger"], NEED_TRIGGER_ENUM)
        self.assertIn(tags["alternative_used"], ALTERNATIVE_USED_ENUM)
        self.assertIn(tags["post_service_expectation"], POST_SERVICE_EXPECTATION_ENUM)
        self.assertIn(tags["discovery_channel"], DISCOVERY_CHANNEL_ENUM)
        self.assertIn(tags["household_type"], HOUSEHOLD_TYPE_ENUM)
        self.assertIn(tags["confidence"], CONFIDENCE_ENUM)

    def test_strict_separation_of_source_and_tagging_fields(self):
        """Verify normalized source metadata and tagging fields reside in separate namespaces."""
        sample_review = {
            "review_id": "appstore-001",
            "source": "App Store",
            "date": "2026-11-15",
            "rating": 1,
            "title": "Terrible plumbing work",
            "text": "Plumber leaked my kitchen pipe and ruined the cabinet. Charged extra. Never booking UC again.",
            "app_version": "7.21",
            "review_created_version": None,
            "thumbs_up": None,
            "vote_count": 2,
            "vote_sum": 2,
            "is_instahelp": False,
        }

        tagged = tag_single_review(sample_review, client=self.mock_client)

        # Namespaces are separate
        self.assertIn("review_id", tagged)
        self.assertIn("normalized_review", tagged)
        self.assertIn("tags", tagged)
        self.assertIn("tag_evidence", tagged)
        self.assertIn("metadata", tagged)

        # Source metadata preserves raw engagement and platform fields
        norm = tagged["normalized_review"]
        self.assertEqual(norm["source"], "App Store")
        self.assertEqual(norm["vote_count"], 2)
        self.assertEqual(norm["vote_sum"], 2)
        self.assertIsNone(norm["thumbs_up"])
        self.assertEqual(norm["app_version"], "7.21")

        # Tags contain schema fields
        self.assertEqual(tagged["tags"]["category"], "plumber")
        self.assertEqual(tagged["tags"]["experience_type"], "negative")
        self.assertEqual(tagged["tags"]["rebook_signal"], "will_not_rebook")


class TestGroundingAndStrictNonInference(unittest.TestCase):
    """Verifies that missing evidence leads to null / unclear and never false assumptions."""

    def setUp(self):
        self.mock_client = MockLLMClient()

    def test_city_never_inferred_without_explicit_mention(self):
        """Verify city is null unless explicitly mentioned in review text."""
        # Case A: No city mentioned
        review_no_city = {
            "review_id": "c-001",
            "source": "Play Store",
            "date": "2026-11-20",
            "rating": 4,
            "text": "Sofa cleaning was thorough and neat.",
            "is_instahelp": False,
        }
        res_a = tag_single_review(review_no_city, client=self.mock_client)
        self.assertIsNone(res_a["tags"]["city"])

        # Case B: City explicitly mentioned
        review_with_city = {
            "review_id": "c-002",
            "source": "Play Store",
            "date": "2026-11-20",
            "rating": 4,
            "text": "AC service technician in Bengaluru arrived on time.",
            "is_instahelp": False,
        }
        res_b = tag_single_review(review_with_city, client=self.mock_client)
        self.assertEqual(res_b["tags"]["city"], "Bengaluru")

    def test_household_and_alternative_and_trigger_not_inferred(self):
        """Verify household_type, alternative_used, and need_trigger default to unclear/null when absent."""
        review = {
            "review_id": "g-001",
            "source": "Play Store",
            "date": "2026-11-20",
            "rating": 4,
            "text": "Electrician fixed the bathroom switch board properly.",
            "is_instahelp": False,
        }
        res = tag_single_review(review, client=self.mock_client)
        self.assertEqual(res["tags"]["household_type"], "unclear")
        self.assertEqual(res["tags"]["alternative_used"], "unclear")
        self.assertIsNone(res["tags"]["need_trigger"])
        self.assertEqual(res["tags"]["discovery_channel"], "unclear")
        self.assertEqual(res["tags"]["post_service_expectation"], "unclear")
        self.assertIsNone(res["tags"]["unmet_need"])

    def test_post_service_expectation_unclear_vs_nothing(self):
        """Verify post_service_expectation defaults to unclear, and uses nothing only when explicitly requested."""
        # Unclear case
        review_unclear = {
            "review_id": "pse-001",
            "source": "Play Store",
            "date": "2026-11-20",
            "rating": 5,
            "text": "AC servicing was done smoothly.",
            "is_instahelp": False,
        }
        res_unclear = tag_single_review(review_unclear, client=self.mock_client)
        self.assertEqual(res_unclear["tags"]["post_service_expectation"], "unclear")

        # Explicit nothing case
        review_nothing = {
            "review_id": "pse-002",
            "source": "Play Store",
            "date": "2026-11-20",
            "rating": 2,
            "text": "Job done but do not call me or send promotional follow ups. I expect nothing more.",
            "is_instahelp": False,
        }
        res_nothing = tag_single_review(review_nothing, client=self.mock_client)
        self.assertEqual(res_nothing["tags"]["post_service_expectation"], "nothing")

    def test_alternative_used_unclear_vs_none(self):
        """Verify alternative_used is unclear when omitted, and none only when explicitly stated."""
        # Unclear case
        review_unclear = {
            "review_id": "alt-001",
            "source": "Play Store",
            "date": "2026-11-20",
            "rating": 5,
            "text": "Sofa cleaning was neat.",
            "is_instahelp": False,
        }
        res_unclear = tag_single_review(review_unclear, client=self.mock_client)
        self.assertEqual(res_unclear["tags"]["alternative_used"], "unclear")

        # Explicit none case
        review_none = {
            "review_id": "alt-002",
            "source": "Play Store",
            "date": "2026-11-20",
            "rating": 5,
            "text": "I did not call anyone else and used only UC for all plumbing issues.",
            "is_instahelp": False,
        }
        res_none = tag_single_review(review_none, client=self.mock_client)
        self.assertEqual(res_none["tags"]["alternative_used"], "none")

    def test_nothing_went_wrong_and_recall_gap_are_nullable_tri_state(self):
        """Verify nothing_went_wrong and recall_gap are null (not false) when evidence is missing."""
        # Standard satisfied review without mention of repeat booking or churn
        review = {
            "review_id": "nww-001",
            "source": "Play Store",
            "date": "2026-11-20",
            "rating": 5,
            "text": "Excellent salon service at home by UC professional.",
            "is_instahelp": False,
        }
        res = tag_single_review(review, client=self.mock_client)
        self.assertIsNone(res["tags"]["nothing_went_wrong"])
        self.assertIsNone(res["tags"]["recall_gap"])

    def test_nothing_went_wrong_true_when_fine_service_but_did_not_rebook(self):
        """Verify nothing_went_wrong is true when service was good but customer stopped rebooking."""
        review = {
            "review_id": "nww-002",
            "source": "Play Store",
            "date": "2026-11-20",
            "rating": 5,
            "text": "Good cleaning service, but I stopped using UC and will not book again because local guy is cheaper.",
            "is_instahelp": False,
        }
        res = tag_single_review(review, client=self.mock_client)
        self.assertTrue(res["tags"]["nothing_went_wrong"])
        self.assertEqual(res["tags"]["alternative_used"], "local provider")

    def test_evidence_quote_must_be_verbatim_substring(self):
        """Verify evidence quote validation detects fabricated or non-existent quotes."""
        text = "The plumber repaired the leaking tap quickly."
        self.assertTrue(validate_evidence_quote("leaking tap", text))
        self.assertTrue(validate_evidence_quote("repaired the leaking tap", text))
        self.assertFalse(validate_evidence_quote("air conditioner cooling", text))


class TestLowInformationAndReviewQueueRouting(unittest.TestCase):
    """Verifies that short/terse reviews are treated as low-information and routed to queue."""

    def setUp(self):
        self.mock_client = MockLLMClient()

    def test_terse_reviews_flagged_as_low_information(self):
        """Verify short reviews ('good', 'ok', 'useful app') are identified as low-info."""
        self.assertTrue(is_low_information_review("good"))
        self.assertTrue(is_low_information_review("ok"))
        self.assertTrue(is_low_information_review("ok ok"))
        self.assertTrue(is_low_information_review("nice"))
        self.assertTrue(is_low_information_review("useful app"))
        self.assertTrue(is_low_information_review("very good service"))

        # Substantive review should not be low info
        self.assertFalse(
            is_low_information_review(
                "Technician came on time, cleaned the split AC filter, and explained the gas pressure."
            )
        )

    def test_low_information_review_routed_to_review_queue(self):
        """Verify low-info review gets confidence: low, rebook_signal: unclear, and enters review queue."""
        terse_review = {
            "review_id": "short-001",
            "source": "Play Store",
            "date": "2026-11-22",
            "rating": 5,
            "text": "good",
            "is_instahelp": False,
        }
        tagged = tag_single_review(terse_review, client=self.mock_client)

        self.assertEqual(tagged["tags"]["confidence"], "low")
        self.assertEqual(tagged["tags"]["rebook_signal"], "unclear")
        self.assertEqual(tagged["tags"]["category"], "unknown")
        self.assertTrue(tagged["metadata"]["requires_human_review"])
        self.assertTrue(any("low_information" in r for r in tagged["metadata"]["review_reasons"]))

    def test_rating_polarity_conflict_triggers_review_queue(self):
        """Verify 5-star review with negative text triggers review queue routing."""
        conflict_review = {
            "review_id": "conf-001",
            "source": "Play Store",
            "date": "2026-11-22",
            "rating": 5,
            "text": "Worst experience ever! The technician broke my tap and flooded the bathroom.",
            "is_instahelp": False,
        }
        tagged = tag_single_review(conflict_review, client=self.mock_client)
        self.assertTrue(tagged["metadata"]["requires_human_review"])
        self.assertTrue(any("rating_polarity_conflict" in r for r in tagged["metadata"]["review_reasons"]))


class TestPipelineEndToEndAndInstaHelpExclusion(unittest.TestCase):
    """Verifies end-to-end pipeline execution, InstaHelp exclusion, and file immutability."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        self.mock_client = MockLLMClient()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_instahelp_excluded_from_core_tagging(self):
        """Verify records with is_instahelp=true are excluded from core tagging files."""
        # Create a mini dataset with 2 core reviews and 1 instahelp review
        test_input = self.temp_path / "test_normalized.jsonl"
        tagged_output = self.temp_path / "tagged.jsonl"
        queue_output = self.temp_path / "queue.jsonl"

        records = [
            {
                "review_id": "core-1",
                "source": "Play Store",
                "date": "2026-11-22",
                "rating": 5,
                "text": "Good AC servicing done by professional technician. Arrived on time.",
                "is_instahelp": False,
            },
            {
                "review_id": "insta-1",
                "source": "Play Store",
                "date": "2026-11-22",
                "rating": 1,
                "text": "InstaHelp maid was late and did not clean utensils properly.",
                "is_instahelp": True,
            },
            {
                "review_id": "core-2",
                "source": "App Store",
                "date": "2026-11-21",
                "rating": 5,
                "title": "Good",
                "text": "ok",
                "is_instahelp": False,
            },
        ]

        with open(test_input, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

        stats = run_tagging_pipeline(
            input_path=test_input,
            tagged_output_path=tagged_output,
            queue_output_path=queue_output,
            client=self.mock_client,
        )

        self.assertEqual(stats.total_input_records, 3)
        self.assertEqual(stats.instahelp_excluded, 1)
        self.assertEqual(stats.eligible_core_reviews, 2)
        self.assertEqual(stats.tagged_saved_count, 1)  # core-1 is substantive
        self.assertEqual(stats.review_queue_count, 1)  # core-2 is short / low-info

        # Verify instahelp review is nowhere in tagged or queue output
        with open(tagged_output, "r", encoding="utf-8") as f:
            tagged_lines = [json.loads(line) for line in f]
            self.assertEqual(len(tagged_lines), 1)
            self.assertEqual(tagged_lines[0]["review_id"], "core-1")
            self.assertFalse(tagged_lines[0]["normalized_review"]["is_instahelp"])

        with open(queue_output, "r", encoding="utf-8") as f:
            queue_lines = [json.loads(line) for line in f]
            self.assertEqual(len(queue_lines), 1)
            self.assertEqual(queue_lines[0]["review_id"], "core-2")

    def test_real_dataset_pipeline_execution_and_integrity(self):
        """Run on data/processed/normalized_reviews.jsonl, check counts and assert raw/proc hash integrity."""
        norm_path = Path("data/processed/normalized_reviews.jsonl")
        gp_path = Path("data/raw/google_play_reviews.jsonl")
        ap_path = Path("data/raw/app_store_reviews.jsonl")

        self.assertTrue(norm_path.exists())
        self.assertTrue(gp_path.exists())
        self.assertTrue(ap_path.exists())

        hash_norm_before = compute_sha256(norm_path)
        hash_gp_before = compute_sha256(gp_path)
        hash_ap_before = compute_sha256(ap_path)

        tagged_output = self.temp_path / "prod_tagged.jsonl"
        queue_output = self.temp_path / "prod_queue.jsonl"

        stats = run_tagging_pipeline(
            input_path=norm_path,
            tagged_output_path=tagged_output,
            queue_output_path=queue_output,
            client=self.mock_client,
        )

        # Integrity check: Raw and normalized files MUST be unchanged
        self.assertEqual(compute_sha256(norm_path), hash_norm_before)
        self.assertEqual(compute_sha256(gp_path), hash_gp_before)
        self.assertEqual(compute_sha256(ap_path), hash_ap_before)

        # Count assertions on 200 real reviews
        self.assertEqual(stats.total_input_records, 200)
        self.assertEqual(stats.instahelp_excluded, 16)
        self.assertEqual(stats.eligible_core_reviews, 184)
        self.assertEqual(stats.tagged_saved_count + stats.review_queue_count, 184)

        # Verify output JSONL files exist and match count
        with open(tagged_output, "r") as f:
            tagged_count = sum(1 for _ in f)
        with open(queue_output, "r") as f:
            queue_count = sum(1 for _ in f)

        self.assertEqual(tagged_count, stats.tagged_saved_count)
        self.assertEqual(queue_count, stats.review_queue_count)


class TestTaggerV2AuditRegressions(unittest.TestCase):
    """Regression tests for all audit cases and edge cases identified in tagger_v1 audit."""

    def setUp(self):
        self.client_v2 = MockLLMClient(version="v2")
        self.client_v1 = MockLLMClient(version="v1")

    def test_audit_case_1_regular_customer_in_churn_context_not_rebooked(self):
        """Audit Case 1 (ID 06b45346-6f25-4d49-9b01-13d980482c2c):
        'regular customer' alone must never imply rebooked, especially when review describes churn.
        """
        review = {
            "review_id": "06b45346-6f25-4d49-9b01-13d980482c2c",
            "source": "Play Store",
            "date": "2026-11-22",
            "rating": 1,
            "text": "I had been a regular customer of urban company but due to one person sujoy mondal I am giving this pap 1 star as he cancelled booking exact half hour before the scheduled time without explaining the reason and customer service seems to be hopeless",
            "is_instahelp": False,
        }
        res_v2 = tag_single_review(review, client=self.client_v2)
        # In v2, rebook_signal must be unclear (NOT rebooked)
        self.assertEqual(res_v2["tags"]["rebook_signal"], "unclear")
        self.assertNotEqual(res_v2["tags"]["rebook_signal"], "rebooked")

        # In v1 legacy, it was erroneously tagged as rebooked
        res_v1 = tag_single_review(review, client=self.client_v1)
        self.assertEqual(res_v1["tags"]["rebook_signal"], "rebooked")

    def test_audit_case_2_washing_machine_repair_not_plumber(self):
        """Audit Case 2 (ID 14816200493):
        Washing machine repair service must be classified as 'other' (appliance), NOT 'plumber'
        simply because an incidental 'water inlet pipe' is mentioned.
        """
        review = {
            "review_id": "14816200493",
            "source": "App Store",
            "date": "2026-11-21",
            "rating": 1,
            "title": "Misleading UC Technicians - Fraud attempts",
            "text": "I had a very disappointing experience with Urban Company. I booked a washing machine repair service because the drum was not rotating. When the technician visited, he claimed that a rat bite had damaged the motherboard and the water inlet pipe, and quoted ₹2,500 for the repair.",
            "is_instahelp": False,
        }
        res_v2 = tag_single_review(review, client=self.client_v2)
        self.assertEqual(res_v2["tags"]["category"], "other")
        self.assertNotEqual(res_v2["tags"]["category"], "plumber")

    def test_audit_case_3_advice_to_customers_not_next_service_advice(self):
        """Audit Case 3 (ID 14816200493):
        'My advice to other customers: Always get a second opinion' is advice to peers,
        NOT a post-service expectation of next-service advice from Urban Company.
        """
        review = {
            "review_id": "14816200493",
            "source": "App Store",
            "date": "2026-11-21",
            "rating": 1,
            "text": "My advice to other customers: Always get a second opinion before approving expensive repairs through Urban Company.",
            "is_instahelp": False,
        }
        res_v2 = tag_single_review(review, client=self.client_v2)
        self.assertEqual(res_v2["tags"]["post_service_expectation"], "unclear")
        self.assertNotEqual(res_v2["tags"]["post_service_expectation"], "next-service advice")

    def test_audit_case_4_warning_against_advice_not_next_service_advice(self):
        """Audit Case 4 (ID 8d00e9ce-01f8-4263-80f1-73d55a830fe7):
        'don't ever take advice of their engineers' warns against technician upsells,
        and must not be tagged as expecting next-service advice.
        """
        review = {
            "review_id": "8d00e9ce-01f8-4263-80f1-73d55a830fe7",
            "source": "Play Store",
            "date": "2026-11-22",
            "rating": 1,
            "text": "don't ever buy any urban company filter parts, it is worst... don't ever take advice of their engineers also, they only pitch for there product which is worst and complete waste of time & money.",
            "is_instahelp": False,
        }
        res_v2 = tag_single_review(review, client=self.client_v2)
        self.assertEqual(res_v2["tags"]["post_service_expectation"], "unclear")
        self.assertNotEqual(res_v2["tags"]["post_service_expectation"], "next-service advice")

    def test_audit_case_5_warranty_complaints_not_warranty_clarity(self):
        """Audit Case 5 (IDs 372c9648-73fe-4245-8121-a8f198701159 & 4e4e2ef9-6dd6-40cc-a65b-a3f327daf7f0):
        Grievances about warranty denial or short warranty periods must not be conflated with
        expecting warranty clarity documentation after service.
        """
        # Case 5a: Criticism of warranty service
        review_a = {
            "review_id": "372c9648-73fe-4245-8121-a8f198701159",
            "source": "Play Store",
            "date": "2026-11-22",
            "rating": 1,
            "text": "Pathetic Warranty Service. Good for low level cleaning jobs. Do NOT go for expensive painting or waterproofing service.",
            "is_instahelp": False,
        }
        res_a = tag_single_review(review_a, client=self.client_v2)
        self.assertEqual(res_a["tags"]["post_service_expectation"], "unclear")
        self.assertNotEqual(res_a["tags"]["post_service_expectation"], "warranty clarity")

        # Case 5b: Complaint about expired 10-day warranty window
        review_b = {
            "review_id": "4e4e2ef9-6dd6-40cc-a65b-a3f327daf7f0",
            "source": "Play Store",
            "date": "2026-11-22",
            "rating": 1,
            "text": "Now I cannot claim warranty as it was just valid for 10 days. I'm extremely unhappy as I already paid almost Rs 1400 and expected to book another paid service.",
            "is_instahelp": False,
        }
        res_b = tag_single_review(review_b, client=self.client_v2)
        self.assertEqual(res_b["tags"]["post_service_expectation"], "unclear")
        self.assertNotEqual(res_b["tags"]["post_service_expectation"], "warranty clarity")

    def test_audit_case_6_unmet_need_null_without_explicit_friction(self):
        """Audit Case 6:
        Generic dissatisfaction without a specific operational friction must leave unmet_need
        as null rather than synthesizing a fallback phrase.
        """
        review = {
            "review_id": "generic-neg-001",
            "source": "Play Store",
            "date": "2026-11-22",
            "rating": 1,
            "text": "Extremely disappointing service. Complete waste of money and time. Very bad overall.",
            "is_instahelp": False,
        }
        res_v2 = tag_single_review(review, client=self.client_v2)
        self.assertIsNone(res_v2["tags"]["unmet_need"])

        # When explicit friction IS present, unmet_need must capture it
        review_cancel = {
            "review_id": "cancel-001",
            "source": "Play Store",
            "date": "2026-11-22",
            "rating": 1,
            "text": "Technician did not show up and cancelled without notice.",
            "is_instahelp": False,
        }
        res_cancel = tag_single_review(review_cancel, client=self.client_v2)
        self.assertEqual(res_cancel["tags"]["unmet_need"], "reliable professional arrival without cancellations")


if __name__ == "__main__":
    unittest.main()
