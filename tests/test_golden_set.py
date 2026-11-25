"""Tests for the 30-review golden dataset, sampling manifest, and annotation guidelines."""
from datetime import datetime
import hashlib
import json
import os
import re
import unittest


GOLDEN_PATH = "data/golden/golden_set.jsonl"
NORMALIZED_PATH = "data/processed/normalized_reviews.jsonl"
MANIFEST_PATH = "docs/golden_set_manifest.md"
GUIDELINES_PATH = "docs/golden_set_guidelines.md"

RAW_GOOGLE_PLAY_HASH = "3fd7f281006826bdcdf82c8c279b7c6819365c868025fa965c18573cf9035301"
RAW_APP_STORE_HASH = "c6e07f5ffbd77573da20f651983d0395da8ced5e57fa1616319d1b578bd2666d"
NORMALIZED_HASH = "673c832ceb42527654e605d2ce7e124d6b895dd38b4cd3d7a80bc1672d0c0cb1"
TAGGED_V1_HASH = "81d556ac5c41dd3e04ca089bd5b5b713d673ab0f0784ecaf6dee75c9324130ea"
QUEUE_V1_HASH = "bfd3c5c5be8ed33d5c1058b35b8832b4d750dc6a6aa2d5917645dbb71df96b3a"

SCHEMA_FIELDS_16 = [
    "source",
    "date",
    "city",
    "category",
    "experience_type",
    "nothing_went_wrong",
    "rebook_signal",
    "need_trigger",
    "recall_gap",
    "alternative_used",
    "post_service_expectation",
    "discovery_channel",
    "household_type",
    "unmet_need",
    "evidence_quote",
    "confidence",
]

ALLOWED_SOURCES = {
    "Play Store",
    "App Store",
    "Reddit",
    "YouTube",
    "Trustpilot",
    "MouthShut",
    "Shareholder Letter",
    "Earnings Call",
}

ALLOWED_CATEGORIES = {
    "AC",
    "deep clean",
    "plumber",
    "salon",
    "electrician",
    "pest control",
    "other",
    "unknown",
}

ALLOWED_EXPERIENCE_TYPES = {
    "positive",
    "neutral",
    "negative",
    "unclear",
}

ALLOWED_REBOOK_SIGNALS = {
    "rebooked",
    "did_not_rebook",
    "will_not_rebook",
    "unclear",
}

ALLOWED_NEED_TRIGGERS = {
    "breakdown",
    "season",
    "festival",
    "move",
    "guests",
    "routine",
    None,
}

ALLOWED_ALTERNATIVE_USED = {
    "neighbour",
    "family",
    "local provider",
    "WhatsApp or society group",
    "another app",
    "DIY",
    "none",
    "unclear",
}

ALLOWED_POST_SERVICE_EXPECTATIONS = {
    "follow-up",
    "reminder",
    "warranty clarity",
    "next-service advice",
    "nothing",
    "unclear",
}

ALLOWED_DISCOVERY_CHANNELS = {
    "search",
    "ad",
    "friend",
    "society group",
    "preinstalled habit",
    "unclear",
}

ALLOWED_HOUSEHOLD_TYPES = {
    "living alone",
    "couple",
    "family",
    "elderly",
    "renter",
    "owner",
    "unclear",
}

ALLOWED_CONFIDENCES = {
    "low",
    "medium",
    "high",
}


def file_sha256(path: str) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


