"""Comprehensive test suite for Apple App Store collector.

Covers:
1. App listing verification (mocked: not found, ID mismatch, title mismatch, developer mismatch, network error).
2. Live Apple iTunes endpoint verification (clearly separated from mocked tests).
3. RSS review entry parsing using representative Apple RSS fixture responses.
4. Handling of empty feeds, non-list entry formats, HTTP 404, HTTP 500, and malformed responses.
5. Multi-page pagination and duplicate review ID handling.
6. Privacy pipeline: phone/email redaction, address/pincode exclusion, zero secondary storage.
7. Safe logging: ensuring no review IDs or review text appear in privacy logs.
8. Preservation and integrity of the Google Play dataset.
"""

from __future__ import annotations

import hashlib
import json
import logging
import tempfile
import unittest
import urllib.error
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from engine.collectors.app_store import (
    OFFICIAL_APP_ID,
    OFFICIAL_COUNTRY,
    collect_reviews,
    fetch_review_page,
    verify_app_store_listing,
)

EXPECTED_GOOGLE_PLAY_SHA256 = (
    "3fd7f281006826bdcdf82c8c279b7c6819365c868025fa965c18573cf9035301"
)
EXPECTED_APPLE_APP_STORE_SHA256 = (
    "c6e07f5ffbd77573da20f651983d0395da8ced5e57fa1616319d1b578bd2666d"
)

# ---------------------------------------------------------------------------
# Representative Apple RSS and iTunes Lookup Fixtures
# ---------------------------------------------------------------------------

MOCK_LOOKUP_SUCCESS_PAYLOAD = {
    "resultCount": 1,
    "results": [
        {
            "trackId": 1032480595,
            "trackName": "Urban Company: Home Services",
            "artistName": "Urban Company Limited",
            "bundleId": "com.urbanclap.customer",
            "averageUserRating": 4.77,
            "userRatingCount": 1249402,
        }
    ],
}

MOCK_RSS_PAGE_1_PAYLOAD = {
    "feed": {
        "title": {"label": "iTunes Store: Customer Reviews"},
        "entry": [
            {
                "id": {"label": "apple-rev-101"},
                "updated": {"label": "2026-11-21T21:49:41-07:00"},
                "im:rating": {"label": "5"},
                "im:version": {"label": "7.22"},
                "title": {"label": "Great service"},
                "content": {"label": "The AC repair was very thorough and done on time."},
                "author": {"name": {"label": "PrivateUser123"}},
                "im:voteCount": {"label": "0"},
                "im:voteSum": {"label": "0"},
            },
            {
                "id": {"label": "apple-rev-102"},
                "updated": {"label": "2026-11-21T20:25:29-07:00"},
                "im:rating": {"label": "4"},
                "im:version": {"label": "7.22"},
                "title": {"label": "Support helped"},
                "content": {"label": "Called +91 9876543210 and wrote to support@example.com for rescheduling."},
                "author": {"name": {"label": "Rahul_K"}},
                "im:voteCount": {"label": "1"},
                "im:voteSum": {"label": "1"},
            },
            {
                "id": {"label": "apple-rev-103-address"},
                "updated": {"label": "2026-11-20T18:10:00-07:00"},
                "im:rating": {"label": "1"},
                "im:version": {"label": "7.21"},
                "title": {"label": "Wrong location"},
                "content": {"label": "The professional went to Flat 402, Sunshine Towers, MG Road instead."},
                "author": {"name": {"label": "DisappointedCustomer"}},
                "im:voteCount": {"label": "0"},
                "im:voteSum": {"label": "0"},
            },
            {
                "id": {"label": "apple-rev-104-pincode"},
                "updated": {"label": "2026-11-20T15:00:00-07:00"},
                "im:rating": {"label": "2"},
                "im:version": {"label": "7.21"},
                "title": {"label": "Area issue"},
                "content": {"label": "Service in pincode 560034 is frequently delayed."},
                "author": {"name": {"label": "BangaloreUser"}},
                "im:voteCount": {"label": "0"},
                "im:voteSum": {"label": "0"},
            },
        ],
    }
}

