import { ArrowUpRight, FileText, LayoutTemplate, MessageSquareQuote, X } from "lucide-react";

/**
 * "Generate Report" no longer sends a prompt to the chat assistant.
 *
 * It used to build a sentence and ask the assistant to answer it, which
 * produced a normal chat reply the user could not preview, edit, save or
 * export. Reports are now persistent objects, so this drawer is a launcher:
 * it hands the current dashboard scope to Report Studio, which owns the real
 * workflow.
 */

const START_POINTS = [
  {
    id: "template",
    icon: LayoutTemplate,
    title: "Use a template",
    detail: "Executive summary, sprint performance, risk and action, weekly update, or DORA performance.",
    href: "/reports?start=template",
  },
  {
    id: "chat",
    icon: MessageSquareQuote,
    title: "Build from chat",
    detail: "Combine answers you have already received — from several messages and several conversations.",
    href: "/reports?start=chat",
  },
  {
    id: "blank",
    icon: FileText,
    title: "Start blank",
    detail: "An empty report you structure yourself, block by block.",
    href: "/reports?start=blank",
  },
];

function scopeQuery(scope = {}) {
  const params = new URLSearchParams();
  for (const key of ["project", "squad", "sprint", "release", "date_from", "date_to"]) {
    if (scope[key]) params.set(key, scope[key]);
  }
  const query = params.toString();
  return query ? `&${query}` : "";
}

export default function ReportGenerationDrawer({ open, scope, onClose }) {
  if (!open) return null;
  const suffix = scopeQuery(scope);
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
          <h3>Current context</h3>
          <div className="report-scope-chips">
            {Object.entries(scope || {})
              .filter(([, value]) => value && typeof value !== "object")
              .map(([key, value]) => (
                <span key={key}>{key.replaceAll("_", " ")}: {String(value)}</span>
              ))}
          </div>
        </section>

        <section>
          <h3>Choose a starting point</h3>
          <div className="report-type-list">
            {START_POINTS.map(({ id, icon: Icon, title, detail, href }) => (
              <a key={id} href={`${href}${suffix}`}>
                <Icon aria-hidden="true" />
                <span><strong>{title}</strong><small>{detail}</small></span>
                <ArrowUpRight aria-hidden="true" />
              </a>
            ))}
          </div>
        </section>

        <p className="report-drawer-note">
          Reports are saved, so you can edit them, refresh their evidence and export a PDF later —
          they are not chat answers.
        </p>
      </aside>
    </div>
  );
}
