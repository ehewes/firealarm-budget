/**
 * Jev System-1 Decision Client (OpenRouter Decisions API)
 *
 * Implements typed, sub-second micro-decisions:
 * - `choice`: Selects from discrete criteria with calibrated probabilities (variant resolution)
 * - `noul`: Evaluates boolean assertions with true-probability (margin & risk gates)
 * - `score`: Evaluates ordinal rating scales
 *
 * Built-in Support:
 * - Configurable Seller & Buyer business rules
 * - Calibrated confidence tracking
 * - Automatic Grok System-2 Cascade triggers (when confidence < threshold)
 */

export const DEFAULT_CONFIDENCE_THRESHOLD = 0.75;
export const DEFAULT_JEV_MODEL = "typesafe/jev-1.13";
const OPENROUTER_DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions";

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

export interface CascadeMetadata {
  confidence: number;
  confidenceThreshold: number;
  shouldEscalateToGrok: boolean;
  escalationReason?: string;
}

/**
 * Seller Business Rules configuration
 */
export interface SellerPolicyRules {
  maxDiscountPct?: number; // e.g. 15%
  minStockForDiscount?: number; // e.g. don't discount if stock < 5
  bulkMinQuantity?: number; // e.g. 3+ items
  bulkExtraDiscountPct?: number; // e.g. extra 5%
  allowClearanceDiscounts?: boolean;
  customRules?: string[];
}

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
 * 1. Variant Resolution Primitive (Choice) with Model Cascading
 * Resolves natural language user intent against raw variant options.
 * Flags Grok escalation if intent is ambiguous or top confidence < threshold.
 */
export async function resolveVariant(params: {
  userIntent: string;
  productTitle: string;
  variants: Array<{
    id: string | number;
    title: string;
    price?: string | number;
    available?: boolean;
    inventoryQuantity?: number;
  }>;
  confidenceThreshold?: number;
}): Promise<{
  variantId: string;
  confidence: number;
  distribution?: Record<string, number>;
  latencyMs: number;
  cascade: CascadeMetadata;
}> {
  const threshold = params.confidenceThreshold ?? DEFAULT_CONFIDENCE_THRESHOLD;
  const criteria: Record<string, string> = {};

  for (const v of params.variants) {
    const stockStatus =
      v.available === false || v.inventoryQuantity === 0
        ? " (Out of Stock)"
        : v.inventoryQuantity !== undefined
        ? ` (In Stock: ${v.inventoryQuantity})`
        : " (In Stock)";
    criteria[String(v.id)] = `${v.title}${v.price ? ` - $${v.price}` : ""}${stockStatus}`;
  }

  const result = await executeJevDecisions({
    state: {
      product_title: params.productTitle,
      user_request: params.userIntent,
      variant_count: params.variants.length,
    },
    questions: {
      selected_variant: {
        type: "choice",
        instructions:
          "Which variant ID strictly matches the user's requested size, color, style, and availability? Return the exact matching variant ID.",
        criteria,
      },
    },
  });

  const decision = result.decisions.selected_variant;
  const variantId = String(decision.value);

  // Extract calibrated confidence from probability or distribution
  let confidence = decision.confidence ?? decision.probability ?? 1.0;
  if (decision.distribution && decision.distribution[variantId] !== undefined) {
    confidence = decision.distribution[variantId];
  }

  const shouldEscalateToGrok = confidence < threshold;
  const escalationReason = shouldEscalateToGrok
    ? `Low confidence match (${Math.round(confidence * 100)}% < ${Math.round(threshold * 100)}%). Customer intent may be ambiguous or requested variant is unavailable.`
    : undefined;

  return {
    variantId,
    confidence,
    distribution: decision.distribution,
    latencyMs: result.latencyMs,
    cascade: {
      confidence,
      confidenceThreshold: threshold,
      shouldEscalateToGrok,
      escalationReason,
    },
  };
}

/**
 * 2. Margin Evaluation Engine (Noul / Choice) with Policy Rules & Cascading
 * Evaluates whether an agent's counter-offer bid complies with merchant business rules.
 */
