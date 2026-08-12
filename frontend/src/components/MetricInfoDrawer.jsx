import { useEffect, useRef } from "react";
import { Database, Info, Sparkles, X } from "lucide-react";
import { groundQuestion } from "../dashboardQuestions";

function displayValue(value) {
  if (value === null || value === undefined) return "Unavailable";
  return typeof value === "number" ? value.toLocaleString(undefined, { maximumFractionDigits: 2 }) : String(value);
}

export default function MetricInfoDrawer({ metric, scope, updatedAt, onClose, onAsk }) {
  const closeRef = useRef(null);

  useEffect(() => {
    if (!metric) return undefined;
    const previous = document.activeElement;
    closeRef.current?.focus();
    function handleKeyDown(event) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      previous?.focus?.();
    };
  }, [metric, onClose]);

  if (!metric) return null;
  const askScope = { squad: scope?.squad, sprint: scope?.sprint, release: scope?.release, project: scope?.project };
  const questions = metric.suggested_questions || metric.suggestedQuestions || [];
  const fields = metric.required_fields || metric.requiredFields || [];
  const sources = metric.source_tables || metric.sourceTables || [];

  return (
    <aside className="metric-info-drawer" role="dialog" aria-modal="false" aria-labelledby="metric-drawer-title">
      <header>
        <span className="metric-drawer-icon" aria-hidden="true"><Info /></span>
        <div>
          <p>Metric intelligence</p>
          <h2 id="metric-drawer-title">{metric.title}</h2>
        </div>
        <button ref={closeRef} type="button" onClick={onClose} aria-label="Close metric information">
          <X aria-hidden="true" />
        </button>
      </header>

      <div className="metric-drawer-value">
        <span>Current value</span>
        <strong>{displayValue(metric.value)}</strong>
      </div>

      <section>
        <h3>Meaning</h3>
        <p>{metric.description}</p>
        <h3>Why it matters</h3>
        <p>{metric.why_it_matters || metric.whyItMatters}</p>
      </section>

      <section>
        <h3>Current scope</h3>
        <div className="metric-scope-chips">
          {Object.entries(scope || {}).filter(([, value]) => value).map(([key, value]) => (
            <span key={key}>{key.replaceAll("_", " ")}: {value}</span>
          ))}
        </div>
      </section>

      <section className="metric-formula-block">
        <h3>Calculation</h3>
        <code>{metric.formula}</code>
      </section>

      <section className="metric-source-block">
        <h3><Database aria-hidden="true" /> Data source</h3>
        <p>{sources.join(", ")}</p>
        <dl>
          <div><dt>Fields</dt><dd>{fields.join(", ")}</dd></div>
          <div><dt>Last updated</dt><dd>{updatedAt ? new Date(updatedAt).toLocaleString() : "Unavailable"}</dd></div>
        </dl>
      </section>

      <section>
        <h3>Data-quality notes</h3>
        <p>{metric.data_quality_note || "Interpret this metric within the displayed scope and source-field limitations."}</p>
      </section>

      <section>
        <h3>Ask Zara</h3>
        <div className="metric-question-chips">
          {questions.map((question) => (
            <button
              key={question}
              type="button"
              // The registry phrases these conversationally ("Rank them by
              // age"), which only works while looking at the drawer. Grounding
              // restates the metric, value and scope so the sent question
              // carries its own antecedent.
              title={groundQuestion(question, { title: metric.title, value: metric.value, scope: askScope })}
              onClick={() => onAsk(
                groundQuestion(question, { title: metric.title, value: metric.value, scope: askScope }),
                { selected_metric: metric.key, current_metric_value: metric.value },
              )}
            >
              <Sparkles aria-hidden="true" />{question}
            </button>
          ))}
        </div>
      </section>
    </aside>
  );
}

