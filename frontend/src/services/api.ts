import { t, locale } from "../i18n";
import { isTauri } from "@tauri-apps/api/core";
import { fetch as fetchDesktop } from "@tauri-apps/plugin-http";

const LOCAL_API_URL = "http://127.0.0.1:8000";
const API_URL =
  import.meta.env.VITE_API_URL || LOCAL_API_URL;

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface Employee {
  id: number;
  employee_number: string;
  first_name: string;
  last_name: string;
  email: string;
  job_title: string;
  status: "active" | "inactive";
  department_id: number | null;
  manager_id: number | null;
  created_at: string;
}

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const fieldLabels: Record<string, string> = {
  first_name: "First name", last_name: "Last name", email: "Email", job_title: "Job title",
  password: "Password", employee_number: "Employee number", department_id: "Department ID",
  name: "Name", code: "Code", reason: "Reason", decision: "Decision", justification: "Justification",
  max_permissions: "Maximum effective permissions", review_max_age_days: "Pending review age (days)",
};

function tField(field: string) { return t(fieldLabels[field] ?? field); }

function tValidation(type: string) {
  if (type === "missing") return t("This field is required.");
  if (type === "string_too_short") return t("The text is too short.");
  if (type === "string_too_long") return t("The text is too long.");
  if (type.startsWith("greater_than") || type.startsWith("less_than")) return t("The value is outside the allowed range.");
  return t("Check this value and try again.");
}

function localizedDetail(detail: string) {
  const permission = detail.match(/^Permission denied: (.+)$/);
  if (permission) return t("Permission denied: {permission}", { permission: permission[1] });
  return t(detail);
}

export async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: string,
): Promise<T> {
  const headers = new Headers(options.headers);

  headers.set("Accept", "application/json");

  if (options.body) {
    headers.set("Content-Type", "application/json");
  }

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const init = { ...options, headers };
  let response: Response;
  try {
    response = isTauri()
      ? await fetchDesktop(`${LOCAL_API_URL}${path}`, { ...init, maxRedirections: 0 })
      : await fetch(`${API_URL}${path}`, init);
  } catch (error) {
    if (options.signal?.aborted) throw error;
    throw new ApiError(t("Could not connect to the IdentityOps API."), 0);
  }

  if (!response.ok) {
    let message = t("Request failed ({status})", { status: response.status });

    try {
      const data = await response.json();
      if (Array.isArray(data.detail)) {
        message = data.detail.map((issue: { loc: string[]; msg: string; type: string }) =>
          `${issue.loc.slice(1).map(tField).join(".")}: ${locale() === "pt-BR" ? tValidation(issue.type) : issue.msg}`,
        ).join("; ");
      } else {
        const detail = typeof data.detail === "string" ? data.detail : data.detail?.message;
        if (typeof detail === "string") message = localizedDetail(detail);
        else if (typeof data.message === "string") message = localizedDetail(data.message);
      }
    } catch {
      // Keep the default error message.
    }

    throw new ApiError(message, response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export async function login(
  email: string,
  password: string,
): Promise<LoginResponse> {
  return request<LoginResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function getCurrentEmployee(
  token: string,
): Promise<Employee> {
  return request<Employee>("/auth/me", {}, token);
}

export async function getEmployees(
  token: string,
): Promise<Employee[]> {
  return request<Employee[]>("/employees", {}, token);
}
