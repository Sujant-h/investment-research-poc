from __future__ import annotations

import json
import unittest

from investment_research_poc.openai_analysis import extract_response_text


class OpenAIResponseParsingTest(unittest.TestCase):
    def test_extract_response_text_reads_output_text_block(self) -> None:
        response = {
            "output": [
                {
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps({"executive_summary": "ok"}),
                        }
                    ]
                }
            ]
        }

        self.assertEqual(extract_response_text(response), '{"executive_summary": "ok"}')


if __name__ == "__main__":
    unittest.main()
