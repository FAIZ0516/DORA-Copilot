export default function DataTable({ table }) {
  if (!table?.rows?.length || !table?.columns?.length) return null;
  return (
    <div className="data-table-card">
      <div className="data-table-heading">
        <strong>{table.title}</strong>
        <span>{table.rows.length} displayed{table.truncated ? " · limited" : ""}</span>
      </div>
      <div className="data-table-scroll">
        <table>
          <thead>
            <tr>
              {table.columns.map((column) => <th key={column.key}>{column.label}</th>)}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, index) => (
              <tr key={index}>
                {table.columns.map((column) => (
                  <td key={column.key}>
                    {row[column.key] == null ? "—" : String(row[column.key])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
