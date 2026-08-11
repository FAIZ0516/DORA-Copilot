/**
 * Client-side CSV export for tables the workspace already holds in memory.
 *
 * The Export buttons in the preview and data drawers were rendered without a
 * handler, so they looked available but did nothing when clicked. The rows are
 * already loaded to draw the table, so exporting needs no backend round trip.
 */

function escapeCell(value: unknown): string {
  if (value == null) return "";
  let text = typeof value === "object" ? JSON.stringify(value) : String(value);
  // Prevent spreadsheet programs from evaluating database text as a formula.
  // Numeric values remain numeric; only string/object cells need neutralising.
  if (typeof value !== "number" && /^[=+\-@]/.test(text)) text = `'${text}`;
  // Quote when the value could otherwise break the row or column structure.
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

export function toCsv(columns: string[], rows: Record<string, unknown>[]): string {
  const header = columns.map(escapeCell).join(",");
  const body = rows.map((row) => columns.map((column) => escapeCell(row[column])).join(","));
  return [header, ...body].join("\r\n");
}

export function downloadCsv(
  filename: string,
  columns: string[],
  rows: Record<string, unknown>[],
): void {
  // The BOM keeps Excel from mangling non-ASCII squad and summary text.
  const blob = new Blob(["\uFEFF", toCsv(columns, rows)], {
    type: "text/csv;charset=utf-8;",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename.endsWith(".csv") ? filename : `${filename}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function safeFilename(value: string, fallback = "zara-export"): string {
  const cleaned = value.trim().replaceAll(/[^\w.-]+/g, "-").replace(/^-+|-+$/g, "");
  return cleaned || fallback;
}
