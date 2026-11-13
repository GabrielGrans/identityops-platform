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

import {
  ApiError,
  getEmployees,
  type Employee,
} from "./services/api";

interface EmployeesPageProps {
  token: string;
}

function EmployeesPage({ token }: EmployeesPageProps) {
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

  return (
    <section className="employees-page">
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

        <button
          className="secondary-button employees-refresh"
          onClick={() => void loadEmployees()}
          disabled={loading}
        >
          <RefreshCw size={15} />
          Refresh
        </button>
      </div>

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
              placeholder="Search employees..."
              value={search}
              onChange={(event) => setSearch(event.target.value)}
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
                </tr>
              </thead>

              <tbody>
                {filteredEmployees.map((employee) => (
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
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="employees-table-footer">
          Showing {filteredEmployees.length} of {employees.length} employees
        </div>
      </div>
    </section>
  );
}

export default EmployeesPage;
