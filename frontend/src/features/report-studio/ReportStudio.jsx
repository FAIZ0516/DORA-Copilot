import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  CheckCircle2,
  ClipboardList,
  Copy,
  Download,
  Eye,
  EyeOff,
  FileText,
  Loader2,
  Plus,
  RefreshCw,
  Sparkles,
  Trash2,
} from "lucide-react";
import {
  addSection,
  addSource,
  composeReport,
  createReport,
  deleteSection,
  duplicateReport,
  exportReport,
  getReport,
  listReports,
  listTemplates,
  reorderSections,
  takePendingSource,
  updateReport,
  updateSection,
  validateReport,
} from "../../services/reports";
import "./report-studio.css";

/**
 * Report Studio.
 *
 * A report is a persistent object, not a chat answer: it is loaded from and
 * saved to the backend, so it survives a refresh and can combine evidence from
 * several conversations. This page owns three views -- the library, the
 * new-report chooser, and the editor.
 */

const CLASSIFICATION_LABEL = {
  observed_fact: "Observed fact",
  interpretation: "Interpretation",
  recommendation: "Recommendation",
  user_authored: "Author's note",
};

const ADDABLE_BLOCKS = [
  ["rich_text", "Text"],
  ["key_finding", "Key finding"],
  ["kpi_group", "KPI group"],
  ["risk", "Risk"],
  ["recommendation", "Recommendation"],
  ["action_list", "Action list"],
  ["data_quality", "Data quality note"],
  ["scope_limitation", "Scope limitation"],
  ["page_break", "Page break"],
];

const label = (value) => String(value || "").replaceAll("_", " ");

function scopeLine(scope = {}) {
  const parts = [
    scope.project ? `Project ${scope.project}` : null,
    scope.squad ? `Squad ${scope.squad}` : "All squads",
    scope.sprint ? `Sprint ${scope.sprint}` : null,
    scope.release ? `Release ${scope.release}` : null,
  ].filter(Boolean);
  if (scope.date_from || scope.date_to) {
    parts.push(`${scope.date_from || "start"} → ${scope.date_to || "today"}`);
  }
  return parts.join(" · ");
}

function StatusPill({ status }) {
  return <span className={`report-status report-status--${status}`}>{label(status)}</span>;
}

/* ------------------------------------------------------------------ */
/* Library                                                            */
/* ------------------------------------------------------------------ */

