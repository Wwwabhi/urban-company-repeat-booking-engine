"""AI Tagging Pipeline for Urban Company Repeat-Booking Discovery Engine.

Tags normalized customer reviews against the 16-field schema defined in `docs/schema.md`,
enforces strict grounding and non-inference rules, routes low-information and ambiguous
records to `data/tagged/review_queue.jsonl`, saves high-confidence tagged records to
`data/tagged/tagged_reviews.jsonl`, and excludes InstaHelp records from core tagging.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Ensure project root is in sys.path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Default file locations
DEFAULT_NORMALIZED_INPUT = Path("data/processed/normalized_reviews.jsonl")
DEFAULT_TAGGED_OUTPUT = Path("data/tagged/tagged_reviews.jsonl")
DEFAULT_QUEUE_OUTPUT = Path("data/tagged/review_queue.jsonl")
DEFAULT_TAGGED_OUTPUT_V2 = Path("data/tagged/tagged_reviews_v2.jsonl")
DEFAULT_QUEUE_OUTPUT_V2 = Path("data/tagged/review_queue_v2.jsonl")
DEFAULT_TAGGED_OUTPUT_V3 = Path("data/tagged/tagged_reviews_v3.jsonl")
DEFAULT_QUEUE_OUTPUT_V3 = Path("data/tagged/review_queue_v3.jsonl")
DEFAULT_TAGGED_OUTPUT_V3_1 = Path("data/tagged/tagged_reviews_v3_1.jsonl")
DEFAULT_QUEUE_OUTPUT_V3_1 = Path("data/tagged/review_queue_v3_1.jsonl")
DEFAULT_TAGGED_OUTPUT_V3_2 = Path("data/tagged/tagged_reviews_v3_2.jsonl")
DEFAULT_QUEUE_OUTPUT_V3_2 = Path("data/tagged/review_queue_v3_2.jsonl")
DEFAULT_PROMPT_PATH_V1 = Path("engine/prompts/tagger_v1.md")
DEFAULT_PROMPT_PATH_V2 = Path("engine/prompts/tagger_v2.md")
DEFAULT_PROMPT_PATH_V3 = Path("engine/prompts/tagger_v3.md")
DEFAULT_PROMPT_PATH_V3_1 = Path("engine/prompts/tagger_v3_1.md")
DEFAULT_PROMPT_PATH_V3_2 = Path("engine/prompts/tagger_v3_2.md")
DEFAULT_PROMPT_PATH = DEFAULT_PROMPT_PATH_V2

# Schema Enumerations from docs/schema.md
CATEGORY_ENUM = {
    "AC",
    "deep clean",
    "plumber",
    "salon",
    "electrician",
    "pest control",
    "other",
    "unknown",
}

EXPERIENCE_TYPE_ENUM = {
    "positive",
    "neutral",
    "negative",
    "unclear",
}

REBOOK_SIGNAL_ENUM = {
    "rebooked",
    "did_not_rebook",
    "will_not_rebook",
    "unclear",
}

NEED_TRIGGER_ENUM = {
    "breakdown",
    "season",
    "festival",
    "move",
    "guests",
    "routine",
    None,
}

ALTERNATIVE_USED_ENUM = {
    "neighbour",
    "family",
    "local provider",
    "WhatsApp or society group",
    "another app",
    "DIY",
    "none",
    "unclear",
}

POST_SERVICE_EXPECTATION_ENUM = {
    "follow-up",
    "reminder",
    "warranty clarity",
    "next-service advice",
    "nothing",
    "unclear",
}

DISCOVERY_CHANNEL_ENUM = {
    "search",
    "ad",
    "friend",
    "society group",
    "preinstalled habit",
    "unclear",
}

HOUSEHOLD_TYPE_ENUM = {
    "living alone",
    "couple",
    "family",
    "elderly",
    "renter",
    "owner",
    "unclear",
}

CONFIDENCE_ENUM = {
    "low",
    "medium",
    "high",
}

EXACT_16_FIELDS = [
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

# Terse / generic phrases that carry no repeat-booking evidence
LOW_INFO_PATTERN = re.compile(
    r"^(good|ok|okay|nice|super|best|great|useful|worst|bad|fine|v good|very good|"
    r"good service|ok ok|worst app|bad app|very bad|poor|excellent|amazing|satisfactory|"
    r"satisfying|loved it|hate it|helpful|awesome|well done|thank you|thanks)\W*$",
    re.IGNORECASE,
)

# Known Indian metropolitan cities for grounding checks
KNOWN_CITIES = {
    "bengaluru",
    "bangalore",
    "delhi",
    "new delhi",
    "mumbai",
    "bombay",
    "chennai",
    "madras",
    "hyderabad",
    "pune",
    "kolkata",
    "calcutta",
    "ahmedabad",
    "gurgaon",
    "gurugram",
    "noida",
    "greater noida",
    "ghaziabad",
    "faridabad",
    "chandigarh",
    "jaipur",
    "lucknow",
    "kochi",
    "cochin",
    "indore",
}


def is_low_information_review(text: str, title: Optional[str] = None) -> bool:
    """Detects whether a review text is too terse or generic to infer customer journey.

    Treats short reviews like 'good', 'ok', 'useful app' as low-information per Requirement 7.
    """
    clean_text = (text or "").strip()
    clean_title = (title or "").strip()
    combined = f"{clean_title} {clean_text}".strip()

    if not combined or len(combined) < 20:
        return True

    words = re.findall(r"\w+", combined)
    if len(words) <= 3 and LOW_INFO_PATTERN.match(combined):
        return True

    return False


def validate_evidence_quote(quote: Optional[str], text: str, title: Optional[str] = None) -> bool:
    """Verifies that the evidence quote is grounded as a verbatim substring in the review text."""
    if not quote:
        return True  # Empty quote is acceptable for low-info / unclear reviews

    clean_quote = re.sub(r"\s+", " ", quote.strip().lower())
    clean_text = re.sub(r"\s+", " ", f"{title or ''} {text or ''}".strip().lower())

    return clean_quote in clean_text


def validate_16_schema_fields(tags: Dict[str, Any]) -> List[str]:
    """Validates that a tags dictionary strictly contains all 16 fields with allowed values."""
    errors = []
    missing_fields = set(EXACT_16_FIELDS) - set(tags.keys())
    if missing_fields:
        errors.append(f"Missing required fields: {sorted(list(missing_fields))}")

    # Check Enum validations
    cat = tags.get("category")
    if cat not in CATEGORY_ENUM:
        errors.append(f"Invalid category '{cat}'. Allowed: {sorted(list(CATEGORY_ENUM))}")

    exp = tags.get("experience_type")
    if exp not in EXPERIENCE_TYPE_ENUM:
        errors.append(f"Invalid experience_type '{exp}'. Allowed: {sorted(list(EXPERIENCE_TYPE_ENUM))}")

    reb = tags.get("rebook_signal")
    if reb not in REBOOK_SIGNAL_ENUM:
        errors.append(f"Invalid rebook_signal '{reb}'. Allowed: {sorted(list(REBOOK_SIGNAL_ENUM))}")

    trig = tags.get("need_trigger")
    if trig not in NEED_TRIGGER_ENUM:
        errors.append(f"Invalid need_trigger '{trig}'. Allowed: {sorted(list(NEED_TRIGGER_ENUM))}")

    alt = tags.get("alternative_used")
    if alt not in ALTERNATIVE_USED_ENUM:
        errors.append(f"Invalid alternative_used '{alt}'. Allowed: {sorted(list(ALTERNATIVE_USED_ENUM))}")

    pse = tags.get("post_service_expectation")
    if pse not in POST_SERVICE_EXPECTATION_ENUM:
        errors.append(f"Invalid post_service_expectation '{pse}'. Allowed: {sorted(list(POST_SERVICE_EXPECTATION_ENUM))}")

    disc = tags.get("discovery_channel")
    if disc not in DISCOVERY_CHANNEL_ENUM:
        errors.append(f"Invalid discovery_channel '{disc}'. Allowed: {sorted(list(DISCOVERY_CHANNEL_ENUM))}")

    hh = tags.get("household_type")
    if hh not in HOUSEHOLD_TYPE_ENUM:
        errors.append(f"Invalid household_type '{hh}'. Allowed: {sorted(list(HOUSEHOLD_TYPE_ENUM))}")

    conf = tags.get("confidence")
    if conf not in CONFIDENCE_ENUM:
        errors.append(f"Invalid confidence '{conf}'. Allowed: {sorted(list(CONFIDENCE_ENUM))}")

    # Check tri-state boolean / nullable fields
    nww = tags.get("nothing_went_wrong")
    if nww not in (True, False, None):
        errors.append(f"Invalid nothing_went_wrong '{nww}'. Must be true, false, or null.")

    rg = tags.get("recall_gap")
    if rg not in (True, False, None):
        errors.append(f"Invalid recall_gap '{rg}'. Must be true, false, or null.")

    unmet = tags.get("unmet_need")
    if unmet is not None and not isinstance(unmet, str):
        errors.append(f"Invalid unmet_need '{unmet}'. Must be string or null.")

    return errors


def evaluate_review_queue_triggers(
    normalized_review: Dict[str, Any],
    tags: Dict[str, Any],
    is_low_info: bool,
) -> Tuple[bool, List[str]]:
    """Determines whether a record must be routed to the human review queue.

    Triggers:
    1. Low information review text (terse or generic).
    2. Overall confidence is low.
    3. Rating contradicts text polarity (e.g. 5-star negative or 1-star positive).
    4. Evidence quote is ungrounded (not found in text).
    5. Schema validation errors.
    """
    reasons = []

    if is_low_info:
        reasons.append("low_information: Review text lacks sufficient detail to infer customer journey")

    if tags.get("confidence") == "low":
        reasons.append("low_confidence: Model reported low tagging confidence")

    rating = normalized_review.get("rating")
    exp_type = tags.get("experience_type")
    if rating is not None:
        if rating >= 4 and exp_type == "negative":
            reasons.append(f"rating_polarity_conflict: High rating ({rating} stars) contradicts negative experience_type")
        elif rating <= 2 and exp_type == "positive":
            reasons.append(f"rating_polarity_conflict: Low rating ({rating} stars) contradicts positive experience_type")

    quote = tags.get("evidence_quote")
    text = normalized_review.get("text") or ""
    title = normalized_review.get("title")
    if quote and not validate_evidence_quote(quote, text, title):
        reasons.append(f"ungrounded_evidence: Evidence quote '{quote}' not found verbatim in review text")

    schema_errors = validate_16_schema_fields(tags)
    if schema_errors:
        reasons.extend([f"schema_error: {e}" for e in schema_errors])

    requires_review = len(reasons) > 0
    return requires_review, reasons


class BaseLLMClient(ABC):
    """Abstract interface for LLM tagging clients."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Name of the model powering the tagger."""
        pass

    @abstractmethod
    def tag_review(self, review: Dict[str, Any]) -> Dict[str, Any]:
        """Tags a normalized review and returns {tags: ..., tag_evidence: ...}."""
        pass


