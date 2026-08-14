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
}
