import { useEffect, useRef } from "react";
import { Database, Info, Sparkles, X } from "lucide-react";
import { groundQuestion } from "../dashboardQuestions";

function displayValue(value, suffix = "") {
  if (value === null || value === undefined) return "Unavailable";
  const displayed = typeof value === "number" ? value.toLocaleString(undefined, { maximumFractionDigits: 2 }) : String(value);
  return `${displayed}${suffix}`;
}

function stringList(value) {
  return Array.isArray(value) ? value.filter((item) => typeof item === "string" && item.trim()) : [];
}

function humanize(value) {
  return String(value).split("_").join(" ");
}

function displayDate(value) {
  if (!value) return "Unavailable";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Unavailable" : date.toLocaleString();
}

export default function MetricInfoDrawer({ metric, scope, updatedAt, onClose, onAsk }) {
  const closeRef = useRef(null);
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!metric) return undefined;
    const previous = document.activeElement;
    closeRef.current?.focus();
    function handleKeyDown(event) {
      if (event.key === "Escape") onCloseRef.current?.();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      if (previous instanceof HTMLElement && previous.isConnected) previous.focus();
    };
  }, [metric]);

  if (!metric) return null;
  const askScope = { squad: scope?.squad, sprint: scope?.sprint, release: scope?.release, project: scope?.project };
  const questions = stringList(metric.suggested_questions || metric.suggestedQuestions);
  const fields = stringList(metric.required_fields || metric.requiredFields);
  const sources = stringList(metric.source_tables || metric.sourceTables);
  const title = metric.title || "Metric information";
  const description = metric.description || "No description is available for this metric.";
  const formula = metric.formula || "Calculation details are unavailable.";
  const whyItMatters = metric.why_it_matters || metric.whyItMatters || "Use this metric with the current dashboard scope and team context.";
  const importantNote = metric.data_quality_note || metric.dataQualityNote || "Interpret this metric within the displayed scope and source-field limitations.";

  return (
    <aside className="metric-info-drawer" role="dialog" aria-modal="false" aria-labelledby="metric-drawer-title">
      <header>
        <span className="metric-drawer-icon" aria-hidden="true"><Info /></span>
        <div>
          <p>Metric intelligence</p>
          <h2 id="metric-drawer-title">{title}</h2>
        </div>
        <button ref={closeRef} type="button" onClick={onClose} aria-label="Close metric information">
          <X aria-hidden="true" />
        </button>
      </header>

      <div className="metric-drawer-value">
        <span>Current value</span>
        <strong>{displayValue(metric.value, metric.suffix || "")}</strong>
      </div>

      <section>
        <h3>What it shows</h3>
        <p>{description}</p>
      </section>

      <section className="metric-formula-block">
        <h3>How Zara calculates</h3>
        <code>{formula}</code>
      </section>

      <section>
        <h3>Why it matters</h3>
        <p>{whyItMatters}</p>
      </section>

      <section>
        <h3>Important note</h3>
        <p>{importantNote}</p>
      </section>

      <section>
        <h3>Current scope</h3>
        <div className="metric-scope-chips">
          {Object.entries(scope || {}).filter(([, value]) => value).map(([key, value]) => (
            <span key={key}>{humanize(key)}: {displayValue(value)}</span>
          ))}
        </div>
      </section>

      <section className="metric-source-block">
        <h3><Database aria-hidden="true" /> Data source</h3>
        <p>{sources.join(", ") || "Unavailable"}</p>
        <dl>
          <div><dt>Fields</dt><dd>{fields.join(", ") || "Unavailable"}</dd></div>
          <div><dt>Last updated</dt><dd>{displayDate(updatedAt)}</dd></div>
        </dl>
      </section>

      <section>
        <h3>Ask Zara</h3>
        <div className="metric-question-chips">
          {questions.map((question) => {
            const grounded = groundQuestion(question, { title, value: metric.value, scope: askScope });
            return (
              <button
                key={question}
                type="button"
                title={grounded}
                onClick={() => onAsk?.(
                  grounded,
                  { selected_metric: metric.key, current_metric_value: metric.value },
                )}
              >
                <Sparkles aria-hidden="true" />{question}
              </button>
            );
          })}
        </div>
      </section>
    </aside>
  );
}

