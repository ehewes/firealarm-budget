/**
 * Model Cascade Orchestrator (System-1 Jev -> System-2 Grok)
 *
 * Implements the Thinking Fast and Slow pattern for Autonomous Commerce:
 * 1. Fast Path (85-90%): Jev evaluates typed rules and variant resolution in ~100ms.
 * 2. Deep Path (10-15%): Low confidence (< threshold) or complex negotiation escalates to Grok.
 */

import {
  resolveVariant,
  evaluateMargin,
  checkPreFlightRisk,
  SellerPolicyRules,
  DEFAULT_CONFIDENCE_THRESHOLD,
} from "./jev";
import { grokNegotiateCounterOffer, grokResolveAmbiguity } from "./grok";

export interface CascadeResult<T> {
  tierUsed: "system_1_jev" | "system_2_grok_escalated";
  data: T;
  confidence: number;
  totalLatencyMs: number;
  system1LatencyMs: number;
  system2LatencyMs?: number;
  tokensSavedEstimate: number;
  costSavedEstimateUsd: number;
  escalationReason?: string;
}

/**
 * 1. Unified Variant Matching with Cascade
 */
export async function cascadeVariantMatch(params: {
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
}): Promise<
  CascadeResult<{
    variantId: string;
    reasoning?: string;
    clarifyingQuestion?: string;
  }>
> {
  const threshold = params.confidenceThreshold ?? DEFAULT_CONFIDENCE_THRESHOLD;
  const t0 = Date.now();

  // Tier 1: Try Jev System-1 first
  const jevRes = await resolveVariant({
    userIntent: params.userIntent,
    productTitle: params.productTitle,
    variants: params.variants,
    confidenceThreshold: threshold,
  });

  // If high confidence, take the instant fast path!
  if (!jevRes.cascade.shouldEscalateToGrok) {
    return {
      tierUsed: "system_1_jev",
      data: {
        variantId: jevRes.variantId,
        reasoning: "Resolved via Jev System-1 high-confidence match.",
      },
      confidence: jevRes.confidence,
      totalLatencyMs: Date.now() - t0,
      system1LatencyMs: jevRes.latencyMs,
      tokensSavedEstimate: 1450, // Saved vs calling heavy LLM prompt
      costSavedEstimateUsd: 0.004,
    };
  }

  // Tier 2: Low confidence detected -> Escalate to Grok System-2
  const grokRes = await grokResolveAmbiguity({
    userIntent: params.userIntent,
    productTitle: params.productTitle,
    variants: params.variants,
    escalationReason: jevRes.cascade.escalationReason,
  });

  return {
    tierUsed: "system_2_grok_escalated",
    data: {
      variantId: grokRes.bestMatchVariantId || jevRes.variantId,
      reasoning: grokRes.reasoning,
      clarifyingQuestion: grokRes.clarifyingQuestionForBuyer,
    },
    confidence: grokRes.confidence,
    totalLatencyMs: Date.now() - t0,
    system1LatencyMs: jevRes.latencyMs,
    system2LatencyMs: grokRes.latencyMs,
    tokensSavedEstimate: 0,
    costSavedEstimateUsd: 0,
    escalationReason: jevRes.cascade.escalationReason,
  };
}

/**
 * 2. Unified Price Negotiation with Cascade
 */
export async function cascadeNegotiation(params: {
  productTitle: string;
  basePrice: number;
  offeredPrice: number;
  quantity: number;
  stockRemaining?: number;
  policy?: SellerPolicyRules;
  confidenceThreshold?: number;
}): Promise<
  CascadeResult<{
    action: "accept" | "counter_offer" | "reject";
    finalPrice: number;
    discountPct: number;
    message: string;
    reasoning: string;
  }>
