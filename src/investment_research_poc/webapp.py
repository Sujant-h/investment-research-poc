from __future__ import annotations

import argparse
import errno as _errno
import ipaddress
import json
import logging
import mimetypes
import os
import re
import threading
import time
import traceback
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .http_client import JsonHttpClient
from .ingest import SUPPORTED_EXTENSIONS
from .models import ResearchBrief
from .pipeline import ResearchAssistant
from .runtime import load_env_file
from .symbol_extraction import LLMSymbolExtractor


LOGGER = logging.getLogger("investment_research_poc.web")

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080
DEFAULT_OUTPUT_DIR = Path("output") / "web_run"
STATIC_DIR = Path(__file__).with_name("web")

# Die Analyse-Payload ist winzig (Frage + optionale Symbole). Ein hartes Limit
# schuetzt vor Speicher-Erschoepfung durch ein grosses Content-Length.
MAX_REQUEST_BODY_BYTES = 64 * 1024
# Idle-/Slow-Client-Timeout pro Verbindung (Schutz vor Slowloris-artigen Verbindungen).
REQUEST_TIMEOUT_SECONDS = 30
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

KEYWORD_TOKEN_PATTERN = re.compile(r"\b\w+\b")
# Fuellwoerter, Waehrungs- und Zeitangaben, die als News-Suchbegriff keinen
# Mehrwert bringen. Firmennamen und Sachbegriffe bleiben bewusst erhalten.
KEYWORD_STOPWORDS = {
    "als",
    "auf",
    "aus",
    "bewerte",
    "bewerten",
    "dem",
    "den",
    "der",
    "des",
    "die",
    "das",
    "dollar",
    "ein",
    "eine",
    "einen",
    "einer",
    "eur",
    "euro",
    "fuer",
    "für",
    "im",
    "in",
    "investiere",
    "investieren",
    "ist",
    "jahr",
    "jahre",
    "jahren",
    "milliarde",
    "milliarden",
    "million",
    "millionen",
    "mit",
    "monat",
    "monate",
    "monaten",
    "nächste",
    "nächsten",
    "nächster",
    "nächstes",
    "ob",
    "oder",
    "prüfe",
    "prüfen",
    "soll",
    "sollte",
    "tausend",
    "und",
    "us",
    "usd",
    "von",
    "zu",
    "zum",
    "zur",
}

NO_EVIDENCE_ERROR = "No relevant evidence found for the provided query."

# Kostenschutz fuer den oeffentlichen Demo-Betrieb: jeder /api/research-Aufruf
# loest bezahlte OpenAI- und News-API-Anfragen aus. Die Werte lassen sich per
# Umgebungsvariable ueberschreiben; <= 0 deaktiviert die jeweilige Grenze.
RATE_LIMIT_TOO_MANY_IP = (
    "Zu viele Anfragen von dieser Adresse. Bitte warte einen Moment und versuche es erneut."
)
RATE_LIMIT_DAILY_EXHAUSTED = (
    "Das tägliche Demo-Kontingent ist aufgebraucht. Diese öffentliche Demo ist bewusst begrenzt – "
    "bitte versuche es morgen erneut."
)
# Generische Meldung fuer unerwartete Serverfehler: interne/Upstream-Fehlertexte
# werden nur serverseitig geloggt, nie an den Client zurueckgegeben.
INTERNAL_ERROR_MESSAGE = (
    "Es ist ein interner Fehler aufgetreten. Bitte versuche es später erneut."
)
PAYLOAD_TOO_LARGE_MESSAGE = "Die Anfrage ist zu groß."


class PayloadTooLarge(Exception):
    """Wird ausgeloest, wenn der Request-Body das erlaubte Limit ueberschreitet."""


def _int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        return int(raw_value.strip())
    except ValueError:
        return default


@dataclass(slots=True)
class RateLimitConfig:
    """Grenzwerte fuer den oeffentlichen Demo-Endpunkt."""

    per_ip_limit: int = 8
    per_ip_window_seconds: int = 3600
    global_daily_limit: int = 150

    @classmethod
    def from_env(cls) -> "RateLimitConfig":
        # Literale Defaults, weil slots=True keinen Zugriff auf Klassen-Defaults
        # (cls.per_ip_limit liefert einen Slot-Deskriptor) erlaubt.
        return cls(
            per_ip_limit=_int_env("RATE_LIMIT_PER_IP", 8),
            per_ip_window_seconds=_int_env("RATE_LIMIT_WINDOW_SECONDS", 3600),
            global_daily_limit=_int_env("RATE_LIMIT_GLOBAL_PER_DAY", 150),
        )