class MockLLMClient(BaseLLMClient):
    """Mock LLM client producing grounded, schema-compliant tags without live API calls.

    Supports v1 (pilot baseline), v2 (hardened policy), and v3 (golden-calibrated).
    """

    def __init__(self, model_name: str = "mock-haiku-5-5", version: str = "v2"):
        self._model_name = model_name
        self.version = version
        self.call_count = 0

    @property
    def model_name(self) -> str:
        return self._model_name

    def tag_review(self, review: Dict[str, Any]) -> Dict[str, Any]:
        self.call_count += 1
        text = (review.get("text") or "").strip()
        title = (review.get("title") or "").strip()
        source = review.get("source")
        date = review.get("date")
        rating = review.get("rating")

        combined = f"{title}. {text}".strip() if title else text
        combined_lower = combined.lower()

        is_low_info = is_low_information_review(text=text, title=title)

        # 1. City grounding
        city = None
        city_quote = None
        for c in KNOWN_CITIES:
            # Check for city as distinct word
            m = re.search(r"\b" + re.escape(c) + r"\b", combined_lower)
            if m:
                # Capitalize nicely
                city = c.title()
                city_quote = combined[m.start():m.end()]
                break

        # 2. Category grounding
        category = "unknown"
        cat_quote = None
        cat_conf = "low"
        if self.version in ("v2", "v3", "v3_1", "v3_2"):
            # Semantic classification: Check booked appliance repair first to avoid incidental plumbing/electrical triggers
            # In v3 / v3_1 / v3_2: Appliance cleaning/repair (including chimney deep clean) maps to 'other'
            # In v3_1 / v3_2: Spa sessions / body spa / massage also map to 'other'
            appliance_pattern = (
                r"\b(washing machine|refrigerator|fridge|microwave|oven|ro purifier|water purifier|water heater|geyser|tv repair|painting|waterproofing|chimney)\b"
                if self.version in ("v3", "v3_1", "v3_2")
                else r"\b(washing machine|refrigerator|fridge|microwave|oven|ro purifier|water purifier|water heater|geyser|tv repair|painting|waterproofing)\b"
            )
            premises_clean_pattern = (
                r"\b(deep clean|cleaning|sofa clean|bathroom clean|kitchen clean|house clean|home deep clean)\b"
                if self.version in ("v3", "v3_1", "v3_2")
                else r"\b(deep clean|cleaning|sofa clean|bathroom clean|kitchen clean|house clean|chimney deep clean)\b"
            )
            if self.version in ("v3_1", "v3_2") and re.search(r"\b(spa|body spa|massage)\b", combined_lower):
                category = "other"
                m = re.search(r"\b(spa|body spa|massage)\b", combined_lower)
                cat_quote = combined[m.start():m.end()]
                cat_conf = "high"
            elif re.search(appliance_pattern, combined_lower):
                category = "other"
                m = re.search(appliance_pattern, combined_lower)
                cat_quote = combined[m.start():m.end()]
                cat_conf = "high"
            elif re.search(r"\b(ac|air conditioner|cooling|compressor)\b", combined_lower):
                category = "AC"
                m = re.search(r"\b(ac|air conditioner|cooling|compressor)\b", combined_lower)
                cat_quote = combined[m.start():m.end()]
                cat_conf = "high"
            elif re.search(premises_clean_pattern, combined_lower):
                category = "deep clean"
                m = re.search(premises_clean_pattern, combined_lower)
                cat_quote = combined[m.start():m.end()]
                cat_conf = "high"
            elif re.search(r"\b(plumb|plumbing|tap repair|blocked drain|sink repair|flush repair)\b", combined_lower) or (
                re.search(r"\b(pipe|leak|drain|tap)\b", combined_lower)
                and not re.search(r"\b(washing machine|refrigerator|fridge|water purifier|ro purifier|chimney)\b", combined_lower)
            ):
                category = "plumber"
                m = re.search(r"\b(plumb|plumbing|tap repair|blocked drain|sink repair|flush repair|pipe|leak|drain|tap)\b", combined_lower)
                cat_quote = combined[m.start():m.end()]
                cat_conf = "high"
            elif self.version in ("v3_1", "v3_2") and re.search(r"\b(salon|hair|waxing|facial|manicure|pedicure|threading|grooming)\b", combined_lower):
                category = "salon"
                m = re.search(r"\b(salon|hair|waxing|facial|manicure|pedicure|threading|grooming)\b", combined_lower)
                cat_quote = combined[m.start():m.end()]
                cat_conf = "high"
            elif self.version not in ("v3_1", "v3_2") and re.search(r"\b(salon|hair|waxing|facial|manicure|pedicure|massage|spa)\b", combined_lower):
                category = "salon"
                m = re.search(r"\b(salon|hair|waxing|facial|manicure|pedicure|massage|spa)\b", combined_lower)
                cat_quote = combined[m.start():m.end()]
                cat_conf = "high"
            elif re.search(r"\b(electric|switch|wiring|fan repair)\b", combined_lower):
                category = "electrician"
                m = re.search(r"\b(electric|switch|wiring|fan repair)\b", combined_lower)
                cat_quote = combined[m.start():m.end()]
                cat_conf = "high"
            elif re.search(r"\b(pest|termite|cockroach|bedbug|mosquito)\b", combined_lower):
                category = "pest control"
                m = re.search(r"\b(pest|termite|cockroach|bedbug|mosquito)\b", combined_lower)
                cat_quote = combined[m.start():m.end()]
                cat_conf = "high"
        else:
            if re.search(r"\b(ac|air conditioner|cooling|compressor)\b", combined_lower):
                category = "AC"
                m = re.search(r"\b(ac|air conditioner|cooling|compressor)\b", combined_lower)
                cat_quote = combined[m.start():m.end()]
                cat_conf = "high"
            elif re.search(r"\b(deep clean|cleaning|sofa clean|bathroom clean|kitchen clean|house clean)\b", combined_lower):
                category = "deep clean"
                m = re.search(r"\b(deep clean|cleaning|sofa clean|bathroom clean|kitchen clean|house clean)\b", combined_lower)
                cat_quote = combined[m.start():m.end()]
                cat_conf = "high"
            elif re.search(r"\b(plumb|tap|pipe|leak|drain)\b", combined_lower):
                category = "plumber"
                m = re.search(r"\b(plumb|tap|pipe|leak|drain)\b", combined_lower)
                cat_quote = combined[m.start():m.end()]
                cat_conf = "high"
            elif re.search(r"\b(salon|hair|waxing|facial|manicure|pedicure|massage|spa)\b", combined_lower):
                category = "salon"
                m = re.search(r"\b(salon|hair|waxing|facial|manicure|pedicure|massage|spa)\b", combined_lower)
                cat_quote = combined[m.start():m.end()]
                cat_conf = "high"
            elif re.search(r"\b(electric|switch|wiring|fan repair|appliance)\b", combined_lower):
                category = "electrician"
                m = re.search(r"\b(electric|switch|wiring|fan repair|appliance)\b", combined_lower)
                cat_quote = combined[m.start():m.end()]
                cat_conf = "high"
            elif re.search(r"\b(pest|termite|cockroach|bedbug|mosquito)\b", combined_lower):
                category = "pest control"
                m = re.search(r"\b(pest|termite|cockroach|bedbug|mosquito)\b", combined_lower)
                cat_quote = combined[m.start():m.end()]
                cat_conf = "high"

        # 3. Experience Type
        experience_type = "unclear"
        exp_quote = None
        exp_conf = "medium"
        if rating is not None:
            if rating >= 4:
                experience_type = "positive"
            elif rating == 3:
                experience_type = "neutral"
            elif rating <= 2:
                experience_type = "negative"

        # Refine with text cues
        if re.search(r"\b(worst|terrible|pathetic|horrible|cheated|loot|fraud|waste|scam)\b", combined_lower):
            experience_type = "negative"
            m = re.search(r"\b(worst|terrible|pathetic|horrible|cheated|loot|fraud|waste|scam)\b", combined_lower)
            exp_quote = combined[m.start():m.end()]
            exp_conf = "high"
        elif re.search(r"\b(excellent|good|great|best|satisfied|superb|loved)\b", combined_lower):
            if experience_type != "negative":  # don't override negative text if mixed
                experience_type = "positive"
                m = re.search(r"\b(excellent|good|great|best|satisfied|superb|loved)\b", combined_lower)
                exp_quote = combined[m.start():m.end()]
                exp_conf = "high"

        # 4. Rebook Signal
        rebook_signal = "unclear"
        rebook_quote = None
        rebook_conf = "low"
        if not is_low_info:
            will_not_rebook_pattern = (
                r"\b(never book again|never booking(?: again)?|will not book|wont book|will never book|never use(?: again)?|will not use(?: this app)?(?: again)?|wont use(?: this app)?(?: again)?|uninstalled|deleting app)\b"
                if self.version in ("v2", "v3", "v3_1", "v3_2")
                else r"\b(never book again|never booking(?: again)?|will not book|wont book|will never book|never use(?: again)?|uninstalled|deleting app)\b"
            )
            future_rebook_pattern = r"\b(definitely book|will .* book .* again|would book .* again|book her again|book him again|book .* anytime again|surely book)\b"
            if re.search(will_not_rebook_pattern, combined_lower):
                rebook_signal = "will_not_rebook"
                m = re.search(will_not_rebook_pattern, combined_lower)
                rebook_quote = combined[m.start():m.end()]
                rebook_conf = "high"
            elif self.version in ("v3_1", "v3_2") and re.search(future_rebook_pattern, combined_lower):
                rebook_signal = "rebooked"
                m = re.search(future_rebook_pattern, combined_lower)
                rebook_quote = combined[m.start():m.end()]
                rebook_conf = "high"
            elif re.search(r"\b(stopped using|did not rebook|didnt book again|haven't booked|not booking again)\b", combined_lower):
                rebook_signal = "did_not_rebook"
                m = re.search(r"\b(stopped using|did not rebook|didnt book again|haven't booked|not booking again)\b", combined_lower)
                rebook_quote = combined[m.start():m.end()]
                rebook_conf = "high"
            elif re.search(r"\b(rebooked|booked again|repeated booking|booking again|booked another|second time booking|third time booking)\b", combined_lower):
                if self.version in ("v2", "v3", "v3_1", "v3_2") and re.search(r"\b(cancelled|canceled|1 star|hopeless|complaint|worst)\b", combined_lower):
                    rebook_signal = "unclear"
                    rebook_quote = None
                    rebook_conf = "low"
                else:
                    rebook_signal = "rebooked"
                    m = re.search(r"\b(rebooked|booked again|repeated booking|booking again|booked another|second time booking|third time booking)\b", combined_lower)
                    rebook_quote = combined[m.start():m.end()]
                    rebook_conf = "high"
            elif re.search(r"\b(regular customer|use regularly|frequent user|always use)\b", combined_lower):
                if self.version in ("v2", "v3", "v3_1", "v3_2"):
                    # Requirement: 'regular customer' alone must never imply rebooked.
                    # Historical usage and current rebooking intent must be distinguished.
                    rebook_signal = "unclear"
                    rebook_quote = None
                    rebook_conf = "low"
                else:
                    rebook_signal = "rebooked"
                    m = re.search(r"\b(regular customer|use regularly|frequent user|always use)\b", combined_lower)
                    rebook_quote = combined[m.start():m.end()]
                    rebook_conf = "high"

        # 5. Nothing Went Wrong (tri-state: True, False, None)
        # Only True when service was good/fine, but did not rebook or used once/switched
        nothing_went_wrong = None
        nww_quote = None
        if not is_low_info:
            if experience_type == "positive" and rebook_signal in ("did_not_rebook", "will_not_rebook"):
                nothing_went_wrong = True
                nww_quote = rebook_quote or exp_quote
            elif experience_type == "negative":
                nothing_went_wrong = False
                nww_quote = exp_quote

        # 6. Need Trigger (tri-state enum: breakdown, season, festival, move, guests, routine, None)
        need_trigger = None
        trig_quote = None
        trig_conf = "low"
        if re.search(r"\b(broke|breakdown|not working|stopped working|emergency|leaking)\b", combined_lower):
            need_trigger = "breakdown"
            m = re.search(r"\b(broke|breakdown|not working|stopped working|emergency|leaking)\b", combined_lower)
            trig_quote = combined[m.start():m.end()]
            trig_conf = "high"
        elif re.search(r"\b(summer|heat|monsoon|winter)\b", combined_lower):
            need_trigger = "season"
            m = re.search(r"\b(summer|heat|monsoon|winter)\b", combined_lower)
            trig_quote = combined[m.start():m.end()]
            trig_conf = "high"
        elif re.search(r"\b(diwali|festival|eid|pooja|puja|wedding)\b", combined_lower):
            need_trigger = "festival"
            m = re.search(r"\b(diwali|festival|eid|pooja|puja|wedding)\b", combined_lower)
            trig_quote = combined[m.start():m.end()]
            trig_conf = "high"
        elif re.search(r"\b(shifting|relocating|moved|new house|new flat)\b", combined_lower):
            need_trigger = "move"
            m = re.search(r"\b(shifting|relocating|moved|new house|new flat)\b", combined_lower)
            trig_quote = combined[m.start():m.end()]
            trig_conf = "high"
        elif re.search(r"\b(guests|party|relatives visiting)\b", combined_lower):
            need_trigger = "guests"
            m = re.search(r"\b(guests|party|relatives visiting)\b", combined_lower)
            trig_quote = combined[m.start():m.end()]
            trig_conf = "high"
        elif re.search(r"\b(routine|monthly|regular maintenance|periodic)\b", combined_lower):
            need_trigger = "routine"
            m = re.search(r"\b(routine|monthly|regular maintenance|periodic)\b", combined_lower)
            trig_quote = combined[m.start():m.end()]
            trig_conf = "high"

        # 7. Recall Gap (tri-state: True, False, None)
        recall_gap = None
        rg_quote = None
        if re.search(r"\b(forgot|didn't think|did not think|didn't know uc did|didn't remember)\b", combined_lower):
            recall_gap = True
            m = re.search(r"\b(forgot|didn't think|did not think|didn't know uc did|didn't remember)\b", combined_lower)
            rg_quote = combined[m.start():m.end()]

        # 8. Alternative Used
        alternative_used = "unclear"
        alt_quote = None
        if re.search(r"\b(local|local guy|offline vendor|market guy|local electrician|local plumber)\b", combined_lower):
            alternative_used = "local provider"
            m = re.search(r"\b(local|local guy|offline vendor|market guy|local electrician|local plumber)\b", combined_lower)
            alt_quote = combined[m.start():m.end()]
        elif re.search(r"\b(neighbour|neighbor|society guard|security guard)\b", combined_lower):
            alternative_used = "neighbour"
            m = re.search(r"\b(neighbour|neighbor|society guard|security guard)\b", combined_lower)
            alt_quote = combined[m.start():m.end()]
        elif re.search(r"\b(whatsapp|society group|rwa group)\b", combined_lower):
            alternative_used = "WhatsApp or society group"
            m = re.search(r"\b(whatsapp|society group|rwa group)\b", combined_lower)
            alt_quote = combined[m.start():m.end()]
        elif re.search(r"\b(family|parents|relatives)\b", combined_lower):
            alternative_used = "family"
            m = re.search(r"\b(family|parents|relatives)\b", combined_lower)
            alt_quote = combined[m.start():m.end()]
        elif re.search(r"\b(diy|fixed it myself|did it myself)\b", combined_lower):
            alternative_used = "DIY"
            m = re.search(r"\b(diy|fixed it myself|did it myself)\b", combined_lower)
            alt_quote = combined[m.start():m.end()]
        elif re.search(r"\b(another app|competitor|nobroker|porter)\b", combined_lower):
            alternative_used = "another app"
            m = re.search(r"\b(another app|competitor|nobroker|porter)\b", combined_lower)
            alt_quote = combined[m.start():m.end()]
        elif re.search(r"\b(no alternative|didn't call anyone|did not call anyone|did not use anyone else|only uc|no one else)\b", combined_lower):
            alternative_used = "none"
            m = re.search(r"\b(no alternative|didn't call anyone|did not call anyone|did not use anyone else|only uc|no one else)\b", combined_lower)
            alt_quote = combined[m.start():m.end()]

        # 9. Post-Service Expectation
        post_service_expectation = "unclear"
        pse_quote = None
        if re.search(r"\b(follow-up|follow up|called back|call back)\b", combined_lower):
            post_service_expectation = "follow-up"
            m = re.search(r"\b(follow-up|follow up|called back|call back)\b", combined_lower)
            pse_quote = combined[m.start():m.end()]
        elif re.search(r"\b(reminder|remind me|next service date)\b", combined_lower):
            post_service_expectation = "reminder"
            m = re.search(r"\b(reminder|remind me|next service date)\b", combined_lower)
            pse_quote = combined[m.start():m.end()]
        elif self.version in ("v2", "v3", "v3_1", "v3_2"):
            # In v2/v3/v3_1/v3_2: Warranty complaints do NOT imply warranty clarity
            adv_pattern = r"\b(next[- ]service advice|future maintenance advice|recommended maintenance advice|advice on (?:when to|next) service|maintenance tips|maintenance advice|service advice)\b"
            if (
                re.search(r"\b(warranty clarity|warranty terms|warranty policy|warranty card|expected warranty|explain warranty|clarify warranty)\b", combined_lower)
                and not re.search(r"\b(pathetic warranty|warranty service|cannot claim warranty|claim warranty|warranty was just|no warranty support|valid for 10 days)\b", combined_lower)
            ):
                post_service_expectation = "warranty clarity"
                m = re.search(r"\b(warranty clarity|warranty terms|warranty policy|warranty card|expected warranty|explain warranty|clarify warranty)\b", combined_lower)
                if m:
                    pse_quote = combined[m.start():m.end()]
            elif re.search(adv_pattern, combined_lower) and not re.search(r"\b(advice to other|advice to customers|advice for others|my advice|don't (?:ever )?take advice|never take advice)\b", combined_lower):
                m = re.search(adv_pattern, combined_lower)
                if m:
                    post_service_expectation = "next-service advice"
                    pse_quote = combined[m.start():m.end()]
            elif re.search(r"\b(don't call|do not call|no follow up|no contact|leave me alone|no calls|want nothing|expect nothing)\b", combined_lower):
                post_service_expectation = "nothing"
                m = re.search(r"\b(don't call|do not call|no follow up|no contact|leave me alone|no calls|want nothing|expect nothing)\b", combined_lower)
                if m:
                    pse_quote = combined[m.start():m.end()]
        else:
            if re.search(r"\b(warranty clarity|warranty card|warranty terms|warranty policy|warranty)\b", combined_lower):
                post_service_expectation = "warranty clarity"
                m = re.search(r"\b(warranty clarity|warranty card|warranty terms|warranty policy|warranty)\b", combined_lower)
                pse_quote = combined[m.start():m.end()]
            elif re.search(r"\b(advice|recommended maintenance|next service advice)\b", combined_lower):
                post_service_expectation = "next-service advice"
                m = re.search(r"\b(advice|recommended maintenance|next service advice)\b", combined_lower)
                pse_quote = combined[m.start():m.end()]
            elif re.search(r"\b(don't call|do not call|no follow up|no contact|leave me alone|no calls|want nothing|expect nothing)\b", combined_lower):
                post_service_expectation = "nothing"
                m = re.search(r"\b(don't call|do not call|no follow up|no contact|leave me alone|no calls|want nothing|expect nothing)\b", combined_lower)
                pse_quote = combined[m.start():m.end()]

        # 10. Discovery Channel
        discovery_channel = "unclear"
        disc_quote = None
        if re.search(r"\b(google search|searched online|app store search)\b", combined_lower):
            discovery_channel = "search"
            m = re.search(r"\b(google search|searched online|app store search)\b", combined_lower)
            disc_quote = combined[m.start():m.end()]
        elif re.search(r"\b(saw an ad|advertisement|youtube ad|tv commercial)\b", combined_lower):
            discovery_channel = "ad"
            m = re.search(r"\b(saw an ad|advertisement|youtube ad|tv commercial)\b", combined_lower)
            disc_quote = combined[m.start():m.end()]
        elif re.search(r"\b(friend recommended|colleague told|word of mouth)\b", combined_lower):
            discovery_channel = "friend"
            m = re.search(r"\b(friend recommended|colleague told|word of mouth)\b", combined_lower)
            disc_quote = combined[m.start():m.end()]
        elif re.search(r"\b(society recommendation|apartment group)\b", combined_lower):
            discovery_channel = "society group"
            m = re.search(r"\b(society recommendation|apartment group)\b", combined_lower)
            disc_quote = combined[m.start():m.end()]

        # 11. Household Type
        household_type = "unclear"
        hh_quote = None
        if re.search(r"\b(bachelor|living alone|stay alone|single)\b", combined_lower):
            household_type = "living alone"
            m = re.search(r"\b(bachelor|living alone|stay alone|single)\b", combined_lower)
            hh_quote = combined[m.start():m.end()]
        elif re.search(r"\b(my husband|my wife|my partner|couple)\b", combined_lower):
            household_type = "couple"
            m = re.search(r"\b(my husband|my wife|my partner|couple)\b", combined_lower)
            hh_quote = combined[m.start():m.end()]
        elif re.search(r"\b(my kids|my children|my parents|our family)\b", combined_lower):
            household_type = "family"
            m = re.search(r"\b(my kids|my children|my parents|our family)\b", combined_lower)
            hh_quote = combined[m.start():m.end()]
        elif re.search(r"\b(elderly|senior citizens|aging parents)\b", combined_lower):
            household_type = "elderly"
            m = re.search(r"\b(elderly|senior citizens|aging parents)\b", combined_lower)
            hh_quote = combined[m.start():m.end()]
        elif re.search(r"\b(rented|tenant|renting|landlord)\b", combined_lower):
            household_type = "renter"
            m = re.search(r"\b(rented|tenant|renting|landlord)\b", combined_lower)
            hh_quote = combined[m.start():m.end()]
        elif re.search(r"\b(homeowner|own home|my house)\b", combined_lower):
            household_type = "owner"
            m = re.search(r"\b(homeowner|own home|my house)\b", combined_lower)
            hh_quote = combined[m.start():m.end()]

        # 12. Unmet Need
        # Nullable: Use null when no unmet need is explicitly expressed.
        unmet_need = None
        if experience_type == "negative":
            if re.search(r"\b(cancel|no show|did not show)\b", combined_lower):
                unmet_need = "reliable professional arrival without cancellations"
            elif (
                re.search(r"\b(overcharge|extra charge|hidden charge|looting|surge charge|price hike|demanded extra|fraud charges|high price|costly|expensive)\b", combined_lower)
                and not re.search(r"\bwaste of money\b", combined_lower)
            ):
                unmet_need = "transparent and fair pricing"
            elif re.search(r"\b(damage|broke|ruined|botched|incomplete work|poor work quality)\b", combined_lower):
                unmet_need = "high service quality and accountability"
            elif self.version not in ("v2", "v3", "v3_1", "v3_2"):
                unmet_need = "satisfactory home service execution"
            else:
                unmet_need = None

        # 13. Primary Evidence Quote
        primary_quote = (
            rebook_quote
            or exp_quote
            or cat_quote
            or trig_quote
            or (combined[:80] if len(combined) >= 10 else combined)
        )

        # 14. Overall Confidence
        if is_low_info:
            overall_confidence = "low"
        elif category != "unknown" and experience_type in ("positive", "negative") and len(combined) > 50:
            overall_confidence = "high"
        else:
            overall_confidence = "medium"

        tags = {
            "source": source,
            "date": date,
            "city": city,
            "category": category,
            "experience_type": experience_type,
            "nothing_went_wrong": nothing_went_wrong,
            "rebook_signal": rebook_signal,
            "need_trigger": need_trigger,
            "recall_gap": recall_gap,
            "alternative_used": alternative_used,
            "post_service_expectation": post_service_expectation,
            "discovery_channel": discovery_channel,
            "household_type": household_type,
            "unmet_need": unmet_need,
            "evidence_quote": primary_quote,
            "confidence": overall_confidence,
        }

        tag_evidence = {
            "city": {"quote": city_quote, "confidence": "high" if city else "low"},
            "category": {"quote": cat_quote, "confidence": cat_conf},
            "experience_type": {"quote": exp_quote, "confidence": exp_conf},
            "rebook_signal": {"quote": rebook_quote, "confidence": rebook_conf},
            "need_trigger": {"quote": trig_quote, "confidence": trig_conf},
            "nothing_went_wrong": {"quote": nww_quote, "confidence": "high" if nww_quote else "low"},
            "recall_gap": {"quote": rg_quote, "confidence": "high" if rg_quote else "low"},
            "alternative_used": {"quote": alt_quote, "confidence": "high" if alt_quote else "low"},
            "post_service_expectation": {"quote": pse_quote, "confidence": "high" if pse_quote else "low"},
            "discovery_channel": {"quote": disc_quote, "confidence": "high" if disc_quote else "low"},
            "household_type": {"quote": hh_quote, "confidence": "high" if hh_quote else "low"},
        }

        return {
            "tags": tags,
            "tag_evidence": tag_evidence,
        }


RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def parse_retry_after(header_val: Optional[Any]) -> Optional[float]:
    """Parses a Retry-After or rate-limit reset header value into seconds."""
    if not header_val:
        return None
    val = str(header_val).strip()
    if val.endswith("ms"):
        try:
            return max(0.0, float(val[:-2]) / 1000.0)
        except ValueError:
            pass
    if val.endswith("s"):
        try:
            return max(0.0, float(val[:-1]))
        except ValueError:
            pass
    try:
        return max(0.0, float(val))
    except ValueError:
        pass
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(val)
        delta = dt.timestamp() - time.time()
        return max(0.0, delta)
    except Exception:
        return None


def is_retryable_error(exc: Exception) -> bool:
    """Determines whether an exception from the Gemini API is transient and retryable."""
    try:
        from google.genai import errors
        if isinstance(exc, errors.APIError):
            if exc.code in RETRYABLE_STATUS_CODES:
                return True
        if isinstance(exc, errors.ServerError):
            return True
    except (ImportError, AttributeError):
        pass

    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return True

    err_str = str(exc).lower()
    retryable_keywords = [
        "429",
        "rate limit",
        "quota",
        "resource exhausted",
        "resource_exhausted",
        "timed out",
        "timeout",
        "connection reset",
        "service unavailable",
        "503",
        "500",
        "502",
        "504",
    ]
    return any(k in err_str for k in retryable_keywords)


