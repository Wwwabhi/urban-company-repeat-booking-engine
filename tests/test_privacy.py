"""Comprehensive privacy and exclusion validation test suite for Google Play collector.

Validates:
1. Phone number redaction across standard and edge-case Indian phone formats.
2. Email redaction across standard, multi-domain, and malformed email patterns.
3. Distinction between postal pincodes (flagged) and ordinary six-digit numbers (order IDs, currency, metrics - not flagged).
4. Physical address detection (flats, apartments, house numbers, named roads, sectors).
5. False positive avoidance on realistic conversational phrases involving 'road', 'colony', and 'nagar'.
6. Exclusion behavior: reviews with addresses or pincodes are never written to JSONL.
7. Zero secondary storage: no quarantine, dump, or secondary files created.
8. Safe logging: exclusion logs omit review IDs and personal data, recording only counts and reason categories.
9. Bit-level and semantic data integrity test for the original 20 collected records.
"""

from __future__ import annotations

import hashlib
import json
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from engine.collectors.google_play import (
    ADDRESS_CUE_PATTERN,
    EMAIL_PATTERN,
    PHONE_PATTERN,
    audit_privacy,
    collect_reviews,
    has_potential_pincode,
    redact_person_names,
    redact_pii,
)

EXPECTED_RAW_DATA_SHA256 = (
    "3fd7f281006826bdcdf82c8c279b7c6819365c868025fa965c18573cf9035301"
)


class TestPhoneRedactionEdgeCases(unittest.TestCase):
    def test_indian_phone_formats_redacted(self):
        """Verify Indian phone numbers across diverse formats are completely redacted."""
        test_cases = [
            ("Call me at 9876543210 please", "Call me at [PHONE_REDACTED] please"),
            ("Reach out on +91 9876543210", "Reach out on [PHONE_REDACTED]"),
            ("Mobile: +91-9876543210", "Mobile: [PHONE_REDACTED]"),
            ("Contact: +919876543210 now", "Contact: [PHONE_REDACTED] now"),
            ("Dial (+91) 9876543210 today", "Dial [PHONE_REDACTED] today"),
            ("Dial (+91)9876543210 today", "Dial [PHONE_REDACTED] today"),
            ("Number: 09876543210", "Number: [PHONE_REDACTED]"),
            ("Phone: 98765 43210", "Phone: [PHONE_REDACTED]"),
            ("Contact: 98765-43210", "Contact: [PHONE_REDACTED]"),
            ("Cell 9876 543 210", "Cell [PHONE_REDACTED]"),
            ("Cell 9876-543-210", "Cell [PHONE_REDACTED]"),
            ("Helpline: 987-654-3210", "Helpline: [PHONE_REDACTED]"),
        ]
        for raw, expected in test_cases:
            redacted = redact_pii(raw)
            self.assertEqual(redacted, expected)
            self.assertFalse(
                PHONE_PATTERN.search(redacted),
                f"Residual phone pattern found in: '{redacted}' (from '{raw}')",
            )

    def test_non_phone_numbers_not_redacted(self):
        """Verify non-phone numbers (ratings, years, prices) are not falsely redacted."""
        clean_cases = [
            "Model number was 1234",
            "Rated 5 stars out of 5",
            "Cost was 5000 rs",
            "Booked in year 2026",
            "Total 45 minutes taken",
        ]
        for text in clean_cases:
            self.assertEqual(redact_pii(text), text)


class TestEmailRedactionEdgeCases(unittest.TestCase):
    def test_standard_and_malformed_emails_redacted(self):
        """Verify standard, sub-domain, and malformed emails are redacted."""
        test_cases = [
            ("Email user@example.com for help", "Email [EMAIL_REDACTED] for help"),
            ("Write to john.doe@company.in", "Write to [EMAIL_REDACTED]"),
            ("Contact rahul.sharma@corp.sub.co.in", "Contact [EMAIL_REDACTED]"),
            # Malformed email patterns commonly seen in reviews
            ("Reach out at rahul@gmail", "Reach out at [EMAIL_REDACTED]"),
            ("Email me at user@.com", "Email me at [EMAIL_REDACTED]"),
            ("Contact user@@domain.com please", "Contact [EMAIL_REDACTED] please"),
            ("Write to user@domain..com", "Write to [EMAIL_REDACTED]"),
        ]
        for raw, expected in test_cases:
            redacted = redact_pii(raw)
            self.assertEqual(redacted, expected)

    def test_non_email_symbols_not_redacted(self):
        """Verify standalone '@' expressions (pricing, time, ratings) are preserved."""
        non_emails = [
            "Price was @ 500 per tap",
            "Technician arrived @ noon",
            "Rating service @ 5 stars",
        ]
        for text in non_emails:
            self.assertEqual(redact_pii(text), text)


