from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class PipelineConfig:
    chunk_size_words: int = 120
    chunk_overlap_words: int = 25
    top_k_chunks: int = 6
    max_summary_sentences: int = 4
    request_timeout_seconds: int = 30
    max_retries: int = 3
    openai_model: str = "gpt-5.4"
    openai_reasoning_effort: str = "medium"
    openai_max_output_tokens: int = 1800
    news_provider: str = "marketaux"
    news_language: str = "en"
    live_news_limit: int = 10
    lookback_days: int = 7
    env_file_name: str = ".env"

    def resolve_env_file(self, base_dir: Path | None = None) -> Path:
        candidate_roots: list[Path] = []

        if base_dir is not None:
            resolved_base_dir = base_dir.resolve()
            candidate_roots.extend([resolved_base_dir, *resolved_base_dir.parents])

        cwd = Path.cwd().resolve()
        candidate_roots.extend([cwd, *cwd.parents])

        project_root = Path(__file__).resolve().parents[2]
        candidate_roots.extend([project_root, *project_root.parents])

        seen: set[Path] = set()
        for root in candidate_roots:
            if root in seen:
                continue
            seen.add(root)
            candidate = root / self.env_file_name
            if candidate.exists():
                return candidate

        fallback_root = base_dir.resolve() if base_dir is not None else cwd
        return fallback_root / self.env_file_name
