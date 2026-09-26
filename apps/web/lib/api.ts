// A thin client for the Eden API (docs/API.md). Every title, price and image the pages show
// comes from these responses, which come from the database (CLAUDE.md rule 3).
import { API_URL } from "./config";

export class EdenApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init.headers },
    cache: "no-store",
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const error = body?.error ?? {};
    throw new EdenApiError(error.code ?? "error", error.message ?? `Request failed (${res.status})`, res.status);
  }
  return body as T;
}

export type SessionCreated = {
  code: string;
  status: string;
  session_url: string;
  grok_url: string;
  scrape_id: string;
};

export type Session = {
  code: string;
  store: string;
  collection: string | null;
  status: "pending" | "crawling" | "classifying" | "ready" | "failed";
  /** Why the page couldn't be read, when status is "failed". */
  error: string | null;
  product_count: number;
  snapshot_at: string;
  rules: Record<string, unknown>;
  can_purchase: boolean;
  session_url: string;
  scrape_id: string;
  expires_at: string;
};

export type TreeNode = { name: string; count: number; children: TreeNode[] };

export type Product = {
  id: string;
  title: string;
  price: number | null;
  per_piece: number | null;
  pieces: number | null;
  currency: string | null;
  tree_path: string[];
  image_url: string | null;
  source_url: string;
  why: string;
};

export const api = {
  createSession: (url: string, token: string) =>
    request<SessionCreated>("/sessions", {
      method: "POST",
      body: JSON.stringify({ url, entry: "prefix" }),
      headers: { Authorization: `Bearer ${token}` },
    }),
  session: (code: string) => request<Session>(`/sessions/${code}`),
  tree: (code: string) => request<{ tree: TreeNode[] }>(`/sessions/${code}/tree`),
  products: (code: string, limit = 12) =>
    request<{ items: Product[]; total_matching: number }>(`/sessions/${code}/products?limit=${limit}`),
  grok: (code: string) => request<{ grok_url: string }>(`/sessions/${code}/grok`),
};

export const productsUrl = (code: string) => `${API_URL}/sessions/${code}/products`;