class GeminiLLMClient(BaseLLMClient):
    """Production-safe Google Gemini LLM client for review tagging.

    Uses the official google-genai Python SDK, structured JSON output, bounded retries
    with exponential backoff, request delay throttling, and safe logging.
    """

    def __init__(
        self,
        model_name: str = "gemini-3.5-flash-lite",
        api_key: Optional[str] = None,
        prompt_path: Optional[Path] = None,
        version: str = "v2",
        max_retries: int = 3,
        request_timeout: float = 20.0,
        initial_backoff: float = 2.0,
        max_backoff: float = 10.0,
        backoff_multiplier: float = 2.0,
        request_delay: float = 0.0,
        client: Optional[Any] = None,
        load_env: bool = True,
    ):
        self._model_name = model_name
        self.version = version
        self.max_retries = max_retries
        self.request_timeout = request_timeout
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.backoff_multiplier = backoff_multiplier
        self.request_delay = request_delay
        self.load_env = load_env

        # Resolve API key securely without exposing it in repr or logs
        resolved_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not resolved_key and client is None and load_env:
            env_file = Path(".env")
            if env_file.exists():
                try:
                    with open(env_file, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line or line.startswith("#"):
                                continue
                            sep = "=" if "=" in line else (":" if ":" in line else None)
                            if sep:
                                k, v = line.split(sep, 1)
                                if k.strip() == "GEMINI_API_KEY":
                                    resolved_key = v.strip().strip('"').strip("'")
                                    os.environ["GEMINI_API_KEY"] = resolved_key
                                    break
                except Exception:
                    pass

        if not resolved_key and client is None:
            raise ValueError(
                "GEMINI_API_KEY environment variable is not set. "
                "Please configure GEMINI_API_KEY before running with the Gemini provider."
            )

        # Load system instruction prompt
        if prompt_path:
            resolved_prompt_path = Path(prompt_path)
        elif version == "v3_2":
            resolved_prompt_path = DEFAULT_PROMPT_PATH_V3_2
        elif version == "v3_1":
            resolved_prompt_path = DEFAULT_PROMPT_PATH_V3_1
        elif version == "v3":
            resolved_prompt_path = DEFAULT_PROMPT_PATH_V3
        elif version == "v2":
            resolved_prompt_path = DEFAULT_PROMPT_PATH_V2
        else:
            resolved_prompt_path = DEFAULT_PROMPT_PATH_V1
        resolved_prompt_path = Path(resolved_prompt_path)
        if not resolved_prompt_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {resolved_prompt_path}")

        with open(resolved_prompt_path, "r", encoding="utf-8") as f:
            self.system_prompt = f.read()

        # Initialize or inject google.genai Client
        if client is not None:
            self._client = client
        else:
            from google import genai
            from google.genai import types
            http_options = types.HttpOptions(
                timeout=int(request_timeout * 1000),
                retry_options=types.HttpRetryOptions(attempts=1),
            )
            self._client = genai.Client(api_key=resolved_key, http_options=http_options)

        self.call_count = 0
        self.total_retries = 0
        self.total_errors = 0
        self.call_history: List[Dict[str, Any]] = []

    @property
    def model_name(self) -> str:
        return self._model_name

    def __repr__(self) -> str:
        return f"GeminiLLMClient(model='{self._model_name}', version='{self.version}')"

    def _call_model_with_retries(self, user_prompt: str, review_id: str) -> str:
        """Invokes the Gemini generate_content API with bounded retries and exponential backoff."""
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=self.system_prompt,
            response_mime_type="application/json",
            temperature=0.0,
        )

        backoff = self.initial_backoff
        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            t_start = time.time()
            try:
                # Safe logging: log review_id and attempt number only; NEVER log review text or API keys
                logger.info(
                    "Calling Gemini API for review ID '%s' (attempt %d/%d)...",
                    review_id,
                    attempt,
                    self.max_retries,
                )
                response = self._client.models.generate_content(
                    model=self._model_name,
                    contents=user_prompt,
                    config=config,
                )
                duration = time.time() - t_start
                if not response or not getattr(response, "text", None):
                    raise ValueError(f"Empty response received from Gemini model for review ID '{review_id}'")
                logger.info(
                    "Gemini API call succeeded for review ID '%s' (attempt %d/%d, duration: %.2fs)",
                    review_id,
                    attempt,
                    self.max_retries,
                    duration,
                )
                return response.text

            except Exception as e:
                duration = time.time() - t_start
                last_error = e
                error_type = type(e).__name__
                status_code = getattr(e, "code", getattr(e, "status_code", None))
                status_desc = f"{error_type} (HTTP {status_code})" if status_code else error_type

                is_retryable = is_retryable_error(e)
                if not is_retryable or attempt == self.max_retries:
                    self.total_errors += 1
                    logger.error(
                        "Gemini API call failed for review ID '%s' on attempt %d/%d (duration: %.2fs, status/error: %s)",
                        review_id,
                        attempt,
                        self.max_retries,
                        duration,
                        status_desc,
                    )
                    raise e

                self.total_retries += 1
                jitter = random.uniform(0.1, 0.4)
                sleep_duration = min(backoff + jitter, self.max_backoff)
                logger.warning(
                    "Gemini API transient failure for review ID '%s' on attempt %d/%d (duration: %.2fs, status/error: %s). Retrying in %.2fs (wait duration with bounded jitter: +%.2fs)...",
                    review_id,
                    attempt,
                    self.max_retries,
                    duration,
                    status_desc,
                    sleep_duration,
                    jitter,
                )
                time.sleep(sleep_duration)
                backoff = min(backoff * self.backoff_multiplier, self.max_backoff)

        self.total_errors += 1
        raise last_error or RuntimeError(
            f"Failed to call Gemini API for review ID '{review_id}' after {self.max_retries} attempts"
        )

    def _parse_and_validate_response(self, response_text: str, review: Dict[str, Any]) -> Dict[str, Any]:
        """Parses model JSON output, extracts 16 fields, and validates schema compliance."""
        review_id = str(review.get("review_id", "")).strip()
        clean_text = response_text.strip()
        if clean_text.startswith("```"):
            clean_text = re.sub(r"^```(?:json)?\s*", "", clean_text)
            clean_text = re.sub(r"\s*```$", "", clean_text)

        try:
            parsed = json.loads(clean_text)
        except json.JSONDecodeError as jde:
            raise ValueError(f"Malformed JSON returned by Gemini for review ID '{review_id}': {jde}") from jde

        if not isinstance(parsed, dict):
            raise ValueError(f"Expected JSON object from Gemini for review ID '{review_id}', got {type(parsed).__name__}")

        if "tags" in parsed and isinstance(parsed["tags"], dict):
            tags = dict(parsed["tags"])
            tag_evidence = parsed.get("tag_evidence", {})
        else:
            tags = {k: parsed[k] for k in EXACT_16_FIELDS if k in parsed}
            tag_evidence = parsed.get("tag_evidence", {})

        # Ensure source and date match review metadata if missing from model output
        if "source" not in tags or tags["source"] is None:
            tags["source"] = review.get("source")
        if "date" not in tags:
            tags["date"] = review.get("date")

        # Handle string booleans if model returns "true"/"false" instead of true/false
        for bool_field in ("nothing_went_wrong", "recall_gap"):
            val = tags.get(bool_field)
            if isinstance(val, str):
                if val.lower() == "true":
                    tags[bool_field] = True
                elif val.lower() == "false":
                    tags[bool_field] = False
                elif val.lower() in ("null", "none"):
                    tags[bool_field] = None

        # Validate strictly all 16 fields
        schema_errors = validate_16_schema_fields(tags)
        if schema_errors:
            raise ValueError(
                f"Gemini response for review ID '{review_id}' failed schema validation: {'; '.join(schema_errors)}"
            )

        return {
            "tags": tags,
            "tag_evidence": tag_evidence,
        }

    def tag_review(self, review: Dict[str, Any]) -> Dict[str, Any]:
        """Tags a normalized review and returns {tags: ..., tag_evidence: ...}."""
        self.call_count += 1
        review_id = str(review.get("review_id", "")).strip()

        # Apply configurable request delay (rate-pacing)
        if self.request_delay > 0:
            time.sleep(self.request_delay)

        payload = {
            "review_id": review_id,
            "source": review.get("source"),
            "date": review.get("date"),
            "rating": review.get("rating"),
            "title": review.get("title"),
            "text": review.get("text"),
        }
        user_prompt = (
            "Analyze and tag the following customer review according to the 16-field schema "
            "and strict policy rules provided in the system instructions. "
            "Return ONLY a single valid JSON object adhering strictly to the schema.\n\n"
            f"```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```"
        )

        response_text = self._call_model_with_retries(user_prompt, review_id=review_id)
        return self._parse_and_validate_response(response_text, review=review)


