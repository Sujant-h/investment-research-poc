from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path

from investment_research_poc.pipeline import ResearchAssistant


class ResearchAssistantTest(unittest.TestCase):
    def test_end_to_end_brief_contains_core_sections(self) -> None:
        test_root = Path(__file__).resolve().parent / "_artifacts" / str(uuid.uuid4())
        source_dir = test_root / "input"
        output_dir = test_root / "output"
        try:
            source_dir.mkdir(parents=True)

            (source_dir / "annual_report.txt").write_text(
                "\n".join(
                    [
                        "Example Corp Annual Report",
                        "Example Corp achieved strong growth and improved margins in 2025.",
                        "Management highlighted robust recurring revenues and attractive pipeline visibility.",
                        "Net debt increased because of acquisition integration costs.",
                    ]
                ),
                encoding="utf-8",
            )

            (source_dir / "news.txt").write_text(
                "\n".join(
                    [
                        "Market Update",
                        "Analysts consider Example Corp an attractive mid-cap target.",
                        "They also warn that integration risk and leverage should be monitored carefully.",
                    ]
                ),
                encoding="utf-8",
            )

            assistant = ResearchAssistant()
            brief = assistant.run(
                query="Assess Example Corp as an acquisition target",
                output_dir=output_dir,
                input_path=source_dir,
                use_openai=False,
            )

            self.assertTrue(brief.executive_summary)
            self.assertIn(brief.sentiment.label, {"positive", "neutral", "negative"})
            self.assertGreaterEqual(len(brief.evidence), 1)
            self.assertTrue((output_dir / "research_brief.md").exists())
            self.assertTrue((output_dir / "research_brief.json").exists())
            self.assertEqual(brief.analysis_mode, "rule_based_fallback")
        finally:
            shutil.rmtree(test_root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
