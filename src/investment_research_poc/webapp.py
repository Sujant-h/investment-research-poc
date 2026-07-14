from __future__ import annotations

import argparse
import errno as _errno
import json
import mimetypes
import re
from dataclasses import asdict, dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .ingest import SUPPORTED_EXTENSIONS
from .models import ResearchBrief
from .pipeline import ResearchAssistant


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080
DEFAULT_OUTPUT_DIR = Path("output") / "web_run"
STATIC_DIR = Path(__file__).with_name("web")
AVAILABLE_NEWS_PROVIDERS = ("marketaux", "alpha_vantage")
SYMBOL_SELECTION_MODES = (
    {
        "value": "query",
        "label": "Aus Analysefrage ableiten",
        "description": "Ticker werden für jede Analyse neu aus der aktuellen Frage erkannt.",
    },
    {
        "value": "manual",
        "label": "Symbole manuell auswählen",
        "description": "Die manuelle Auswahl überschreibt die automatische Erkennung.",
    },
)
SUGGESTED_QUERIES = (
    {
        "label": "Halbleiter, 5 Jahre",
        "query": "Bewerte 2 Millionen US-Dollar in Intel, Nvidia oder Qualcomm für die nächsten 5 Jahre.",
        "symbols": ["INTC", "NVDA", "QCOM"],
    },
    {
        "label": "SAP als Übernahmeziel",
        "query": "Prüfe, ob SAP ein attraktives strategisches Übernahmeziel im Bereich Enterprise-AI-Software ist.",
        "symbols": ["SAP"],
    },
)
SYMBOL_OPTIONS = (
    {"value": "AAPL", "label": "Apple (AAPL)"},
    {"value": "AMZN", "label": "Amazon (AMZN)"},
    {"value": "CRM", "label": "Salesforce (CRM)"},
    {"value": "GOOGL", "label": "Alphabet (GOOGL)"},
    {"value": "INTC", "label": "Intel (INTC)"},
    {"value": "META", "label": "Meta (META)"},
    {"value": "MSFT", "label": "Microsoft (MSFT)"},
    {"value": "NOW", "label": "ServiceNow (NOW)"},
    {"value": "NVDA", "label": "Nvidia (NVDA)"},
    {"value": "QCOM", "label": "Qualcomm (QCOM)"},
    {"value": "SAP", "label": "SAP (SAP)"},
    {"value": "SIEGY", "label": "Siemens (SIEGY)"},
    {"value": "TSLA", "label": "Tesla (TSLA)"},
)
SYMBOL_TOKEN_PATTERN = re.compile(r"\$?([A-Z]{1,5})\b")
SYMBOL_STOPWORDS = {
    "A",
    "AI",
    "AG",
    "CO",
    "CORP",
    "FY",
    "INC",
    "LLC",
    "LTD",
    "MA",
    "Q1",
    "Q2",
    "Q3",
    "Q4",
    "SA",
    "SE",
    "THE",
}
COMPANY_SYMBOL_ALIASES = {
    "alphabet": "GOOGL",
    "amazon": "AMZN",
    "apple": "AAPL",
    "meta": "META",
    "microsoft": "MSFT",
    "nvidia": "NVDA",
    "openai": "MSFT",
    "sap": "SAP",
    "salesforce": "CRM",
    "service now": "NOW",
    "servicenow": "NOW",
    "siemens": "SIEGY",
    "tesla": "TSLA",
}

NO_EVIDENCE_ERROR = "No relevant evidence found for the provided query."


@dataclass(slots=True)
class AppContext:
    assistant: ResearchAssistant
    base_dir: Path

    @property
    def default_output_dir(self) -> Path:
        return self.base_dir / DEFAULT_OUTPUT_DIR


def serialize_brief(brief: ResearchBrief) -> dict[str, object]:
    payload = asdict(brief)
    for item in payload["evidence"]:
        source_path = item.get("source_path")
        if source_path is not None:
            item["source_path"] = str(source_path)
    return payload


def build_app_context(base_dir: Path | None = None) -> AppContext:
    default_base_dir = Path(__file__).resolve().parents[2]
    if base_dir is None:
        candidate_base_dir = default_base_dir
    else:
        candidate_base_dir = Path(str(base_dir).strip().rstrip('"'))
    resolved_base_dir = candidate_base_dir.resolve()
    return AppContext(assistant=ResearchAssistant(), base_dir=resolved_base_dir)


