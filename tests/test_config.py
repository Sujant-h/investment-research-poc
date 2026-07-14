from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path

from investment_research_poc.config import PipelineConfig


class PipelineConfigTest(unittest.TestCase):
    def test_resolve_env_file_finds_parent_env_file(self) -> None:
        test_root = Path(__file__).resolve().parent / "_artifacts" / str(uuid.uuid4())
        nested_dir = test_root / "nested" / "child"
        env_path = test_root / ".env"
        try:
            nested_dir.mkdir(parents=True)
            env_path.write_text("MARKETAUX_API_TOKEN=test-token\n", encoding="utf-8")

            resolved = PipelineConfig().resolve_env_file(nested_dir)

            self.assertEqual(resolved, env_path)
        finally:
            shutil.rmtree(test_root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
