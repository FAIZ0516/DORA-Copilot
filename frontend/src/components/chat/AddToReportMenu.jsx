import { useEffect, useState } from "react";
import { ChevronDown, FilePlus2 } from "lucide-react";
import { addSource, listReports, stashPendingSource } from "../../services/reports";

/**
 * "Add to report" on an assistant answer.
 *
 * The answer is evidence, not report text: the backend snapshots its chart,
 * table, warnings, approved query ids and scope, so the report stays
 * reproducible even after this conversation is archived. That is why only the
 * conversation and message identifiers are sent — the server re-reads the
 * message under the caller's own identity rather than trusting anything the
 * browser copies out of it.
 */

const SELECTIONS = [
  ["full", "Whole response"],
  ["narrative", "Narrative only"],
  ["chart", "Chart only"],
  ["table", "Table only"],
  ["warnings", "Warnings only"],
];

const MODES = [
  ["rewrite", "Rewrite for report"],
  ["summarize", "Summarize"],
  ["original", "Keep original wording"],
];

export default function AddToReportMenu({ conversationId, messageId, hasChart, hasTable }) {
  const [open, setOpen] = useState(false);
  const [reports, setReports] = useState([]);
  const [status, setStatus] = useState("idle");
  const [selection, setSelection] = useState("full");
  const [mode, setMode] = useState("rewrite");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!open || status !== "idle") return;
    setStatus("loading");
    listReports()
      .then((payload) => { setReports(payload.reports || []); setStatus("ready"); })
      .catch((error) => { setMessage(error.message); setStatus("error"); });
  }, [open, status]);

  useEffect(() => {
    if (!open) return undefined;
    function onKeyDown(event) { if (event.key === "Escape") setOpen(false); }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open]);

  const available = SELECTIONS.filter(([value]) =>
    (value !== "chart" || hasChart) && (value !== "table" || hasTable));

  async function attach(reportId) {
    setStatus("saving");
    try {
      await addSource(reportId, {
        conversation_id: conversationId,
        message_id: messageId,
        selection,
        content_mode: mode,
      });
      setMessage("Added to the report.");
      setStatus("ready");
      window.setTimeout(() => { setOpen(false); setMessage(""); }, 1400);
    } catch (error) {
      setMessage(error.message);
      setStatus("error");
    }
  }

  function createNew() {
    // Report Studio owns creation, so hand the selection over and navigate.
    stashPendingSource({
      conversation_id: conversationId,
      message_id: messageId,
      selection,
      content_mode: mode,
    });
    window.location.assign("/reports?start=chat");
  }

  if (!conversationId || !messageId) return null;

  return (
    <div className={`add-to-report ${open ? "is-open" : ""}`}>
      <button
        type="button"
        aria-expanded={open}
        aria-haspopup="true"
        title="Add this answer to a report"
        onClick={() => setOpen((value) => !value)}
      >
        <FilePlus2 aria-hidden="true" />
        <span>Add to report</span>
        <ChevronDown aria-hidden="true" />
      </button>

      {open && (
        <>
          <button className="add-to-report-scrim" type="button" aria-label="Close" onClick={() => setOpen(false)} />
          <div className="add-to-report-menu" role="dialog" aria-label="Add this answer to a report">
            <label>
              <span>Include</span>
              <select value={selection} onChange={(event) => setSelection(event.target.value)}>
                {available.map(([value, text]) => <option key={value} value={value}>{text}</option>)}
              </select>
            </label>
            <label>
              <span>Wording</span>
              <select value={mode} onChange={(event) => setMode(event.target.value)}>
                {MODES.map(([value, text]) => <option key={value} value={value}>{text}</option>)}
              </select>
            </label>

            <p className="add-to-report-heading">Add to</p>
            {status === "loading" && <p className="add-to-report-note">Loading your reports…</p>}
            {status === "ready" && reports.length === 0 && (
              <p className="add-to-report-note">You have no reports yet.</p>
            )}
            <div className="add-to-report-list">
              {reports.map((report) => (
                <button key={report.id} type="button" disabled={status === "saving"} onClick={() => attach(report.id)}>
                  <strong>{report.title}</strong>
                  <small>{report.section_count} sections · {report.source_count} sources</small>
                </button>
              ))}
            </div>
            <button type="button" className="add-to-report-new" onClick={createNew}>
              <FilePlus2 aria-hidden="true" /> Create a new report from this answer
            </button>
            {message && (
              <p className={`add-to-report-note ${status === "error" ? "is-error" : ""}`} role="status">{message}</p>
            )}
          </div>
        </>
      )}
    </div>
  );
}
