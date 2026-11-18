import { useState, type FormEvent } from "react";
import { type Employee } from "../services/api";
import { Feedback, Page, Panel, QueryState, SelectId } from "./common";
import { type CatalogItem, type Session, useMutation, useQuery } from "./data";

const operations = [
  { value: "joiner", label: "Joiner", permission: "employees:create" },
  { value: "mover", label: "Mover", permission: "employees:update" },
  { value: "leaver", label: "Leaver", permission: "employees:deactivate" },
];

function optionalNumber(form: FormData, field: string) {
  const value = form.get(field);
  return value ? Number(value) : null;
}

export function LifecyclePage({ session }: { session: Session }) {
  const { token, permissions } = session;
  const allowed = operations.filter((item) => permissions.includes(item.permission));
  const [operation, setOperation] = useState(allowed[0]?.value);
  const mutation = useMutation(token);
  const [employeeId, setEmployeeId] = useState("");
  const [successId, setSuccessId] = useState("");
  const employees = useQuery<Employee[]>(token, permissions.includes("employees:read") ? "/employees" : null, mutation.revision);
  const departments = useQuery<CatalogItem[]>(token, operation !== "leaver" && permissions.includes("departments:read") ? "/departments" : null);
  const groups = useQuery<CatalogItem[]>(token, operation !== "leaver" && permissions.includes("groups:read") ? "/groups" : null);
  const memberships = useQuery<CatalogItem[]>(token, operation === "mover" && employeeId ? `/employees/${employeeId}/groups` : null, mutation.revision);
  const employee = employees.data?.find((entry) => String(entry.id) === employeeId);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    const groupIds = groups.data
      ? fields.getAll("groups").map(Number)
      : String(fields.get("group_ids") ?? "").split(",").map((id) => id.trim()).filter(Boolean).map(Number);
    const profile = {
      job_title: fields.get("job_title"),
      department_id: optionalNumber(fields, "department_id"),
      manager_id: optionalNumber(fields, "manager_id"),
      group_ids: groupIds,
    };
    const id = employeeId || String(fields.get("employee"));
    const payload = operation === "joiner" ? {
      ...profile, employee_number: fields.get("employee_number"), first_name: fields.get("first_name"),
      last_name: fields.get("last_name"), email: fields.get("email"),
    } : operation === "mover" ? {
      ...profile, expected_group_ids: memberships.data?.map((group) => group.id),
    } : { reason: fields.get("reason") };
    const path = operation === "joiner" ? "/lifecycle/joiner" : `/lifecycle/${id}/${operation}`;
    if (await mutation.mutate(path, "POST", payload)) {
      form.reset();
      setSuccessId(operation === "joiner" ? String(fields.get("employee_number")) : id);
      setEmployeeId("");
    }
  }

  function profileFields(currentGroups: CatalogItem[]) {
    const defaults = new Set(currentGroups.filter((group) => group.is_active).map((group) => group.id));
    return <>
      <label>Job title<input name="job_title" required minLength={2} maxLength={120} defaultValue={employee?.job_title} /></label>
      {departments.data
        ? <SelectId label="Department" name="department_id" items={departments.data.filter((item) => item.is_active)} required={false} defaultValue={employee?.department_id ?? undefined} />
        : <label>Department ID<input name="department_id" type="number" min={1} defaultValue={employee?.department_id ?? undefined} /></label>}
      <label>Manager ID<input name="manager_id" type="number" min={1} defaultValue={employee?.manager_id ?? undefined} /></label>
      {groups.data ? <fieldset className="iam-groups">
        <legend>{operation === "mover" ? "Resulting memberships" : "Initial memberships"}</legend>
        {groups.data.filter((item) => item.is_active).map((group) => (
          <label className="iam-checkbox" key={group.id}>
            <input name="groups" type="checkbox" value={group.id} defaultChecked={defaults.has(group.id)} /> {group.name}
          </label>
        ))}
      </fieldset> : <label>Group IDs (comma-separated)<input name="group_ids" pattern="[1-9][0-9]*(,\\s*[1-9][0-9]*)*" defaultValue={[...defaults].join(", ")} /></label>}
    </>;
  }

  return <Page title="Identity Lifecycle">
    <Feedback message={mutation.message} />
    {successId && !mutation.message?.error && <p role="status">Employee reference #{successId}</p>}
    <Panel title="Run lifecycle event">
      <label>Event<select aria-label="Event" value={operation} onChange={(event) => {
        setOperation(event.target.value);
        setEmployeeId("");
        setSuccessId("");
      }}>
        {allowed.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
      </select></label>
      {operation !== "joiner" && <form className="iam-form" onSubmit={(event) => {
        event.preventDefault();
        setEmployeeId(String(new FormData(event.currentTarget).get("employee")));
        mutation.refresh();
      }}>
        {employees.data ? <SelectId label="Employee" name="employee" items={employees.data
          .filter((entry) => entry.id !== session.employeeId && (operation === "leaver" || entry.status === "active"))
          .map((entry) => ({ id: entry.id, name: `${entry.first_name} ${entry.last_name} (#${entry.id})` }))} />
          : <label>Employee ID<input name="employee" type="number" min={1} required /></label>}
        <button className="secondary-button">Load employee</button>
      </form>}
      {operation === "joiner" && <form className="iam-form" onSubmit={submit}>
        <label>Employee number<input name="employee_number" required minLength={2} maxLength={30} /></label>
        <label>First name<input name="first_name" required minLength={2} maxLength={100} /></label>
        <label>Last name<input name="last_name" required minLength={2} maxLength={100} /></label>
        <label>Email<input name="email" type="email" required /></label>
        {profileFields([])}
        <button className="primary-button" disabled={mutation.busy}>Create employee</button>
      </form>}
      {employeeId && operation === "mover" && <QueryState result={memberships}>{(currentGroups) => (
        <form key={employeeId} className="iam-form" onSubmit={submit}>
          <h3>Move employee #{employeeId}</h3>
          <p>The selected memberships replace the employee&apos;s current memberships.</p>
          {profileFields(currentGroups)}
          <button className="primary-button" disabled={mutation.busy}>Apply move</button>
        </form>
      )}</QueryState>}
      {employeeId && operation === "leaver" && <form key={employeeId} className="iam-form" onSubmit={submit}>
        <h3>Offboard employee #{employeeId}</h3>
        <p>This disables sign-in and revokes all group memberships.</p>
        <label>Reason<textarea name="reason" required maxLength={1000} /></label>
        <button className="primary-button" disabled={mutation.busy}>Offboard employee</button>
      </form>}
    </Panel>
  </Page>;
}
