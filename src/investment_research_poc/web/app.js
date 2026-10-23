const form = document.querySelector("#research-form");
const submitButton = document.querySelector("#submit-button");
const formMessage = document.querySelector("#form-message");
const resultsPanel = document.querySelector("#results-panel");
const resultsEmpty = document.querySelector("#results-empty");
const healthIndicator = document.querySelector("#health-indicator");
const evidenceTemplate = document.querySelector("#evidence-template");
const querySuggestions = document.querySelector("#query-suggestions");
const storageKey = "investment-research-webapp-state";

const fields = {
  query: document.querySelector("#query"),
  providerName: document.querySelector("#provider_name"),
  symbolModeOptions: document.querySelector("#symbol-mode-options"),
  symbolPickerPanel: document.querySelector("#symbol-picker-panel"),
  symbolModeNote: document.querySelector("#symbol-mode-note"),
  symbols: document.querySelector("#symbols"),
  clearSymbols: document.querySelector("#clear-symbols"),
  customTickerInput: document.querySelector("#custom-ticker-input"),
  addCustomTicker: document.querySelector("#add-custom-ticker"),
};

const resultNodes = {
  title: document.querySelector("#result-title"),
  resultOutputPath: document.querySelector("#result-output-path"),
  summary: document.querySelector("#executive-summary"),
  recommendation: document.querySelector("#recommendation"),
  sentimentBadge: document.querySelector("#sentiment-badge"),
  sentimentScore: document.querySelector("#sentiment-score"),
  positiveTerms: document.querySelector("#positive-terms"),
  negativeTerms: document.querySelector("#negative-terms"),
  opportunities: document.querySelector("#opportunities"),
  risks: document.querySelector("#risks"),
  evidenceCount: document.querySelector("#evidence-count"),
  evidenceList: document.querySelector("#evidence-list"),
};

const state = {
  defaults: null,
  restoredSnapshot: null,
  currentRun: null,
};

init();

async function init() {
  restoreState();
  bindEvents();
  await Promise.all([loadDefaults(), checkHealth()]);
}

function bindEvents() {
  form.addEventListener("submit", handleSubmit);
  fields.query.addEventListener("input", persistState);
  fields.providerName.addEventListener("change", persistState);
  fields.symbols.addEventListener("change", persistState);
  fields.symbolModeOptions.addEventListener("change", handleSymbolModeChange);
  fields.clearSymbols.addEventListener("click", handleClearSymbols);
  fields.addCustomTicker.addEventListener("click", handleAddCustomTicker);
  fields.customTickerInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); handleAddCustomTicker(); }
  });
}

async function loadDefaults() {
  try {
    const response = await fetch("/api/defaults");
    if (!response.ok) {
      throw new Error("Standardeinstellungen konnten nicht geladen werden.");
    }
    state.defaults = await response.json();
    applyDefaults();
  } catch (error) {
    setMessage(error.message, true);
  }
}

async function checkHealth() {
  try {
    const response = await fetch("/api/health");
    if (!response.ok) {
      throw new Error("Serverstatus nicht verfügbar.");
    }
    healthIndicator.textContent = "Server bereit";
    healthIndicator.classList.add("is-ready");
    healthIndicator.classList.remove("muted");
  } catch (error) {
    healthIndicator.textContent = "Serverfehler";
    healthIndicator.classList.add("muted");
    healthIndicator.classList.remove("is-ready");
  }
}

function applyDefaults() {
  if (!state.defaults) {
    return;
  }

  populateProviderOptions(state.defaults.providers || [], state.defaults.default_provider);
  populateSymbolOptions(state.defaults.symbol_options || []);
  renderSymbolModeOptions(
    state.defaults.symbol_modes || [],
    state.defaults.default_symbol_mode || "query",
  );
  renderSuggestedQueries(state.defaults.suggested_queries || []);

  if (state.restoredSnapshot) {
    applySnapshot(state.restoredSnapshot);
  } else {
    setSymbolMode(state.defaults.default_symbol_mode || "query");
  }

  if (!fields.providerName.value) {
    fields.providerName.value = state.defaults.default_provider;
  }

  syncSymbolModeUI();
  persistState();
}

function populateProviderOptions(providers, defaultProvider) {
  fields.providerName.replaceChildren();
  providers.forEach((provider) => {
    const option = document.createElement("option");
    option.value = provider;
    option.textContent = formatProviderName(provider);
    option.selected = provider === defaultProvider;
    fields.providerName.appendChild(option);
  });
}

function populateSymbolOptions(options) {
  fields.symbols.replaceChildren();
  options.forEach((item) => {
    const option = document.createElement("option");
    option.value = item.value;
    option.textContent = item.label;
    fields.symbols.appendChild(option);
  });
}

