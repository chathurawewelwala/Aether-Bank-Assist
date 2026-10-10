const DOCS = [
  { name: "Payment gateway runbook", type: "runbook", dept: "Payments" },
  { name: "Payment outage INC-2025-0312", type: "incident", dept: "Payments" },
  { name: "UPI failures INC-2024-1122", type: "incident", dept: "Payments" },
  { name: "Settlement delay INC-2025-0108", type: "incident", dept: "Payments" },
  { name: "Payments architecture v3.2", type: "architecture", dept: "Payments" },
  { name: "Data access policy", type: "policy", dept: "Security" },
];

export function KnowledgePage() {
  return (
    <div className="page">
      <header className="page-header">
        <h1>Knowledge base</h1>
        <p>Indexed documents available to Aether Assistant (filtered by your role).</p>
      </header>
      <div className="table-card">
        <table>
          <thead>
            <tr>
              <th>Document</th>
              <th>Type</th>
              <th>Department</th>
            </tr>
          </thead>
          <tbody>
            {DOCS.map((d) => (
              <tr key={d.name}>
                <td>{d.name}</td>
                <td>
                  <span className="tag">{d.type}</span>
                </td>
                <td>{d.dept}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
