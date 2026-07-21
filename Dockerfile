# syntax=docker/dockerfile:1

FROM python:3.12-slim AS runtime

# Sinnvolle Defaults fuer Container-Betrieb.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HOST=0.0.0.0 \
    PORT=8080

WORKDIR /app

# Nur die fuer den Build noetigen Metadaten zuerst kopieren, damit Docker-Layer
# gecached werden, solange sich das Paket-Manifest nicht aendert.
COPY pyproject.toml README.md ./
COPY src ./src

# Das Projekt hat keine Laufzeit-Abhaengigkeiten (nur Python-Stdlib); pip
# installiert damit lediglich das Paket selbst inklusive Konsolen-Skripte.
RUN pip install --no-cache-dir .

# Beispieldaten mitnehmen (optional, fuer lokale Datei-Analyse / Referenz).
COPY data ./data

# Ausgabeverzeichnis anlegen und als Nicht-Root-Nutzer betreiben.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/output \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

# Healthcheck gegen den bestehenden /api/health-Endpunkt.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request,sys; \
url='http://127.0.0.1:%s/api/health' % os.getenv('PORT','8080'); \
sys.exit(0 if urllib.request.urlopen(url, timeout=3).status == 200 else 1)"

# HOST/PORT werden ueber die Umgebung gelesen (siehe webapp.build_parser).
CMD ["investment-research-web", "--base-dir", "/app"]
