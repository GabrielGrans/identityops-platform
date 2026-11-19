import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  Search,
  Users,
  RefreshCw,
} from "lucide-react";

import { EmployeeAccess, EmployeeForm, EmployeePasswordForm } from "./iam/EmployeeAdministration";
import { DirectoryPagination } from "./iam/DirectoryControls";
import { Feedback, Panel, QueryState } from "./iam/common";
import { employeeLabel, PAGE_SIZE, useMutation, useQuery } from "./iam/data";

import {
  ApiError,
  getEmployees,
  type Employee,
} from "./services/api";

interface EmployeesPageProps {
  token: string;
  employeeId: number;
}

function EmployeesPage({ token, employeeId }: EmployeesPageProps) {
  const permissions = useQuery<string[]>(token, "/auth/me/permissions");
  const mutation = useMutation(token);
  const [action, setAction] = useState<"new" | "view" | "edit" | "access" | "password">();
  const [selectedId, setSelectedId] = useState<number>();
  const [saved, setSaved] = useState(false);
  const [page, setPage] = useState(1);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Initial API request
  useEffect(() => {
    let active = true;

    async function fetchEmployees() {
      try {
        const data = await getEmployees(token);

        if (active) {
          setEmployees(data);
          setError("");
        }
      } catch (err) {
        if (!active) return;

        if (err instanceof ApiError && err.status === 401) {
          setError(
            "Your session may have expired. Please sign in again.",
          );
        } else {
          setError(
            err instanceof Error
              ? err.message
              : "Unable to load employees.",
          );
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    void fetchEmployees();

    return () => {
      active = false;
    };
  }, [token]);

  // Refresh employee records
  const loadEmployees = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      const data = await getEmployees(token);
      setEmployees(data);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError(
          "Your session may have expired. Please sign in again.",
        );
      } else {
        setError(
          err instanceof Error
            ? err.message
            : "Unable to load employees.",
        );
      }
    } finally {
      setLoading(false);
    }
  }, [token]);

  const filteredEmployees = useMemo(() => {
    const term = search.toLowerCase().trim();

    if (!term) {
      return employees;
    }

    return employees.filter((employee) =>
      [
        employee.employee_number,
        employee.first_name,
        employee.last_name,
        employee.email,
        employee.job_title,
        employee.status,
      ]
        .join(" ")
        .toLowerCase()
        .includes(term),
    );
  }, [employees, search]);

  const selected = employees.find(employee => employee.id === selectedId);
  const session = { token, employeeId, permissions: permissions.data ?? [] };
  const has = (code: string) => session.permissions.includes(code);
  const pages = Math.max(1, Math.ceil(filteredEmployees.length / PAGE_SIZE));
  const currentPage = Math.min(page, pages);
  const rows = filteredEmployees.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  async function changeStatus(employee: Employee) {
    const active = employee.status === "active";
    if (!window.confirm(`${active ? "Deactivate" : "Activate"} ${employeeLabel(employee)}?`)) return;
    const path = `/employees/${employee.id}`;
    if (await mutation.mutate(active ? path : `${path}/activate`, active ? "DELETE" : "POST")) await loadEmployees();
  }

  return (
    <section className="employees-page iam-page">
      <div className="employees-heading">
        <div>
          <div className="eyebrow">
            <span className="eyebrow-dot" />
            IDENTITY MANAGEMENT
          </div>

          <h1>Employees</h1>

          <p>
            Manage employee identities across your organization.
          </p>
        </div>

        <div className="iam-actions">
          {has("employees:create") && <button className="primary-button" onClick={() => { setSaved(false); setAction("new"); }}>New Employee</button>}
          <button
          className="secondary-button employees-refresh"
          onClick={() => void loadEmployees()}
          disabled={loading}
        >
          <RefreshCw size={15} />
          Refresh
          </button>
        </div>
      </div>

      <Feedback message={mutation.message} />
      {saved && <p role="status">Employee saved.</p>}
      {permissions.error && <p role="alert">Could not load administrative permissions.</p>}
      {(action === "new" && has("employees:create") || action === "edit" && selected && has("employees:update")) &&
        <EmployeeForm key={action === "new" ? "new" : selectedId} employee={action === "edit" ? selected : undefined}
          employees={employees} session={session} onClose={() => setAction(undefined)}
          onSaved={() => { setSaved(true); setAction(undefined); void loadEmployees(); }} />}
      {selected && action && action !== "edit" && action !== "new" && <Panel title={employeeLabel(selected)}>
        <div className="iam-actions">
          {has("employees:update") && <button className="secondary-button" onClick={() => { setSaved(false); setAction("edit"); }}>Edit Employee</button>}
          {has("access:manage") && <button className="secondary-button" onClick={() => setAction("access")}>Manage Access</button>}
          {has("employees:reset_password") && <button className="secondary-button" onClick={() => setAction("password")}>Set / Reset Password</button>}
          {has(selected.status === "active" ? "employees:deactivate" : "employees:update") &&
            <button className="secondary-button" disabled={mutation.busy} onClick={() => void changeStatus(selected)}>
              {selected.status === "active" ? "Deactivate" : "Activate"}
            </button>}
          <button className="secondary-button" onClick={() => setAction(undefined)}>Close details</button>
        </div>
        <EmployeeDetails id={selected.id} token={token} revision={mutation.revision} />
        {action === "access" && has("access:manage") && <EmployeeAccess key={selected.id} employee={selected} session={session} />}
        {action === "password" && has("employees:reset_password") &&
          <EmployeePasswordForm key={selected.id} employee={selected} token={token} onClose={() => setAction("view")} />}
      </Panel>}

      <div className="employees-summary">
        <div className="employees-summary-icon">
          <Users size={21} />
        </div>

        <div>
          <span>Total employees</span>
          <strong>{employees.length}</strong>
        </div>
      </div>

      <div className="panel employees-panel">
        <div className="employees-toolbar">
          <div>
            <h2>Employee directory</h2>
            <p>
              Employee records retrieved from IdentityOps API
            </p>
          </div>

          <label className="employees-search">
            <Search size={16} />

            <input
              type="search"
              aria-label="Search employees"
              placeholder="Search employees..."
              value={search}
              onChange={(event) => { setSearch(event.target.value); setPage(1); }}
            />
          </label>
        </div>

        {loading ? (
          <div className="employees-message">
            Loading employee records...
          </div>
        ) : error ? (
          <div
            className="employees-message employees-error"
            role="alert"
          >
            {error}
          </div>
        ) : filteredEmployees.length === 0 ? (
          <div className="employees-message">
            No employees found.
          </div>
        ) : (
          <div className="employees-table-wrap">
            <table className="employees-table">
              <thead>
                <tr>
                  <th>Employee</th>
                  <th>Employee ID</th>
                  <th>Job title</th>
                  <th>Department ID</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>

              <tbody>
                {rows.map((employee) => (
                  <tr key={employee.id}>
                    <td>
                      <div className="employee-cell">
                        <div className="employee-avatar">
                          {employee.first_name.charAt(0)}
                          {employee.last_name.charAt(0)}
                        </div>

                        <div>
                          <strong>
                            {employee.first_name} {employee.last_name}
                          </strong>

                          <span>{employee.email}</span>
                        </div>
                      </div>
                    </td>

                    <td>{employee.employee_number}</td>
                    <td>{employee.job_title}</td>
                    <td>{employee.department_id ?? "—"}</td>

                    <td>
                      <span
                        className={`employee-status ${
                          employee.status === "active"
                            ? "employee-status-active"
                            : "employee-status-inactive"
                        }`}
                      >
                        {employee.status}
                      </span>
                    </td>
                    <td><button className="secondary-button" aria-label={`View ${employeeLabel(employee)}`}
                      onClick={() => { setSelectedId(employee.id); setAction("view"); }}>View</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="employees-table-footer">
          Showing {rows.length} of {filteredEmployees.length} matching employees
          {pages > 1 && <DirectoryPagination page={currentPage} total={pages} onPage={setPage} />}
        </div>
      </div>
    </section>
  );
}

function EmployeeDetails({ id, token, revision }: { id: number; token: string; revision: number }) {
  const result = useQuery<Employee>(token, `/employees/${id}`, revision);
  return <QueryState result={result}>{employee => <p>
    {employee.email} · {employee.job_title} · {employee.status}
    {employee.department_id && ` · Department #${employee.department_id}`}
    {employee.manager_id && ` · Manager #${employee.manager_id}`}
  </p>}</QueryState>;
}

export default EmployeesPage;