class TestPincodeVsOrdinaryNumbers(unittest.TestCase):
    def test_ordinary_six_digit_numbers_not_flagged(self):
        """Verify 6-digit numbers in order IDs, references, or monetary amounts are NOT flagged as pincodes."""
        non_pincode_cases = [
            "My booking ID 123456 was cancelled without reason",
            "Order #654321 was delayed by 2 hours",
            "Order id: 789012 needs refund",
            "Complaint ref 987654 is still open",
            "Ticket number 112233",
            "Transaction id 543210 failed",
            "Service request sr-654321",
            "Paid 100000 rupees for complete home renovation",
            "Cost was INR 150000 which is too high",
            "Charged Rs 120000 for electrical wiring",
            "Over 500000 happy customers mentioned in app",
            "App has 250000+ reviews on store",
        ]
        for text in non_pincode_cases:
            self.assertFalse(
                has_potential_pincode(text),
                f"Ordinary 6-digit number falsely flagged as pincode in: '{text}'",
            )
            flags = audit_privacy(redact_pii(text))
            self.assertNotIn("potential_postal_pincode", flags)

    def test_actual_postal_pincodes_flagged(self):
        """Verify authentic postal pincodes (explicit or address-contextual) are flagged."""
        pincode_cases = [
            "Service at 560034 Bangalore was very quick",
            "Pincode: 110001 Delhi",
            "Area pin 400001 South Mumbai",
            "Living near postal code 201301",
            "Delivered to 560 102 layout",
            "Area code 500081",
        ]
        for text in pincode_cases:
            self.assertTrue(
                has_potential_pincode(text),
                f"Authentic pincode was NOT detected in: '{text}'",
            )
            flags = audit_privacy(redact_pii(text))
            self.assertIn("potential_postal_pincode", flags)


class TestAddressDetectionAndFalsePositives(unittest.TestCase):
    def test_realistic_ordinary_reviews_false_positive_avoidance(self):
        """Verify conversational phrases containing 'road', 'colony', and 'nagar' are NOT flagged as addresses."""
        ordinary_phrases = [
            # Usages of 'road'
            "The technician was delayed because the road was under repair.",
            "I just called the local electrician down the road.",
            "Traffic on the road was bad, but he arrived quickly.",
            "The best salon service on the road today.",
            "Great service, smooth road to regular home maintenance.",
            "The toll road took longer than expected.",
            "Cross the road to get groceries while the cleaner worked.",
            "His bike broke down on the road.",
            "The road was bumpy but the driver was careful.",
            "Called him when he was on the road.",
            # Usages of 'colony'
            "Pest control cleared an ant colony in our kitchen.",
            "Termite colony found behind the wooden cupboard.",
            "We moved to a new colony recently and used Urban Company.",
            "Living in a gated colony with strict security.",
            "Our colony maintenance team could not fix the leakage.",
            # Usages of personal names with 'nagar'
            "The professional, Nagaraj, was polite and skilled.",
            "Nagarjuna was our AC service guy, very thorough.",
            "Technician named Nagarathna did a wonderful job.",
        ]
        for text in ordinary_phrases:
            redacted = redact_pii(text)
            flags = audit_privacy(redacted)
            self.assertEqual(
                flags,
                [],
                f"False positive triggered for ordinary review: '{text}' -> Flags: {flags}",
            )

    def test_real_address_cues_detected(self):
        """Verify specific residential, apartment, and street addresses are flagged."""
        address_samples = [
            "Technician visited Flat 302, Palm Springs Apartments",
            "Delivered to Apt 4B, Sunrise Towers",
            "House no 15/A, Block C",
            "Office is at 12th Main Road",
            "Located at MG Road near metro station",
            "Living in Sector 62, Noida",
            "I stay in Rose Colony, 5th Cross",
            "Service at JP Nagar 2nd Phase",
            "Road no 4, Banjara Hills",
        ]
        for text in address_samples:
            flags = audit_privacy(text)
            self.assertIn("potential_address_cue", flags, f"Failed on: '{text}'")


