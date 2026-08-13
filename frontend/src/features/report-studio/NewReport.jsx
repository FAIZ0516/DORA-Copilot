import { useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  FileText,
  Loader2,
  MessageSquareQuote,
  Sparkles,
  Wand2,
} from "lucide-react";

/**
 * Creating a report, as two clear steps rather than one long form.
 *
 * The earlier version showed every template and every setting at once, which
 * buried the decision that actually matters -- what kind of report this is --
 * under a wall of inputs. Step 1 is the choice; step 2 is the detail, with the
 * chosen template's own defaults already filled in so most users can press
 * Create straight away.
 *
 * The three entry points from the dashboard launcher (template / chat / blank)
 * land on genuinely different starting states rather than the same screen.
 */

const START_MODES = {
  template: {
    title: "Start from a template",
    detail: "Pick a report type. Zara answers its standard questions from live data.",
    icon: Wand2,
  },
  chat: {
    title: "Build from your conversation",
    detail: "The answer you selected becomes the first piece of evidence.",
    icon: MessageSquareQuote,
  },
  blank: {
    title: "Start blank",
    detail: "An empty report you structure yourself, block by block.",
    icon: FileText,
  },
};

const label = (value) => String(value || "").replaceAll("_", " ");

export default function NewReport({ catalogue, start, pending, busy, onCreate, onCancel }) {
  const mode = START_MODES[start] ? start : "template";
  const [step, setStep] = useState(mode === "blank" ? 2 : 1);
  const [template, setTemplate] = useState(mode === "blank" ? "blank" : "executive_summary");
  const [title, setTitle] = useState("");
  const [audience, setAudience] = useState("senior_leadership");
  const [tone, setTone] = useState("executive");
  const [detail, setDetail] = useState("standard");
  const [recommendations, setRecommendations] = useState(true);
  const [generate, setGenerate] = useState(mode === "template");
  const [scope, setScope] = useState({
    project: "DCPM", squad: "", sprint: "", release: "", date_from: "", date_to: "",
  });

  const templates = catalogue?.templates || [];
  const chosen = useMemo(
    () => templates.find((item) => item.id === template),
    [templates, template],
  );

  // Adopt the template's own defaults, so step 2 usually needs no edits.
  useEffect(() => {
    if (!chosen) return;
    setTitle(chosen.default_title);
    setAudience(chosen.default_audience);
    setTone(chosen.default_tone);
    setGenerate(mode === "template" && (chosen.questions?.length || 0) > 0);
  }, [chosen, mode]);

  function submit(event) {
    event.preventDefault();
    const cleaned = Object.fromEntries(Object.entries(scope).filter(([, value]) => value));
    onCreate(
      {
        template,
        title: title || chosen?.default_title,
        audience,
        tone,
        detail_level: detail,
        include_recommendations: recommendations,
        scope: cleaned,
      },
      { generate: generate && (chosen?.questions?.length || 0) > 0 },
    );
  }

  const Icon = START_MODES[mode].icon;
  const questionCount = chosen?.questions?.length || 0;

  return (
    <form className="report-new" onSubmit={submit}>
      <header className="report-new-intro">
        <span aria-hidden="true"><Icon /></span>
        <div>
          <h2>{START_MODES[mode].title}</h2>
          <p>{START_MODES[mode].detail}</p>
        </div>
      </header>

      {pending && (
        <p className="report-new-pending" role="status">
          <Check aria-hidden="true" /> The selected answer will be attached once the report is created.
        </p>
      )}

      <ol className="report-steps" aria-label="Progress">
        <li className={step === 1 ? "is-current" : "is-done"}><span>1</span> Choose a type</li>
        <li className={step === 2 ? "is-current" : ""}><span>2</span> Set the details</li>
      </ol>

      {step === 1 ? (
        <>
          <div className="report-template-grid">
            {templates.map((item) => (
              <label key={item.id} className={template === item.id ? "is-selected" : ""}>
                <input
                  type="radio"
                  name="template"
                  value={item.id}
                  checked={template === item.id}
                  onChange={() => setTemplate(item.id)}
                />
                <strong>{item.label}</strong>
                <small>{item.description}</small>
                <em>
                  {item.section_count} section{item.section_count === 1 ? "" : "s"}
                  {item.questions?.length ? ` · ${item.questions.length} standard questions` : ""}
                </em>
              </label>
            ))}
          </div>

          {questionCount > 0 && (
            <section className="report-question-preview">
              <h3>What this report answers</h3>
              <p>
                These questions are fixed, so the report stays comparable over time — the
                wording stays the same and the answers come from whatever the data says
                when you generate it.
              </p>
              <ul>
                {chosen.questions.map((question) => <li key={question}>{question}</li>)}
              </ul>
            </section>
          )}

          <div className="report-new-actions">
            <button type="button" onClick={onCancel}>Cancel</button>
            <button type="button" className="primary" onClick={() => setStep(2)}>
              Continue <ArrowRight aria-hidden="true" />
            </button>
          </div>
        </>
      ) : (
        <>
          <fieldset>
            <legend>Report details</legend>
            <div className="report-config-grid">
              <label className="is-wide"><span>Report title</span>
                <input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={200} required />
              </label>
              <label><span>Audience</span>
                <select value={audience} onChange={(event) => setAudience(event.target.value)}>
                  {(catalogue?.audiences || []).map((value) => <option key={value} value={value}>{label(value)}</option>)}
                </select>
              </label>
              <label><span>Tone</span>
                <select value={tone} onChange={(event) => setTone(event.target.value)}>
                  {(catalogue?.tones || []).map((value) => <option key={value} value={value}>{label(value)}</option>)}
                </select>
              </label>
              <label><span>Level of detail</span>
                <select value={detail} onChange={(event) => setDetail(event.target.value)}>
                  {(catalogue?.detail_levels || []).map((value) => <option key={value} value={value}>{label(value)}</option>)}
                </select>
              </label>
            </div>
          </fieldset>

          <fieldset>
            <legend>What the report covers</legend>
            <div className="report-config-grid">
              <label><span>Project</span>
                <input value={scope.project} onChange={(event) => setScope({ ...scope, project: event.target.value })} />
              </label>
              <label><span>Squad</span>
                <input value={scope.squad} placeholder="All squads" onChange={(event) => setScope({ ...scope, squad: event.target.value })} />
              </label>
              <label><span>Sprint</span>
                <input value={scope.sprint} placeholder="All sprints" onChange={(event) => setScope({ ...scope, sprint: event.target.value })} />
              </label>
              <label><span>Release</span>
                <input value={scope.release} placeholder="All releases" onChange={(event) => setScope({ ...scope, release: event.target.value })} />
              </label>
              <label><span>From</span>
                <input type="date" value={scope.date_from} onChange={(event) => setScope({ ...scope, date_from: event.target.value })} />
              </label>
              <label><span>To</span>
                <input type="date" value={scope.date_to} onChange={(event) => setScope({ ...scope, date_to: event.target.value })} />
              </label>
            </div>
          </fieldset>

          <fieldset>
            <legend>When you press Create</legend>
            <label className="report-toggle">
              <input
                type="checkbox"
                checked={generate}
                disabled={questionCount === 0}
                onChange={(event) => setGenerate(event.target.checked)}
              />
              <span>
                <strong>
                  <Sparkles aria-hidden="true" /> Answer the {questionCount || "standard"} questions from live data now
                </strong>
                <small>
                  {questionCount === 0
                    ? "This template has no standard questions — you will add evidence yourself."
                    : "Zara runs them through the governed queries and writes the report. This takes a minute."}
                </small>
              </span>
            </label>
            <label className="report-toggle">
              <input type="checkbox" checked={recommendations} onChange={(event) => setRecommendations(event.target.checked)} />
              <span>
                <strong>Include recommendations</strong>
                <small>Clearly labelled as recommendations, kept separate from observed facts.</small>
              </span>
            </label>
          </fieldset>

          <div className="report-new-actions">
            <button type="button" onClick={() => setStep(1)}><ArrowLeft aria-hidden="true" /> Back</button>
            <button type="button" onClick={onCancel}>Cancel</button>
            <button type="submit" className="primary" disabled={busy}>
              {busy ? <Loader2 className="is-spinning" aria-hidden="true" /> : <FileText aria-hidden="true" />}
              {busy ? "Working…" : generate ? "Create and generate" : "Create report"}
            </button>
          </div>
        </>
      )}
    </form>
  );
}