class TestGoldenSetStructureAndIntegrity(unittest.TestCase):
    """Verifies file structure, uniqueness, normalization provenance, and schema conformity."""

    @classmethod
    def setUpClass(cls):
        cls.golden_records = []
        if os.path.exists(GOLDEN_PATH):
            with open(GOLDEN_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        cls.golden_records.append(json.loads(line))

        cls.normalized_records = {}
        if os.path.exists(NORMALIZED_PATH):
            with open(NORMALIZED_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        rec = json.loads(line)
                        cls.normalized_records[rec["review_id"]] = rec

    def test_golden_file_exists_and_exact_30_records(self):
        """Verify data/golden/golden_set.jsonl exists and contains exactly 30 records."""
        self.assertTrue(os.path.exists(GOLDEN_PATH), f"Golden file not found at {GOLDEN_PATH}")
        self.assertEqual(len(self.golden_records), 30, f"Expected exactly 30 records, got {len(self.golden_records)}")

    def test_unique_review_ids(self):
        """Verify all 30 review IDs in the golden set are unique and non-empty."""
        review_ids = [r["review_id"] for r in self.golden_records]
        self.assertEqual(len(review_ids), 30)
        self.assertEqual(len(set(review_ids)), 30, "Found duplicate review IDs in golden set")
        for rid in review_ids:
            self.assertIsInstance(rid, str)
            self.assertTrue(len(rid) > 0, "Empty review ID found")

    def test_all_records_exist_in_normalized_and_no_instahelp(self):
        """Verify all 30 records exist in normalized_reviews.jsonl and strictly exclude InstaHelp."""
        for r in self.golden_records:
            rid = r["review_id"]
            self.assertIn(rid, self.normalized_records, f"Golden review_id {rid} missing from normalized dataset")
            norm_rec = self.normalized_records[rid]
            self.assertFalse(norm_rec.get("is_instahelp", False), f"InstaHelp review {rid} found in golden set!")

    def test_platform_balance(self):
        """Verify balanced platform representation: exactly 15 Play Store and 15 App Store."""
        gp_count = sum(1 for r in self.golden_records if r["source"] == "Play Store")
        ap_count = sum(1 for r in self.golden_records if r["source"] == "App Store")
        self.assertEqual(gp_count, 15, f"Expected 15 Play Store reviews, got {gp_count}")
        self.assertEqual(ap_count, 15, f"Expected 15 App Store reviews, got {ap_count}")

    def test_record_structure_and_status(self):
        """Verify record keys, annotation_status, and annotator_notes across all 30 annotated records."""
        required_keys = {"review_id", "source", "review_text", "annotation_status", "annotator_notes", "human_tags"}
        for idx, r in enumerate(self.golden_records):
            self.assertTrue(required_keys.issubset(r.keys()), f"Record {r.get('review_id')} missing required keys")
            self.assertTrue(len(r["review_text"]) > 0, f"Record {r.get('review_id')} has empty review_text")
            self.assertEqual(r["annotation_status"], "annotated", f"Record {idx+1} ({r.get('review_id')}) must be annotated")
            self.assertIsNotNone(r["annotator_notes"], f"Record {idx+1} ({r.get('review_id')}) missing annotator_notes")
            self.assertTrue(len(r["annotator_notes"]) > 0)

    def test_16_schema_fields_present_and_status_conformity(self):
        """Verify human_tags contains all 16 schema fields with allowed enum values, nullable types, and quotes."""
        for idx, r in enumerate(self.golden_records):
            rid = r.get("review_id")
            tags = r["human_tags"]
            self.assertIsInstance(tags, dict, f"Record {rid} human_tags is not a dict")
            self.assertEqual(set(tags.keys()), set(SCHEMA_FIELDS_16), f"Record {rid} schema key mismatch")
            
            # 1. source: non-empty string in allowed sources
            self.assertIn(tags["source"], ALLOWED_SOURCES, f"Record {rid} invalid source: {tags['source']}")
            
            # 2. date: String (Nullable), YYYY-MM-DD format only when date exists
            if tags["date"] is not None:
                self.assertIsInstance(tags["date"], str, f"Record {rid} date is not a string or None")
                self.assertTrue(
                    bool(re.match(r"^\d{4}-\d{2}-\d{2}$", tags["date"])),
                    f"Record {rid} date '{tags['date']}' does not match YYYY-MM-DD format"
                )
                try:
                    datetime.strptime(tags["date"], "%Y-%m-%d")
                except ValueError as e:
                    self.fail(f"Record {rid} date '{tags['date']}' is not a valid calendar date: {e}")
            
            # 3. city: String (Nullable)
            if tags["city"] is not None:
                self.assertIsInstance(tags["city"], str, f"Record {rid} city must be a string or None")
                self.assertTrue(len(tags["city"]) > 0, f"Record {rid} city is empty string")
            
            # 4. category: Enum
            self.assertIn(tags["category"], ALLOWED_CATEGORIES, f"Record {rid} invalid category: {tags['category']}")
            
            # 5. experience_type: Enum
            self.assertIn(tags["experience_type"], ALLOWED_EXPERIENCE_TYPES, f"Record {rid} invalid experience_type: {tags['experience_type']}")
            
            # 6. nothing_went_wrong: Boolean (Nullable) - exactly bool or None (integers 0/1 disallowed)
            nww = tags["nothing_went_wrong"]
            self.assertTrue(
                nww is None or type(nww) is bool,
                f"Record {rid} invalid nothing_went_wrong: {nww!r} of type {type(nww).__name__} is not strictly bool or None"
            )
            self.assertNotEqual(type(nww), int, f"Record {rid} nothing_went_wrong must not be integer {nww!r}")
            
            # 7. rebook_signal: Enum
            self.assertIn(tags["rebook_signal"], ALLOWED_REBOOK_SIGNALS, f"Record {rid} invalid rebook_signal: {tags['rebook_signal']}")
            
            # 8. need_trigger: Enum (Nullable)
            self.assertIn(tags["need_trigger"], ALLOWED_NEED_TRIGGERS, f"Record {rid} invalid need_trigger: {tags['need_trigger']}")
            
            # 9. recall_gap: Boolean (Nullable) - exactly bool or None (integers 0/1 disallowed)
            rg = tags["recall_gap"]
            self.assertTrue(
                rg is None or type(rg) is bool,
                f"Record {rid} invalid recall_gap: {rg!r} of type {type(rg).__name__} is not strictly bool or None"
            )
            self.assertNotEqual(type(rg), int, f"Record {rid} recall_gap must not be integer {rg!r}")
            
            # 10. alternative_used: Enum
            self.assertIn(tags["alternative_used"], ALLOWED_ALTERNATIVE_USED, f"Record {rid} invalid alternative_used: {tags['alternative_used']}")
            
            # 11. post_service_expectation: Enum
            self.assertIn(tags["post_service_expectation"], ALLOWED_POST_SERVICE_EXPECTATIONS, f"Record {rid} invalid post_service_expectation: {tags['post_service_expectation']}")
            
            # 12. discovery_channel: Enum
            self.assertIn(tags["discovery_channel"], ALLOWED_DISCOVERY_CHANNELS, f"Record {rid} invalid discovery_channel: {tags['discovery_channel']}")
            
            # 13. household_type: Enum
            self.assertIn(tags["household_type"], ALLOWED_HOUSEHOLD_TYPES, f"Record {rid} invalid household_type: {tags['household_type']}")
            
            # 14. unmet_need: String (Nullable)
            if tags["unmet_need"] is not None:
                self.assertIsInstance(tags["unmet_need"], str, f"Record {rid} unmet_need must be a string or None")
                self.assertTrue(len(tags["unmet_need"]) > 0, f"Record {rid} unmet_need is empty string")
            
            # 15. evidence_quote: String, exact substring of review_text
            self.assertIsInstance(tags["evidence_quote"], str, f"Record {rid} evidence_quote must be a string")
            self.assertTrue(len(tags["evidence_quote"]) > 0, f"Record {rid} evidence_quote is empty")
            self.assertIn(tags["evidence_quote"], r["review_text"], f"Record {rid} evidence quote not in review_text")
            
            # 16. confidence: Enum
            self.assertIn(tags["confidence"], ALLOWED_CONFIDENCES, f"Record {rid} invalid confidence: {tags['confidence']}")

    def test_metadata_separation_from_human_tags(self):
        """Verify source, date, and rating metadata are preserved at root and accurately mapped into human_tags."""
        for idx, r in enumerate(self.golden_records):
            rid = r.get("review_id")
            self.assertIn(r["source"], ["Play Store", "App Store"])
            if r.get("date") is not None:
                self.assertIsInstance(r["date"], str)
                self.assertTrue(
                    bool(re.match(r"^\d{4}-\d{2}-\d{2}$", r["date"])),
                    f"Record {rid} root date '{r['date']}' does not match YYYY-MM-DD"
                )
                try:
                    datetime.strptime(r["date"], "%Y-%m-%d")
                except ValueError as e:
                    self.fail(f"Record {rid} root date '{r['date']}' is not a valid date: {e}")
            self.assertIn(r.get("rating"), [1, 2, 3, 4, 5])
            self.assertEqual(r["human_tags"]["source"], r["source"])
            self.assertEqual(r["human_tags"]["date"], r.get("date"))

    def test_annotated_records_ground_truth(self):
        """Verify the exact confirmed values for all 30 annotated records (Batches 1, 2, and 3)."""
        expected_records = {
            "bb81193d-cf36-41b3-abce-4d201b3c4a59": {
                "category": "salon",
                "experience_type": "positive",
                "rebook_signal": "rebooked",
                "nothing_went_wrong": None,
                "confidence": "medium",
                "evidence_quote": "The last one was the best.",
                "note": "Repeat usage inferred from explicit phrase \"The last one\"."
            },
            "99226311-a2f2-4ecf-b1ed-7d28518cd95e": {
                "category": "deep clean",
                "experience_type": "positive",
                "rebook_signal": "unclear",
                "nothing_went_wrong": None,
                "confidence": "medium",
                "evidence_quote": "Very good kitchen cleaning done by [NAME_REDACTED]. Very polite, explains well and does a clean job.",
                "note": "Kitchen cleaning mapped to deep clean."
            },
            "75c91a8d-c132-48e2-a420-ea4221bb6059": {
                "category": "unknown",
                "experience_type": "positive",
                "rebook_signal": "unclear",
                "nothing_went_wrong": None,
                "confidence": "medium",
                "evidence_quote": "Excellent service, well-organised and very hygienic.",
                "note": "General service review, no specific category."
            },
            "36b24dd5-1cd2-4752-9a46-68307d86382c": {
                "category": "plumber",
                "experience_type": "negative",
                "rebook_signal": "unclear",
                "nothing_went_wrong": False,
                "unmet_need": "transparent cancellation fee policy",
                "confidence": "high",
                "evidence_quote": "The cancellation amount is definitely unjustified and I did not even get any clarity.",
                "note": "Customer cancellation does not establish future churn."
            },
            "4e4e2ef9-6dd6-40cc-a65b-a3f327daf7f0": {
                "category": "other",
                "experience_type": "negative",
                "rebook_signal": "unclear",
                "nothing_went_wrong": False,
                "unmet_need": "reliable post-service installation",
                "confidence": "high",
                "evidence_quote": "oil started dripping from outside indicating some leakage while reinstallation of chimney after service.",
                "note": "Chimney classified as other; warranty complaint is not automatically a warranty-clarity expectation."
            },
            "43582ef1-c85a-4b67-ad13-662ab7a72dcb": {
                "category": "other",
                "experience_type": "negative",
                "rebook_signal": "unclear",
                "nothing_went_wrong": False,
                "unmet_need": None,
                "confidence": "high",
                "evidence_quote": "Stay away from their Spa sessions , they are just going to treat you as their ginni pig !",
                "note": "Spa sessions mapped to other category per approved decision; warning to other users does not establish personal rebooking intent, so rebook_signal is unclear."
            },
            "1876c25b-b9ea-4720-9fcd-d11a7caa4bf1": {
                "category": "other",
                "experience_type": "negative",
                "rebook_signal": "unclear",
                "nothing_went_wrong": False,
                "unmet_need": "responsive customer care and punctual technician arrival",
                "confidence": "high",
                "evidence_quote": "They don't provide any RO technician if any problem occurs.",
                "note": "RO purifier classified as other; multiple operational failures (delay, rude staff, lack of guidelines)."
            },
            "bec86ea9-9a8f-495d-a091-1e4ec7843980": {
                "category": "unknown",
                "experience_type": "negative",
                "rebook_signal": "unclear",
                "nothing_went_wrong": False,
                "unmet_need": "full promised service duration",
                "confidence": "high",
                "evidence_quote": "instead of 1 hr standard service, you provide only 45 minutes.",
                "note": "3-star rating overridden to negative experience_type due to explicit shortfall in service delivery duration."
            },
            "6b579933-e83a-459c-b7c7-73f83b669c16": {
                "category": "unknown",
                "experience_type": "negative",
                "rebook_signal": "unclear",
                "nothing_went_wrong": False,
                "unmet_need": "reliable app booking tracking",
                "confidence": "high",
                "evidence_quote": "Suddenly it stops working and one can't see the status or details of their current or ongoing booking.",
                "note": "Technical failure during active booking; classified as negative despite 2-star score."
            },
            "06b45346-6f25-4d49-9b01-13d980482c2c": {
                "category": "unknown",
                "experience_type": "negative",
                "rebook_signal": "unclear",
                "nothing_went_wrong": False,
                "unmet_need": "protection against partner cancellations",
                "confidence": "high",
                "evidence_quote": "he cancelled booking exact half hour before the scheduled time without explaining the reason",
                "note": "Past tenure as regular customer overridden to unclear rebook_signal due to cancellation and churn context."
            },
            "b04a772a-f857-4356-ae3d-fa83612fdb90": {
                "category": "unknown",
                "experience_type": "negative",
                "rebook_signal": "unclear",
                "nothing_went_wrong": False,
                "unmet_need": "adherence to scheduled booking slot",
                "confidence": "medium",
                "evidence_quote": "after booking cancellation from UC and not arriving at the opted time slot.",
                "note": "Severe rating-polarity conflict: 4-star awarded but text reports partner cancellation and no-show; tagged based on text."
            },
            "372c9648-73fe-4245-8121-a8f198701159": {
                "category": "unknown",
                "experience_type": "negative",
                "rebook_signal": "unclear",
                "nothing_went_wrong": False,
                "unmet_need": "reliable warranty support for major services",
                "confidence": "high",
                "evidence_quote": "Pathetic Warranty Service. Good for low level cleaning jobs. Do NOT go for expensive painting or waterproofing service.",
                "note": "Category assigned as unknown due to cross-category comparison (cleaning vs painting/waterproofing); warranty complaint does not imply warranty clarity expectation."
            },
            "bbf12112-379a-4f54-9112-99d788cb9d2e": {
                "category": "unknown",
                "experience_type": "positive",
                "rebook_signal": "unclear",
                "nothing_went_wrong": None,
                "unmet_need": None,
                "confidence": "low",
                "evidence_quote": "good work",
                "note": "Terse low-information review (< 20 chars); confidence set to low, rebook_signal unclear."
            },
            "b31f176a-29af-4454-bf5d-4eacf25b7a38": {
                "category": "unknown",
                "experience_type": "unclear",
                "rebook_signal": "unclear",
                "nothing_went_wrong": None,
                "unmet_need": None,
                "confidence": "low",
                "evidence_quote": "ok ok",
                "note": "Terse 4-star review with tepid 'ok ok' text; experience_type set to unclear per approved decision."
            },
            "83ea578e-2a5e-41fc-a0b7-6b542aa3953e": {
                "category": "unknown",
                "experience_type": "negative",
                "rebook_signal": "unclear",
                "nothing_went_wrong": False,
                "unmet_need": "transparent and fair pricing",
                "confidence": "low",
                "evidence_quote": "lut rahe hai",
                "note": "Terse vernacular Hindi slang expressing overcharging friction; confidence low due to brevity."
            },
            "14815231009": {
                "category": "AC",
                "experience_type": "positive",
                "rebook_signal": "rebooked",
                "nothing_went_wrong": None,
                "unmet_need": None,
                "confidence": "high",
                "evidence_quote": "I have been using urban company for AC services since last 5 year",
                "note": "Explicit five-year repeat usage and positive AC service experience."
            },
            "14805610926": {
                "category": "deep clean",
                "experience_type": "positive",
                "rebook_signal": "unclear",
                "nothing_went_wrong": None,
                "unmet_need": None,
                "confidence": "high",
                "evidence_quote": "Had booked for deep cleaning a week ago.",
                "note": "Detailed positive deep-cleaning experience. No explicit future rebooking intention."
            },
            "14809078193": {
                "category": "other",
                "experience_type": "positive",
                "rebook_signal": "rebooked",
                "nothing_went_wrong": None,
                "unmet_need": None,
                "confidence": "high",
                "evidence_quote": "would recommend and book her anytime again!",
                "note": "Body spa mapped to other. Explicit future booking intention."
            },
            "14816200493": {
                "category": "other",
                "experience_type": "negative",
                "rebook_signal": "unclear",
                "nothing_went_wrong": False,
                "unmet_need": "reliable diagnosis and accountable customer support",
                "confidence": "high",
                "evidence_quote": "To get a second opinion, I contacted a local technician.",
                "note": "Washing machine repair classified as other. A local technician was explicitly used as an alternative. \"I would think twice\" does not establish definite churn."
            },
            "14811772838": {
                "category": "deep clean",
                "experience_type": "negative",
                "rebook_signal": "unclear",
                "nothing_went_wrong": False,
                "unmet_need": "reliable compensation handling for service damage",
                "confidence": "high",
                "evidence_quote": "The cleaning person spilled over excess cleaning acid over the bathroom tiles and damaged tiles.",
                "note": "Category confirmed as deep clean. Explicit property damage and compensation handling complaint."
            },
            "14813121635": {
                "category": "other",
                "experience_type": "negative",
                "rebook_signal": "unclear",
                "nothing_went_wrong": False,
                "unmet_need": "reliable product replacement and clear job-status tracking",
                "confidence": "high",
                "evidence_quote": "They delivered a faulty product,technician could do only partial installation.",
                "note": "Native M1 Pro purifier classified as other. Multiple explicit product and installation failures."
            },
            "14800891393": {
                "category": "deep clean",
                "experience_type": "negative",
                "rebook_signal": "unclear",
                "nothing_went_wrong": False,
                "unmet_need": "reliable booking fulfilment and clear service eligibility",
                "confidence": "high",
                "evidence_quote": "On the scheduled day, nobody arrived.",
                "note": "Explicit no-show followed by refusal to perform the deep-cleaning job."
            },
            "14819013371": {
                "category": "salon",
                "experience_type": "negative",
                "rebook_signal": "rebooked",
                "nothing_went_wrong": None,
                "unmet_need": "affordable salon services and transparent pricing",
                "confidence": "high",
                "evidence_quote": "Their prices have been steadily increasing",
                "note": "Explicit six-year regular salon usage. Pricing dissatisfaction does not establish churn."
            },
            "14787997500": {
                "category": "unknown",
                "experience_type": "neutral",
                "rebook_signal": "unclear",
                "nothing_went_wrong": False,
                "unmet_need": "easy and efficient service selection in the app",
                "confidence": "high",
                "evidence_quote": "Cannot select services properly & a lot of time is spent unnecessarily",
                "note": "Mixed feedback: service providers are good, but app usability has deteriorated."
            },
            "14784151525": {
                "category": "unknown",
                "experience_type": "positive",
                "rebook_signal": "rebooked",
                "nothing_went_wrong": False,
                "unmet_need": "consistent AC servicing quality",
                "confidence": "high",
                "evidence_quote": "Ac servicing quality wasn’t good.",
                "note": "Overall positive review with explicit repeat usage across multiple service categories. AC servicing is a specific negative exception."
            },
            "14811553737": {
                "category": "unknown",
                "experience_type": "negative",
                "rebook_signal": "will_not_rebook",
                "nothing_went_wrong": False,
                "unmet_need": "transparent plan terms and dependable customer support",
                "confidence": "high",
                "evidence_quote": "Pay extra to anyone but not them. Don’t trust this brand",
                "note": "Explicit recommendation to avoid the brand, indicating will_not_rebook."
            },
            "14792849957": {
                "category": "unknown",
                "experience_type": "positive",
                "rebook_signal": "rebooked",
                "nothing_went_wrong": None,
                "unmet_need": None,
                "confidence": "high",
                "evidence_quote": "It is my go-to app for all services",
                "note": "Explicit long-term usage and habitual repeat use across multiple categories. Category remains unknown because multiple services are mentioned."
            },
            "14793598838": {
                "category": "salon",
                "experience_type": "unclear",
                "rebook_signal": "unclear",
                "nothing_went_wrong": None,
                "unmet_need": None,
                "confidence": "low",
                "evidence_quote": "Therapist not reported",
                "note": "Pedicure maps to salon. Do not infer a missing therapist, failed appointment, or negative experience from this terse statement."
            },
            "14807881351": {
                "category": "unknown",
                "experience_type": "positive",
                "rebook_signal": "unclear",
                "nothing_went_wrong": None,
                "unmet_need": None,
                "confidence": "low",
                "evidence_quote": "Good",
                "note": "Low-information positive review. No other fields can be inferred."
            },
            "14812347184": {
                "category": "unknown",
                "experience_type": "negative",
                "rebook_signal": "unclear",
                "nothing_went_wrong": None,
                "unmet_need": "affordable and transparent service charges",
                "confidence": "low",
                "evidence_quote": "Very expensive.",
                "note": "Brief pricing complaint. Do not infer a service failure or future churn."
            }
        }
        
        golden_map = {r["review_id"]: r for r in self.golden_records}
        for rid, expected in expected_records.items():
            self.assertIn(rid, golden_map, f"Annotated review {rid} not found in golden records")
            r = golden_map[rid]
            self.assertEqual(r["annotation_status"], "annotated")
            self.assertEqual(
                r["annotator_notes"],
                expected["note"],
                f"Record {rid} annotator_notes mismatch"
            )
            tags = r["human_tags"]
            self.assertEqual(tags["category"], expected["category"])
            self.assertEqual(tags["experience_type"], expected["experience_type"])
            self.assertEqual(tags["rebook_signal"], expected["rebook_signal"])
            self.assertEqual(tags["nothing_went_wrong"], expected["nothing_went_wrong"])
            self.assertEqual(tags["confidence"], expected["confidence"])
            self.assertEqual(tags["evidence_quote"], expected["evidence_quote"])
            self.assertEqual(tags.get("unmet_need"), expected.get("unmet_need"))

    def test_record_43582ef1_consistency_and_approved_annotation(self):
        """Verify review 43582ef1 keeps approved rebook_signal='unclear' and requires exact corrected note."""
        r = {r["review_id"]: r for r in self.golden_records}["43582ef1-c85a-4b67-ad13-662ab7a72dcb"]
        tags = r["human_tags"]
        # Approved annotation must remain strictly "unclear"
        self.assertEqual(tags["rebook_signal"], "unclear")
        self.assertEqual(tags["category"], "other")
        self.assertEqual(tags["experience_type"], "negative")
        self.assertFalse(tags["nothing_went_wrong"])
        self.assertIsNone(tags["unmet_need"])
        # Annotator note must exactly equal the corrected note (no prefix-based condition allowed)
        expected_note = "Spa sessions mapped to other category per approved decision; warning to other users does not establish personal rebooking intent, so rebook_signal is unclear."
        self.assertEqual(r["annotator_notes"], expected_note)

    def test_boolean_fields_exact_type_validation(self):
        """Verify nothing_went_wrong and recall_gap strictly require bool or None, rejecting int 0/1."""
        for r in self.golden_records:
            rid = r.get("review_id")
            for field in ("nothing_went_wrong", "recall_gap"):
                val = r["human_tags"][field]
                self.assertTrue(
                    val is None or type(val) is bool,
                    f"Record {rid} {field} value {val!r} (type {type(val).__name__}) is not strictly bool or None"
                )
                self.assertNotEqual(type(val), int, f"Record {rid} {field} must not be int")

        # Directly test the validation logic rejecting 0 and 1
        def validate_strict_bool(val):
            if val is not None and type(val) is not bool:
                raise TypeError(f"Expected bool or None, got {type(val).__name__}")
            return True

        self.assertTrue(validate_strict_bool(True))
        self.assertTrue(validate_strict_bool(False))
        self.assertTrue(validate_strict_bool(None))
        with self.assertRaises(TypeError):
            validate_strict_bool(0)
        with self.assertRaises(TypeError):
            validate_strict_bool(1)
        with self.assertRaises(TypeError):
            validate_strict_bool("True")

    def test_nullable_date_validation_rule(self):
        """Verify that date is nullable per docs/schema.md and validates YYYY-MM-DD only when non-null."""
        for r in self.golden_records:
            date_val = r["human_tags"]["date"]
            if date_val is not None:
                self.assertIsInstance(date_val, str)
                self.assertTrue(bool(re.match(r"^\d{4}-\d{2}-\d{2}$", date_val)))
                datetime.strptime(date_val, "%Y-%m-%d")
        
        # Verify schema rule logic directly: null permitted, valid YYYY-MM-DD permitted, malformed rejected
        def validate_schema_date(d):
            if d is not None:
                if not isinstance(d, str) or not re.match(r"^\d{4}-\d{2}-\d{2}$", d):
                    raise ValueError("Invalid format")
                datetime.strptime(d, "%Y-%m-%d")
            return True

        self.assertTrue(validate_schema_date(None))
        self.assertTrue(validate_schema_date("2026-11-24"))
        with self.assertRaises(ValueError):
            validate_schema_date("invalid-date")
        with self.assertRaises(ValueError):
            validate_schema_date("2026/11/24")
        with self.assertRaises(ValueError):
            validate_schema_date("24-11-2026")

    def test_privacy_redactions_applied_in_golden_set(self):
        """Verify that third-party personal names in the golden copy are redacted per privacy policy."""
        golden_map = {r["review_id"]: r for r in self.golden_records}

        # 1. Specifically verify review ID 14809078193
        r_14809 = golden_map["14809078193"]
        self.assertIn("[NAME_REDACTED]", r_14809["review_text"])
        self.assertIn("[NAME_REDACTED]", r_14809.get("title", ""))
        self.assertNotIn("NengneiPhal", r_14809["review_text"])
        self.assertNotIn("NengneiPhal", r_14809.get("title", ""))
        self.assertNotIn("Singson", r_14809["review_text"])

        # 2. Verify review ID 14805610926
        r_14805 = golden_map["14805610926"]
        self.assertIn("[NAME_REDACTED]", r_14805["review_text"])
        self.assertNotIn("minhajul Islam", r_14805["review_text"])
        self.assertNotIn("minhaj", r_14805["review_text"])

        # 3. Verify review ID 06b45346-6f25-4d49-9b01-13d980482c2c
        r_06b4 = golden_map["06b45346-6f25-4d49-9b01-13d980482c2c"]
        self.assertIn("[NAME_REDACTED]", r_06b4["review_text"])
        self.assertNotIn("sujoy mondal", r_06b4["review_text"])


class TestGoldenSetDiversityAndManifest(unittest.TestCase):
    """Verifies rating diversity, category coverage, and documentation consistency."""

    @classmethod
    def setUpClass(cls):
        cls.golden_records = []
        if os.path.exists(GOLDEN_PATH):
            with open(GOLDEN_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        cls.golden_records.append(json.loads(line))

    def test_rating_diversity(self):
        """Verify representation of 1, 2, 3, 4, and 5-star reviews in the golden set."""
        ratings = {r.get("rating") for r in self.golden_records}
        self.assertIn(1, ratings, "Missing 1-star reviews in golden set")
        self.assertIn(2, ratings, "Missing 2-star reviews in golden set")
        self.assertIn(3, ratings, "Missing 3-star reviews in golden set")
        self.assertIn(4, ratings, "Missing 4-star reviews in golden set")
        self.assertIn(5, ratings, "Missing 5-star reviews in golden set")

    def test_documentation_files_exist(self):
        """Verify docs/golden_set_guidelines.md and docs/golden_set_manifest.md exist."""
        self.assertTrue(os.path.exists(GUIDELINES_PATH), f"Missing {GUIDELINES_PATH}")
        self.assertTrue(os.path.exists(MANIFEST_PATH), f"Missing {MANIFEST_PATH}")

    def test_manifest_contains_all_30_ids(self):
        """Verify sampling manifest documents every single golden review ID."""
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            manifest_text = f.read()

        for r in self.golden_records:
            rid = r["review_id"]
            self.assertIn(rid, manifest_text, f"Review ID {rid} missing from {MANIFEST_PATH}")

    def test_stratum_correction_for_review_6b579933(self):
        """Verify review 6b579933-e83a-459c-b7c7-73f83b669c16 is documented as Substantive Negative."""
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            manifest_text = f.read()

        # Find the line for 6b579933
        lines = [line for line in manifest_text.splitlines() if "6b579933-e83a-459c-b7c7-73f83b669c16" in line]
        self.assertEqual(len(lines), 1, "Review 6b579933-e83a-459c-b7c7-73f83b669c16 not found in manifest table")
        self.assertIn("Substantive Negative", lines[0], "Review 6b579933 was not updated to Substantive Negative")
        self.assertNotIn("Neutral / Mixed", lines[0], "Review 6b579933 still contains Neutral / Mixed stratum")

    def test_immutable_dataset_hash_integrity(self):
        """Verify raw, normalized, and existing tagged datasets have not been modified."""
        self.assertEqual(file_sha256("data/raw/google_play_reviews.jsonl"), RAW_GOOGLE_PLAY_HASH)
        self.assertEqual(file_sha256("data/raw/app_store_reviews.jsonl"), RAW_APP_STORE_HASH)
        self.assertEqual(file_sha256("data/processed/normalized_reviews.jsonl"), NORMALIZED_HASH)
        self.assertEqual(file_sha256("data/tagged/tagged_reviews.jsonl"), TAGGED_V1_HASH)
        self.assertEqual(file_sha256("data/tagged/review_queue.jsonl"), QUEUE_V1_HASH)


if __name__ == "__main__":
    unittest.main()