class RateLimiter:
    """Thread-sicheres In-Memory-Rate-Limiting.

    Kombiniert ein gleitendes Fenster pro IP mit einer globalen Tagesobergrenze,
    damit ein einzelner Besucher – und alle Besucher zusammen – kein unbegrenztes
    Budget an bezahlten API-Aufrufen verbrauchen koennen.
    """

    def __init__(self, config: RateLimitConfig) -> None:
        self.config = config
        self._lock = threading.Lock()
        self._ip_hits: dict[str, deque[float]] = defaultdict(deque)
        self._day_key: str | None = None
        self._day_count = 0

    def check(self, client_ip: str, *, now: float | None = None) -> tuple[bool, str | None]:
        current = time.time() if now is None else now
        with self._lock:
            if self.config.global_daily_limit > 0:
                today = time.strftime("%Y-%m-%d", time.gmtime(current))
                if today != self._day_key:
                    self._day_key = today
                    self._day_count = 0
                if self._day_count >= self.config.global_daily_limit:
                    return False, RATE_LIMIT_DAILY_EXHAUSTED

            if self.config.per_ip_limit > 0:
                hits = self._ip_hits[client_ip]
                cutoff = current - self.config.per_ip_window_seconds
                while hits and hits[0] < cutoff:
                    hits.popleft()
                if len(hits) >= self.config.per_ip_limit:
                    if not hits:
                        self._ip_hits.pop(client_ip, None)
                    return False, RATE_LIMIT_TOO_MANY_IP
                hits.append(current)
                self._prune_locked(cutoff)

            if self.config.global_daily_limit > 0:
                self._day_count += 1
            return True, None

    def _prune_locked(self, cutoff: float) -> None:
        # Verhindert unbegrenztes Wachstum, wenn viele verschiedene IPs anfragen.
        if len(self._ip_hits) <= 4096:
            return
        stale = [ip for ip, hits in self._ip_hits.items() if not hits or hits[-1] < cutoff]
        for ip in stale:
            self._ip_hits.pop(ip, None)


@dataclass(slots=True)
class AppContext:
    assistant: ResearchAssistant
    base_dir: Path
    # Optionaler Override, damit Tests den LLM-Extractor offline halten koennen.
    # None bedeutet: den echten build_symbol_extractor verwenden.
    extractor_factory: Callable[["AppContext"], "LLMSymbolExtractor | None"] | None = field(default=None)
    # Kostenschutz fuer den oeffentlichen Betrieb. None => Konfiguration aus den
    # Umgebungsvariablen ableiten (siehe RateLimitConfig.from_env).
    rate_limiter: "RateLimiter | None" = field(default=None)

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


def build_symbol_extractor(context: AppContext) -> LLMSymbolExtractor | None:
    """Baut den LLM-Ticker-Extractor, falls ein OpenAI-Schluessel vorliegt.

    Ohne Schluessel wird None zurueckgegeben und resolve_symbols faellt
    kontrolliert auf die regelbasierte Ableitung zurueck.
    """
    config = context.assistant.config
    load_env_file(config.resolve_env_file(context.base_dir))
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    client = JsonHttpClient(
        timeout_seconds=config.request_timeout_seconds,
        max_retries=config.max_retries,
    )
    return LLMSymbolExtractor(client, api_key, config)


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


def build_keyword_query(query: str) -> str:
    """Verdichtet eine Analysefrage zu einem News-tauglichen Suchbegriff.

    Zahlen, Waehrungs- und Zeitangaben sowie Fuellwoerter werden entfernt,
    Firmennamen und Sachbegriffe bleiben erhalten. Falls nach dem Filtern
    nichts uebrig bleibt, werden die ersten Woerter der Frage zurueckgegeben,
    damit nie ein leerer Suchbegriff entsteht.
    """
    kept: list[str] = []
    seen: set[str] = set()
    for token in KEYWORD_TOKEN_PATTERN.findall(query):
        lowered = token.lower()
        if len(token) <= 1 or lowered in seen:
            continue
        if any(char.isdigit() for char in token) or lowered in KEYWORD_STOPWORDS:
            continue
        kept.append(token)
        seen.add(lowered)

    result = " ".join(kept).strip()
    if result:
        return result

    fallback = " ".join(query.split()[:6]).strip()
    return fallback or query.strip()