MOCK_RSS_PAGE_2_PAYLOAD = {
    "feed": {
        "title": {"label": "iTunes Store: Customer Reviews"},
        "entry": [
            # One duplicate from page 1 to verify deduplication
            {
                "id": {"label": "apple-rev-101"},
                "updated": {"label": "2026-11-21T21:49:41-07:00"},
                "im:rating": {"label": "5"},
                "im:version": {"label": "7.22"},
                "title": {"label": "Great service"},
                "content": {"label": "The AC repair was very thorough and done on time."},
                "author": {"name": {"label": "PrivateUser123"}},
            },
            # One new valid review
            {
                "id": {"label": "apple-rev-201"},
                "updated": {"label": "2026-11-19T10:00:00-07:00"},
                "im:rating": {"label": "5"},
                "im:version": {"label": "7.20"},
                "title": {"label": "Salon service"},
                "content": {"label": "Punctual and very clean salon experience."},
                "author": {"name": {"label": "AnanyaS"}},
            },
        ],
    }
}


def _make_http_response(payload: dict) -> MagicMock:
    """Helper to create a mocked urllib.request response context manager."""
    data = json.dumps(payload).encode("utf-8")
    mock_resp = MagicMock()
    mock_resp.read.return_value = data
    mock_resp.__enter__.return_value = mock_resp
    return mock_resp


# ---------------------------------------------------------------------------
# Test Suite 1: App Listing Verification (Mocked)
# ---------------------------------------------------------------------------

class TestAppListingVerificationMocked(unittest.TestCase):
    @patch("urllib.request.urlopen")
    def test_verify_success(self, mock_urlopen):
        """Verify that a valid iTunes lookup response successfully verifies the app."""
        mock_urlopen.return_value = _make_http_response(MOCK_LOOKUP_SUCCESS_PAYLOAD)

        app_info = verify_app_store_listing(app_id="1032480595", country="in")
        self.assertEqual(str(app_info["trackId"]), "1032480595")
        self.assertIn("Urban Company", app_info["trackName"])
        self.assertIn("Urban Company", app_info["artistName"])

    @patch("urllib.request.urlopen")
    def test_verify_app_not_found_raises_value_error(self, mock_urlopen):
        """Verify that empty lookup results raise a ValueError."""
        mock_urlopen.return_value = _make_http_response({"resultCount": 0, "results": []})

        with self.assertRaises(ValueError) as ctx:
            verify_app_store_listing(app_id="9999999999", country="in")
        self.assertIn("No App Store listing found", str(ctx.exception))

    @patch("urllib.request.urlopen")
    def test_verify_track_id_mismatch_raises_value_error(self, mock_urlopen):
        """Verify that a track ID mismatch raises a ValueError."""
        mismatched_payload = {
            "resultCount": 1,
            "results": [
                {
                    "trackId": 888888888,
                    "trackName": "Urban Company: Home Services",
                    "artistName": "Urban Company Limited",
                }
            ],
        }
        mock_urlopen.return_value = _make_http_response(mismatched_payload)

        with self.assertRaises(ValueError) as ctx:
            verify_app_store_listing(app_id="1032480595", country="in")
        self.assertIn("App Store ID mismatch", str(ctx.exception))

    @patch("urllib.request.urlopen")
    def test_verify_title_mismatch_raises_value_error(self, mock_urlopen):
        """Verify that an unexpected app title raises a ValueError."""
        wrong_title_payload = {
            "resultCount": 1,
            "results": [
                {
                    "trackId": 1032480595,
                    "trackName": "Unrelated Competitor App",
                    "artistName": "Urban Company Limited",
                }
            ],
        }
        mock_urlopen.return_value = _make_http_response(wrong_title_payload)

        with self.assertRaises(ValueError) as ctx:
            verify_app_store_listing(app_id="1032480595", country="in")
        self.assertIn("Title mismatch", str(ctx.exception))

    @patch("urllib.request.urlopen")
    def test_verify_developer_mismatch_raises_value_error(self, mock_urlopen):
        """Verify that an unexpected developer name raises a ValueError."""
        wrong_dev_payload = {
            "resultCount": 1,
            "results": [
                {
                    "trackId": 1032480595,
                    "trackName": "Urban Company: Home Services",
                    "artistName": "Unknown Third Party LLC",
                }
            ],
        }
        mock_urlopen.return_value = _make_http_response(wrong_dev_payload)

        with self.assertRaises(ValueError) as ctx:
            verify_app_store_listing(app_id="1032480595", country="in")
        self.assertIn("Developer mismatch", str(ctx.exception))

    @patch("urllib.request.urlopen")
    def test_verify_network_error_raises_runtime_error(self, mock_urlopen):
        """Verify that network exceptions are caught and wrapped as RuntimeError."""
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        with self.assertRaises(RuntimeError) as ctx:
            verify_app_store_listing(app_id="1032480595", country="in")
        self.assertIn("Failed to query iTunes lookup endpoint", str(ctx.exception))