export async function evaluateMargin(params: {
  basePrice: number;
  offeredPrice: number;
  quantity: number;
  stockRemaining?: number;
  policy?: SellerPolicyRules;
  confidenceThreshold?: number;
}): Promise<{
  acceptable: boolean;
  probability: number;
  discountPct: number;
  latencyMs: number;
  rulesEvaluated: string[];
  cascade: CascadeMetadata;
}> {
  const threshold = params.confidenceThreshold ?? DEFAULT_CONFIDENCE_THRESHOLD;
  const policy = params.policy || {};
  const maxDiscount = policy.maxDiscountPct ?? 15;
  const minStock = policy.minStockForDiscount ?? 5;
  const bulkQty = policy.bulkMinQuantity ?? 3;
  const bulkExtra = policy.bulkExtraDiscountPct ?? 5;

  const unitDiscountPct =
    ((params.basePrice - params.offeredPrice) / params.basePrice) * 100;

  // Build merchant rules summary
  const rulesEvaluated: string[] = [
    `Base discount cap: max ${maxDiscount}% off`,
    `Low stock protection: stock must be >= ${minStock} to allow discount`,
    `Bulk volume rule: qty >= ${bulkQty} unlocks an additional ${bulkExtra}% discount`,
    ...(policy.customRules || []),
  ];

  const statePayload = {
    base_price_usd: params.basePrice,
    offered_price_usd: params.offeredPrice,
    quantity_ordered: params.quantity,
    stock_remaining: params.stockRemaining ?? 25,
    unit_discount_pct: Math.round(unitDiscountPct * 10) / 10,
    max_allowed_discount_pct: maxDiscount,
    min_stock_required: minStock,
    bulk_min_quantity: bulkQty,
    bulk_extra_discount_pct: bulkExtra,
    policy_rules: rulesEvaluated,
  };

  const result = await executeJevDecisions({
    state: statePayload,
    questions: {
      is_acceptable_margin: {
        type: "noul",
        instructions:
          "Does this buyer's offer satisfy the seller policy allowing up to the maximum discount percentage, respecting stock thresholds and volume bonuses?",
      },
    },
  });

  const decision = result.decisions.is_acceptable_margin;
  const probability = decision.probability ?? (decision.value === true ? 1.0 : 0.0);
  const acceptable = probability >= 0.5;

  // Confidence is distance from 0.5 (near 0.5 means highly borderline/uncertain)
  // Normalizing |prob - 0.5| * 2 -> 0 to 1
  const decisionConfidence = Math.abs(probability - 0.5) * 2;
  const shouldEscalateToGrok = decisionConfidence < (1 - threshold);

  const escalationReason = shouldEscalateToGrok
    ? `Borderline negotiation offer (probability: ${Math.round(probability * 100)}%). Escalate to Grok to formulate an intelligent counter-proposal.`
    : undefined;

  return {
    acceptable,
    probability,
    discountPct: unitDiscountPct,
    latencyMs: result.latencyMs,
    rulesEvaluated,
    cascade: {
      confidence: Math.round(decisionConfidence * 100) / 100,
      confidenceThreshold: threshold,
      shouldEscalateToGrok,
      escalationReason,
    },
  };
}

/**
 * 3. Pre-Flight Spend Risk Gate (Noul) with Cascading
 * Verifies final basket amount against hard spend caps and safety parameters.
 */
export async function checkPreFlightRisk(params: {
  basketTotal: number;
  spendCap: number;
  itemCount: number;
  merchantName: string;
  userPolicy?: string[];
  confidenceThreshold?: number;
}): Promise<{
  allowed: boolean;
  probability: number;
  latencyMs: number;
  cascade: CascadeMetadata;
}> {
  const threshold = params.confidenceThreshold ?? DEFAULT_CONFIDENCE_THRESHOLD;

  // Hard deterministic check first (Layer 1 code defense)
  if (params.basketTotal > params.spendCap) {
    return {
      allowed: false,
      probability: 0.0,
      latencyMs: 1,
      cascade: {
        confidence: 1.0,
        confidenceThreshold: threshold,
        shouldEscalateToGrok: false,
        escalationReason: undefined,
      },
    };
  }

  const result = await executeJevDecisions({
    state: {
      basket_total: params.basketTotal,
      spend_cap: params.spendCap,
      item_count: params.itemCount,
      merchant: params.merchantName,
      user_policy: params.userPolicy || ["Strict spend cap enforcement", "Legitimate merchant domain"],
    },
    questions: {
      within_budget_policy: {
        type: "noul",
        instructions:
          "Is the total transaction strictly within authorized limits and compliant with security & spend policies?",
      },
    },
  });

  const decision = result.decisions.within_budget_policy;
  const probability = decision.probability ?? (decision.value === true ? 1.0 : 0.0);
  const confidence = Math.abs(probability - 0.5) * 2;
  const shouldEscalateToGrok = confidence < (1 - threshold);

  return {
    allowed: probability >= 0.5,
    probability,
    latencyMs: result.latencyMs,
    cascade: {
      confidence: Math.round(confidence * 100) / 100,
      confidenceThreshold: threshold,
      shouldEscalateToGrok,
      escalationReason: shouldEscalateToGrok
        ? "Risk boundary uncertain; escalate to Grok for user confirmation."
        : undefined,
    },
  };
}
