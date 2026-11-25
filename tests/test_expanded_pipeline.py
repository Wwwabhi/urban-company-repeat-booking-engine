"""Unit tests for expanded Level 1 collectors, normalizer_v2, and analyze_evidence."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from engine.analyze_evidence import run_analysis
from engine.collectors.investor_relations import (
    classify_ir_source,
    extract_relevant_paragraphs_from_pdf_bytes,
    infer_document_title_and_date,
)
from engine.normalizer_v2 import run_normalization_v2


class TestInvestorRelationsCollector(unittest.TestCase):
    def test_classify_ir_source(self):
        self.assertEqual(
            classify_ir_source("https://example.com/Urban_Company_Shareholders_Letter_Q2_FY27.pdf"),
            "Shareholder Letter",
        )
        self.assertEqual(
            classify_ir_source("https://example.com/Q2%20FY27%20Earnings%20Conference%20Call%20Transcript.pdf"),
            "Earnings Call",
        )
        self.assertEqual(
            classify_ir_source("https://example.com/Urban_Company_Q2_FY27_results_Press_release.pdf"),
            "Press Release",
        )

    def test_infer_title_and_date(self):
        title, date = infer_document_title_and_date(
            "https://example.com/Urban_Company_Shareholders%27_Letter_and_Results_Q3_FY26.pdf"
        )
        self.assertIn("Shareholders' Letter", title)
        self.assertEqual(date, "2026-01-31")

    @patch("engine.collectors.investor_relations.PdfReader")
    def test_extract_relevant_paragraphs_filters_and_redacts(self, mock_reader_cls):
        mock_page = MagicMock()
        mock_page.extract_text.return_value = (
            "Short header\n\n"
            "Customer retention and repeat booking frequency improved across core categories including AC and salon. "
            "Contact investor@urbancompany.com for details.\n\n"
            "Unrelated legal boilerplate text that mentions nothing about services or customers at all."
        )
        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]
        mock_reader_cls.return_value = mock_reader

        records = extract_relevant_paragraphs_from_pdf_bytes(
            b"%PDF-1.4 mock",
            source_url="https://example.com/Urban_Company_Shareholders_Letter_Q2_FY27.pdf",
        )
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertTrue(rec["id"].startswith("ir_"))
        self.assertEqual(rec["source"], "Shareholder Letter")
        self.assertEqual(rec["date"], "2026-10-31")
        self.assertIn("[EMAIL_REDACTED]", rec["text"])
        self.assertIn("collected_at", rec)


class TestNormalizerV2AndAnalysis(unittest.TestCase):
    def test_normalizer_v2_deduplicates_and_flags_instahelp(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            gp1 = tmp_path / "gp1.jsonl"
            gp2 = tmp_path / "gp2.jsonl"
            ir = tmp_path / "ir.jsonl"
            out = tmp_path / "norm.jsonl"
            rep = tmp_path / "rep.json"

            gp1.write_text(
                json.dumps({"id": "r1", "source": "Play Store", "date": "2026-11-22", "score": 5, "text": "Great AC service by technician!"}) + "\n",
                encoding="utf-8",
            )
            # r1 duplicate ID, r2 duplicate text, r3 unique InstaHelp
            gp2.write_text(
                "\n".join([
                    json.dumps({"id": "r1", "source": "Play Store", "date": "2026-11-22", "score": 5, "text": "Great AC service by technician!"}),
                    json.dumps({"id": "r2", "source": "Play Store", "date": "2026-11-22", "score": 5, "text": "Great AC service by technician!"}),
                    json.dumps({"id": "r3", "source": "Play Store", "date": "2026-11-23", "score": 1, "text": "InstaHelp maid cancelled my booking last minute."}),
                ]) + "\n",
                encoding="utf-8",
            )
            ir.write_text(
                json.dumps({"id": "ir_1", "source": "Shareholder Letter", "date": "2026-10-31", "text": "Repeat usage in core categories remained strong in Q2 FY27."}) + "\n",
                encoding="utf-8",
            )

            report = run_normalization_v2(
                sources=[("Play Store", gp1), ("Play Store", gp2), ("Investor Relations", ir)],
                output_path=out,
                report_path=rep,
            )
            self.assertEqual(report["total_raw_read"], 5)
            self.assertEqual(report["total_normalized_kept"], 3)
            self.assertEqual(report["removed_counts"]["duplicate_id"], 1)
            self.assertEqual(report["removed_counts"]["duplicate_text"], 1)
            self.assertEqual(report["instahelp_flagged"], 1)
            self.assertEqual(report["core_eligible"], 2)

            summary_out = tmp_path / "summary.json"
            summary = run_analysis(
                normalized_v2_path=out,
                tagged_v1_path=tmp_path / "missing1.jsonl",
                queue_v1_path=tmp_path / "missing2.jsonl",
                golden_path=tmp_path / "missing3.jsonl",
                ir_path=ir,
                output_path=summary_out,
            )
            self.assertEqual(summary["normalized_v2_totals"]["total_records"], 3)
            self.assertEqual(summary["normalized_v2_totals"]["consumer_core_excl_instahelp"], 1)
            self.assertEqual(summary["directional_category_counts_consumer_core"]["AC"], 1)


if __name__ == "__main__":
    unittest.main()