function renderSymbolModeOptions(modes, defaultMode) {
  fields.symbolModeOptions.replaceChildren();

  modes.forEach((item) => {
    const label = document.createElement("label");
    label.className = "choice-card";

    const input = document.createElement("input");
    input.type = "radio";
    input.name = "symbol_mode";
    input.value = item.value;
    input.checked = item.value === defaultMode;

    const copy = document.createElement("span");
    copy.className = "choice-copy";
    copy.innerHTML = `
      <span class="choice-kicker">${item.value === "query" ? "Automatik" : "Manuell"}</span>
      <strong class="choice-title">${item.label}</strong>
      <span>${item.description}</span>
    `;

    label.append(input, copy);
    fields.symbolModeOptions.appendChild(label);
  });

  updateChoiceCardState();
}

function renderSuggestedQueries(suggestions) {
  querySuggestions.replaceChildren();

  suggestions.forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "suggestion-button";
    button.innerHTML = `
      <span class="suggestion-label">${item.label}</span>
      <strong>${item.query}</strong>
    `;
    button.addEventListener("click", () => {
      fields.query.value = item.query;
      setSelectedSymbols(item.symbols || []);
      setSymbolMode(item.symbol_mode || (item.symbols?.length ? "manual" : "query"));
      fields.query.focus();
      persistState();
    });
    querySuggestions.appendChild(button);
  });
}

function handleSymbolModeChange() {
  syncSymbolModeUI();
  persistState();
}

function handleClearSymbols() {
  setSelectedSymbols([]);
  fields.customTickerInput.value = "";
  persistState();
}

function handleAddCustomTicker() {
  const raw = fields.customTickerInput.value.trim();
  if (!raw) return;

  const tickers = raw
    .split(/[,\s]+/)
    .map((t) => t.toUpperCase().replace(/[^A-Z0-9.]/g, ""))
    .filter(Boolean);

  tickers.forEach((ticker) => {
    const existing = fields.symbols.querySelector(`option[value="${ticker}"]`);
    if (existing) {
      existing.selected = true;
    } else {
      const option = document.createElement("option");
      option.value = ticker;
      option.textContent = ticker;
      option.selected = true;
      option.dataset.custom = "true";
      fields.symbols.appendChild(option);
    }
  });

  fields.customTickerInput.value = "";
  persistState();
}

async function handleSubmit(event) {
  event.preventDefault();

  const query = fields.query.value.trim();
  if (!query) {
    setMessage("Bitte gib eine Analysefrage ein.", true);
    fields.query.focus();
    return;
  }

  const symbolMode = getSymbolMode();
  const selectedSymbols = symbolMode === "manual" ? getSelectedSymbols() : [];

  if (symbolMode === "manual" && selectedSymbols.length === 0) {
    setMessage("Bitte wähle mindestens ein Symbol aus oder wechsle zum Automatikmodus.", true);
    fields.symbols.focus();
    return;
  }

  const payload = {
    query,
    provider_name: fields.providerName.value.trim(),
    symbol_mode: symbolMode,
    symbols: selectedSymbols.join(","),
  };

  submitButton.disabled = true;
  submitButton.textContent = "Analyse läuft …";
  setMessage("Live-Nachrichten und Analyse werden mit den gewählten Einstellungen vorbereitet.", false);

  try {
    const response = await fetch("/api/research", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) {
      // Only the HTTP status (429 = rate limit), never the question itself.
      track("analysis-error", { status: response.status, mode: symbolMode });
      throw new Error(result.error || "Die Analyse konnte nicht abgeschlossen werden.");
    }
    track("analysis-run", { mode: symbolMode, symbols: selectedSymbols.length });
    state.currentRun = result;
    renderResults(result);
    setMessage("Analysebericht erfolgreich erstellt.", false);
    if (resultsEmpty) {
      resultsEmpty.hidden = true;
    }
    resultsPanel.hidden = false;
    resultsPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    setMessage(error.message, true);
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Analyse starten";
  }
}

function renderResults(result) {
  const { brief } = result;
  resultNodes.title.textContent = brief.query;
  resultNodes.resultOutputPath.textContent = result.output_path;
  resultNodes.summary.textContent = brief.executive_summary;
  resultNodes.recommendation.textContent = brief.recommendation;

  resultNodes.sentimentBadge.textContent = formatSentimentLabel(brief.sentiment.label);
  resultNodes.sentimentBadge.className = `badge sentiment-badge ${brief.sentiment.label}`;
  resultNodes.sentimentScore.textContent = brief.sentiment.score.toFixed(3);

  fillList(resultNodes.positiveTerms, brief.sentiment.matched_positive_terms, "Keine positiven Treffer erkannt.");
  fillList(resultNodes.negativeTerms, brief.sentiment.matched_negative_terms, "Keine negativen Treffer erkannt.");

  fillList(resultNodes.opportunities, brief.opportunities, "Keine Chancen-Signale erkannt.");
  fillList(resultNodes.risks, brief.risks, "Keine Risiko-Signale erkannt.");

  resultNodes.evidenceCount.textContent = `${brief.evidence.length} Evidenzquellen`;
  resultNodes.evidenceList.replaceChildren();

  brief.evidence.forEach((item) => {
    const fragment = evidenceTemplate.content.cloneNode(true);
    fragment.querySelector(".evidence-title").textContent = item.title;
    fragment.querySelector(".evidence-meta").textContent = buildEvidenceMeta(item);
    fragment.querySelector(".evidence-score").textContent = `Wert ${item.score.toFixed(2)}`;
    fragment.querySelector(".evidence-text").textContent = item.text;
    resultNodes.evidenceList.appendChild(fragment);
  });
}