# ---------------------------------------------------------------------------
# Test Suite 2: Actual Apple Endpoint Verification (Live)
# ---------------------------------------------------------------------------

class TestAppListingVerificationLive(unittest.TestCase):
    """Clearly distinguished test that verifies the actual Apple iTunes endpoint."""

    def test_actual_apple_endpoint_verification(self):
        """Live verification against Apple's official iTunes Lookup endpoint for India."""
        app_info = verify_app_store_listing(app_id=OFFICIAL_APP_ID, country=OFFICIAL_COUNTRY)
        self.assertEqual(str(app_info.get("trackId")), OFFICIAL_APP_ID)
        self.assertEqual(app_info.get("bundleId"), "com.urbanclap.customer")
        self.assertIn("Urban Company", app_info.get("trackName", ""))
        self.assertIn("Urban Company", app_info.get("artistName", ""))


# ---------------------------------------------------------------------------
# Test Suite 3: Apple RSS Review Entry Parsing with Fixtures
# ---------------------------------------------------------------------------

class TestRSSReviewParsingWithFixtures(unittest.TestCase):
    @patch("urllib.request.urlopen")
    def test_parse_valid_rss_fixture_entries(self, mock_urlopen):
        """Verify parsing of valid customer review entries from Apple RSS JSON."""
        mock_urlopen.return_value = _make_http_response(MOCK_RSS_PAGE_1_PAYLOAD)

        entries = fetch_review_page(app_id="1032480595", page=1, country="in")
        self.assertEqual(len(entries), 4)

        entry_0 = entries[0]
        self.assertEqual(entry_0["id"]["label"], "apple-rev-101")
        self.assertEqual(entry_0["im:rating"]["label"], "5")
        self.assertEqual(entry_0["title"]["label"], "Great service")
        self.assertIn("AC repair was very thorough", entry_0["content"]["label"])
        self.assertEqual(entry_0["im:version"]["label"], "7.22")

    @patch("urllib.request.urlopen")
    def test_parse_empty_feed_fixture(self, mock_urlopen):
        """Verify that an empty feed cleanly returns an empty list."""
        mock_urlopen.return_value = _make_http_response({"feed": {"entry": []}})

        entries = fetch_review_page(app_id="1032480595", page=5, country="in")
        self.assertEqual(entries, [])

    @patch("urllib.request.urlopen")
    def test_parse_single_entry_dict_fixture(self, mock_urlopen):
        """Verify that Apple RSS feeds with a single entry (as a dict instead of list) are parsed."""
        single_entry_payload = {
            "feed": {
                "entry": {
                    "id": {"label": "apple-single-1"},
                    "im:rating": {"label": "5"},
                    "content": {"label": "Single review in feed."},
                }
            }
        }
        mock_urlopen.return_value = _make_http_response(single_entry_payload)

        entries = fetch_review_page(app_id="1032480595", page=1, country="in")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["id"]["label"], "apple-single-1")

    @patch("urllib.request.urlopen")
    def test_parse_http_404_returns_empty_list(self, mock_urlopen):
        """Verify that HTTP 404 (end of pagination) cleanly returns an empty list."""
        http_error = urllib.error.HTTPError(
            url="https://itunes.apple.com/...", code=404, msg="Not Found", hdrs={}, fp=None
        )
        mock_urlopen.side_effect = http_error

        entries = fetch_review_page(app_id="1032480595", page=11, country="in")
        self.assertEqual(entries, [])

    @patch("urllib.request.urlopen")
    def test_parse_http_500_raises_runtime_error(self, mock_urlopen):
        """Verify that HTTP 500 raises RuntimeError."""
        http_error = urllib.error.HTTPError(
            url="https://itunes.apple.com/...", code=500, msg="Server Error", hdrs={}, fp=None
        )
        mock_urlopen.side_effect = http_error

        with self.assertRaises(RuntimeError) as ctx:
            fetch_review_page(app_id="1032480595", page=1, country="in")
        self.assertIn("HTTP error 500", str(ctx.exception))

    @patch("urllib.request.urlopen")
    def test_parse_malformed_json_raises_runtime_error(self, mock_urlopen):
        """Verify that non-dict or malformed feed responses raise RuntimeError."""
        mock_urlopen.return_value = _make_http_response({"unexpected_root": []})

        with self.assertRaises(RuntimeError) as ctx:
            fetch_review_page(app_id="1032480595", page=1, country="in")
        self.assertIn("missing 'feed' object", str(ctx.exception))


