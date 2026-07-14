from __future__ import annotations

import argparse
from pathlib import Path

from .pipeline import ResearchAssistant


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate an automated research brief from financial documents."
    )
    parser.add_argument("--input", help="Directory or file containing source documents.")
    parser.add_argument("--query", required=True, help="Research query or investment thesis.")
    parser.add_argument("--output", required=True, help="Directory for generated output artifacts.")
    parser.add_argument("--symbols", help="Comma-separated ticker symbols for live news ingestion.")
    parser.add_argument(
        "--provider",
        choices=["marketaux", "alpha_vantage"],
        default="marketaux",
        help="Financial news provider for live ingestion.",
    )
    parser.add_argument(
        "--live-news",
        action="store_true",
        help="Fetch current financial news from the configured provider.",
    )
    parser.add_argument(
        "--disable-openai",
        action="store_true",
        help="Use the local fallback analyzer instead of the OpenAI Responses API.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    assistant = ResearchAssistant()
    brief = assistant.run(
        query=args.query,
        output_dir=Path(args.output),
        input_path=Path(args.input) if args.input else None,
        symbols=[item.strip() for item in args.symbols.split(",")] if args.symbols else None,
        include_live_news=args.live_news,
        provider_name=args.provider,
        use_openai=not args.disable_openai,
    )

    print("Research brief created successfully.")
    print(f"Sentiment: {brief.sentiment.label} ({brief.sentiment.score})")
    print(f"Analysis mode: {brief.analysis_mode}")
    print(f"Opportunities: {len(brief.opportunities)} | Risks: {len(brief.risks)}")


if __name__ == "__main__":
    main()
