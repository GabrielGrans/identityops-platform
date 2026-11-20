import { t } from "../i18n";
import { Panel, QueryState } from "./common";
import { useQuery } from "./data";

interface DepartmentCount {
  name: string | null; official: string | null; employees: number | null; policies: string[];
}
interface DepartmentCatalog {
  local: (DepartmentCount & { id: number })[];
  entra: (DepartmentCount & { key: string })[];
}

export function DepartmentOperations({ token, revision }: { token: string; revision: number }) {
  const result = useQuery<DepartmentCatalog>(token, "/departments/operations/catalog", revision);
  return <Panel title={t("Department inventory and policies")}>
    <QueryState result={result}>{catalog => <>
      <h3>{t("Local IdentityOps")}</h3>
      <ul className="iam-list">{catalog.local.map(row => <DepartmentRow key={row.id} row={row} />)}</ul>
      <h3>Microsoft Entra ID</h3>
      {catalog.entra.length ? <ul className="iam-list">{catalog.entra.map(row => <DepartmentRow key={row.key} row={row} />)}</ul>
        : <p>{t("No synchronized departments available.")}</p>}
    </>}</QueryState>
  </Panel>;
}

function DepartmentRow({ row }: { row: DepartmentCount }) {
  return <li><div>
    <strong>{row.name ?? t("Unassigned department")}</strong>
    {row.official && <p>{t("Official department")}: {row.official}</p>}
    <p>{t("Employees")}: {row.employees ?? "—"}</p>
    <p>{t("Linked policies")}: {row.policies.join(", ") || "—"}</p>
  </div></li>;
}
