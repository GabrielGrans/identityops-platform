import { locale, t } from "../i18n";
import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
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

const listeners = new Set<() => void>();
let localRevision = 0;

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

export function refreshLocalData() {
  localRevision++;
  for (const listener of listeners) listener();
}

export type QueryResult<T> = { data?: T; error?: string; errorStatus?: number; loading?: boolean };
export function useQuery<T>(token: string, path: string | null, revision = 0, keepPrevious = true): QueryResult<T> {
  const [result, setResult] = useState<QueryResult<T> & { key?: string; path?: string; token?: string }>({});
  const epoch = useSyncExternalStore(subscribe, () => localRevision);
  const key = path === null ? undefined : `${epoch}:${revision}:${path}`;
  useEffect(() => {
    if (path === null) return;
    const controller = new AbortController();
    request<T>(path, { signal: controller.signal, cache: "no-store" }, token).then(
      (data) => { if (!controller.signal.aborted) setResult({ key, path, token, data }); },
      (error: Error) => {
        if (!controller.signal.aborted) setResult({ key, path, token, error: error.message, errorStatus: error instanceof ApiError ? error.status : undefined });
      },
    );
    return () => controller.abort();
  }, [token, path, key]);
  if (path === null) return {};
  if (result.token === token && result.key === key) return { ...result, loading: false };
  if (keepPrevious && result.token === token && result.path === path) return { data: result.data, loading: true };
  return { loading: true };
}

export function useMutation(token: string) {
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; error: boolean }>();
  const refresh = useCallback(() => setRevision((value) => value + 1), []);
  async function mutate(path: string, method: string, body?: unknown) {
    setBusy(true);
    setMessage(undefined);
    try {
      await request(path, { method, body: body === undefined ? undefined : JSON.stringify(body) }, token);
      refresh();
      setMessage({ text: t("Changes saved."), error: false });
      return true;
    } catch (error) {
      setMessage({ text: error instanceof Error ? t(error.message) : t("Request failed."), error: true });
      return false;
    } finally {
      setBusy(false);
    }
  }
  return { revision, busy, message, mutate, refresh };
}

export function displayTime(value: string) {
  return new Date(value).toLocaleString(locale());
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

export function provisioningStatus(status: string) {
  const labels: Record<string, string> = {
    direct_authorized: "Queued (administrator)", approved: "Queued",
    executing: "Processing", succeeded: "Completed", failed: "Failed",
  };
  return t(labels[status] ?? status);
}
