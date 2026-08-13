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
  Wand2,
} from "lucide-react";
import {
  addSection,
  addSource,
  composeReport,
  generateReport,
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
import NewReport from "./NewReport";
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

function ReportEditor({ report, busy, notice, onBack, onPatch, onSection, onMove, onRemove, onAdd, onCompose, onGenerate, onValidate, onExport, onExportCsv, onDuplicate }) {
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
          <button type="button" onClick={onGenerate} disabled={busy} title="Answer this template's standard questions from live data">
            {busy ? <Loader2 className="is-spinning" aria-hidden="true" /> : <Wand2 aria-hidden="true" />} Refresh from data
          </button>
          <button type="button" onClick={onCompose} disabled={busy} title="Rewrite the narrative from the attached evidence">
            <Sparkles aria-hidden="true" /> Rewrite text
          </button>
          <button type="button" onClick={onDuplicate} disabled={busy}><Copy aria-hidden="true" /> Duplicate</button>
          <button type="button" className="primary" onClick={() => onExport("pdf")} disabled={busy}><Download aria-hidden="true" /> Export PDF</button>
          <button type="button" onClick={() => onExport("docx")} disabled={busy}>DOCX</button>
        </div>
      </header>

      {notice && <div className={`report-notice report-notice--${notice.tone}`} role="status">{notice.text}</div>}

      {report.sources.length === 0 && report.template !== "blank" && (
        <div className="report-fill-prompt">
          <div>
            <strong>This report has no data yet</strong>
            <p>
              Answer its standard questions from {scopeLine(report.scope)} and Zara will write
              every section for you. You can edit anything afterwards.
            </p>
          </div>
          <button type="button" className="primary" onClick={onGenerate} disabled={busy}>
            {busy ? <Loader2 className="is-spinning" aria-hidden="true" /> : <Wand2 aria-hidden="true" />}
            {busy ? "Generating…" : "Fill from live data"}
          </button>
        </div>
      )}

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
  // The launcher links to /reports?start=template|chat|blank. Without this the
  // three options all landed on the same library screen.
  // Three entry shapes, all from the launcher:
  //   ?create=<template>  one click -> create, generate from live data, open it
  //   ?start=chat|blank   the author-it-yourself paths
  //   /reports/<id>       a deep link straight to one report
  const params = typeof window === "undefined" ? null : new URLSearchParams(window.location.search);
  const startMode = params?.get("start") || "";
  const autoTemplate = params?.get("create") || "";
  const deepLinkId = typeof window === "undefined"
    ? ""
    : (window.location.pathname.match(/\/reports\/([0-9a-f-]{36})/i)?.[1] || "");
  const scopeFromQuery = Object.fromEntries(
    ["project", "squad", "sprint", "release", "date_from", "date_to"]
      .map((key) => [key, params?.get(key) || ""])
      .filter(([, value]) => value),
  );
  const [view, setView] = useState(startMode || autoTemplate || deepLinkId ? "new" : "library");
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

  const [pending, setPending] = useState(false);
  const [autoRan, setAutoRan] = useState(false);

  // A deep link opens that report directly instead of the library.
  useEffect(() => {
    if (status !== "ready" || !deepLinkId || autoRan) return;
    setAutoRan(true);
    open(deepLinkId);
  }, [status, deepLinkId, autoRan]); // eslint-disable-line react-hooks/exhaustive-deps

  // ?create=<template> is the whole journey in one click: no form, no choices.
  useEffect(() => {
    if (status !== "ready" || !autoTemplate || autoRan || !catalogue) return;
    const template = catalogue.templates?.find((item) => item.id === autoTemplate);
    if (!template) return;
    setAutoRan(true);
    create(
      {
        template: autoTemplate,
        title: template.default_title,
        audience: template.default_audience,
        tone: template.default_tone,
        detail_level: "standard",
        include_recommendations: true,
        scope: scopeFromQuery,
      },
      { generate: (template.questions?.length || 0) > 0 },
    );
  }, [status, autoTemplate, autoRan, catalogue]); // eslint-disable-line react-hooks/exhaustive-deps

  // An "add this answer to a report" hand-off from the chat lands here.
  useEffect(() => {
    if (status !== "ready") return;
    const handed = takePendingSource();
    if (!handed) return;
    setPending(true);
    setView("new");
    window.sessionStorage.setItem("zara-pending-source", JSON.stringify(handed));
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

  async function create(payload, { generate = false } = {}) {
    setBusy(true);
    setNotice(generate ? { tone: "info", text: "Answering the template questions from live data…" } : null);
    try {
      const created = await createReport(payload);
      const attached = await attachPending(created.id);
      setReport(attached || created);
      setView("editor");
      setPending(false);
      if (generate) {
        // The template's fixed questions are answered now, so the report is
        // filled from whatever the data currently says.
        const result = await generateReport(created.id);
        setReport(result.report);
        setNotice(
          result.warnings?.length
            ? { tone: "warn", text: result.warnings.join(" ") }
            : { tone: "info", text: `Report generated from ${result.report.sources.length} evidence sources.` },
        );
      }
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
    if ((autoTemplate || deepLinkId) && !report) {
      return (
        <div className="report-empty" role="status">
          <Loader2 className="is-spinning" aria-hidden="true" />
          <strong>{autoTemplate ? "Building your report" : "Opening your report"}</strong>
          <p>
            {autoTemplate
              ? "Zara is answering this report's standard questions from today's data. This takes about a minute."
              : "Loading the saved report."}
          </p>
        </div>
      );
    }
    if (view === "new") {
      return (
        <NewReport
          catalogue={catalogue}
          start={startMode}
          initialScope={scopeFromQuery}
          pending={pending}
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
          onGenerate={() => run(async () => {
            const result = await generateReport(report.id);
            setNotice(
              result.warnings?.length
                ? { tone: "warn", text: result.warnings.join(" ") }
                : { tone: "info", text: "Report refreshed from live data." },
            );
            return result;
          })}
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
  }, [view, report, reports, status, error, busy, notice, catalogue, pending, startMode, autoTemplate, deepLinkId]); // eslint-disable-line react-hooks/exhaustive-deps

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