def parse_symbols(raw_value: str | None) -> list[str] | None:
    if not raw_value:
        return None
    values = [item.strip().upper() for item in raw_value.split(",")]
    filtered = [item for item in values if item]
    return filtered or None


def normalize_provider_name(raw_value: str | None, *, default_provider: str) -> str:
    provider_name = str(raw_value or "").strip() or default_provider
    if provider_name not in AVAILABLE_NEWS_PROVIDERS:
        raise ValueError("Bitte wähle einen gültigen News-Provider aus.")
    return provider_name


def normalize_symbol_mode(raw_value: str | None) -> str:
    symbol_mode = str(raw_value or "").strip() or "query"
    valid_modes = {item["value"] for item in SYMBOL_SELECTION_MODES}
    if symbol_mode not in valid_modes:
        raise ValueError("Bitte wähle eine gültige Symbol-Einstellung aus.")
    return symbol_mode


def _alias_matches_query(alias: str, query_lower: str) -> bool:
    """Prüft ob ein Firmenalias in der Anfrage vorkommt.

    Exakter Substring-Match zuerst; für mehrwörtige Aliase zusätzlich
    präfix-tolerantes Wort-Matching (bis zu 1 fehlenden Buchstaben am Ende),
    damit Tippfehler wie "servic now" → ServiceNow erkannt werden.
    """
    if alias in query_lower:
        return True

    alias_words = alias.split()
    if len(alias_words) < 2:
        return False

    query_words = re.findall(r"\b\w+\b", query_lower)
    for alias_word in alias_words:
        if len(alias_word) <= 3:
            # Kurze Wörter müssen exakt matchen
            if alias_word not in query_words:
                return False
        else:
            # Präfix-Toleranz: mind. die ersten (len-1) Zeichen müssen übereinstimmen
            prefix = alias_word[: len(alias_word) - 1]
            if not any(qw.startswith(prefix) for qw in query_words):
                return False
    return True