function buildEvidenceMeta(item) {
  const parts = [];
  if (item.provider) {
    parts.push(formatProviderName(item.provider));
  }
  if (item.source_type) {
    parts.push(formatSourceType(item.source_type));
  }
  if (item.published_at) {
    parts.push(formatDate(item.published_at));
  }
  return parts.join(" | ");
}

function fillList(container, values, emptyText) {
  container.replaceChildren();
  const items = values.length > 0 ? values : [emptyText];
  items.forEach((value) => {
    const li = document.createElement("li");
    li.textContent = value;
    container.appendChild(li);
  });
}

function setMessage(message, isError) {
  formMessage.textContent = message;
  formMessage.classList.toggle("is-error", Boolean(isError));
}

function formatMode(value) {
  const labels = {
    openai_structured_output: "OpenAI Strukturierte Ausgabe",
    rule_based_fallback: "Regelbasierte Alternative",
  };
  return labels[value] || value;
}

function formatDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("de-DE", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function formatProviderName(value) {
  const labels = {
    alpha_vantage: "Alpha Vantage",
    marketaux: "Marketaux",
  };
  return labels[value] || value;
}

function formatSentimentLabel(value) {
  const labels = {
    negative: "Negativ",
    neutral: "Neutral",
    positive: "Positiv",
  };
  return labels[value] || value;
}

function formatSourceType(value) {
  const labels = {
    market_news: "Marktnachrichten",
  };
  return labels[value] || value;
}

function formatSymbolMode(value) {
  const labels = {
    manual: "Symbole manuell",
    query: "Aus Analysefrage abgeleitet",
  };
  return labels[value] || value;
}

function formatSymbolSource(value) {
  if (value === "manual") return "Manuell ausgewählt";
  if (value === "inferred") return "Automatisch aus der Analysefrage abgeleitet";
  if (value === "keyword") return "Stichwortsuche (kein Ticker erkannt)";
  return value || "Unbekannt";
}

function getSelectedSymbols() {
  return Array.from(fields.symbols.selectedOptions).map((option) => option.value);
}

function setSelectedSymbols(symbols) {
  const selected = new Set(symbols);
  Array.from(fields.symbols.options).forEach((option) => {
    option.selected = selected.has(option.value);
  });
}

function getSymbolMode() {
  const selectedOption = document.querySelector('input[name="symbol_mode"]:checked');
  return selectedOption?.value || state.defaults?.default_symbol_mode || "query";
}

function setSymbolMode(symbolMode) {
  const target = document.querySelector(`input[name="symbol_mode"][value="${symbolMode}"]`);
  const fallback = document.querySelector('input[name="symbol_mode"][value="query"]');
  (target || fallback)?.click();
  syncSymbolModeUI();
}

function syncSymbolModeUI() {
  const symbolMode = getSymbolMode();
  const isManual = symbolMode === "manual";
  form.dataset.symbolMode = symbolMode;
  fields.symbolPickerPanel.hidden = !isManual;
  fields.symbolModeNote.textContent = isManual
    ? "Die manuelle Auswahl wird für die nächste Analyse verbindlich verwendet."
    : "Im Automatikmodus werden Symbole für jede Analyse neu aus der aktuellen Frage abgeleitet.";
  updateChoiceCardState();
}

function updateChoiceCardState() {
  Array.from(fields.symbolModeOptions.querySelectorAll(".choice-card")).forEach((card) => {
    const input = card.querySelector('input[name="symbol_mode"]');
    card.classList.toggle("is-active", Boolean(input?.checked));
  });
}

function persistState() {
  const snapshot = {
    query: fields.query.value,
    providerName: fields.providerName.value,
    symbolMode: getSymbolMode(),
    symbols: getSelectedSymbols(),
  };
  window.localStorage.setItem(storageKey, JSON.stringify(snapshot));
}

function restoreState() {
  const rawState = window.localStorage.getItem(storageKey);
  if (!rawState) {
    return;
  }

  try {
    state.restoredSnapshot = JSON.parse(rawState);
  } catch {
    window.localStorage.removeItem(storageKey);
  }
}

function applySnapshot(snapshot) {
  fields.query.value = snapshot.query || "";
  fields.providerName.value = snapshot.providerName || "";
  setSelectedSymbols(snapshot.symbols || []);
  setSymbolMode(snapshot.symbolMode || state.defaults?.default_symbol_mode || "query");
}

// umami custom event. window.umami is missing locally and when the visitor
// opts out (Do Not Track), so this is a no-op then. Never pass user input.
function track(event, data) {
  try {
    window.umami?.track(event, data);
  } catch {
    // Analytics must never break the workspace.
  }
}
