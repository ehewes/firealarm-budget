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
  grok: (code: string) =>
    request<{ grok_url: string; prompt: string; bot_prompt: string }>(`/sessions/${code}/grok`),
};

export type Card = {
  provider: string;
  label: string | null;
  last4: string | null;
  spend_cap: number | null;
  currency: string;
};

export type Agent = { id: string; name: string; token_hint: string; created_at: string; last_used_at: string | null };

export type AgentCreated = Agent & {
  token: string;
  mcp_url: string;
  mcp_config: Record<string, unknown>;
  /** For clients that only take a URL (grok.com custom connectors). It holds the token. */
  connector_url: string;
};

export type Me = {
  id: string;
  email: string | null;
  is_anonymous: boolean;
  card: Card | null;
  agents: Agent[];
  grok_bot_webhook: { host: string; last_sent_at: string | null } | null;
};

export type PastSession = {
  code: string;
  store: string;
  collection: string | null;
  status: Session["status"];
  product_count: number;
  created_at: string;
  expires_at: string;
  session_url: string;
};

export type Purchase = {
  id: string;
  status: "pending" | "price_changed" | "confirmed" | "executing" | "completed" | "failed" | "cancelled";
  store: string | null;
  session_code: string | null;
  items: {
    id: string;
    title: string;
    price: number | null;
    currency: string | null;
    image_url: string | null;
    source_url: string;
    in_stock: boolean | null;
  }[];
  total: number;
  currency: string | null;
  card: { status: "card_ready"; last4: string | null; limit: number | null } | null;
  confirm_url: string;
  expires_at: string;
  order_ref: string | null;
  error: string | null;
};

const as = (token: string, init: RequestInit = {}): RequestInit => ({
  ...init,
  headers: { ...init.headers, Authorization: `Bearer ${token}` },
});

/** The signed-in shopper's own things, and purchases. Every call needs their token. */
export const account = {
  me: (token: string) => request<Me>("/me", as(token)),
  sessions: (token: string) => request<PastSession[]>("/me/sessions", as(token)),
  linkCard: (token: string, spend_cap: number, currency = "GBP") =>
    request<Card>("/me/card", as(token, { method: "PUT", body: JSON.stringify({ spend_cap, currency }) })),
  unlinkCard: (token: string) => request<void>("/me/card", as(token, { method: "DELETE" })),
  connectAgent: (token: string, name: string) =>
    request<AgentCreated>("/me/agents", as(token, { method: "POST", body: JSON.stringify({ name }) })),
  disconnectAgent: (token: string, id: string) => request<void>(`/me/agents/${id}`, as(token, { method: "DELETE" })),
  setWebhook: (token: string, url: string, key: string) =>
    request<Me["grok_bot_webhook"]>(
      "/me/grok-bot-webhook",
      as(token, { method: "PUT", body: JSON.stringify({ url, key }) }),
    ),
  removeWebhook: (token: string) => request<void>("/me/grok-bot-webhook", as(token, { method: "DELETE" })),
  sendToGrokBot: (token: string, code: string) =>
    request<{ sent: boolean }>(`/sessions/${code}/send-to-grok-bot`, as(token, { method: "POST" })),
  purchase: (token: string, id: string) => request<Purchase>(`/purchase-intents/${id}`, as(token)),
  confirm: (token: string, id: string) =>
    request<Purchase>(`/purchase-intents/${id}/confirm`, as(token, { method: "POST" })),
  cancel: (token: string, id: string) =>
    request<Purchase>(`/purchase-intents/${id}/cancel`, as(token, { method: "POST" })),
};

export function money(amount: number | null, currency: string | null): string {
  if (amount === null) return "";
  try {
    return new Intl.NumberFormat("en-GB", { style: "currency", currency: currency || "USD" }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${currency ?? ""}`.trim();
  }
}

export const productsUrl = (code: string) => `${API_URL}/sessions/${code}/products`;