> {
  const threshold = params.confidenceThreshold ?? DEFAULT_CONFIDENCE_THRESHOLD;
  const stock = params.stockRemaining ?? 20;
  const t0 = Date.now();

  // Tier 1: Jev evaluates margin against seller rules
  const jevRes = await evaluateMargin({
    basePrice: params.basePrice,
    offeredPrice: params.offeredPrice,
    quantity: params.quantity,
    stockRemaining: stock,
    policy: params.policy,
    confidenceThreshold: threshold,
  });

  // Fast Path: Clear acceptance or clear rejection that doesn't warrant Grok reasoning
  if (!jevRes.cascade.shouldEscalateToGrok) {
    const isAccepted = jevRes.acceptable;
    return {
      tierUsed: "system_1_jev",
      data: {
        action: isAccepted ? "accept" : "reject",
        finalPrice: isAccepted ? params.offeredPrice : params.basePrice,
        discountPct: isAccepted ? jevRes.discountPct : 0,
        message: isAccepted
          ? `Offer accepted at $${params.offeredPrice}/unit.`
          : `Offer declined. Base price remains $${params.basePrice}.`,
        reasoning: `Decided instantly by Jev System-1 (${Math.round(jevRes.probability * 100)}% margin compliance).`,
      },
      confidence: jevRes.cascade.confidence,
      totalLatencyMs: Date.now() - t0,
      system1LatencyMs: jevRes.latencyMs,
      tokensSavedEstimate: 1800,
      costSavedEstimateUsd: 0.005,
    };
  }

  // Tier 2: Borderline bid or complex policy -> Escalate to Grok System-2
  const grokRes = await grokNegotiateCounterOffer({
    productTitle: params.productTitle,
    basePrice: params.basePrice,
    offeredPrice: params.offeredPrice,
    quantity: params.quantity,
    stockRemaining: stock,
    sellerRules: jevRes.rulesEvaluated,
    escalationReason: jevRes.cascade.escalationReason,
  });

  let finalAction = grokRes.action;
  const rawFinalPrice =
    finalAction === "accept"
      ? params.offeredPrice
      : finalAction === "counter_offer" && grokRes.counterPrice
      ? grokRes.counterPrice
      : params.basePrice;
  let finalPrice = Math.round(rawFinalPrice * 100) / 100;
  let message = grokRes.messageToBuyer;
  let reasoning = grokRes.reasoning;

  // HARD INVARIANT POST-GUARD (Defense against Prompt Injection & Model Exploits):
  // Never allow LLM outputs to violate the seller's mathematical margin policy.
  const baseMaxDiscount = params.policy?.maxDiscountPct ?? 25;
  const bulkExtra =
    params.policy?.bulkMinQuantity && params.quantity >= params.policy.bulkMinQuantity
      ? params.policy.bulkExtraDiscountPct ?? 0
      : 0;
  const effectiveMaxDiscount = Math.min(baseMaxDiscount + bulkExtra, 80);
  const minAllowedPrice = Math.round(params.basePrice * (1 - effectiveMaxDiscount / 100) * 100) / 100;

  if (finalPrice < minAllowedPrice) {
    if (finalAction === "accept") {
      // Prompt injection or model drift attempted to accept below-floor price
      finalAction = "counter_offer";
      finalPrice = minAllowedPrice;
      message = `We cannot accept $${params.offeredPrice}. The lowest allowed price is $${minAllowedPrice}.`;
      reasoning = `Financial Invariant Guard: Prevented unauthorized discount ($${params.offeredPrice} vs floor $${minAllowedPrice} at max ${effectiveMaxDiscount}% discount). Overridden to compliant counter-offer.`;
    } else if (finalAction === "counter_offer") {
      finalPrice = minAllowedPrice;
      message = `Our best possible price is $${minAllowedPrice}.`;
      reasoning = `Financial Invariant Guard: Clamped counter-offer to seller's minimum floor price of $${minAllowedPrice} (${effectiveMaxDiscount}% max discount cap).`;
    }
  }

  // Invariant: Never counter higher than original base price
  if (finalPrice > params.basePrice) {
    finalPrice = params.basePrice;
  }

  const discountPct = ((params.basePrice - finalPrice) / params.basePrice) * 100;

  return {
    tierUsed: "system_2_grok_escalated",
    data: {
      action: finalAction,
      finalPrice,
      discountPct: Math.round(discountPct * 10) / 10,
      message,
      reasoning,
    },
    confidence: 0.9,
    totalLatencyMs: Date.now() - t0,
    system1LatencyMs: jevRes.latencyMs,
    system2LatencyMs: grokRes.latencyMs,
    tokensSavedEstimate: 0,
    costSavedEstimateUsd: 0,
    escalationReason: jevRes.cascade.escalationReason,
  };
}
