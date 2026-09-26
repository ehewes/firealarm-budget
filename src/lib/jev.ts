/**
 * Jev System-1 Decision Client (OpenRouter Decisions API)
 *
 * Implements typed, sub-second micro-decisions:
 * - `choice`: Selects from discrete criteria with calibrated probabilities (variant resolution)
 * - `noul`: Evaluates boolean assertions with true-probability (margin & risk gates)
 * - `score`: Evaluates ordinal rating scales
 *
 * Built-in Defense:
 * - Layer 1 Mathematical & Financial Guardrails (0ms fast path)
 * - Regional sizing normalization (UK/EU -> US)
 * - Semantic color synonym enrichment
 * - Negative intent ("NOT" clause) protection
 * - Out-of-stock detection and Grok substitution cascade
 */

import {
  validateAndSanitizePricing,
  normalizeShoeSize,
  enrichVariantAttributes,
  extractExclusions,
} from "./normalizer";

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
 * 1. Hardened Variant Resolution with Normalization, Negative Intent, and Stock Awareness
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

  // Step 1: Regional size normalization (e.g. UK 9 -> US 10)
  const { normalizedQuery, detectedRegionalSize } = normalizeShoeSize(params.userIntent);

  // Step 2: Negative intent extraction (e.g. "NOT black or navy")
  const { hasExclusions, excludedTerms } = extractExclusions(normalizedQuery);

  // Step 3: Build enriched criteria with color family tags and inventory status
  const criteria: Record<string, string> = {};
  const variantMap = new Map<string, (typeof params.variants)[0]>();

  for (const v of params.variants) {
    const vid = String(v.id);
    variantMap.set(vid, v);

    const isOOS = v.available === false || v.inventoryQuantity === 0;
    const stockStatus = isOOS
      ? " [OUT OF STOCK - 0 AVAILABLE]"
      : v.inventoryQuantity !== undefined
      ? ` [IN STOCK: ${v.inventoryQuantity}]`
      : " [IN STOCK]";

    // Enrich title with standard color families (e.g. Triple Noir -> Black)
    const enrichedTitle = enrichVariantAttributes(v.title);
    criteria[vid] = `${enrichedTitle}${v.price ? ` - $${v.price}` : ""}${stockStatus}`;
  }

  // Construct strict instructions handling exclusions and regional equivalents
  let instructions =
    "Select the exact variant ID that matches the buyer's specifications (size, color, style, availability).";

  if (hasExclusions) {
    instructions += ` CRITICAL NEGATIVE CONSTRAINT: The user explicitly demanded NO: [${excludedTerms.join(
      ", "
    )}]. You MUST NEVER select a variant containing these excluded attributes.`;
  }

  if (detectedRegionalSize) {
    instructions += ` SIZING NOTE: User requested ${detectedRegionalSize.region} ${detectedRegionalSize.originalSize}, which equals US ${detectedRegionalSize.usEquivalent}.`;
  }

  const result = await executeJevDecisions({
    state: {
      product_title: params.productTitle,
      user_request: normalizedQuery,
      original_request: params.userIntent,
      excluded_terms: excludedTerms,
      has_negative_constraint: hasExclusions,
      detected_regional_sizing: detectedRegionalSize,
    },
    questions: {
      selected_variant: {
        type: "choice",
        instructions,
        criteria,
      },
    },
  });

  const decision = result.decisions.selected_variant;
  const variantId = String(decision.value);
  const selectedVariantObj = variantMap.get(variantId);

  // Compute confidence
  let confidence = decision.confidence ?? decision.probability ?? 1.0;
  if (decision.distribution && decision.distribution[variantId] !== undefined) {
    confidence = decision.distribution[variantId];
  }

  // Out-of-Stock Protection: If the matched variant is out of stock, drop confidence and trigger Grok substitution
  const isSelectedOOS =
    selectedVariantObj &&
    (selectedVariantObj.available === false || selectedVariantObj.inventoryQuantity === 0);

  let shouldEscalateToGrok = confidence < threshold;
  let escalationReason: string | undefined;

  if (isSelectedOOS) {
    shouldEscalateToGrok = true;
    confidence = Math.min(confidence, 0.45); // Depress confidence because item cannot be purchased immediately
    escalationReason = `Selected variant '${selectedVariantObj.title}' is currently Out of Stock. Escalate to Grok to offer nearest in-stock alternatives or backorder.`;
  } else if (shouldEscalateToGrok) {
    escalationReason = `Low confidence match (${Math.round(confidence * 100)}% < ${Math.round(
      threshold * 100
    )}%). Customer intent may be ambiguous or conflicting.`;
  }

  return {
    variantId,
    confidence: Math.round(confidence * 100) / 100,
    distribution: decision.distribution,
    latencyMs: result.latencyMs,
    cascade: {
      confidence: Math.round(confidence * 100) / 100,
      confidenceThreshold: threshold,
      shouldEscalateToGrok,
      escalationReason,
    },
  };
}