class TestExclusionAndStorageBehavior(unittest.TestCase):
    def test_excluded_reviews_never_written_to_storage_or_secondary_files(self):
        """Verify flagged reviews with addresses/pincodes are excluded from JSONL and no secondary files exist."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            test_jsonl = tmp_path / "test_reviews.jsonl"

            mock_reviews = [
                {
                    "reviewId": "rev-clean",
                    "content": "Excellent AC service, very professional.",
                    "score": 5,
                    "at": None,
                    "thumbsUpCount": 0,
                    "appVersion": "1.0",
                    "reviewCreatedVersion": "1.0",
                },
                {
                    "reviewId": "rev-phone",
                    "content": "Called +91 9876543210 to reschedule, great support.",
                    "score": 4,
                    "at": None,
                    "thumbsUpCount": 1,
                    "appVersion": "1.0",
                    "reviewCreatedVersion": "1.0",
                },
                {
                    "reviewId": "rev-address",
                    "content": "Technician came to Flat 402, Sunshine Towers, MG Road.",
                    "score": 1,
                    "at": None,
                    "thumbsUpCount": 0,
                    "appVersion": "1.0",
                    "reviewCreatedVersion": "1.0",
                },
                {
                    "reviewId": "rev-pincode",
                    "content": "Poor service in area pincode 560034.",
                    "score": 1,
                    "at": None,
                    "thumbsUpCount": 0,
                    "appVersion": "1.0",
                    "reviewCreatedVersion": "1.0",
                },
            ]

            with patch("engine.collectors.google_play.reviews", return_value=(mock_reviews, None)):
                saved_count = collect_reviews(
                    app_id="com.urbanclap.urbanclap",
                    target_count=4,
                    output_path=test_jsonl,
                )

            self.assertEqual(saved_count, 2)
            self.assertTrue(test_jsonl.exists())

            with test_jsonl.open("r", encoding="utf-8") as f:
                saved_records = [json.loads(line) for line in f]

            saved_ids = [r["id"] for r in saved_records]
            self.assertIn("rev-clean", saved_ids)
            self.assertIn("rev-phone", saved_ids)
            self.assertNotIn("rev-address", saved_ids)
            self.assertNotIn("rev-pincode", saved_ids)

            # Verify no quarantine, secondary, or error files exist
            all_files_in_dir = list(tmp_path.iterdir())
            self.assertEqual(
                all_files_in_dir,
                [test_jsonl],
                f"Unexpected secondary files found: {all_files_in_dir}",
            )


class TestSafeExclusionLoggingWithoutReviewIds(unittest.TestCase):
    def test_exclusion_logs_omit_review_ids_and_personal_text(self):
        """Verify that privacy-exclusion logs contain NO review IDs, NO review text, and only counts/reasons."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_jsonl = Path(tmp_dir) / "test_log_reviews.jsonl"
            sensitive_review = {
                "reviewId": "secret-rev-id-998877",
                "content": "Please come to Flat 402, Sunshine Towers, MG Road, 560001, phone 9876543210",
                "score": 1,
                "at": None,
                "thumbsUpCount": 0,
                "appVersion": "1.0",
                "reviewCreatedVersion": "1.0",
            }

            logger = logging.getLogger("engine.collectors.google_play")
            with self.assertLogs(logger, level="INFO") as log_capture:
                with patch(
                    "engine.collectors.google_play.reviews",
                    return_value=([sensitive_review], None),
                ):
                    collect_reviews(
                        app_id="com.urbanclap.urbanclap",
                        target_count=1,
                        output_path=test_jsonl,
                    )

            all_logs = " ".join(log_capture.output)

            # Assert NO review IDs appear in the exclusion logs
            self.assertNotIn(
                "secret-rev-id-998877",
                all_logs,
                "Review ID was leaked in privacy-exclusion logs!",
            )

            # Assert NO sensitive text appears in logs
            self.assertNotIn("Flat 402", all_logs)
            self.assertNotIn("Sunshine Towers", all_logs)
            self.assertNotIn("MG Road", all_logs)
            self.assertNotIn("560001", all_logs)
            self.assertNotIn("9876543210", all_logs)

            # Assert aggregate count and reason categories are reported
            self.assertIn("Privacy exclusion summary:", all_logs)
            self.assertTrue(
                "potential_address_cue" in all_logs or "potential_postal_pincode" in all_logs
            )


