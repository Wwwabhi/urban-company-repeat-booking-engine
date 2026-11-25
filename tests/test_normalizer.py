"""Comprehensive unit test suite for review normalization pipeline.

Validates:
1. Field mapping: Correct extraction and transformation of source fields into normalized schema.
2. Missing values: Preserves null/None values without fabricating default strings or numbers.
3. Intra-source deduplication: Duplicate IDs within a platform are skipped; cross-platform collisions are not merged.
4. InstaHelp handling: Correctly flags InstaHelp / Insta maid reviews while ignoring words like 'install' or 'instead'.
5. Raw-file integrity: Asserts raw JSONL files remain strictly untouched (byte-for-byte SHA-256 match).
6. End-to-end pipeline execution and output schema completeness.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from engine.normalizer import (
    DEFAULT_APP_STORE_RAW,
    DEFAULT_GOOGLE_PLAY_RAW,
    detect_instahelp,
    normalize_app_store_record,
    normalize_dataset,
    normalize_google_play_record,
    run_normalization_pipeline,
)

EXPECTED_GOOGLE_PLAY_SHA256 = (
    "3fd7f281006826bdcdf82c8c279b7c6819365c868025fa965c18573cf9035301"
)
EXPECTED_APPLE_APP_STORE_SHA256 = (
    "c6e07f5ffbd77573da20f651983d0395da8ced5e57fa1616319d1b578bd2666d"
)

EXPECTED_NORMALIZED_KEYS = {
    "review_id",
    "source",
    "date",
    "rating",
    "title",
    "text",
    "app_version",
    "review_created_version",
    "thumbs_up",
    "vote_count",
    "vote_sum",
    "is_instahelp",
}


class TestFieldMappingAndMissingValues(unittest.TestCase):
    """Verifies mapping of platform-specific fields and preservation of missing values."""

    def test_google_play_field_mapping(self):
        """Verify Google Play fields are mapped correctly and App Store fields are None."""
        raw = {
            "id": "gp-test-1",
            "source": "Play Store",
            "date": "2026-11-22",
            "score": 5,
            "text": "Great service done on time.",
            "thumbs_up": 2,
            "app_version": "7.6.92",
            "review_created_version": "7.6.92",
        }
        normalized = normalize_google_play_record(raw)

        self.assertEqual(normalized["review_id"], "gp-test-1")
        self.assertEqual(normalized["source"], "Play Store")
        self.assertEqual(normalized["date"], "2026-11-22")
        self.assertEqual(normalized["rating"], 5)
        self.assertIsNone(normalized["title"])
        self.assertEqual(normalized["text"], "Great service done on time.")
        self.assertEqual(normalized["app_version"], "7.6.92")
        self.assertEqual(normalized["review_created_version"], "7.6.92")
        self.assertEqual(normalized["thumbs_up"], 2)
        # Platform-specific fields from App Store must be None, not fabricated
        self.assertIsNone(normalized["vote_count"])
        self.assertIsNone(normalized["vote_sum"])
        self.assertFalse(normalized["is_instahelp"])
        self.assertEqual(set(normalized.keys()), EXPECTED_NORMALIZED_KEYS)

    def test_app_store_field_mapping(self):
        """Verify App Store fields are mapped correctly and Play Store fields are None."""
        raw = {
            "id": "apple-test-1",
            "source": "App Store",
            "date": "2026-11-21",
            "score": 4,
            "title": "Good experience",
            "text": "Good experience. Professional cleaner.",
            "app_version": "7.22",
            "vote_count": 1,
            "vote_sum": 1,
        }
        normalized = normalize_app_store_record(raw)

        self.assertEqual(normalized["review_id"], "apple-test-1")
        self.assertEqual(normalized["source"], "App Store")
        self.assertEqual(normalized["date"], "2026-11-21")
        self.assertEqual(normalized["rating"], 4)
        self.assertEqual(normalized["title"], "Good experience")
        self.assertEqual(normalized["text"], "Good experience. Professional cleaner.")
        self.assertEqual(normalized["app_version"], "7.22")
        self.assertEqual(normalized["vote_count"], 1)
        self.assertEqual(normalized["vote_sum"], 1)
        # Platform-specific fields from Play Store must be None, not fabricated
        self.assertIsNone(normalized["review_created_version"])
        self.assertIsNone(normalized["thumbs_up"])
        self.assertFalse(normalized["is_instahelp"])
        self.assertEqual(set(normalized.keys()), EXPECTED_NORMALIZED_KEYS)

    def test_preserves_null_values_without_fabrication(self):
        """Verify null/missing fields (e.g. app_version or date) remain None and are not invented."""
        raw_gp = {
            "id": "gp-null-1",
            "source": "Play Store",
            "date": None,
            "score": 3,
            "text": "Average",
            "thumbs_up": None,
            "app_version": None,
            "review_created_version": None,
        }
        norm_gp = normalize_google_play_record(raw_gp)
        self.assertIsNone(norm_gp["date"])
        self.assertIsNone(norm_gp["app_version"])
        self.assertIsNone(norm_gp["review_created_version"])
        self.assertIsNone(norm_gp["thumbs_up"])


class TestInstaHelpDetection(unittest.TestCase):
    """Verifies accurate detection of InstaHelp / Insta maid reviews without false positives."""

    def test_instahelp_positive_matches(self):
        """Verify common phrasings of InstaHelp / Insta maids are detected."""
        positive_cases = [
            ("insta help is a good idea", None),
            ("The insta help professional was slow", None),
            ("Insta maids constantly pester for ratings", None),
            ("UC Insta help services are unreliable", "Insta help"),
            ("InstaHelp failed to provide service", "InstaHelp"),
            ("Very bad service", "Instahelp"),
            ("I took today first INSTA help service from UC", "Service"),
            ("Purchased instahelp pack", "Instahelp pack"),
        ]
        for text, title in positive_cases:
            self.assertTrue(
                detect_instahelp(text=text, title=title),
                f"Failed to detect InstaHelp in: title='{title}', text='{text}'",
            )

    def test_instahelp_negative_matches(self):
        """Verify non-InstaHelp reviews containing 'install', 'instead', or 'instant' are NOT flagged."""
        negative_cases = [
            ("Ikea stuff install. Done by urban company very well", "Ikea stuff install"),
            ("No one else was assigned to my task instead and my order got canceled", "Order got canceled"),
            ("Stop fake advertising of Instant service", "Instant service"),
            ("Excellent AC repair and installation", "AC repair"),
            ("Good salon service at home", "Salon"),
        ]
        for text, title in negative_cases:
            self.assertFalse(
                detect_instahelp(text=text, title=title),
                f"False positive InstaHelp flag in: title='{title}', text='{text}'",
            )


class TestIntraSourceDeduplication(unittest.TestCase):
    """Verifies that duplicate review IDs within a source are skipped without merging cross-platform records."""

    def test_deduplication_within_source(self):
        """Verify duplicate review IDs within one platform are deduplicated."""
        records = [
            {"id": "gp-1", "source": "Play Store", "date": "2026-11-22", "score": 5, "text": "Review 1"},
            {"id": "gp-1", "source": "Play Store", "date": "2026-11-22", "score": 5, "text": "Review 1 Duplicate"},
            {"id": "gp-2", "source": "Play Store", "date": "2026-11-22", "score": 4, "text": "Review 2"},
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_file = Path(tmp_dir) / "test_dedup.jsonl"
            with test_file.open("w", encoding="utf-8") as f:
                for r in records:
                    f.write(json.dumps(r) + "\n")

            normalized, dups = normalize_dataset(test_file, "Play Store")
            self.assertEqual(len(normalized), 2)
            self.assertEqual(dups, 1)
            self.assertEqual([r["review_id"] for r in normalized], ["gp-1", "gp-2"])

    def test_cross_platform_ids_not_merged(self):
        """Verify that identical review IDs across platforms are kept distinct."""
        gp_records = [
            {"id": "shared-id-100", "source": "Play Store", "date": "2026-11-22", "score": 5, "text": "Play text"},
        ]
        as_records = [
            {"id": "shared-id-100", "source": "App Store", "date": "2026-11-21", "score": 1, "title": "Apple title", "text": "Apple text"},
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            gp_file = Path(tmp_dir) / "gp.jsonl"
            as_file = Path(tmp_dir) / "as.jsonl"
            out_file = Path(tmp_dir) / "out.jsonl"

            with gp_file.open("w", encoding="utf-8") as f:
                f.write(json.dumps(gp_records[0]) + "\n")
            with as_file.open("w", encoding="utf-8") as f:
                f.write(json.dumps(as_records[0]) + "\n")

            summary = run_normalization_pipeline(
                google_play_path=gp_file,
                app_store_path=as_file,
                output_path=out_file,
            )

            self.assertEqual(summary["total_normalized"], 2)
            with out_file.open("r", encoding="utf-8") as f:
                lines = [json.loads(l) for l in f if l.strip()]

            self.assertEqual(len(lines), 2)
            sources = [r["source"] for r in lines]
            self.assertIn("Play Store", sources)
            self.assertIn("App Store", sources)


class TestRawDatasetIntegrityAndPipelineEndToEnd(unittest.TestCase):
    """Verifies that running the pipeline on actual raw data preserves raw files and outputs 200 records."""

    def test_raw_datasets_strictly_preserved(self):
        """Verify raw datasets match expected SHA-256 hashes before and after normalization."""
        # 1. Check Google Play hash
        with DEFAULT_GOOGLE_PLAY_RAW.open("rb") as f:
            gp_hash = hashlib.sha256(f.read()).hexdigest()
        self.assertEqual(
            gp_hash,
            EXPECTED_GOOGLE_PLAY_SHA256,
            "Raw Google Play dataset was modified!",
        )

        # 2. Check Apple App Store hash
        with DEFAULT_APP_STORE_RAW.open("rb") as f:
            apple_hash = hashlib.sha256(f.read()).hexdigest()
        self.assertEqual(
            apple_hash,
            EXPECTED_APPLE_APP_STORE_SHA256,
            "Raw Apple App Store dataset was modified!",
        )

    def test_end_to_end_pipeline_output(self):
        """Verify normalization of current raw datasets produces 200 records with consistent schema."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_file = Path(tmp_dir) / "normalized_reviews.jsonl"
            summary = run_normalization_pipeline(
                google_play_path=DEFAULT_GOOGLE_PLAY_RAW,
                app_store_path=DEFAULT_APP_STORE_RAW,
                output_path=out_file,
            )

            self.assertEqual(summary["total_normalized"], 200)
            self.assertEqual(summary["google_play_count"], 100)
            self.assertEqual(summary["app_store_count"], 100)
            self.assertEqual(summary["instahelp_count"], 16)
            self.assertEqual(summary["core_uc_count"], 184)

            self.assertTrue(out_file.exists())
            with out_file.open("r", encoding="utf-8") as f:
                records = [json.loads(l) for l in f if l.strip()]

            self.assertEqual(len(records), 200)
            for r in records:
                self.assertEqual(set(r.keys()), EXPECTED_NORMALIZED_KEYS)
                self.assertIn(r["source"], {"Play Store", "App Store"})
                self.assertIsInstance(r["is_instahelp"], bool)


if __name__ == "__main__":
    unittest.main()