def infer_symbols_from_query(query: str) -> list[str]:
    inferred: list[str] = []
    seen: set[str] = set()
    lowered_query = query.lower()

    for company_name, symbol in sorted(COMPANY_SYMBOL_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if symbol not in seen and _alias_matches_query(company_name, lowered_query):
            inferred.append(symbol)
            seen.add(symbol)

    for match in SYMBOL_TOKEN_PATTERN.findall(query):
        symbol = match.upper()
        if symbol in SYMBOL_STOPWORDS or symbol in seen:
            continue
        inferred.append(symbol)
        seen.add(symbol)

    return inferred


def resolve_symbols(
    *, query: str, raw_symbols: str | None, symbol_mode: str
) -> tuple[list[str], str, str | None]:
    """Gibt (symbols, source, keywords) zurück.

    keywords ist nur gesetzt wenn keine Ticker gefunden wurden und
    eine Keyword-Suche als Fallback verwendet wird.
    """
    manual_symbols = parse_symbols(raw_symbols)
    if symbol_mode == "manual":
        if manual_symbols:
            return manual_symbols, "manual", None
        raise ValueError(
            "Bitte wähle mindestens ein Symbol aus oder wechsle zur automatischen Ableitung aus der Analysefrage."
        )

    inferred_symbols = infer_symbols_from_query(query)
    if inferred_symbols:
        return inferred_symbols, "inferred", None

    # Kein Ticker erkannt → Keyword-Fallback: erste 6 Wörter der Frage als Suchbegriff
    keywords = " ".join(query.split()[:6])
    return [], "keyword", keywords


def localize_error_message(message: str) -> str:
    if message == NO_EVIDENCE_ERROR:
        return (
            "Keine relevanten Nachrichten für diese Anfrage gefunden. "
            "Bitte prüfe die Nachrichtenquelle, wechsle die Symbol-Einstellung oder formuliere die Analysefrage präziser."
        )
    return message


def build_defaults_payload(context: AppContext) -> dict[str, object]:
    return {
        "default_output_path": str(context.default_output_dir),
        "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
        "default_provider": context.assistant.config.news_provider,
        "default_model": context.assistant.config.openai_model,
        "default_symbol_mode": "query",
        "providers": list(AVAILABLE_NEWS_PROVIDERS),
        "symbol_modes": list(SYMBOL_SELECTION_MODES),
        "symbol_options": list(SYMBOL_OPTIONS),
        "suggested_queries": list(SUGGESTED_QUERIES),
    }


def create_handler(context: AppContext) -> type[BaseHTTPRequestHandler]:
    class ResearchRequestHandler(BaseHTTPRequestHandler):
        server_version = "InvestmentResearchWeb/0.1"

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/defaults":
                self._send_json(HTTPStatus.OK, build_defaults_payload(context))
                return
            if parsed.path == "/api/health":
                self._send_json(HTTPStatus.OK, {"status": "ok"})
                return
            self._serve_static(parsed.path)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path != "/api/research":
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Endpoint not found."})
                return

            try:
                payload = self._read_json_body()
                query = str(payload.get("query", "")).strip()
                if not query:
                    raise ValueError("Eine Analysefrage ist erforderlich.")

                output_path = context.default_output_dir.resolve()
                provider_name = normalize_provider_name(
                    payload.get("provider_name"),
                    default_provider=context.assistant.config.news_provider,
                )
                symbol_mode = normalize_symbol_mode(payload.get("symbol_mode"))
                symbols, symbol_source, keywords = resolve_symbols(
                    query=query,
                    raw_symbols=str(payload.get("symbols", "")).strip() or None,
                    symbol_mode=symbol_mode,
                )

                brief = context.assistant.run(
                    query=query,
                    output_dir=output_path,
                    input_path=None,
                    symbols=symbols,
                    keywords=keywords,
                    include_live_news=True,
                    provider_name=provider_name,
                    use_openai=True,
                    base_dir=context.base_dir,
                )
            except FileNotFoundError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            except ValueError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": localize_error_message(str(exc))})
                return
            except json.JSONDecodeError:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Malformed JSON payload."})
                return
            except Exception as exc:  # pragma: no cover - defensive branch
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
                return

            self._send_json(
                HTTPStatus.OK,
                {
                    "brief": serialize_brief(brief),
                    "input_source": "Nachrichtenquellen-API",
                    "provider_name": provider_name,
                    "resolved_symbols": symbols if symbols else ([f'Stichwort: "{keywords}"'] if keywords else []),
                    "requested_symbol_mode": symbol_mode,
                    "symbol_source": symbol_source,
                    "keywords": keywords,
                    "output_path": str(output_path.resolve()),
                    "markdown_path": str((output_path / "research_brief.md").resolve()),
                    "json_path": str((output_path / "research_brief.json").resolve()),
                },
            )

        def log_message(self, format: str, *args: object) -> None:
            return

        def _read_json_body(self) -> dict[str, object]:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length <= 0:
                return {}
            raw_body = self.rfile.read(content_length)
            return json.loads(raw_body.decode("utf-8"))

        def _serve_static(self, raw_path: str) -> None:
            target = raw_path.lstrip("/") or "index.html"
            file_path = (STATIC_DIR / target).resolve()
            if not str(file_path).startswith(str(STATIC_DIR.resolve())):
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Asset not found."})
                return
            if file_path.is_dir():
                file_path = file_path / "index.html"
            if not file_path.exists():
                if target == "favicon.ico":
                    file_path = STATIC_DIR / "favicon.svg"
                elif target == "index.html" or "." not in target:
                    file_path = STATIC_DIR / "index.html"
                else:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "Asset not found."})
                    return

            mime_type, _ = mimetypes.guess_type(file_path.name)
            content_type = mime_type or "application/octet-stream"
            body = file_path.read_bytes()
            try:
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except OSError as exc:
                if exc.errno not in (_errno.EBADF, _errno.ECONNRESET, _errno.EPIPE):
                    raise

        def _send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
            body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except OSError as exc:
                if exc.errno not in (_errno.EBADF, _errno.ECONNRESET, _errno.EPIPE):
                    raise

    return ResearchRequestHandler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the local investment research web app.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host interface to bind to.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to listen on.")
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path.cwd(),
        help="Project root used for default output directory and .env resolution.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    context = build_app_context(args.base_dir)
    handler = create_handler(context)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Investment Research web app available at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
