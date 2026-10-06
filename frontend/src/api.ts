/** Compatibilità con le schermate v0.7: stesso trasporto del client tipizzato (api/client.ts). */
import { ApiError, collect, csrfToken, request } from "./api/client";
export { ApiError, csrfToken };
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const body = typeof init.body === "string" ? JSON.parse(init.body) : undefined;
  return request<T>(init.method || "GET", path, { body, headers: init.headers as Record<string, string> | undefined });
}
export async function list<T>(path: string): Promise<T[]> {
  return (await collect<T>(path, { maxPages: 1000 })).rows;
}