def resolve_symbols(
    *, query: str, raw_symbols: str | None, symbol_mode: str, extractor: object | None = None
) -> tuple[list[str], str, str | None]:
    """Gibt (symbols, source, keywords) zurück.

    Reihenfolge im Automatikmodus: LLM-Extraktion (falls verfuegbar), sonst
    die regelbasierte Ticker-Ableitung. keywords wird als News-Suchbegriff
    verwendet, wenn kein Ticker eindeutig zugeordnet werden kann.
    """
    manual_symbols = parse_symbols(raw_symbols)
    if symbol_mode == "manual":
        if manual_symbols:
            return manual_symbols, "manual", None
        raise ValueError(
            "Bitte wähle mindestens ein Symbol aus oder wechsle zur automatischen Ableitung aus der Analysefrage."
        )

    if extractor is not None:
        try:
            extraction = extractor.extract(query)
        except Exception:
            # LLM nicht erreichbar oder fehlerhaft → kontrollierter Rückfall auf Regeln.
            pass
        else:
            if extraction.symbols:
                return extraction.symbols, "llm", extraction.search_query
            return [], "keyword", extraction.search_query or build_keyword_query(query)

    inferred_symbols = infer_symbols_from_query(query)
    keywords = build_keyword_query(query)
    if inferred_symbols:
        return inferred_symbols, "inferred", keywords

    return [], "keyword", keywords


def localize_error_message(message: str) -> str:
    if message == NO_EVIDENCE_ERROR:
        return (
            "Keine relevanten Nachrichten für diese Anfrage gefunden. "
            "Bitte prüfe die Nachrichtenquelle, wechsle die Symbol-Einstellung oder formuliere die Analysefrage präziser."
        )
    return message


_PROVIDER_KEY_ENV = {
    "marketaux": "MARKETAUX_API_TOKEN",
    "alpha_vantage": "ALPHA_VANTAGE_API_KEY",
}


