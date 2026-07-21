# Investment Research PoC

Dieser Proof of Concept implementiert einen produktionsnahen Research-Assistenten fuer das Investmentbanking. Der Fokus liegt auf der automatisierten Analyse von Finanzberichten, Pressemitteilungen und Marktnachrichten, um Analysten bei der Vorqualifizierung potenzieller Investments oder Akquisitionsziele zu unterstuetzen.

## Zielbild

Der PoC bildet eine Best-Practice-Zielarchitektur im Kleinen ab:

- mehrstufige Dokumentenverarbeitung
- nachvollziehbare Retrieval-Logik statt Black Box
- OpenAI-basierte Brief-Erstellung ueber die Responses API mit strukturiertem JSON-Output
- live-faehige News-Ingestion ueber externe Finanznachrichten-APIs
- automatisch erzeugter Research-Brief mit Evidenz
- Human-in-the-Loop als Kontrollinstanz

Die Implementierung ist lokal testbar und zugleich fuer echte API-Keys vorbereitet. Wenn kein API-Key vorhanden ist, faellt das System kontrolliert auf eine lokale regelbasierte Analyse zurueck.

## Projektstruktur

```text
data/samples/                Beispieldokumente fuer den PoC
output/                      Generierte Reports
src/investment_research_poc/ Anwendungslogik
tests/                       Basis-Tests
```

## Schneller Start

1. Optional: `.env.example` nach `.env` kopieren und mit deinen Schluesseln fuellen.
2. `OPENAI_API_KEY` setzen.
3. Fuer Live-News einen News-Provider-Key setzen, empfohlen `MARKETAUX_API_TOKEN`.

## Lokaler Lauf mit Beispieldaten

```powershell
$env:PYTHONPATH="C:\Users\Sujanth\Documents\Digitale Transformation\src"
& "C:\Users\Sujanth\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m investment_research_poc.cli `
  --input "C:\Users\Sujanth\Documents\Digitale Transformation\data\samples" `
  --query "Assess AlphaTech AG as a potential acquisition target in industrial AI" `
  --output "C:\Users\Sujanth\Documents\Digitale Transformation\output"
```

## Produktiver Lauf mit Live-News

```powershell
$env:PYTHONPATH="C:\Users\Sujanth\Documents\Digitale Transformation\src"
$env:OPENAI_API_KEY="..."
$env:MARKETAUX_API_TOKEN="..."
& "C:\Users\Sujanth\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m investment_research_poc.cli `
  --input "C:\Users\Sujanth\Documents\Digitale Transformation\data\samples" `
  --live-news `
  --provider marketaux `
  --symbols "SAP,MSFT" `
  --query "Assess whether SAP is an attractive strategic acquisition candidate in enterprise AI software" `
  --output "C:\Users\Sujanth\Documents\Digitale Transformation\output"
```

Danach liegen zwei Artefakte im Ausgabeordner:

- `research_brief.md`
- `research_brief.json`

## Web-Frontend starten

Fuer eine lokale Website mit Formular, Ergebnis-Dashboard und Evidenzansicht:

```powershell
& "C:\Users\Sujanth\Documents\Digitale Transformation\run-web.cmd"
```

Danach ist die Anwendung unter [http://127.0.0.1:8080](http://127.0.0.1:8080) verfuegbar.

Die Web-App:

- nutzt dieselbe Pipeline wie die CLI
- unterstuetzt lokale Input-Pfade fuer `.txt`, `.md`, `.json` und `.docx`
- kann optional Live-News und OpenAI aktivieren
- schreibt weiterhin `research_brief.md` und `research_brief.json` in den gewaehlten Ausgabeordner

## Deployment (oeffentliche Subdomain)

Fuer den produktiven Betrieb unter einer eigenen Subdomain (z. B.
`invest.suthaharan.de`) liegt eine Docker-Compose-Konfiguration bei. Der
Container wird nur auf `127.0.0.1` veroeffentlicht; das globale nginx des VPS
terminiert TLS und leitet die Subdomain als Reverse-Proxy weiter:

```bash
cp .env.example .env   # API-Keys, APP_PORT und Rate-Limits eintragen
docker compose up -d --build
```

Details, DNS- und nginx-Einrichtung sowie der Kostenschutz (Rate-Limiting je IP
und globales Tageslimit fuer den bezahlten API-Verbrauch) sind in
[DEPLOYMENT.md](DEPLOYMENT.md) beschrieben.

## Methodischer Aufbau

1. Dokumente werden aus einem Eingabeverzeichnis geladen.
2. Texte werden in ueberschaubare Chunks zerlegt.
3. Ein transparenter Keyword-Retriever priorisiert relevante Textstellen.
4. Die relevantesten Evidenzen werden an die OpenAI Responses API uebergeben.
5. Das Modell liefert einen strukturierten Research-Brief im JSON-Schema zurueck.
6. Falls OpenAI nicht verfuegbar ist, greift eine lokale Fallback-Analyse.

## Wissenschaftlicher Mehrwert

Der PoC eignet sich fuer eine wissenschaftliche Modularbeit, weil er zentrale Gestaltungsprinzipien digitaler Transformation im Investmentbanking konkret abbildet:

- Effizienzsteigerung durch Automatisierung unstrukturierter Analysearbeit
- Entscheidungsunterstuetzung durch datenbasierte Vorselektion
- Risikoreduktion durch Quellenbezug und Human-in-the-Loop
- modulare Erweiterbarkeit in Richtung RAG, LLM und Echtzeit-Datenfeeds

## Grenzen des PoC

- keine Echtzeit-Anbindung an Bloomberg, Reuters oder regulatorische Feeds
- keine Authentifizierungs- oder Rollenlogik fuer Mehrbenutzerbetrieb
- kein internes Datenqualitaets-Monitoring oder SIEM-Logging
- fallbackbasierte Sentiment-Analyse bleibt einfacher als ein feinabgestimmtes Fachmodell

Fuer eine produktive Umsetzung waeren zusaetzlich Data Governance, Zugriffssteuerung, Modellueberwachung, Auditierbarkeit und regulatorische Kontrollmechanismen erforderlich.
