const API_URL =
  import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

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

  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let message = `Request failed (${response.status})`;

    try {
      const data = await response.json();
      if (Array.isArray(data.detail)) {
        message = data.detail.map((issue: { loc: string[]; msg: string }) =>
          `${issue.loc.slice(1).join(".")}: ${issue.msg}`,
        ).join("; ");
      } else {
        message = data.detail || data.message || message;
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
