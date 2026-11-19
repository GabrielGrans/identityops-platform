import { useState, type FormEvent } from "react";
import { type Employee } from "../services/api";
import { Feedback, Panel, QueryState } from "./common";
import { SearchChecks, SearchSelect } from "./DirectoryControls";
import { employeeLabel, useQuery, type CatalogItem, type Session, useMutation } from "./data";

function PasswordFields({ required }: { required: boolean }) {
  return <>
    <label>{required ? "New password" : "Initial password"}<input name="password" type="password"
      autoComplete="new-password" minLength={12} maxLength={128} required={required} /></label>
    <label>Confirm password<input name="confirmation" type="password" autoComplete="new-password"
      minLength={12} maxLength={128} required={required} /></label>
  </>;
}

export function EmployeeForm({ employee, employees, session, onClose, onSaved }: {
  employee?: Employee; employees: Employee[]; session: Session; onClose: () => void; onSaved: () => void;
}) {
  const { token, permissions } = session;
  const mutation = useMutation(token);
  const canSetPassword = !employee && permissions.includes("employees:reset_password");
  const canAssign = !employee && ["access:manage", "groups:read"].every(code => permissions.includes(code));
  const departments = useQuery<CatalogItem[]>(token, permissions.includes("departments:read") ? "/departments" : null);
  const groups = useQuery<CatalogItem[]>(token, canAssign ? "/groups" : null);
  const [groupIds, setGroupIds] = useState<number[]>([]);
  const [status, setStatus] = useState("active");
  const [validation, setValidation] = useState("");

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const password = String(form.get("password") ?? "");
    if (password !== String(form.get("confirmation") ?? "")) {
      setValidation("The passwords must match.");
      return;
    }
    if (!employee && (password || groupIds.length) &&
      !window.confirm("Create this employee with the selected credentials and access settings?")) return;
    setValidation("");
    const reference = (field: string, previous?: number | null) =>
      form.has(field) ? Number(form.get(field)) || null : previous ?? null;
    const body = {
      employee_number: form.get("employee_number"), first_name: form.get("first_name"),
      last_name: form.get("last_name"), email: form.get("email"), job_title: form.get("job_title"),
      department_id: reference("department_id", employee?.department_id),
      manager_id: reference("manager_id", employee?.manager_id),
      ...(!employee && { status, group_ids: status === "active" ? groupIds : [], ...(password && { password }) }),
    };
    if (await mutation.mutate(employee ? `/employees/${employee.id}` : "/employees", employee ? "PUT" : "POST", body)) {
      onSaved();
    }
  }

  return <Panel title={employee ? "Edit employee" : "New employee"}>
    {validation && <p role="alert">{validation}</p>}
    <Feedback message={mutation.message} />
    <form className="iam-form" onSubmit={save}>
      <label>First name<input name="first_name" required minLength={2} maxLength={100} defaultValue={employee?.first_name} /></label>
      <label>Last name<input name="last_name" required minLength={2} maxLength={100} defaultValue={employee?.last_name} /></label>
      <label>Employee number<input name="employee_number" required minLength={2} maxLength={30} defaultValue={employee?.employee_number} /></label>
      <label>Corporate email<input name="email" type="email" required maxLength={255} defaultValue={employee?.email} /></label>
      <label>Job title<input name="job_title" required minLength={2} maxLength={120} defaultValue={employee?.job_title} /></label>
      {permissions.includes("departments:read") && <QueryState result={departments}>{options =>
        <SearchSelect label="Department" name="department_id" optional initial={String(employee?.department_id ?? "")}
          options={options.filter(item => item.is_active || item.id === employee?.department_id)} />
      }</QueryState>}
      <SearchSelect label="Manager" name="manager_id" optional initial={String(employee?.manager_id ?? "")}
        options={employees.filter(item => item.id !== employee?.id &&
          (item.status === "active" || item.id === employee?.manager_id)).map(item => ({ id: item.id, name: employeeLabel(item) }))} />
      {!employee && <label>Account status<select value={status} onChange={event => {
        setStatus(event.target.value);
        if (event.target.value === "inactive") setGroupIds([]);
      }}><option value="active">Active</option><option value="inactive">Inactive</option></select></label>}
      {canSetPassword && <PasswordFields required={false} />}
      {canAssign && status === "active" && <QueryState result={groups}>{options =>
        <SearchChecks label="Access groups" options={options.filter(item => item.is_active)}
          selected={groupIds} onChange={setGroupIds} />
      }</QueryState>}
      <div className="iam-actions">
        <button className="primary-button" disabled={mutation.busy}>{mutation.busy ? "Saving…" : "Save employee"}</button>
        <button className="secondary-button" type="button" disabled={mutation.busy} onClick={onClose}>Cancel</button>
      </div>
    </form>
  </Panel>;
}