# ---------------------------------------------------------------------------
# Test Suite 4: Collection Pipeline & Privacy Validation (Mocked)
# ---------------------------------------------------------------------------

class TestAppStoreCollectionPipelineMocked(unittest.TestCase):
    @patch("engine.collectors.app_store.fetch_review_page")
    def test_pagination_and_deduplication(self, mock_fetch):
        """Verify multi-page fetching, target count bounding, and duplicate review ID skipping."""
        # Page 1 returns 4 reviews (rev-101, rev-102, rev-103-address, rev-104-pincode)
        # Page 2 returns rev-101 (duplicate) and rev-201 (new)
        mock_fetch.side_effect = [
            MOCK_RSS_PAGE_1_PAYLOAD["feed"]["entry"],
            MOCK_RSS_PAGE_2_PAYLOAD["feed"]["entry"],
            [],
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            test_jsonl = Path(tmp_dir) / "test_app_store.jsonl"

            # Request 3 valid reviews
            saved_count = collect_reviews(
                app_id="1032480595",
                target_count=3,
                output_path=test_jsonl,
                request_delay=0.0,
            )

            # Valid reviews should be rev-101, rev-102, and rev-201 (rev-103 and 104 excluded by privacy)
            self.assertEqual(saved_count, 3)

            with test_jsonl.open("r", encoding="utf-8") as f:
                saved = [json.loads(line) for line in f]

            saved_ids = [r["id"] for r in saved]
            self.assertEqual(saved_ids, ["apple-rev-101", "apple-rev-102", "apple-rev-201"])
            self.assertEqual(len(set(saved_ids)), 3, "Duplicate review ID found in saved output!")

    @patch("engine.collectors.app_store.fetch_review_page")
    def test_phone_email_redaction_in_saved_records(self, mock_fetch):
        """Verify phone numbers and emails are redacted in both title and text."""
        mock_fetch.return_value = [MOCK_RSS_PAGE_1_PAYLOAD["feed"]["entry"][1]]  # rev-102

        with tempfile.TemporaryDirectory() as tmp_dir:
            test_jsonl = Path(tmp_dir) / "test_phone_email.jsonl"
            collect_reviews(
                app_id="1032480595",
                target_count=1,
                output_path=test_jsonl,
                request_delay=0.0,
            )

            with test_jsonl.open("r", encoding="utf-8") as f:
                record = json.loads(f.readline())

            self.assertIn("[PHONE_REDACTED]", record["text"])
            self.assertIn("[EMAIL_REDACTED]", record["text"])
            self.assertNotIn("9876543210", record["text"])
            self.assertNotIn("support@example.com", record["text"])
            # Ensure author metadata was completely stripped
            self.assertNotIn("author", record)
            self.assertNotIn("Rahul_K", json.dumps(record))

    @patch("engine.collectors.app_store.fetch_review_page")
    def test_address_and_pincode_exclusion(self, mock_fetch):
        """Verify reviews with address cues or postal pincodes are excluded from storage."""
        # Entries 2 and 3 contain address ("Flat 402, Sunshine Towers, MG Road") and pincode ("560034")
        mock_fetch.return_value = MOCK_RSS_PAGE_1_PAYLOAD["feed"]["entry"]

        with tempfile.TemporaryDirectory() as tmp_dir:
            test_jsonl = Path(tmp_dir) / "test_exclusion.jsonl"
            saved_count = collect_reviews(
                app_id="1032480595",
                target_count=4,
                output_path=test_jsonl,
                request_delay=0.0,
            )

            # Only rev-101 and rev-102 should be saved; rev-103 and rev-104 excluded
            self.assertEqual(saved_count, 2)

            with test_jsonl.open("r", encoding="utf-8") as f:
                saved = [json.loads(line) for line in f]

            saved_ids = [r["id"] for r in saved]
            self.assertNotIn("apple-rev-103-address", saved_ids)
            self.assertNotIn("apple-rev-104-pincode", saved_ids)

            # Verify zero secondary or quarantine files created
            all_files = list(Path(tmp_dir).iterdir())
            self.assertEqual(all_files, [test_jsonl])

    @patch("engine.collectors.app_store.fetch_review_page")
    def test_safe_logging_omits_review_ids_and_text(self, mock_fetch):
        """Verify privacy logs contain NO review IDs, NO review text, and only counts/reasons."""
        mock_fetch.return_value = [
            MOCK_RSS_PAGE_1_PAYLOAD["feed"]["entry"][2]  # rev-103-address
        ]

        logger = logging.getLogger("engine.collectors.app_store")
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_jsonl = Path(tmp_dir) / "test_logs.jsonl"

            with self.assertLogs(logger, level="INFO") as log_capture:
                collect_reviews(
                    app_id="1032480595",
                    target_count=1,
                    output_path=test_jsonl,
                    request_delay=0.0,
                )

            all_logs = " ".join(log_capture.output)

            # Assert NO review IDs appear in logs
            self.assertNotIn("apple-rev-103-address", all_logs)

            # Assert NO sensitive text appears in logs
            self.assertNotIn("Flat 402", all_logs)
            self.assertNotIn("Sunshine Towers", all_logs)
            self.assertNotIn("MG Road", all_logs)

            # Assert aggregate count and reason codes are logged
            self.assertIn("Privacy exclusion summary:", all_logs)
            self.assertIn("potential_address_cue", all_logs)

    @patch("engine.collectors.app_store.fetch_review_page")
    def test_fetch_failure_before_any_records_collected(self, mock_fetch):
        """Verify that an unexpected fetch error on page 1 raises RuntimeError and leaves output empty."""
        mock_fetch.side_effect = RuntimeError("Simulated network outage on page 1")

        with tempfile.TemporaryDirectory() as tmp_dir:
            test_jsonl = Path(tmp_dir) / "test_fail_early.jsonl"

            with self.assertRaises(RuntimeError) as ctx:
                collect_reviews(
                    app_id="1032480595",
                    target_count=5,
                    output_path=test_jsonl,
                    request_delay=0.0,
                )

            self.assertIn("Apple RSS collection failed on page 1 after collecting 0 reviews", str(ctx.exception))
            self.assertIn("Simulated network outage on page 1", str(ctx.exception))

            # Verify no records written to output file
            if test_jsonl.exists():
                with test_jsonl.open("r", encoding="utf-8") as f:
                    lines = [l for l in f if l.strip()]
                self.assertEqual(len(lines), 0)

    @patch("engine.collectors.app_store.fetch_review_page")
    def test_fetch_failure_after_partial_batch_preserves_records_and_deduplicates_on_retry(self, mock_fetch):
        """Verify that failure on page 2 preserves page 1 records and retry completes without duplicates."""
        # Initial run: Page 1 yields 2 valid reviews (rev-101, rev-102), Page 2 fails
        mock_fetch.side_effect = [
            MOCK_RSS_PAGE_1_PAYLOAD["feed"]["entry"],
            RuntimeError("Simulated 500 error on page 2"),
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            test_jsonl = Path(tmp_dir) / "test_partial_failure.jsonl"

            # 1. First run must fail with RuntimeError and non-zero-inducing exception
            with self.assertRaises(RuntimeError) as ctx:
                collect_reviews(
                    app_id="1032480595",
                    target_count=3,
                    output_path=test_jsonl,
                    request_delay=0.0,
                )

            self.assertIn("Apple RSS collection failed on page 2 after collecting 2 reviews", str(ctx.exception))
            self.assertIn("Simulated 500 error on page 2", str(ctx.exception))

            # 2. Verify that the 2 valid reviews from page 1 were preserved on disk
            self.assertTrue(test_jsonl.exists())
            with test_jsonl.open("r", encoding="utf-8") as f:
                saved_lines = [json.loads(l) for l in f if l.strip()]

            self.assertEqual(len(saved_lines), 2)
            self.assertEqual([r["id"] for r in saved_lines], ["apple-rev-101", "apple-rev-102"])

            # 3. Simulate retry: Page 1 returns the same reviews (should be skipped), Page 2 returns rev-201
            mock_fetch.side_effect = [
                MOCK_RSS_PAGE_1_PAYLOAD["feed"]["entry"],
                MOCK_RSS_PAGE_2_PAYLOAD["feed"]["entry"],
                [],
            ]

            retry_count = collect_reviews(
                app_id="1032480595",
                target_count=1,  # Only need 1 more to reach 3
                output_path=test_jsonl,
                request_delay=0.0,
            )

            self.assertEqual(retry_count, 1)

            # 4. Verify output file contains exactly 3 records, with zero duplicates
            with test_jsonl.open("r", encoding="utf-8") as f:
                all_records = [json.loads(l) for l in f if l.strip()]

            all_ids = [r["id"] for r in all_records]
            self.assertEqual(all_ids, ["apple-rev-101", "apple-rev-102", "apple-rev-201"])
            self.assertEqual(len(all_ids), len(set(all_ids)), "Duplicate reviews found after retry!")

    @patch("engine.collectors.app_store.fetch_review_page")
    def test_http_404_treated_as_normal_end_of_pagination(self, mock_fetch):
        """Verify that HTTP 404 returning empty list stops collection normally without error."""
        # Page 1 has entries, Page 2 returns empty list (from HTTP 404 handled in fetch_review_page)
        mock_fetch.side_effect = [
            MOCK_RSS_PAGE_1_PAYLOAD["feed"]["entry"],
            [],  # Represents 404 end of pagination
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            test_jsonl = Path(tmp_dir) / "test_404_end.jsonl"
            # Request 10 reviews even though only 2 valid ones exist across pages
            saved = collect_reviews(
                app_id="1032480595",
                target_count=10,
                output_path=test_jsonl,
                request_delay=0.0,
            )

            # Should stop cleanly without error, returning the 2 valid reviews
            self.assertEqual(saved, 2)
            with test_jsonl.open("r", encoding="utf-8") as f:
                lines = [l for l in f if l.strip()]
            self.assertEqual(len(lines), 2)

    @patch("engine.collectors.app_store.verify_app_store_listing")
    @patch("engine.collectors.app_store.collect_reviews")
    def test_main_cli_exits_with_non_zero_status_on_failure(self, mock_collect, mock_verify):
        """Verify main() entrypoint exits with status code 1 when collection fails."""
        from engine.collectors.app_store import main

        mock_verify.return_value = {"trackId": 1032480595}
        mock_collect.side_effect = RuntimeError("Collection failed unexpectedly")

        with patch("sys.argv", ["app_store.py", "--count", "5"]):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 1)


# ---------------------------------------------------------------------------
# Test Suite 5: Raw Datasets Preservation & Sanitization Verification
# ---------------------------------------------------------------------------

class TestGooglePlayDatasetPreserved(unittest.TestCase):
    def test_google_play_file_strictly_unchanged(self):
        """Verify that data/raw/google_play_reviews.jsonl contains 100 unique records and matches expected hash."""
        gp_file = Path("data/raw/google_play_reviews.jsonl")
        self.assertTrue(gp_file.exists(), "Google Play raw dataset is missing!")

        with gp_file.open("rb") as f:
            actual_sha256 = hashlib.sha256(f.read()).hexdigest()

        self.assertEqual(
            actual_sha256,
            EXPECTED_GOOGLE_PLAY_SHA256,
            "Google Play dataset hash mismatch!",
        )

        with gp_file.open("r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]

        self.assertEqual(len(lines), 100, f"Expected 100 records, found {len(lines)}")


class TestAppleAppStoreDatasetSanitized(unittest.TestCase):
    def test_apple_dataset_sanitized_and_preserved(self):
        """Verify that data/raw/app_store_reviews.jsonl contains 20 unique records, third-party names are redacted, and matches expected hash."""
        apple_file = Path("data/raw/app_store_reviews.jsonl")
        self.assertTrue(apple_file.exists(), "Apple App Store raw dataset is missing!")

        # 1. Byte-level SHA-256 hash verification
        with apple_file.open("rb") as f:
            actual_sha256 = hashlib.sha256(f.read()).hexdigest()

        self.assertEqual(
            actual_sha256,
            EXPECTED_APPLE_APP_STORE_SHA256,
            f"Apple App Store dataset hash mismatch! Expected {EXPECTED_APPLE_APP_STORE_SHA256}, got {actual_sha256}",
        )

        # 2. Semantic line and content verification
        with apple_file.open("r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]

        self.assertEqual(len(lines), 100, f"Expected 100 records, found {len(lines)}")
        records = [json.loads(l) for l in lines]

        # 3. Verify uniqueness of review IDs
        unique_ids = {r["id"] for r in records}
        self.assertEqual(len(unique_ids), 100, "Duplicate review IDs found in Apple dataset!")

        # 4. Verify specific sanitized record 14816172315
        rec = next((r for r in records if r["id"] == "14816172315"), None)
        self.assertIsNotNone(rec, "Review 14816172315 not found in dataset!")
        self.assertNotIn("Ramprit", rec["text"], "Personal name 'Ramprit' was not redacted!")
        self.assertNotIn("Mohammad", rec["text"], "Personal name 'Mohammad' was not redacted!")
        self.assertIn("Whether it is [NAME_REDACTED], [NAME_REDACTED]", rec["text"])

        # 5. Verify required schema keys on all records
        required_keys = {"id", "source", "date", "score", "text"}
        for r in records:
            self.assertTrue(required_keys.issubset(r.keys()))
            self.assertEqual(r["source"], "App Store")
            self.assertNotIn("author", r)


if __name__ == "__main__":
    unittest.main()