def is_retryable_groq_error(exc: Exception) -> bool:
    """Determines whether an exception from the Groq API is transient and retryable."""
    try:
        from groq import (
            RateLimitError,
            InternalServerError,
            APIConnectionError,
            APITimeoutError,
            APIStatusError,
        )
        if isinstance(exc, (RateLimitError, InternalServerError, APIConnectionError, APITimeoutError)):
            return True
        if isinstance(exc, APIStatusError):
            if exc.status_code in RETRYABLE_STATUS_CODES:
                return True
    except (ImportError, AttributeError):
        pass

    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return True

    err_str = str(exc).lower()
    retryable_keywords = [
        "429",
        "rate limit",
        "quota",
        "resource exhausted",
        "resource_exhausted",
        "timed out",
        "timeout",
        "connection reset",
        "service unavailable",
        "503",
        "500",
        "502",
        "504",
    ]
    return any(k in err_str for k in retryable_keywords)


class GroqLLMClient(BaseLLMClient):
    """Production-safe Groq LLM client for review tagging.

    Uses the official groq Python SDK, structured JSON output, bounded retries
    with exponential backoff, rate-limit and Retry-After header respect,
    request delay throttling, and safe logging.
    """

    def __init__(
        self,
        model_name: str = "openai/gpt-oss-120b",
        api_key: Optional[str] = None,
        prompt_path: Optional[Path] = None,
        version: str = "v3_1",
        max_retries: int = 3,
        request_timeout: float = 20.0,
        initial_backoff: float = 3.0,
        max_backoff: float = 35.0,
        backoff_multiplier: float = 2.0,
        request_delay: float = 0.0,
        max_completion_tokens: Optional[int] = 1000,
        client: Optional[Any] = None,
        load_env: bool = True,
    ):
        self._model_name = model_name
        self.version = version
        self.max_retries = max_retries
        self.request_timeout = request_timeout
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.backoff_multiplier = backoff_multiplier
        self.request_delay = request_delay
        self.max_completion_tokens = max_completion_tokens
        self.load_env = load_env

        # Resolve GROQ_API_KEY securely without exposing it in repr or logs
        resolved_key = api_key or os.environ.get("GROQ_API_KEY")
        if not resolved_key and client is None and load_env:
            env_file = Path(".env")
            if env_file.exists():
                try:
                    with open(env_file, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line or line.startswith("#"):
                                continue
                            sep = "=" if "=" in line else (":" if ":" in line else None)
                            if sep:
                                k, v = line.split(sep, 1)
                                if k.strip() == "GROQ_API_KEY":
                                    resolved_key = v.strip().strip('"').strip("'")
                                    os.environ["GROQ_API_KEY"] = resolved_key
                                    break
                except Exception:
                    pass

        if not resolved_key and client is None:
            raise ValueError(
                "GROQ_API_KEY environment variable is not set. "
                "Please configure GROQ_API_KEY before running with the Groq provider."
            )

        # Load system instruction prompt
        if prompt_path:
            resolved_prompt_path = Path(prompt_path)
        elif version == "v3_2":
            resolved_prompt_path = DEFAULT_PROMPT_PATH_V3_2
        elif version == "v3_1":
            resolved_prompt_path = DEFAULT_PROMPT_PATH_V3_1
        elif version == "v3":
            resolved_prompt_path = DEFAULT_PROMPT_PATH_V3
        elif version == "v2":
            resolved_prompt_path = DEFAULT_PROMPT_PATH_V2
        else:
            resolved_prompt_path = DEFAULT_PROMPT_PATH_V1
        resolved_prompt_path = Path(resolved_prompt_path)
        if not resolved_prompt_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {resolved_prompt_path}")

        with open(resolved_prompt_path, "r", encoding="utf-8") as f:
            self.system_prompt = f.read()

        # Initialize or inject groq.Groq client
        if client is not None:
            self._client = client
        else:
            from groq import Groq
            self._client = Groq(
                api_key=resolved_key,
                timeout=request_timeout,
                max_retries=0,
            )

        self.call_count = 0
        self.total_retries = 0
        self.total_errors = 0
        self.call_history: List[Dict[str, Any]] = []

    @property
    def model_name(self) -> str:
        return self._model_name

    def __repr__(self) -> str:
        return f"GroqLLMClient(model='{self._model_name}', version='{self.version}')"

    def _call_model_with_retries(self, user_prompt: str, review_id: str) -> str:
        """Invokes the Groq chat.completions.create API with bounded retries, header respect, and safe logging."""
        backoff = self.initial_backoff
        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            t_start = time.time()
            try:
                # Safe logging: log review_id and attempt number only; NEVER log review text or API keys
                logger.info(
                    "Calling Groq API for review ID '%s' (attempt %d/%d)...",
                    review_id,
                    attempt,
                    self.max_retries,
                )
                create_kwargs: Dict[str, Any] = {
                    "model": self._model_name,
                    "messages": [
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.0,
                }
                if self.max_completion_tokens is not None:
                    create_kwargs["max_completion_tokens"] = self.max_completion_tokens
                response = self._client.chat.completions.create(**create_kwargs)
                duration = time.time() - t_start
                if not response or not getattr(response, "choices", None):
                    raise ValueError(f"Empty response received from Groq model for review ID '{review_id}'")

                choice = response.choices[0]
                message = getattr(choice, "message", None)
                content = getattr(message, "content", None) if message else None
                if not content:
                    raise ValueError(f"Empty content received from Groq model for review ID '{review_id}'")

                req_id = getattr(response, "id", "unknown")
                usage = getattr(response, "usage", None)
                prompt_tokens = getattr(usage, "prompt_tokens", None) if usage else None
                completion_tokens = getattr(usage, "completion_tokens", None) if usage else None
                total_tokens = getattr(usage, "total_tokens", None) if usage else None

                logger.info(
                    "Groq API call succeeded for review ID '%s' (attempt %d/%d, status: 200, latency: %.2fs, request_id: %s, prompt_tokens: %s, completion_tokens: %s, total_tokens: %s)",
                    review_id,
                    attempt,
                    self.max_retries,
                    duration,
                    req_id,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                )
                self.call_history.append({
                    "review_id": review_id,
                    "attempt": attempt,
                    "status_code": 200,
                    "latency": round(duration, 3),
                    "request_id": req_id,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                })
                return content

            except Exception as e:
                duration = time.time() - t_start
                last_error = e
                error_type = type(e).__name__
                status_code = getattr(e, "status_code", None)
                if status_code is None and hasattr(e, "response") and e.response is not None:
                    status_code = getattr(e.response, "status_code", None)
                status_desc = f"{error_type} (HTTP {status_code})" if status_code else error_type

                # Extract request ID from exception or response headers if available
                req_id = getattr(e, "request_id", None)
                if not req_id and hasattr(e, "response") and e.response is not None:
                    headers = getattr(e.response, "headers", {}) or {}
                    req_id = headers.get("x-request-id") or headers.get("request-id")
                req_id = req_id or "unknown"

                self.call_history.append({
                    "review_id": review_id,
                    "attempt": attempt,
                    "status_code": status_code,
                    "latency": round(duration, 3),
                    "request_id": req_id,
                    "error_type": error_type,
                })

                is_retryable = is_retryable_groq_error(e)
                if not is_retryable or attempt == self.max_retries:
                    self.total_errors += 1
                    logger.error(
                        "Groq API call failed for review ID '%s' on attempt %d/%d (status: %s, latency: %.2fs, request_id: %s)",
                        review_id,
                        attempt,
                        self.max_retries,
                        status_desc,
                        duration,
                        req_id,
                    )
                    raise e

                self.total_retries += 1

                # Inspect Retry-After and rate-limit headers
                retry_after_val: Optional[float] = None
                if hasattr(e, "response") and e.response is not None:
                    headers = getattr(e.response, "headers", {}) or {}
                    raw_retry = (
                        headers.get("retry-after")
                        or headers.get("x-ratelimit-reset-requests")
                        or headers.get("x-ratelimit-reset-tokens")
                    )
                    retry_after_val = parse_retry_after(raw_retry)

                jitter = random.uniform(0.1, 0.4)
                if retry_after_val is not None and retry_after_val > 0:
                    base_wait = max(retry_after_val, backoff)
                    effective_max = max(self.max_backoff, retry_after_val + 1.0)
                    sleep_duration = min(base_wait + jitter, effective_max)
                else:
                    sleep_duration = min(backoff + jitter, self.max_backoff)

                logger.warning(
                    "Groq API transient failure for review ID '%s' on attempt %d/%d (status: %s, latency: %.2fs, request_id: %s). Retrying in %.2fs (wait duration with bounded jitter: +%.2fs)...",
                    review_id,
                    attempt,
                    self.max_retries,
                    status_desc,
                    duration,
                    req_id,
                    sleep_duration,
                    jitter,
                )
                time.sleep(sleep_duration)
                backoff = min(backoff * self.backoff_multiplier, self.max_backoff)

        self.total_errors += 1
        raise last_error or RuntimeError(
            f"Failed to call Groq API for review ID '{review_id}' after {self.max_retries} attempts"
        )

    def _parse_and_validate_response(self, response_text: str, review: Dict[str, Any]) -> Dict[str, Any]:
        """Parses model JSON output, extracts 16 fields, and validates schema compliance."""
        review_id = str(review.get("review_id", "")).strip()
        clean_text = response_text.strip()
        if clean_text.startswith("```"):
            clean_text = re.sub(r"^```(?:json)?\s*", "", clean_text)
            clean_text = re.sub(r"\s*```$", "", clean_text)

        try:
            parsed = json.loads(clean_text)
        except json.JSONDecodeError as jde:
            raise ValueError(f"Malformed JSON returned by Groq for review ID '{review_id}': {jde}") from jde

        if not isinstance(parsed, dict):
            raise ValueError(f"Expected JSON object from Groq for review ID '{review_id}', got {type(parsed).__name__}")

        if "tags" in parsed and isinstance(parsed["tags"], dict):
            tags = dict(parsed["tags"])
            tag_evidence = parsed.get("tag_evidence", {})
        else:
            tags = {k: parsed[k] for k in EXACT_16_FIELDS if k in parsed}
            tag_evidence = parsed.get("tag_evidence", {})

        # Ensure source and date match review metadata if missing from model output
        if "source" not in tags or tags["source"] is None:
            tags["source"] = review.get("source")
        if "date" not in tags:
            tags["date"] = review.get("date")

        # Handle string booleans if model returns "true"/"false" instead of true/false
        for bool_field in ("nothing_went_wrong", "recall_gap"):
            val = tags.get(bool_field)
            if isinstance(val, str):
                if val.lower() == "true":
                    tags[bool_field] = True
                elif val.lower() == "false":
                    tags[bool_field] = False
                elif val.lower() in ("null", "none"):
                    tags[bool_field] = None

        # Validate strictly all 16 fields
        schema_errors = validate_16_schema_fields(tags)
        if schema_errors:
            raise ValueError(
                f"Groq response for review ID '{review_id}' failed schema validation: {'; '.join(schema_errors)}"
            )

        return {
            "tags": tags,
            "tag_evidence": tag_evidence,
        }

    def tag_review(self, review: Dict[str, Any]) -> Dict[str, Any]:
        """Tags a normalized review and returns {tags: ..., tag_evidence: ...}."""
        self.call_count += 1
        review_id = str(review.get("review_id", "")).strip()

        # Apply configurable request delay (rate-pacing)
        if self.request_delay > 0:
            time.sleep(self.request_delay)

        payload = {
            "review_id": review_id,
            "source": review.get("source"),
            "date": review.get("date"),
            "rating": review.get("rating"),
            "title": review.get("title"),
            "text": review.get("text"),
        }
        user_prompt = (
            "Analyze and tag the following customer review according to the 16-field schema "
            "and strict policy rules provided in the system instructions. "
            "Return ONLY a single valid JSON object adhering strictly to the schema.\n\n"
            f"```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```"
        )

        response_text = self._call_model_with_retries(user_prompt, review_id=review_id)
        return self._parse_and_validate_response(response_text, review=review)


def tag_single_review(
    normalized_review: Dict[str, Any],
    client: BaseLLMClient,
    prompt_version: Optional[str] = None,
) -> Dict[str, Any]:
    """Tags a normalized review, verifies grounding, checks triggers, and packages metadata."""
    review_id = str(normalized_review.get("review_id", "")).strip()
    text = normalized_review.get("text") or ""
    title = normalized_review.get("title")

    is_low_info = is_low_information_review(text=text, title=title)

    if prompt_version is None:
        client_ver = getattr(client, "version", "v2")
        prompt_version = f"tagger_{client_ver}"

    # Invoke LLM client
    result = client.tag_review(normalized_review)
    tags = result.get("tags", {})
    tag_evidence = result.get("tag_evidence", {})

    # Evaluate human review queue triggers
    requires_review, review_reasons = evaluate_review_queue_triggers(
        normalized_review=normalized_review,
        tags=tags,
        is_low_info=is_low_info,
    )

    metadata = {
        "model": client.model_name,
        "prompt_version": prompt_version,
        "requires_human_review": requires_review,
        "review_reasons": review_reasons,
    }

    # Keep normalized source fields and tagging fields strictly separate
    return {
        "review_id": review_id,
        "normalized_review": normalized_review,
        "tags": tags,
        "tag_evidence": tag_evidence,
        "metadata": metadata,
    }


@dataclass
class PipelineStatistics:
    total_input_records: int = 0
    instahelp_excluded: int = 0
    golden_excluded: int = 0
    eligible_core_reviews: int = 0
    tagged_saved_count: int = 0
    review_queue_count: int = 0
    low_info_count: int = 0
    low_confidence_count: int = 0
    rating_polarity_conflicts: int = 0
    ungrounded_evidence_count: int = 0
    errors_count: int = 0
    retries_count: int = 0


def run_tagging_pipeline(
    input_path: Path = DEFAULT_NORMALIZED_INPUT,
    tagged_output_path: Optional[Path] = None,
    queue_output_path: Optional[Path] = None,
    client: Optional[BaseLLMClient] = None,
    limit: Optional[int] = None,
    version: str = "v2",
    failure_output_path: Optional[Path] = None,
    exclude_file_path: Optional[Path] = None,
    resume: bool = True,
) -> PipelineStatistics:
    """Executes the AI tagging pipeline across normalized customer reviews.

    Excludes InstaHelp records from the core tagging run.
    Routes low-info and ambiguous reviews to the human review queue.
    Saves high-confidence tagged reviews incrementally to tagged_output_path.
    """
    if client is None:
        client = MockLLMClient(version=version)

    client_ver = getattr(client, "version", version)
    if tagged_output_path is None:
        if client_ver == "v3_1":
            tagged_output_path = DEFAULT_TAGGED_OUTPUT_V3_1
        elif client_ver == "v3":
            tagged_output_path = DEFAULT_TAGGED_OUTPUT_V3
        elif client_ver == "v2":
            tagged_output_path = DEFAULT_TAGGED_OUTPUT_V2
        else:
            tagged_output_path = DEFAULT_TAGGED_OUTPUT
    if queue_output_path is None:
        if client_ver == "v3_1":
            queue_output_path = DEFAULT_QUEUE_OUTPUT_V3_1
        elif client_ver == "v3":
            queue_output_path = DEFAULT_QUEUE_OUTPUT_V3
        elif client_ver == "v2":
            queue_output_path = DEFAULT_QUEUE_OUTPUT_V2
        else:
            queue_output_path = DEFAULT_QUEUE_OUTPUT

    if not input_path.exists():
        raise FileNotFoundError(f"Normalized input dataset not found at: {input_path}")

    # Ensure output directories exist
    tagged_output_path.parent.mkdir(parents=True, exist_ok=True)
    queue_output_path.parent.mkdir(parents=True, exist_ok=True)

    # Load excluded review IDs if specified (e.g. golden set)
    excluded_ids: Set[str] = set()
    if exclude_file_path is not None and Path(exclude_file_path).exists():
        with open(exclude_file_path, "r", encoding="utf-8") as ef:
            for eline in ef:
                eline_s = eline.strip()
                if eline_s:
                    erec = json.loads(eline_s)
                    if "review_id" in erec:
                        excluded_ids.add(erec["review_id"])
        logger.info(f"Loaded {len(excluded_ids)} review IDs to exclude from: {exclude_file_path}")

    # Track already-processed reviews for incremental resume
    already_tagged_ids: Set[str] = set()
    already_queue_ids: Set[str] = set()
    if resume:
        if tagged_output_path.exists():
            with open(tagged_output_path, "r", encoding="utf-8") as tf:
                for tline in tf:
                    tline_s = tline.strip()
                    if tline_s:
                        already_tagged_ids.add(json.loads(tline_s).get("review_id"))
        if queue_output_path.exists():
            with open(queue_output_path, "r", encoding="utf-8") as qf:
                for qline in qf:
                    qline_s = qline.strip()
                    if qline_s:
                        already_queue_ids.add(json.loads(qline_s).get("review_id"))
        if already_tagged_ids or already_queue_ids:
            logger.info(
                f"Resuming pipeline: {len(already_tagged_ids)} tagged, "
                f"{len(already_queue_ids)} queued reviews already on disk."
            )

    stats = PipelineStatistics()

    logger.info(f"Starting AI tagging pipeline ({client_ver}) using model '{client.model_name}'...")
    logger.info(f"Reading normalized reviews from: {input_path}")

    # Open output files in append mode if resume is enabled, else overwrite
    file_mode = "a" if resume else "w"
    tagged_f = open(tagged_output_path, file_mode, encoding="utf-8")
    queue_f = open(queue_output_path, file_mode, encoding="utf-8")
    fail_f = open(failure_output_path, file_mode, encoding="utf-8") if failure_output_path else None

    try:
        with open(input_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                line_str = line.strip()
                if not line_str:
                    continue

                stats.total_input_records += 1
                record = json.loads(line_str)
                rid = record.get("review_id")

                # Exclude InstaHelp records from core tagging run (Requirement 8)
                if record.get("is_instahelp", False):
                    stats.instahelp_excluded += 1
                    continue

                # Exclude review IDs in excluded_ids set (e.g. golden set)
                if rid in excluded_ids:
                    stats.golden_excluded += 1
                    continue

                stats.eligible_core_reviews += 1

                # Incremental resume: skip already persisted reviews
                if resume and rid in already_tagged_ids:
                    stats.tagged_saved_count += 1
                    continue
                if resume and rid in already_queue_ids:
                    stats.review_queue_count += 1
                    continue

                if limit is not None and stats.eligible_core_reviews > limit:
                    break

                try:
                    tagged_item = tag_single_review(record, client=client, prompt_version=f"tagger_{client_ver}")
                    metadata = tagged_item.get("metadata", {})
                    reasons = metadata.get("review_reasons", [])

                    if metadata.get("requires_human_review", False):
                        stats.review_queue_count += 1
                        queue_f.write(json.dumps(tagged_item, ensure_ascii=False) + "\n")
                        queue_f.flush()

                        for r in reasons:
                            if "low_information" in r:
                                stats.low_info_count += 1
                            if "low_confidence" in r:
                                stats.low_confidence_count += 1
                            if "rating_polarity_conflict" in r:
                                stats.rating_polarity_conflicts += 1
                            if "ungrounded_evidence" in r:
                                stats.ungrounded_evidence_count += 1
                    else:
                        stats.tagged_saved_count += 1
                        tagged_f.write(json.dumps(tagged_item, ensure_ascii=False) + "\n")
                        tagged_f.flush()
                except Exception as e:
                    stats.errors_count += 1
                    logger.error(
                        "Review ID '%s' failed processing after all retries: %s",
                        rid,
                        type(e).__name__,
                    )
                    if fail_f:
                        fail_rec = {
                            "review_id": rid,
                            "error_type": type(e).__name__,
                            "status_code": getattr(e, "code", getattr(e, "status_code", None)),
                        }
                        fail_f.write(json.dumps(fail_rec, ensure_ascii=False) + "\n")
                        fail_f.flush()
    finally:
        tagged_f.close()
        queue_f.close()
        if fail_f:
            fail_f.close()

    # Record client retries and errors into pipeline stats if available
    stats.retries_count = getattr(client, "total_retries", 0)
    stats.errors_count = max(stats.errors_count, getattr(client, "total_errors", 0))

    logger.info(f"Tagging pipeline complete!")
    logger.info(f"  Total Input:             {stats.total_input_records}")
    logger.info(f"  InstaHelp Excluded:      {stats.instahelp_excluded}")
    logger.info(f"  Eligible Core Reviews:   {stats.eligible_core_reviews}")
    logger.info(f"  Successfully Tagged:     {stats.tagged_saved_count} -> {tagged_output_path}")
    logger.info(f"  Sent to Review Queue:    {stats.review_queue_count} -> {queue_output_path}")
    logger.info(f"  Errors:                  {stats.errors_count}")
    logger.info(f"  Retries:                 {stats.retries_count}")

    return stats


def main() -> None:
    """CLI entrypoint for engine.tagger."""
    parser = argparse.ArgumentParser(description="Urban Company Review AI Tagging Pipeline")
    parser.add_argument(
        "--provider",
        choices=["mock", "gemini", "groq"],
        default="mock",
        help="LLM provider: 'mock' (default), 'gemini', or 'groq'",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model name (defaults: openai/gpt-oss-120b for groq, gemini-3.5-flash-lite for gemini, mock-haiku-5-5 for mock)",
    )
    parser.add_argument(
        "--version",
        choices=["v1", "v2", "v3", "v3_1", "v3_2"],
        default="v2",
        help="Tagger prompt and policy version: 'v1' (baseline), 'v2' (hardened), 'v3' (golden-calibrated), 'v3_1' (taxonomy & future intent calibrated), or 'v3_2' (token-efficiency optimized)",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_NORMALIZED_INPUT,
        help="Path to normalized input reviews JSONL",
    )
    parser.add_argument(
        "--tagged-output",
        type=Path,
        default=None,
        help="Path to output successfully tagged reviews JSONL (defaults by version)",
    )
    parser.add_argument(
        "--queue-output",
        type=Path,
        default=None,
        help="Path to output human review queue JSONL (defaults by version)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit on number of reviews to process",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="Configurable request delay in seconds between review API calls (default: 0.0)",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Maximum attempts per review (default: 3)",
    )
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=20.0,
        help="Request timeout in seconds (default: 20.0)",
    )
    parser.add_argument(
        "--initial-backoff",
        type=float,
        default=2.0,
        help="Initial backoff in seconds (default: 2.0)",
    )
    parser.add_argument(
        "--max-backoff",
        type=float,
        default=10.0,
        help="Maximum backoff in seconds (default: 10.0)",
    )
    parser.add_argument(
        "--backoff-multiplier",
        type=float,
        default=2.0,
        help="Backoff multiplier (default: 2.0)",
    )
    parser.add_argument(
        "--max-completion-tokens",
        type=int,
        default=1000,
        help="Groq-specific maximum completion tokens (default: 1000)",
    )
    parser.add_argument(
        "--metrics-output",
        type=Path,
        default=None,
        help="Optional path to output JSON file containing detailed LLM call metrics",
    )
    parser.add_argument(
        "--failure-output",
        type=Path,
        default=None,
        help="Optional path to output failed reviews JSONL report",
    )
    parser.add_argument(
        "--exclude-file",
        type=Path,
        default=None,
        help="Optional path to JSONL file containing review IDs to exclude (e.g. golden set)",
    )
    parser.add_argument(
        "--no-resume",
        dest="resume",
        action="store_false",
        default=True,
        help="Overwrite existing output files instead of resuming",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        default=False,
        help="Legacy flag: use deterministic mock LLM client (equivalent to --provider mock)",
    )

    args = parser.parse_args()

    provider = args.provider
    if args.mock:
        provider = "mock"

    if provider == "gemini":
        model_name = args.model or "gemini-3.5-flash-lite"
        client = GeminiLLMClient(
            model_name=model_name,
            version=args.version,
            max_retries=args.max_retries,
            request_timeout=args.request_timeout,
            initial_backoff=args.initial_backoff,
            max_backoff=args.max_backoff,
            backoff_multiplier=args.backoff_multiplier,
            request_delay=args.delay,
        )
    elif provider == "groq":
        model_name = args.model or "openai/gpt-oss-120b"
        client = GroqLLMClient(
            model_name=model_name,
            version=args.version,
            max_retries=args.max_retries,
            request_timeout=args.request_timeout,
            initial_backoff=args.initial_backoff,
            max_backoff=args.max_backoff,
            backoff_multiplier=args.backoff_multiplier,
            request_delay=args.delay,
            max_completion_tokens=args.max_completion_tokens,
        )
    elif provider == "mock":
        model_name = args.model or "mock-haiku-5-5"
        client = MockLLMClient(
            model_name=model_name,
            version=args.version,
        )
    else:
        raise ValueError(f"Unsupported provider: {provider}")

    if args.version == "v3_2":
        default_tagged = DEFAULT_TAGGED_OUTPUT_V3_2
        default_queue = DEFAULT_QUEUE_OUTPUT_V3_2
    elif args.version == "v3_1":
        default_tagged = DEFAULT_TAGGED_OUTPUT_V3_1
        default_queue = DEFAULT_QUEUE_OUTPUT_V3_1
    elif args.version == "v3":
        default_tagged = DEFAULT_TAGGED_OUTPUT_V3
        default_queue = DEFAULT_QUEUE_OUTPUT_V3
    elif args.version == "v2":
        default_tagged = DEFAULT_TAGGED_OUTPUT_V2
        default_queue = DEFAULT_QUEUE_OUTPUT_V2
    else:
        default_tagged = DEFAULT_TAGGED_OUTPUT
        default_queue = DEFAULT_QUEUE_OUTPUT

    tagged_out = args.tagged_output or default_tagged
    queue_out = args.queue_output or default_queue

    stats = run_tagging_pipeline(
        input_path=args.input,
        tagged_output_path=tagged_out,
        queue_output_path=queue_out,
        client=client,
        limit=args.limit,
        version=args.version,
        failure_output_path=args.failure_output,
        exclude_file_path=args.exclude_file,
        resume=args.resume,
    )

    print("\n=== AI Tagging Pipeline Summary ===")
    print(f"Provider:                      {provider}")
    print(f"Model:                         {client.model_name}")
    print(f"Version:                       {args.version}")
    print(f"Total Normalized Reviews Read: {stats.total_input_records}")
    print(f"InstaHelp Excluded:            {stats.instahelp_excluded}")
    print(f"Eligible Core Reviews:         {stats.eligible_core_reviews}")
    print(f"Successfully Tagged:           {stats.tagged_saved_count}")
    print(f"Sent to Review Queue:          {stats.review_queue_count}")
    print(f"  - Low Information:           {stats.low_info_count}")
    print(f"  - Low Confidence:            {stats.low_confidence_count}")
    print(f"  - Rating/Polarity Conflict:  {stats.rating_polarity_conflicts}")
    print(f"  - Ungrounded Evidence:       {stats.ungrounded_evidence_count}")
    print(f"Errors:                        {stats.errors_count}")
    print(f"Retries:                       {stats.retries_count}")
    print(f"Tagged Output File:            {tagged_out}")
    print(f"Review Queue File:             {queue_out}")
    if args.failure_output:
        print(f"Failure Report File:           {args.failure_output}")
    if args.metrics_output and hasattr(client, "call_history"):
        args.metrics_output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.metrics_output, "w", encoding="utf-8") as mf:
            json.dump(client.call_history, mf, indent=2)
        print(f"Call Metrics File:             {args.metrics_output}")


if __name__ == "__main__":
    main()
