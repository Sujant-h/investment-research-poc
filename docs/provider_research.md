# Provider Research

## Empfohlener Finanznachrichten-Provider

Fuer diesen Research-Assistenten ist **Marketaux** die beste Standardwahl.

Warum:

- finanzspezifische News statt allgemeiner Nachrichtenaggregation
- entity-basierte Filter fuer Symbole, Laender, Branchen und Sentiment
- strukturierte Highlights und `sentiment_score` pro identifizierter Entitaet
- globaler Scope mit 5.000+ Quellen, 80+ Maerkten und 30+ Sprachen
- verhaeltnismaessig niedrige Einstiegskosten

## Eignung nach Use Case

### 1. Marketaux

Beste Wahl fuer:

- Investment-Research
- Screening von M&A Targets
- Sentiment-gestuetzte Vorqualifizierung
- internationale Abdeckung mit strukturierter Entity-Metadaten

### 2. Polygon

Beste Wahl fuer:

- US-Aktienfokus
- Anwendungen mit starker Marktdata- und Tick-Daten-Orientierung
- Workflows, in denen News eng mit Kurs- und Referenzdaten kombiniert werden

### 3. Alpha Vantage

Beste Wahl fuer:

- guenstigen Einstieg
- kleine Projekte oder Studienarbeiten
- News plus Sentiment als einfacher API-Zugang

## Implementierungsentscheidung

Im Code ist **Marketaux** als empfohlener Live-News-Provider umgesetzt. Als alternative Integration ist **Alpha Vantage** ebenfalls vorbereitet.

## Quellen

- OpenAI Models: https://developers.openai.com/api/docs/models
- OpenAI Responses API: https://platform.openai.com/docs/api-reference/responses/compact?api-mode=responses
- OpenAI Structured Outputs: https://platform.openai.com/docs/guides/structured-outputs
- Marketaux Documentation: https://www.marketaux.com/documentation
- Marketaux Pricing: https://www.marketaux.com/pricing
- Polygon News API: https://polygon.io/docs/stocks/get_v2_reference_news
- Polygon Pricing: https://polygon.io/pricing
- Alpha Vantage Documentation: https://www.alphavantage.co/documentation/
- Alpha Vantage Premium: https://www.alphavantage.co/premium/
- Finnhub official client examples: https://github.com/Finnhub-Stock-API/finnhub-js