def missing_required_keys(context: AppContext) -> list[str]:
    """Namen der fuer den Live-Betrieb noetigen, aber nicht gesetzten Env-Variablen.

    Prueft den OpenAI-Schluessel und den Token des Standard-News-Providers. Wird
    beim Start (Warnung) und vom /api/health-Endpunkt (Readiness) genutzt.
    """
    provider = context.assistant.config.news_provider
    required = ["OPENAI_API_KEY", _PROVIDER_KEY_ENV.get(provider, "MARKETAUX_API_TOKEN")]
    return [name for name in required if not os.getenv(name)]


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
    rate_limiter = context.rate_limiter or RateLimiter(RateLimitConfig.from_env())

    class ResearchRequestHandler(BaseHTTPRequestHandler):
        server_version = "InvestmentResearchWeb/0.1"
        # Verbindungs-Timeout, damit langsame/haengende Clients keine Threads binden.
        timeout = REQUEST_TIMEOUT_SECONDS

        def _client_ip(self) -> str:
            # Hinter dem nginx-Reverse-Proxy ueberschreibt der Proxy den
            # X-Forwarded-For-Header mit der echten Client-IP (siehe DEPLOYMENT.md).
            # Wir nehmen die *letzte* Adresse der Kette (die vom vertrauenswuerdigen
            # Proxy angehaengte), damit ein vom Client selbst gesetztes XFF das
            # Rate-Limiting nicht aushebeln kann, und validieren sie als IP.
            forwarded = self.headers.get("X-Forwarded-For", "")
            if forwarded:
                candidate = forwarded.split(",")[-1].strip()
                try:
                    return str(ipaddress.ip_address(candidate))
                except ValueError:
                    pass
            return self.client_address[0] if self.client_address else "unknown"

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/defaults":
                self._send_json(HTTPStatus.OK, build_defaults_payload(context))
                return
            if parsed.path == "/api/health":
                # "ok" bleibt fuer den Container-Healthcheck erhalten; "ready"
                # spiegelt, ob die Live-API-Schluessel konfiguriert sind, damit ein
                # fehlkonfiguriertes Deployment sichtbar wird, ohne Geld auszugeben.
                self._send_json(
                    HTTPStatus.OK,
                    {"status": "ok", "ready": not missing_required_keys(context)},
                )
                return
            self._serve_static(parsed.path)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path != "/api/research":
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Endpoint not found."})
                return

            client_ip = self._client_ip()
            started_at = time.monotonic()

            allowed, limit_message = rate_limiter.check(client_ip)
            if not allowed:
                self._log_research(client_ip, HTTPStatus.TOO_MANY_REQUESTS, started_at)
                self._send_json(HTTPStatus.TOO_MANY_REQUESTS, {"error": limit_message})
                return

            symbol_source = "-"
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
                extractor_factory = context.extractor_factory or build_symbol_extractor
                extractor = extractor_factory(context) if symbol_mode != "manual" else None
                symbols, resolved_symbol_source, keywords = resolve_symbols(
                    query=query,
                    raw_symbols=str(payload.get("symbols", "")).strip() or None,
                    symbol_mode=symbol_mode,
                    extractor=extractor,
                )
                symbol_source = resolved_symbol_source

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
            except PayloadTooLarge:
                self._log_research(client_ip, HTTPStatus.REQUEST_ENTITY_TOO_LARGE, started_at)
                self._send_json(
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": PAYLOAD_TOO_LARGE_MESSAGE}
                )
                return
            except FileNotFoundError as exc:
                self._log_research(client_ip, HTTPStatus.BAD_REQUEST, started_at)
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            except ValueError as exc:
                self._log_research(client_ip, HTTPStatus.BAD_REQUEST, started_at)
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": localize_error_message(str(exc))})
                return
            except json.JSONDecodeError:
                self._log_research(client_ip, HTTPStatus.BAD_REQUEST, started_at)
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Malformed JSON payload."})
                return
            except Exception:
                # Vollstaendigen Traceback nur serverseitig loggen; dem Client wird
                # eine generische Meldung zurueckgegeben (keine internen Details).
                LOGGER.error(
                    "research error ip=%s symbol_source=%s\n%s",
                    client_ip,
                    symbol_source,
                    traceback.format_exc(),
                )
                self._log_research(client_ip, HTTPStatus.INTERNAL_SERVER_ERROR, started_at)
                self._send_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR, {"error": INTERNAL_ERROR_MESSAGE}
                )
                return

            self._log_research(client_ip, HTTPStatus.OK, started_at, symbol_source=symbol_source)
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
            # Stdlib-Zugriffslog unterdruecken; wir loggen /api/research gezielt
            # ueber _log_research (strukturiert, ueber den Modul-Logger).
            return

        def _log_research(
            self,
            client_ip: str,
            status: HTTPStatus,
            started_at: float,
            *,
            symbol_source: str = "-",
        ) -> None:
            duration_ms = (time.monotonic() - started_at) * 1000.0
            LOGGER.info(
                "research ip=%s status=%d symbol_source=%s duration_ms=%.0f",
                client_ip,
                int(status),
                symbol_source,
                duration_ms,
            )

        def _read_json_body(self) -> dict[str, object]:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length <= 0:
                return {}
            if content_length > MAX_REQUEST_BODY_BYTES:
                raise PayloadTooLarge
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
    parser = argparse.ArgumentParser(description="Run the investment research web app.")
    # Defaults kommen aus der Umgebung (HOST/PORT), damit derselbe Befehl lokal
    # (127.0.0.1) und im Container (0.0.0.0, Plattform-PORT) funktioniert.
    parser.add_argument(
        "--host",
        default=os.getenv("HOST", DEFAULT_HOST),
        help="Host interface to bind to (env: HOST).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=_int_env("PORT", DEFAULT_PORT),
        help="Port to listen on (env: PORT).",
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path.cwd(),
        help="Project root used for default output directory and .env resolution.",
    )
    return parser


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args = build_parser().parse_args()
    context = build_app_context(args.base_dir)
    # .env fruehzeitig laden, damit Rate-Limit- und API-Konfiguration bereitstehen.
    load_env_file(context.assistant.config.resolve_env_file(context.base_dir))

    # Fehlende Schluessel beim Start deutlich melden: sonst startet der Server und
    # scheitert erst pro Anfrage (oder degradiert stillschweigend zur Regel-Analyse).
    missing = missing_required_keys(context)
    if missing:
        LOGGER.warning(
            "Missing API keys: %s. Live analysis will fail or fall back until these are set.",
            ", ".join(missing),
        )

    handler = create_handler(context)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    LOGGER.info("Investment Research web app available at http://%s:%s", args.host, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
