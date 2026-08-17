<<<<<<< HEAD
/** Build the direct dashboard-to-Studio route from identifiers only.
 *
 * The server resolves every report value again. No rendered KPI or chart value
 * is included in this URL.
 */
export function reportStudioUrl(scope = {}) {
  const params = new URLSearchParams();
  for (const key of ["project", "squad", "sprint", "release", "date_from", "date_to", "feature", "issue_type", "status", "priority"]) {
    if (scope[key]) params.set(key, scope[key]);
  }
  params.set("start", "current");
  params.set("auto", "1");
  return `/reports?${params.toString()}`;
=======
import { useEffect, useState } from "react";
import { ArrowRight, FileText, Loader2, MessageSquareQuote, PenLine, X } from "lucide-react";
import { listTemplates } from "../services/reports";

/**
 * The report launcher.
 *
 * "Generate Report" used to build a sentence and post it to the chat endpoint,
 * producing an answer the user could not preview, edit, save or export.
 *
 * It also used to be a two-hop journey: pick "use a template", land on a
 * chooser, pick again, fill a form, then create. The templates are now listed
 * here directly, and one click creates the report, answers its standard
 * questions from live data and opens it ready to export -- no form, nothing to
 * write.
 */

function scopeQuery(scope = {}) {
  const params = new URLSearchParams();
  for (const key of ["project", "squad", "sprint", "release", "date_from", "date_to"]) {
    if (scope[key]) params.set(key, scope[key]);
  }
  return params;
}

export default function ReportGenerationDrawer({ open, scope, onClose }) {
  const [templates, setTemplates] = useState([]);
  const [status, setStatus] = useState("idle");

  useEffect(() => {
    if (!open || status !== "idle") return;
    setStatus("loading");
    listTemplates()
      .then((payload) => {
        // Only the ready-to-run report types belong here; "blank" is offered
        // separately because it is the one path that needs authoring.
        setTemplates((payload.templates || []).filter((item) => item.questions?.length));
        setStatus("ready");
      })
      .catch(() => setStatus("error"));
  }, [open, status]);

  useEffect(() => {
    if (!open) return undefined;
    function onKeyDown(event) { if (event.key === "Escape") onClose(); }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  function go(params) {
    const query = scopeQuery(scope);
    for (const [key, value] of Object.entries(params)) query.set(key, value);
    window.location.assign(`/reports?${query.toString()}`);
  }

  return (
    <div
      className="report-drawer-backdrop"
      onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}
    >
      <aside className="report-generation-drawer" role="dialog" aria-modal="true" aria-labelledby="report-drawer-title">
        <header>
          <span><FileText aria-hidden="true" /></span>
          <div>
            <p>Report Studio</p>
            <h2 id="report-drawer-title">Create a report</h2>
          </div>
          <button type="button" onClick={onClose} aria-label="Close report launcher"><X aria-hidden="true" /></button>
        </header>

        <section>
          <h3>Covering</h3>
          <div className="report-scope-chips">
            {Object.entries(scope || {})
              .filter(([, value]) => value && typeof value !== "object")
              .map(([key, value]) => <span key={key}>{key.replaceAll("_", " ")}: {String(value)}</span>)}
          </div>
        </section>

        <section>
          <h3>Generate now</h3>
          <p className="report-drawer-lead">
            Zara answers each report's standard questions from today's data and writes it for
            you. Nothing to fill in.
          </p>

          {status === "loading" && (
            <p className="report-drawer-note"><Loader2 className="is-spinning" aria-hidden="true" /> Loading report types…</p>
          )}
          {status === "error" && (
            <p className="report-drawer-note is-error">Report types could not be loaded. Check the backend is running.</p>
          )}

          <div className="report-type-list">
            {templates.map((template) => (
              <button
                key={template.id}
                type="button"
                onClick={() => go({ create: template.id })}
              >
                <span className="report-type-icon" aria-hidden="true"><FileText /></span>
                <span className="report-type-text">
                  <strong>{template.label}</strong>
                  <small>{template.description}</small>
                  <em>{template.questions.length} questions answered from live data</em>
                </span>
                <ArrowRight aria-hidden="true" />
              </button>
            ))}
          </div>
        </section>

        <section>
          <h3>Or build it yourself</h3>
          <div className="report-type-list report-type-list--secondary">
            <button type="button" onClick={() => go({ start: "chat" })}>
              <span className="report-type-icon" aria-hidden="true"><MessageSquareQuote /></span>
              <span className="report-type-text">
                <strong>From saved answers</strong>
                <small>Combine answers you have already received, across conversations.</small>
              </span>
              <ArrowRight aria-hidden="true" />
            </button>
            <button type="button" onClick={() => go({ start: "blank" })}>
              <span className="report-type-icon" aria-hidden="true"><PenLine /></span>
              <span className="report-type-text">
                <strong>Blank report</strong>
                <small>An empty report you structure block by block.</small>
              </span>
              <ArrowRight aria-hidden="true" />
            </button>
          </div>
        </section>

        <p className="report-drawer-note">
          Reports are saved. You can edit, refresh the evidence and export a PDF at any time.
        </p>
      </aside>
    </div>
  );
>>>>>>> d7a58633ffe37fc0be2f3b43ac9913145a90716f
}