function ReportLibrary({ reports, status, error, onOpen, onNew, onDuplicate, onRetry }) {
  if (status === "loading") {
    return (
      <div className="report-empty" role="status">
        <Loader2 className="is-spinning" aria-hidden="true" />
        <p>Loading your reports…</p>
      </div>
    );
  }
  if (status === "error") {
    return (
      <div className="report-empty" role="alert">
        <AlertTriangle aria-hidden="true" />
        <strong>Your reports could not be loaded.</strong>
        <p>{error}</p>
        <button type="button" onClick={onRetry}>Try again</button>
      </div>
    );
  }
  if (!reports.length) {
    return (
      <div className="report-empty">
        <ClipboardList aria-hidden="true" />
        <strong>No reports yet</strong>
        <p>Start from a template, or add an answer to a report from any conversation.</p>
        <button type="button" className="primary" onClick={onNew}>
          <Plus aria-hidden="true" /> New report
        </button>
      </div>
    );
  }
  return (
    <div className="report-library">
      {reports.map((report) => (
        <article key={report.id} className="report-card">
          <header>
            <h3>{report.title}</h3>
            <StatusPill status={report.status} />
          </header>
          <p className="report-card-scope">{scopeLine(report.scope)}</p>
          <dl>
            <div><dt>Template</dt><dd>{label(report.template)}</dd></div>
            <div><dt>Sections</dt><dd>{report.section_count}</dd></div>
            <div><dt>Evidence</dt><dd>{report.source_count} source{report.source_count === 1 ? "" : "s"}</dd></div>
            <div><dt>Version</dt><dd>v{report.version}</dd></div>
            <div><dt>Edited</dt><dd>{new Date(report.updated_at).toLocaleString()}</dd></div>
            <div>
              <dt>Data</dt>
              <dd>{report.freshness?.stale ? "May be outdated" : "Current"}</dd>
            </div>
          </dl>
          <footer>
            <button type="button" className="primary" onClick={() => onOpen(report.id)}>Open</button>
            <button type="button" onClick={() => onDuplicate(report.id)}>
              <Copy aria-hidden="true" /> Duplicate
            </button>
          </footer>
        </article>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* New report                                                         */
/* ------------------------------------------------------------------ */

function NewReport({ catalogue, onCreate, onCancel, busy }) {
  const [template, setTemplate] = useState("executive_summary");
  const [title, setTitle] = useState("");
  const [audience, setAudience] = useState("senior_leadership");
  const [tone, setTone] = useState("executive");
  const [detail, setDetail] = useState("standard");
  const [recommendations, setRecommendations] = useState(true);
  const [scope, setScope] = useState({ project: "DCPM", squad: "", sprint: "", release: "", date_from: "", date_to: "" });

  const chosen = catalogue?.templates?.find((item) => item.id === template);
  useEffect(() => {
    if (!chosen) return;
    setTitle(chosen.default_title);
    setAudience(chosen.default_audience);
    setTone(chosen.default_tone);
  }, [template]); // eslint-disable-line react-hooks/exhaustive-deps

  function submit(event) {
    event.preventDefault();
    const cleaned = Object.fromEntries(Object.entries(scope).filter(([, value]) => value));
    onCreate({
      template,
      title: title || chosen?.default_title,
      audience,
      tone,
      detail_level: detail,
      include_recommendations: recommendations,
      scope: cleaned,
    });
  }

  return (
    <form className="report-new" onSubmit={submit}>
      <fieldset>
        <legend>Start from</legend>
        <div className="report-template-grid">
          {(catalogue?.templates || []).map((item) => (
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
              <em>{item.section_count} section{item.section_count === 1 ? "" : "s"}</em>
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset>
        <legend>Configure</legend>
        <div className="report-config-grid">
          <label><span>Report title</span>
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
          <label className="report-checkbox">
            <input type="checkbox" checked={recommendations} onChange={(event) => setRecommendations(event.target.checked)} />
            <span>Include recommendations</span>
          </label>
        </div>
      </fieldset>

      <div className="report-new-actions">
        <button type="button" onClick={onCancel}>Cancel</button>
        <button type="submit" className="primary" disabled={busy}>
          {busy ? <Loader2 className="is-spinning" aria-hidden="true" /> : <FileText aria-hidden="true" />}
          Create report
        </button>
      </div>
    </form>
  );
}

/* ------------------------------------------------------------------ */
/* Editor                                                             */
/* ------------------------------------------------------------------ */

function SectionBlock({ section, index, total, busy, onChange, onMove, onToggle, onRemove, onExportCsv }) {
  const [draft, setDraft] = useState(section.content);
  const [editing, setEditing] = useState(false);
  useEffect(() => { setDraft(section.content); }, [section.content]);

  const tabular = section.type === "data_table" || section.type === "chart" || section.type === "kpi_group";

  return (
    <article className={`report-block ${section.visible ? "" : "is-hidden"}`} data-type={section.type}>
      <header>
        <div>
          <span className="report-block-type">{label(section.type)}</span>
          <h4>{section.title || label(section.type)}</h4>
        </div>
        <div className="report-block-actions">
          <button type="button" onClick={() => onMove(index, -1)} disabled={index === 0 || busy} aria-label={`Move ${section.title || section.type} up`}><ArrowUp aria-hidden="true" /></button>
          <button type="button" onClick={() => onMove(index, 1)} disabled={index === total - 1 || busy} aria-label={`Move ${section.title || section.type} down`}><ArrowDown aria-hidden="true" /></button>
          <button type="button" onClick={() => onToggle(section)} aria-label={section.visible ? `Hide ${section.title || section.type}` : `Show ${section.title || section.type}`}>
            {section.visible ? <Eye aria-hidden="true" /> : <EyeOff aria-hidden="true" />}
          </button>
          {tabular && (
            <button type="button" onClick={() => onExportCsv(section)} aria-label={`Export ${section.title || section.type} as CSV`}>
              <Download aria-hidden="true" />
            </button>
          )}
          <button type="button" className="danger" onClick={() => onRemove(section)} aria-label={`Delete ${section.title || section.type}`}><Trash2 aria-hidden="true" /></button>
        </div>
      </header>

      <div className="report-block-flags">
        <span className={`report-classification report-classification--${section.content_classification}`}>
          {CLASSIFICATION_LABEL[section.content_classification] || label(section.content_classification)}
        </span>
        {section.source_ids?.length > 0 && <span className="report-flag">{section.source_ids.length} source{section.source_ids.length === 1 ? "" : "s"}</span>}
        {section.manually_edited && <span className="report-flag">Edited by hand</span>}
        {section.needs_review && <span className="report-flag report-flag--warn">Needs review — not re-verified</span>}
        {section.content_mode !== "rewrite" && <span className="report-flag">{label(section.content_mode)}</span>}
      </div>

      {section.type !== "page_break" && (
        editing ? (
          <div className="report-block-editor">
            <textarea
              value={draft}
              rows={6}
              aria-label={`Edit ${section.title || section.type}`}
              onChange={(event) => setDraft(event.target.value)}
            />
            <div>
              <button type="button" onClick={() => { setDraft(section.content); setEditing(false); }}>Cancel</button>
              <button type="button" className="primary" disabled={busy} onClick={() => { onChange(section, draft); setEditing(false); }}>Save section</button>
            </div>
          </div>
        ) : (
          <div className="report-block-body">
            {section.content
              ? section.content.split("\n").filter(Boolean).map((line, i) => <p key={i}>{line}</p>)
              : <p className="report-placeholder">Not written yet.</p>}
            {section.payload?.rows?.length > 0 && (
              <p className="report-placeholder">{section.payload.rows.length} rows of supporting data.</p>
            )}
            {section.payload?.data?.length > 0 && (
              <p className="report-placeholder">{section.payload.data.length} plotted values.</p>
            )}
            <button type="button" onClick={() => setEditing(true)}>Edit section</button>
          </div>
        )
      )}
    </article>
  );
}

function ReportEditor({ report, busy, notice, onBack, onPatch, onSection, onMove, onRemove, onAdd, onCompose, onValidate, onExport, onExportCsv, onDuplicate }) {
  const visible = report.sections.filter((section) => section.visible);
  return (
    <div className="report-editor">
      <header className="report-editor-header">
        <button type="button" onClick={onBack}><ArrowLeft aria-hidden="true" /> All reports</button>
        <div className="report-editor-title">
          <input
            value={report.title}
            aria-label="Report title"
            maxLength={200}
            onChange={(event) => onPatch({ title: event.target.value })}
          />
          <div className="report-editor-meta">
            <StatusPill status={report.status} />
            <span>v{report.version}</span>
            <span>{scopeLine(report.scope)}</span>
            <span>{report.freshness?.stale ? `Data may be outdated — ${report.freshness.reason}` : "Data current"}</span>
          </div>
        </div>
        <div className="report-editor-actions">
          <button type="button" onClick={onValidate} disabled={busy}><CheckCircle2 aria-hidden="true" /> Validate</button>
          <button type="button" onClick={onCompose} disabled={busy}>
            {busy ? <Loader2 className="is-spinning" aria-hidden="true" /> : <Sparkles aria-hidden="true" />} Generate text
          </button>
          <button type="button" onClick={onDuplicate} disabled={busy}><Copy aria-hidden="true" /> Duplicate</button>
          <button type="button" className="primary" onClick={() => onExport("pdf")} disabled={busy}><Download aria-hidden="true" /> Export PDF</button>
          <button type="button" onClick={() => onExport("docx")} disabled={busy}>DOCX</button>
        </div>
      </header>

      {notice && <div className={`report-notice report-notice--${notice.tone}`} role="status">{notice.text}</div>}

      {report.conflicts?.length > 0 && (
        <div className="report-conflicts" role="alert">
          <AlertTriangle aria-hidden="true" />
          <div>
            <strong>Scope differences between sources</strong>
            {report.conflicts.map((conflict) => <p key={conflict.field}>{conflict.message}</p>)}
          </div>
        </div>
      )}

      {report.validation?.issues?.length > 0 && (
        <div className="report-conflicts report-conflicts--info" role="status">
          <ClipboardList aria-hidden="true" />
          <div>
            <strong>Validation</strong>
            {report.validation.issues.map((issue) => <p key={issue}>{issue}</p>)}
          </div>
        </div>
      )}

      <div className="report-editor-body">
        <nav className="report-navigator" aria-label="Report sections">
          <h3>Sections</h3>
          <ol>
            {report.sections.map((section) => (
              <li key={section.id} className={section.visible ? "" : "is-hidden"}>
                <a href={`#section-${section.id}`}>{section.title || label(section.type)}</a>
              </li>
            ))}
          </ol>
          <h3>Evidence</h3>
          {report.sources.length === 0 ? (
            <p className="report-placeholder">No sources yet. Use “Add to report” on a Zara answer.</p>
          ) : (
            <ul className="report-source-list">
              {report.sources.map((source) => (
                <li key={source.id}>
                  <strong>{source.label}</strong>
                  <small>{scopeLine(source.scope)}</small>
                  {source.query_ids?.length > 0 && <small>{source.query_ids.length} approved quer{source.query_ids.length === 1 ? "y" : "ies"}</small>}
                </li>
              ))}
            </ul>
          )}
          <h3>Add a block</h3>
          <div className="report-add-blocks">
            {ADDABLE_BLOCKS.map(([type, text]) => (
              <button key={type} type="button" disabled={busy} onClick={() => onAdd(type, text)}>
                <Plus aria-hidden="true" /> {text}
              </button>
            ))}
          </div>
        </nav>

        <main className="report-preview" aria-label="Report preview">
          <div className="report-page">
            <p className="report-page-brand">DORA COPILOT · ZARA</p>
            <h1>{report.title}</h1>
            <p className="report-page-scope">{scopeLine(report.scope)}</p>
            <p className="report-page-meta">
              Version v{report.version} · {visible.length} visible section{visible.length === 1 ? "" : "s"} ·{" "}
              {report.data_as_of ? `Data as of ${new Date(report.data_as_of).toLocaleString()}` : "No evidence attached"}
            </p>
          </div>
          {report.sections.map((section, index) => (
            <div id={`section-${section.id}`} key={section.id}>
              <SectionBlock
                section={section}
                index={index}
                total={report.sections.length}
                busy={busy}
                onChange={onSection}
                onMove={onMove}
                onToggle={(target) => onPatch(null, target, { visible: !target.visible })}
                onRemove={onRemove}
                onExportCsv={onExportCsv}
              />
            </div>
          ))}
        </main>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Page                                                               */
/* ------------------------------------------------------------------ */

export default function ReportStudio() {
  const [view, setView] = useState("library");
  const [catalogue, setCatalogue] = useState(null);
  const [reports, setReports] = useState([]);
  const [report, setReport] = useState(null);
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);

  const refreshLibrary = useCallback(async () => {
    setStatus("loading");
    try {
      const [templates, library] = await Promise.all([listTemplates(), listReports()]);
      setCatalogue(templates);
      setReports(library.reports || []);
      setStatus("ready");
    } catch (failure) {
      setError(failure.message);
      setStatus("error");
    }
  }, []);

  useEffect(() => { refreshLibrary(); }, [refreshLibrary]);

  // A "add this answer to a report" hand-off from the chat lands here.
  useEffect(() => {
    if (status !== "ready") return;
    const pending = takePendingSource();
    if (!pending) return;
    setView("new");
    setNotice({ tone: "info", text: "Create or open a report to attach the selected answer." });
    window.sessionStorage.setItem("zara-pending-source", JSON.stringify(pending));
  }, [status]);

  const attachPending = useCallback(async (reportId) => {
    const raw = window.sessionStorage.getItem("zara-pending-source");
    if (!raw) return null;
    window.sessionStorage.removeItem("zara-pending-source");
    try {
      return await addSource(reportId, JSON.parse(raw));
    } catch (failure) {
      setNotice({ tone: "warn", text: `The answer could not be attached: ${failure.message}` });
      return null;
    }
  }, []);

  async function open(reportId) {
    setBusy(true);
    try {
      const attached = await attachPending(reportId);
      setReport(attached || (await getReport(reportId)));
      setView("editor");
      setNotice(attached ? { tone: "info", text: "The selected answer was added as evidence." } : null);
    } catch (failure) {
      setNotice({ tone: "warn", text: failure.message });
    } finally {
      setBusy(false);
    }
  }

  async function create(payload) {
    setBusy(true);
    try {
      const created = await createReport(payload);
      const attached = await attachPending(created.id);
      setReport(attached || created);
      setView("editor");
      setNotice(null);
      refreshLibrary();
    } catch (failure) {
      setNotice({ tone: "warn", text: failure.message });
    } finally {
      setBusy(false);
    }
  }

  // Debounced title/metadata patching, and section-level patching.
  const patch = useCallback(async (reportFields, section = null, sectionFields = null) => {
    if (!report) return;
    if (section && sectionFields) {
      setReport(await updateSection(report.id, section.id, sectionFields));
      return;
    }
    setReport((current) => ({ ...current, ...reportFields }));
    try {
      const saved = await updateReport(report.id, reportFields);
      setReport(saved);
    } catch (failure) {
      setNotice({ tone: "warn", text: failure.message });
    }
  }, [report]);

  async function run(action, message) {
    setBusy(true);
    try {
      const next = await action();
      if (next) setReport(next.report || next);
      if (message) setNotice({ tone: "info", text: message });
      refreshLibrary();
      return next;
    } catch (failure) {
      setNotice({ tone: "warn", text: failure.message });
      return null;
    } finally {
      setBusy(false);
    }
  }

  const move = useCallback(async (index, delta) => {
    if (!report) return;
    const order = report.sections.map((section) => section.id);
    const target = index + delta;
    if (target < 0 || target >= order.length) return;
    [order[index], order[target]] = [order[target], order[index]];
    await run(() => reorderSections(report.id, order));
  }, [report]); // eslint-disable-line react-hooks/exhaustive-deps

  const body = useMemo(() => {
    if (view === "new") {
      return (
        <NewReport
          catalogue={catalogue}
          busy={busy}
          onCreate={create}
          onCancel={() => { setView("library"); setNotice(null); }}
        />
      );
    }
    if (view === "editor" && report) {
      return (
        <ReportEditor
          report={report}
          busy={busy}
          notice={notice}
          onBack={() => { setView("library"); setReport(null); setNotice(null); refreshLibrary(); }}
          onPatch={patch}
          onSection={(section, content) => run(() => updateSection(report.id, section.id, { content }), "Section saved.")}
          onMove={move}
          onRemove={(section) => {
            if (!window.confirm(`Delete “${section.title || label(section.type)}”? This cannot be undone.`)) return;
            run(() => deleteSection(report.id, section.id), "Section deleted.");
          }}
          onAdd={(type, text) => run(() => addSection(report.id, { type, title: text }), `${text} block added.`)}
          onCompose={() => run(async () => {
            const result = await composeReport(report.id);
            const warnings = result.warnings || [];
            setNotice(
              warnings.length
                ? { tone: "warn", text: warnings.join(" ") }
                : { tone: "info", text: `${result.updated_sections.length} section(s) written from the attached evidence.` },
            );
            return result;
          })}
          onValidate={() => run(() => validateReport(report.id), null)}
          onExport={(format) => run(async () => {
            const name = await exportReport(report.id, format);
            setNotice({ tone: "info", text: `Downloaded ${name}.` });
            return getReport(report.id);
          })}
          onExportCsv={(section) => run(async () => {
            const name = await exportReport(report.id, "csv", section.id);
            setNotice({ tone: "info", text: `Downloaded ${name}.` });
            return null;
          })}
          onDuplicate={() => run(async () => {
            const copy = await duplicateReport(report.id);
            setNotice({ tone: "info", text: `Created “${copy.title}”.` });
            return copy;
          })}
        />
      );
    }
    return (
      <ReportLibrary
        reports={reports}
        status={status}
        error={error}
        onOpen={open}
        onNew={() => setView("new")}
        onRetry={refreshLibrary}
        onDuplicate={(id) => run(() => duplicateReport(id), "Report duplicated.")}
      />
    );
  }, [view, report, reports, status, error, busy, notice, catalogue]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <main className="report-studio">
      <header className="report-studio-header">
        <a className="report-back" href="/" aria-label="Return to DORA Copilot"><ArrowLeft aria-hidden="true" /></a>
        <div>
          <p>DORA Copilot</p>
          <h1>Report Studio</h1>
        </div>
        <div className="report-studio-actions">
          <button type="button" onClick={refreshLibrary} disabled={busy}><RefreshCw aria-hidden="true" /> Refresh</button>
          {view !== "new" && (
            <button type="button" className="primary" onClick={() => setView("new")}>
              <Plus aria-hidden="true" /> New report
            </button>
          )}
        </div>
      </header>
      {view === "library" && notice && (
        <div className={`report-notice report-notice--${notice.tone}`} role="status">{notice.text}</div>
      )}
      {body}
    </main>
  );
}