/**
 * 2. Hardened Margin Evaluation with Layer 1 Guardrails and Tipping Support
 */
export async function evaluateMargin(params: {
  basePrice: number;
  offeredPrice: number;
  quantity?: number;
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

  // LAYER 1 DEFENSE: Run mathematical and financial sanity checks first (0ms latency, zero tokens)
  const sanity = validateAndSanitizePricing({
    basePrice: params.basePrice,
    offeredPrice: params.offeredPrice,
    quantity: params.quantity,
    stockRemaining: params.stockRemaining,
  });

  // If Layer 1 caught a definite outcome (e.g. Tipping, negative offer, or volume exploit)
  if (sanity.immediateAction) {
    const isAccepted = sanity.immediateAction === "accept";
    return {
      acceptable: isAccepted,
      probability: isAccepted ? 1.0 : 0.0,
      discountPct: sanity.effectiveDiscountPct,
      latencyMs: 1, // 1ms instant evaluation
      rulesEvaluated: [`Layer 1 Financial Guardrail: ${sanity.reason}`],
      cascade: {
        confidence: 1.0,
        confidenceThreshold: threshold,
        shouldEscalateToGrok: false,
        escalationReason: undefined,
      },
    };
  }

  const effectiveDiscount = sanity.effectiveDiscountPct;
  const safeQty = sanity.sanitizedQuantity;
  const safeStock = params.stockRemaining ?? 25;

  // Build merchant rules summary
  const rulesEvaluated: string[] = [
    `Base discount cap: max ${maxDiscount}% off`,
    `Low stock protection: stock must be >= ${minStock} to allow discount`,
    `Bulk volume rule: qty >= ${bulkQty} unlocks an additional ${bulkExtra}% discount`,
    ...(policy.customRules || []),
  ];

  // LAYER 2: Evaluate through Jev System-1
  const result = await executeJevDecisions({
    state: {
      base_price_usd: sanity.sanitizedBasePrice,
      offered_price_usd: sanity.sanitizedOfferedPrice,
      quantity_ordered: safeQty,
      stock_remaining: safeStock,
      unit_discount_pct: effectiveDiscount,
      max_allowed_discount_pct: maxDiscount,
      min_stock_required: minStock,
      bulk_min_quantity: bulkQty,
      bulk_extra_discount_pct: bulkExtra,
      policy_rules: rulesEvaluated,
    },
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

  // Calibrate confidence (distance from 0.5)
  const decisionConfidence = Math.abs(probability - 0.5) * 2;
  const shouldEscalateToGrok = decisionConfidence < (1 - threshold);

  const escalationReason = shouldEscalateToGrok
    ? `Borderline negotiation offer (probability: ${Math.round(
        probability * 100
      )}%). Escalate to Grok to formulate an intelligent counter-proposal.`
    : undefined;

  return {
    acceptable,
    probability,
    discountPct: effectiveDiscount,
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
 * 3. Pre-Flight Spend Risk Gate (Noul)
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

/**
 * 4. Jev Score Primitive: Dynamic Deal Quality Index (1 - 10)
 * Evaluates the overall commercial attractiveness of an offer on an ordinal scale.
 */
export async function scoreDealQuality(params: {
  basePrice: number;
  offeredPrice: number;
  quantity?: number;
  stockRemaining?: number;
  customerTier?: "standard" | "vip" | "enterprise";
}): Promise<{
  score: number; // 1 to 10
  action: "auto_accept" | "negotiate_counter" | "reject";
  rationale: string;
  latencyMs: number;
}> {
  const sanity = validateAndSanitizePricing({
    basePrice: params.basePrice,
    offeredPrice: params.offeredPrice,
    quantity: params.quantity,
    stockRemaining: params.stockRemaining,
  });

  if (sanity.immediateAction === "accept") {
    return {
      score: 10,
      action: "auto_accept",
      rationale: sanity.reason || "Full price or tipping premium offer.",
      latencyMs: 1,
    };
  }

  if (sanity.immediateAction === "reject") {
    return {
      score: 1,
      action: "reject",
      rationale: sanity.reason || "Violates financial sanity bounds.",
      latencyMs: 1,
    };
  }

  const result = await executeJevDecisions({
    state: {
      base_price_usd: sanity.sanitizedBasePrice,
      offered_price_usd: sanity.sanitizedOfferedPrice,
      effective_discount_pct: sanity.effectiveDiscountPct,
      quantity_ordered: sanity.sanitizedQuantity,
      stock_remaining: params.stockRemaining ?? 20,
      customer_tier: params.customerTier || "standard",
    },
    questions: {
      deal_quality_score: {
        type: "score",
        instructions:
          "On a scale of 1 (terrible deal for merchant) to 10 (exceptionally profitable win-win deal), rate this buyer's offer considering volume, margin, and stock.",
        min: 1,
        max: 10,
      },
    },
  });

  const rawScore = Number(result.decisions.deal_quality_score?.value ?? 5);
  const score = Math.max(1, Math.min(10, Math.round(rawScore)));

  let action: "auto_accept" | "negotiate_counter" | "reject" = "negotiate_counter";
  let rationale = `Deal score evaluated at ${score}/10.`;

  if (score >= 8) {
    action = "auto_accept";
    rationale = `High-scoring deal (${score}/10). Instant approval recommended.`;
  } else if (score <= 4) {
    action = "reject";
    rationale = `Low-scoring deal (${score}/10). Discount too steep for available inventory.`;
  } else {
    action = "negotiate_counter";
    rationale = `Borderline deal (${score}/10). Moderate compromise counter-offer recommended.`;
  }

  return {
    score,
    action,
    rationale,
    latencyMs: result.latencyMs,
  };
}

/**
 * 5. Review & Sizing Fit Intelligence (Jev Sub-100ms Review Distiller)
 * Extracts structured sizing fit, durability, and buyer sentiment from customer review snippets.
 */
export async function distillProductReviews(params: {
  productTitle: string;
  reviews: string[];
  targetSize?: string | number;
}): Promise<{
  sizeFit: "runs_small" | "true_to_size" | "runs_large";
  durabilityScore: number; // 1 to 10
  overallSentimentRecommendation: boolean;
  recommendedSizeAdjustment: string;
  latencyMs: number;
}> {
  const reviewSnippets = params.reviews.slice(0, 8).join("\n---\n");

  const result = await executeJevDecisions({
    state: {
      product_title: params.productTitle,
      user_target_size: params.targetSize || "Standard",
      customer_reviews: reviewSnippets,
    },
    questions: {
      sizing_fit: {
        type: "choice",
        instructions:
          "Based on the customer reviews, how does this shoe fit relative to standard sizing?",
        criteria: {
          "runs_small": "Customers consistently report shoe feels tight/small, recommend sizing up half a size.",
          "true_to_size": "Customers report true to size, fits as expected.",
          "runs_large": "Customers report shoe runs big/loose, recommend sizing down.",
        },
      },
      durability_rating: {
        type: "score",
        instructions:
          "On a scale of 1 to 10, how well does the product hold up according to long-term review feedback?",
        min: 1,
        max: 10,
      },
      verified_satisfaction: {
        type: "noul",
        instructions:
          "Do the vast majority of verified purchasers recommend this item to other runners?",
      },
    },
  });

  const fitDecision = String(result.decisions.sizing_fit?.value || "true_to_size") as
    | "runs_small"
    | "true_to_size"
    | "runs_large";

  const durability = Math.max(
    1,
    Math.min(10, Math.round(Number(result.decisions.durability_rating?.value ?? 8)))
  );

  const satisfactionProb = result.decisions.verified_satisfaction?.probability ?? 0.8;
  const isRecommended = satisfactionProb >= 0.5;

  let adjustment = "Order your normal standard size.";
  if (fitDecision === "runs_small") {
    adjustment = "Consider sizing up by +0.5 based on frequent customer feedback.";
  } else if (fitDecision === "runs_large") {
    adjustment = "Consider sizing down by -0.5 based on frequent customer feedback.";
  }

  return {
    sizeFit: fitDecision,
    durabilityScore: durability,
    overallSentimentRecommendation: isRecommended,
    recommendedSizeAdjustment: adjustment,
    latencyMs: result.latencyMs,
  };
}