export function EmployeePasswordForm({ employee, token, onClose }: {
  employee: Employee; token: string; onClose: () => void;
}) {
  const mutation = useMutation(token);
  const [validation, setValidation] = useState("");

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    const password = fields.get("password");
    if (password !== fields.get("confirmation")) {
      setValidation("The passwords must match.");
      return;
    }
    if (!window.confirm(`Set or reset the password for ${employeeLabel(employee)}?`)) return;
    setValidation("");
    if (await mutation.mutate(`/employees/${employee.id}/password`, "PUT", { password })) form.reset();
  }

  return <Panel title={`Set or reset password for ${employeeLabel(employee)}`}>
    {validation && <p role="alert">{validation}</p>}
    <Feedback message={mutation.message} />
    <form className="iam-form" onSubmit={save}>
      <PasswordFields required />
      <button className="primary-button" disabled={mutation.busy}>{mutation.busy ? "Saving…" : "Save password"}</button>
      <button className="secondary-button" type="button" disabled={mutation.busy} onClick={onClose}>Close</button>
    </form>
  </Panel>;
}

export function EmployeeAccess({ employee, session }: { employee: Employee; session: Session }) {
  const mutation = useMutation(session.token);
  const path = `/employees/${employee.id}`;
  const assigned = useQuery<CatalogItem[]>(session.token, `${path}/groups`, mutation.revision);
  const effective = useQuery<string[]>(session.token, `${path}/permissions`, mutation.revision);
  const groups = useQuery<CatalogItem[]>(session.token, session.permissions.includes("groups:read") ? "/groups" : null);

  return <Panel title="Manage access">
    <Feedback message={mutation.message} />
    <QueryState result={assigned}>{items => <>
      <h3>Assigned groups</h3>
      {items.length ? <ul className="iam-list">{items.map(item => <li key={item.id}>
        <span>{item.name} · {item.is_active ? "Active" : "Inactive"}</span>
        <button className="secondary-button" disabled={mutation.busy} onClick={() => {
          if (window.confirm(`Remove ${item.name} from this employee?`)) void mutation.mutate(`${path}/groups/${item.id}`, "DELETE");
        }}>Remove</button>
      </li>)}</ul> : <p>No assigned groups.</p>}
      {employee.status === "active" && groups.data && <form className="iam-form" onSubmit={event => {
        event.preventDefault();
        const group = new FormData(event.currentTarget).get("group");
        if (window.confirm("Assign this group to the employee?")) void mutation.mutate(`${path}/groups/${group}`, "POST");
      }}>
        <SearchSelect label="Group" name="group" options={groups.data.filter(item => item.is_active && !items.some(row => row.id === item.id))} />
        <button className="primary-button" disabled={mutation.busy}>Assign group</button>
      </form>}
      {groups.error && <p role="alert">{groups.error}</p>}
    </>}</QueryState>
    <h3>Effective permissions</h3>
    <QueryState result={effective}>{codes => codes.length ? <ul className="directory-options">
      {codes.map(code => <li key={code}>{code}</li>)}
    </ul> : <p>No effective permissions.</p>}</QueryState>
  </Panel>;
}