class TestExistingCollectedDataIntegrity(unittest.TestCase):
    def test_original_records_strictly_preserved_in_scaled_dataset(self):
        """Verify that data/raw/google_play_reviews.jsonl has 100 unique records, matching SHA-256 and preserving original records."""
        data_path = Path("data/raw/google_play_reviews.jsonl")
        self.assertTrue(data_path.exists(), "Raw data file does not exist!")

        # 1. Byte-level SHA-256 verification
        with data_path.open("rb") as f:
            actual_sha256 = hashlib.sha256(f.read()).hexdigest()

        self.assertEqual(
            actual_sha256,
            EXPECTED_RAW_DATA_SHA256,
            f"Raw data file content has changed! Expected SHA256 {EXPECTED_RAW_DATA_SHA256}, got {actual_sha256}",
        )

        # 2. Semantic line and content verification
        with data_path.open("r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]

        self.assertEqual(len(lines), 100, f"Expected exactly 100 records, found {len(lines)}")

        records = [json.loads(line) for line in lines]
        unique_ids = {r["id"] for r in records}
        self.assertEqual(len(unique_ids), 100, "Duplicate review IDs found in Google Play dataset!")

        # Verify original anchor records are preserved at indices 0 and 19
        self.assertEqual(records[0]["id"], "f4bcceaf-e12b-46d6-9658-33735b080f2e")
        self.assertEqual(records[19]["id"], "4343259e-45ba-41dd-9750-940b886887c2")

        required_keys = {"id", "source", "date", "score", "text"}
        for r in records:
            self.assertTrue(required_keys.issubset(r.keys()))
            self.assertNotIn("userName", r)
            self.assertNotIn("userImage", r)
            self.assertEqual(r["source"], "Play Store")


class TestPersonNameRedaction(unittest.TestCase):
    """Test suite for contextual third-party personal name redaction."""

    def test_pilot_dataset_apple_review_names_redacted(self):
        """Verify exact case found in Apple review 14816172315: partner names Ramprit and Mohammad are redacted."""
        text = "The other deep cleaning services provided by UC are excellent. Whether it is Ramprit, Mohammad they are very professional."
        redacted = redact_person_names(text)
        self.assertIn("Whether it is [NAME_REDACTED], [NAME_REDACTED] they are very professional.", redacted)
        self.assertNotIn("Ramprit", redacted)
        self.assertNotIn("Mohammad", redacted)
        self.assertIn("UC", redacted)

    def test_role_prefixed_person_names_redacted(self):
        """Verify worker names following role cues (technician, beautician, cleaner) are redacted."""
        text = "The technician named Amit was punctual. Beautician Priya did a great job. Cleaner Anita was polite."
        redacted = redact_person_names(text)
        self.assertEqual(
            redacted,
            "The technician named [NAME_REDACTED] was punctual. Beautician [NAME_REDACTED] did a great job. Cleaner [NAME_REDACTED] was polite.",
        )

    def test_honorific_prefixed_person_names_redacted(self):
        """Verify names following honorifics (Mr., Ms., Dr., Mohd.) are redacted."""
        text = "Mr. Sharma and Dr. Verma praised the plumber Mohd. Khan for quick repairs."
        redacted = redact_person_names(text)
        self.assertIn("Mr. [NAME_REDACTED]", redacted)
        self.assertIn("Dr. [NAME_REDACTED]", redacted)
        self.assertIn("plumber [NAME_REDACTED]", redacted)
        self.assertNotIn("Sharma", redacted)
        self.assertNotIn("Verma", redacted)

    def test_attribution_and_gratitude_person_names_redacted(self):
        """Verify names preceded by 'done by' or 'thanks to' are redacted."""
        text = "AC repair done by Ramesh was great. Special thanks to Suresh Kumar for prompt response."
        redacted = redact_person_names(text)
        self.assertEqual(
            redacted,
            "AC repair done by [NAME_REDACTED] was great. Special thanks to [NAME_REDACTED] for prompt response.",
        )

    def test_brand_and_product_whitelist_not_redacted(self):
        """Verify platform, brand, and proprietary product names are NEVER redacted."""
        text = "Ikea stuff install. Done by urban company very well. We also tried InstaHelp and Native M1 Pro Purifier."
        redacted = redact_person_names(text)
        self.assertIn("Ikea stuff install", redacted)
        self.assertIn("Done by urban company very well", redacted)
        self.assertIn("InstaHelp", redacted)
        self.assertIn("Native M1 Pro Purifier", redacted)
        self.assertNotIn("[NAME_REDACTED]", redacted)

    def test_cosmetics_and_acronyms_not_redacted(self):
        """Verify cosmetic treatments and industry acronyms are preserved."""
        text = "I booked kanpeki detan facial but she gave me o3 detan. Need human care instead of AI."
        redacted = redact_person_names(text)
        self.assertIn("kanpeki", redacted)
        self.assertIn("o3", redacted)
        self.assertIn("AI", redacted)
        self.assertNotIn("[NAME_REDACTED]", redacted)

    def test_ordinary_capitalized_words_not_redacted(self):
        """Verify ordinary capitalized sentence starters and title words are preserved."""
        text = "Cleaning. Good service. Surge Charge. Price hikes. Not reliable."
        redacted = redact_person_names(text)
        self.assertEqual(redacted, text)

    def test_redact_pii_integration_includes_names(self):
        """Verify that redact_pii() integrates phone, email, and contextual name redaction seamlessly."""
        text = "Call 9876543210 or email test@example.com. Service done by Ramesh."
        cleaned = redact_pii(text)
        self.assertIn("[PHONE_REDACTED]", cleaned)
        self.assertIn("[EMAIL_REDACTED]", cleaned)
        self.assertIn("Service done by [NAME_REDACTED].", cleaned)
        self.assertNotIn("9876543210", cleaned)
        self.assertNotIn("test@example.com", cleaned)
        self.assertNotIn("Ramesh", cleaned)


class TestGooglePlayCollectorReliabilityAndResume(unittest.TestCase):
    """Test suite for Google Play collector immediate batch persistence, resume, delay, and deduplication."""

    @patch("engine.collectors.google_play.reviews")
    def test_batch_immediate_persistence_and_fault_tolerance(self, mock_reviews):
        """Verify that records are persisted batch-by-batch and preserved on subsequent failure."""
        batch_1 = [
            {"reviewId": "gp-batch1-1", "content": "Good service on batch 1", "score": 5, "at": None},
            {"reviewId": "gp-batch1-2", "content": "Nice AC cleaning", "score": 4, "at": None},
        ]
        mock_reviews.side_effect = [
            (batch_1, "token-page-2"),
            RuntimeError("Simulated connection timeout on batch 2"),
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            test_jsonl = Path(tmp_dir) / "test_gp_persistence.jsonl"

            with self.assertRaises(RuntimeError) as ctx:
                collect_reviews(
                    app_id="com.urbanclap.urbanclap",
                    target_count=4,
                    output_path=test_jsonl,
                    request_delay=0.0,
                )

            self.assertIn("Google Play collection failed on batch 2 after collecting 2 reviews", str(ctx.exception))
            self.assertIn("Simulated connection timeout on batch 2", str(ctx.exception))

            # Verify that the 2 valid reviews from batch 1 were persisted to disk
            self.assertTrue(test_jsonl.exists())
            with test_jsonl.open("r", encoding="utf-8") as f:
                saved = [json.loads(l) for l in f if l.strip()]

            self.assertEqual(len(saved), 2)
            self.assertEqual([r["id"] for r in saved], ["gp-batch1-1", "gp-batch1-2"])

    @patch("engine.collectors.google_play.reviews")
    def test_resume_and_retry_skips_duplicates_and_preserves_data(self, mock_reviews):
        """Verify resume run reads existing IDs, skips duplicates, and appends only new records."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_jsonl = Path(tmp_dir) / "test_gp_resume.jsonl"

            # Pre-populate with existing records (from an earlier run)
            initial_records = [
                {"id": "gp-existing-1", "source": "Play Store", "date": "2026-11-22", "score": 5, "text": "First"},
                {"id": "gp-existing-2", "source": "Play Store", "date": "2026-11-22", "score": 4, "text": "Second"},
            ]
            with test_jsonl.open("w", encoding="utf-8") as f:
                for r in initial_records:
                    f.write(json.dumps(r) + "\n")

            # Mock scraper returning:
            # Batch 1: returns existing-1 and existing-2 (both duplicate)
            # Batch 2: returns new-3 and new-4
            batch_1 = [
                {"reviewId": "gp-existing-1", "content": "First", "score": 5, "at": None},
                {"reviewId": "gp-existing-2", "content": "Second", "score": 4, "at": None},
            ]
            batch_2 = [
                {"reviewId": "gp-new-3", "content": "Third new review", "score": 5, "at": None},
                {"reviewId": "gp-new-4", "content": "Fourth new review", "score": 4, "at": None},
            ]
            mock_reviews.side_effect = [
                (batch_1, "token-2"),
                (batch_2, None),
            ]

            collected = collect_reviews(
                app_id="com.urbanclap.urbanclap",
                target_count=2,
                output_path=test_jsonl,
                request_delay=0.0,
            )

            self.assertEqual(collected, 2)

            with test_jsonl.open("r", encoding="utf-8") as f:
                all_saved = [json.loads(l) for l in f if l.strip()]

            self.assertEqual(len(all_saved), 4)
            all_ids = [r["id"] for r in all_saved]
            self.assertEqual(all_ids, ["gp-existing-1", "gp-existing-2", "gp-new-3", "gp-new-4"])
            self.assertEqual(len(all_ids), len(set(all_ids)), "Duplicate review ID found in output file!")

    @patch("time.sleep")
    @patch("engine.collectors.google_play.reviews")
    def test_request_delay_applied_between_batches(self, mock_reviews, mock_sleep):
        """Verify time.sleep is called with configured request_delay between batches."""
        batch_1 = [{"reviewId": "gp-delay-1", "content": "Batch 1 review", "score": 5, "at": None}]
        batch_2 = [{"reviewId": "gp-delay-2", "content": "Batch 2 review", "score": 5, "at": None}]

        mock_reviews.side_effect = [
            (batch_1, "token-2"),
            (batch_2, None),
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            test_jsonl = Path(tmp_dir) / "test_delay.jsonl"
            collect_reviews(
                app_id="com.urbanclap.urbanclap",
                target_count=2,
                output_path=test_jsonl,
                request_delay=1.5,
            )

            mock_sleep.assert_called_once_with(1.5)

    @patch("engine.collectors.google_play.reviews")
    def test_duplicate_prevention_within_same_batch(self, mock_reviews):
        """Verify duplicate review IDs appearing in the same batch are deduplicated."""
        dup_batch = [
            {"reviewId": "gp-dup-1", "content": "Same review once", "score": 5, "at": None},
            {"reviewId": "gp-dup-1", "content": "Same review duplicate", "score": 5, "at": None},
            {"reviewId": "gp-dup-2", "content": "Distinct review", "score": 4, "at": None},
        ]
        mock_reviews.return_value = (dup_batch, None)

        with tempfile.TemporaryDirectory() as tmp_dir:
            test_jsonl = Path(tmp_dir) / "test_dup_batch.jsonl"
            collected = collect_reviews(
                app_id="com.urbanclap.urbanclap",
                target_count=3,
                output_path=test_jsonl,
                request_delay=0.0,
            )

            self.assertEqual(collected, 2)
            with test_jsonl.open("r", encoding="utf-8") as f:
                saved = [json.loads(l) for l in f if l.strip()]

            saved_ids = [r["id"] for r in saved]
            self.assertEqual(saved_ids, ["gp-dup-1", "gp-dup-2"])

    @patch("engine.collectors.google_play.verify_app_listing")
    @patch("engine.collectors.google_play.collect_reviews")
    def test_cli_delay_argument_passed(self, mock_collect, mock_verify):
        """Verify --delay CLI argument is parsed and forwarded to collect_reviews."""
        from engine.collectors.google_play import main

        mock_verify.return_value = {"title": "Urban Company: Home Services"}
        mock_collect.return_value = 5

        with patch("sys.argv", ["google_play.py", "--count", "5", "--delay", "2.5"]):
            main()

        mock_collect.assert_called_once()
        _, kwargs = mock_collect.call_args
        self.assertEqual(kwargs.get("request_delay"), 2.5)


if __name__ == "__main__":
    unittest.main()
