import { useEffect, useState } from "react";
import { ApiError, request, type Employee } from "../services/api";

export interface Session {
  token: string;
  employeeId: number;
  permissions: string[];
}

export interface CatalogItem {
  id: number;
  name: string;
  code: string;
  description: string | null;
  is_active: boolean;
  resource?: string;
  action?: string;
}

export type QueryResult<T> = { data?: T; error?: string; errorStatus?: number };
export function useQuery<T>(token: string, path: string | null, revision = 0, keepPrevious = false) {
  const [result, setResult] = useState<QueryResult<T> & { key?: string; path?: string; token?: string }>({});
  const key = path === null ? undefined : `${revision}:${path}`;
  useEffect(() => {
    if (path === null) return;
    const controller = new AbortController();
    request<T>(path, { signal: controller.signal }, token).then(
      (data) => setResult({ key, path, token, data }),
      (error: Error) => {
        if (!controller.signal.aborted) setResult({ key, path, token, error: error.message, errorStatus: error instanceof ApiError ? error.status : undefined });
      },
    );
    return () => controller.abort();
  }, [token, path, key]);
  return result.token === token && (result.key === key || (keepPrevious && result.path === path)) ? result : {};
}

export function useMutation(token: string) {
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; error: boolean }>();
  function refresh() {
    setRevision((value) => value + 1);
  }
  async function mutate(path: string, method: string, body?: unknown) {
    setBusy(true);
    setMessage(undefined);
    try {
      await request(path, { method, body: body === undefined ? undefined : JSON.stringify(body) }, token);
      refresh();
      setMessage({ text: "Changes saved.", error: false });
      return true;
    } catch (error) {
      setMessage({ text: error instanceof Error ? error.message : "Request failed.", error: true });
      return false;
    } finally {
      setBusy(false);
    }
  }
  return { revision, busy, message, mutate, refresh };
}

export function displayTime(value: string) {
  return new Date(value).toLocaleString();
}

export function useCursor() {
  const [positions, setPositions] = useState<number[]>([]);
  const before = positions.at(-1);
  return {
    query: before === undefined ? "" : `&before_id=${before}`,
    previous: positions.length ? () => setPositions((current) => current.slice(0, -1)) : undefined,
    next: (id: number) => setPositions((current) => [...current, id]),
    reset: () => setPositions([]),
  };
}

export const PAGE_SIZE = 25;

export function employeeLabel(employee: Employee) {
  return `${employee.first_name} ${employee.last_name} (${employee.employee_number})`;
}
