/**
 * Jev System-1 Decision Client (OpenRouter Decisions API)
 *
 * Implements typed, sub-second micro-decisions:
 * - `choice`: Selects from discrete criteria with calibrated probabilities (variant resolution)
 * - `noul`: Evaluates boolean assertions with true-probability (margin & risk gates)
 * - `score`: Evaluates ordinal rating scales
 */

export type JevQuestionChoice = {
  type: "choice";
  instructions: string;
  criteria: Record<string, string>;
};

export type JevQuestionNoul = {
  type: "noul";
  instructions: string;
};

export type JevQuestionScore = {
  type: "score";
  instructions: string;
  min?: number;
  max?: number;
  scale?: Record<string, string>;
};

export type JevQuestion = JevQuestionChoice | JevQuestionNoul | JevQuestionScore;

export interface JevDecisionRequest {
  model?: string;
  state: Record<string, unknown>;
  questions: Record<string, JevQuestion>;
}

export interface JevDecisionResult<T = unknown> {
  type: "choice" | "noul" | "score";
  value: T;
  probability?: number;
  distribution?: Record<string, number>;
  confidence?: number;
  raw?: unknown;
}

export interface JevResponse {
  decisions: Record<string, JevDecisionResult>;
  latencyMs: number;
  model: string;
  usage?: {
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
  };
}

const DEFAULT_JEV_MODEL = "typesafe/jev-1.13";
const OPENROUTER_DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions";

/**
 * Executes a raw System-1 Decision request via OpenRouter Jev
 */
export async function executeJevDecisions(
  request: JevDecisionRequest,
  apiKey?: string
): Promise<JevResponse> {
  const token = apiKey || process.env.OPENROUTER_API_KEY;

  if (!token) {
    throw new Error(
      "OPENROUTER_API_KEY is not defined in environment variables or parameters."
    );
  }

  const model = request.model || process.env.JEV_MODEL || DEFAULT_JEV_MODEL;
  const startTime = Date.now();

  const response = await fetch(OPENROUTER_DECISIONS_URL, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${token}`,
      "Content-Type": "application/json",
      "HTTP-Referer": "https://agent-gateway.dev",
      "X-Title": "Agent Gateway - Jev System-1 Core",
    },
    body: JSON.stringify({
      model,
      state: request.state,
      questions: request.questions,
    }),
  });

  const latencyMs = Date.now() - startTime;

  if (!response.ok) {
    const errorBody = await response.text();
    throw new Error(
      `Jev API Error (${response.status} ${response.statusText}): ${errorBody}`
    );
  }

  const data = await response.json();

  // Normalize decisions output
  const rawDecisions = data.decisions || data.results || data;
  const decisions: Record<string, JevDecisionResult> = {};

  for (const [key, value] of Object.entries(rawDecisions)) {
    if (typeof value === "object" && value !== null) {
      const v = value as Record<string, unknown>;
      decisions[key] = {
        type: (v.type as "choice" | "noul" | "score") || "choice",
        value: v.value ?? v.choice ?? v.answer ?? v,
        probability: typeof v.probability === "number" ? v.probability : undefined,
        distribution: (v.distribution as Record<string, number>) || undefined,
        confidence: typeof v.confidence === "number" ? v.confidence : undefined,
        raw: v,
      };
    } else {
      decisions[key] = {
        type: "choice",
        value,
        raw: value,
      };
    }
  }

  return {
    decisions,
    latencyMs,
    model,
    usage: data.usage,
  };
}

/**
 * 1. Variant Resolution Primitive (Choice)
 * Resolves natural language user intent against raw variant options with zero hallucination.
 */
export async function resolveVariant(params: {
  userIntent: string;
  productTitle: string;
  variants: Array<{ id: string | number; title: string; price?: string | number; available?: boolean }>;
}): Promise<{
  variantId: string;
  confidence: number;
  distribution?: Record<string, number>;
  latencyMs: number;
}> {
  const criteria: Record<string, string> = {};
  for (const v of params.variants) {
    const stock = v.available === false ? " (Out of Stock)" : " (In Stock)";
    criteria[String(v.id)] = `${v.title}${v.price ? ` - $${v.price}` : ""}${stock}`;
  }

  const result = await executeJevDecisions({
    state: {
      product_title: params.productTitle,
      user_request: params.userIntent,
    },
    questions: {
      selected_variant: {
        type: "choice",
        instructions:
          "Which variant ID strictly matches the user's requested size, color, style, and availability?",
        criteria,
      },
    },
  });

  const decision = result.decisions.selected_variant;
  const variantId = String(decision.value);
  const confidence = decision.confidence ?? decision.probability ?? 1.0;

  return {
    variantId,
    confidence,
    distribution: decision.distribution,
    latencyMs: result.latencyMs,
  };
}

/**
 * 2. Margin Evaluation Engine (Noul / Choice)
 * Evaluates whether an agent's counter-offer bid falls within authorized seller discount policy.
 */
export async function evaluateMargin(params: {
  basePrice: number;
  offeredPrice: number;
  quantity: number;
  maxDiscountPct?: number;
}): Promise<{
  acceptable: boolean;
  probability: number;
  discountPct: number;
  latencyMs: number;
}> {
  const maxDiscount = params.maxDiscountPct ?? 15;
  const unitDiscountPct = ((params.basePrice - params.offeredPrice) / params.basePrice) * 100;

  const result = await executeJevDecisions({
    state: {
      base_price_usd: params.basePrice,
      offered_price_usd: params.offeredPrice,
      quantity_ordered: params.quantity,
      max_allowed_discount_pct: maxDiscount,
      computed_discount_pct: Math.round(unitDiscountPct * 10) / 10,
    },
    questions: {
      is_acceptable_margin: {
        type: "noul",
        instructions:
          "Does this buyer's offer satisfy the seller policy allowing up to the maximum discount percentage for this volume?",
      },
    },
  });

  const decision = result.decisions.is_acceptable_margin;
  const prob = decision.probability ?? (decision.value === true ? 1.0 : 0.0);
  const acceptable = prob >= 0.5;

  return {
    acceptable,
    probability: prob,
    discountPct: unitDiscountPct,
    latencyMs: result.latencyMs,
  };
}

/**
 * 3. Pre-Flight Spend Risk Gate (Noul)
 * Verifies final basket amount against spend caps and policy constraints.
 */
export async function checkPreFlightRisk(params: {
  basketTotal: number;
  spendCap: number;
  itemCount: number;
  merchantName: string;
}): Promise<{
  allowed: boolean;
  probability: number;
  latencyMs: number;
}> {
  const result = await executeJevDecisions({
    state: {
      basket_total: params.basketTotal,
      spend_cap: params.spendCap,
      item_count: params.itemCount,
      merchant: params.merchantName,
    },
    questions: {
      within_budget_policy: {
        type: "noul",
        instructions:
          "Is the total transaction strictly within the authorized spend cap with safe execution parameters?",
      },
    },
  });

  const decision = result.decisions.within_budget_policy;
  const prob = decision.probability ?? (decision.value === true ? 1.0 : 0.0);

  return {
    allowed: prob >= 0.5,
    probability: prob,
    latencyMs: result.latencyMs,
  };
}
