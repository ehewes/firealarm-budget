/**
 * Agent-vs-Agent Commerce Negotiation Simulator
 *
 * Simulates a live, multi-round negotiation between:
 * 1. Autonomous Buyer Bot (driven by user constraints, spend cap & strategy)
 * 2. Seller Gateway (driven by Jev System-1 fast margin/score & Grok System-2 compromise)
 */

import { evaluateMargin, scoreDealQuality, SellerPolicyRules } from "./jev";
import { grokNegotiateCounterOffer } from "./grok";

export interface BuyerStrategy {
  buyerName: string;
  initialBid: number;
  maxSpendCap: number;
  urgency: "low" | "medium" | "high";
  allowCounterBumps?: boolean;
}

export interface NegotiationRound {
  round: number;
  buyerOffer: number;
  sellerDecision: "accept" | "counter_offer" | "reject";
  sellerCounterPrice?: number;
  sellerReasoning: string;
  sellerTier: "system_1_jev" | "system_2_grok_escalated";
  latencyMs: number;
  buyerResponse: "accept" | "counter" | "walk_away";
  dealStruck: boolean;
}

export interface AgentBattleResult {
  status: "deal_struck" | "impasse";
  productTitle: string;
  basePrice: number;
  finalPrice?: number;
  totalDiscountPct?: number;
  roundsCount: number;
  history: NegotiationRound[];
  totalLatencyMs: number;
  summary: string;
}

/**
 * Executes a live autonomous Agent-vs-Agent negotiation battle
 */
export async function runAgentNegotiationBattle(params: {
  productTitle: string;
  basePrice: number;
  stockRemaining?: number;
  buyer: BuyerStrategy;
  sellerPolicy?: SellerPolicyRules;
  maxRounds?: number;
}): Promise<AgentBattleResult> {
  const maxRounds = params.maxRounds || 3;
  const stock = params.stockRemaining ?? 15;
  const history: NegotiationRound[] = [];
  const startTime = Date.now();

  let currentBuyerBid = params.buyer.initialBid;
  let dealStruck = false;
  let finalAgreedPrice: number | undefined;

  for (let roundNum = 1; roundNum <= maxRounds; roundNum++) {
    const roundStart = Date.now();

    // 1. Seller evaluates buyer's bid through System-1 Jev
    const marginCheck = await evaluateMargin({
      basePrice: params.basePrice,
      offeredPrice: currentBuyerBid,
      quantity: 1,
      stockRemaining: stock,
      policy: params.sellerPolicy,
    });

    let sellerDecision: "accept" | "counter_offer" | "reject" = "reject";
    let sellerCounterPrice: number | undefined;
    let sellerReasoning = "";
    let sellerTier: "system_1_jev" | "system_2_grok_escalated" = "system_1_jev";

    // Fast Path: Jev accepts instantly
    if (marginCheck.acceptable && !marginCheck.cascade.shouldEscalateToGrok) {
      sellerDecision = "accept";
      sellerReasoning = `Approved instantly by Jev System-1 (${Math.round(
        marginCheck.probability * 100
      )}% margin safety).`;
      dealStruck = true;
      finalAgreedPrice = currentBuyerBid;
    } else if (!marginCheck.cascade.shouldEscalateToGrok && !marginCheck.acceptable) {
      // Jev rejects clearly (discount too ridiculous, e.g. 50% off)
      sellerDecision = "reject";
      sellerReasoning = `Offer of $${currentBuyerBid} rejected by Jev System-1: exceeds allowable discount cap.`;
    } else {
      // Deep Path: Borderline bid -> Escalate to Grok System-2 for counter-proposal
      sellerTier = "system_2_grok_escalated";
      const grokRes = await grokNegotiateCounterOffer({
        productTitle: params.productTitle,
        basePrice: params.basePrice,
        offeredPrice: currentBuyerBid,
        quantity: 1,
        stockRemaining: stock,
        sellerRules: marginCheck.rulesEvaluated,
        escalationReason: marginCheck.cascade.escalationReason,
      });

      sellerDecision = grokRes.action;
      sellerCounterPrice = grokRes.counterPrice;
      sellerReasoning = grokRes.reasoning;

      if (sellerDecision === "accept") {
        dealStruck = true;
        finalAgreedPrice = currentBuyerBid;
      }
    }

    // 2. Buyer bot reacts to seller's response
    let buyerResponse: "accept" | "counter" | "walk_away" = "walk_away";

    if (dealStruck) {
      buyerResponse = "accept";
    } else if (sellerDecision === "counter_offer" && sellerCounterPrice) {
      if (sellerCounterPrice <= params.buyer.maxSpendCap) {
        // Seller counter is within buyer's max budget: Buyer accepts!
        buyerResponse = "accept";
        dealStruck = true;
        finalAgreedPrice = sellerCounterPrice;
      } else if (roundNum < maxRounds && currentBuyerBid < params.buyer.maxSpendCap) {
        // Seller counter is too high, but buyer still has headroom to increment
        buyerResponse = "counter";
        const bump = Math.round((params.buyer.maxSpendCap - currentBuyerBid) * 0.5 * 100) / 100;
        currentBuyerBid = Math.min(params.buyer.maxSpendCap, currentBuyerBid + Math.max(2, bump));
      } else {
        buyerResponse = "walk_away";
      }
    } else if (sellerDecision === "reject") {
      if (roundNum < maxRounds && currentBuyerBid < params.buyer.maxSpendCap) {
        buyerResponse = "counter";
        const bump = Math.round((params.buyer.maxSpendCap - currentBuyerBid) * 0.6 * 100) / 100;
        currentBuyerBid = Math.min(params.buyer.maxSpendCap, currentBuyerBid + Math.max(3, bump));
      } else {
        buyerResponse = "walk_away";
      }
    }

    const roundElapsed = Date.now() - roundStart;

    history.push({
      round: roundNum,
      buyerOffer: currentBuyerBid,
      sellerDecision,
      sellerCounterPrice,
      sellerReasoning,
      sellerTier,
      latencyMs: roundElapsed,
      buyerResponse,
      dealStruck,
    });

    if (dealStruck || buyerResponse === "walk_away") {
      break;
    }
  }

  const totalTime = Date.now() - startTime;
  const discountPct =
    finalAgreedPrice !== undefined
      ? Math.round(((params.basePrice - finalAgreedPrice) / params.basePrice) * 1000) / 10
      : undefined;

  const summary = dealStruck
    ? `Deal struck in Round ${history.length} at $${finalAgreedPrice?.toFixed(
        2
      )} (${discountPct}% off base price $${params.basePrice}).`
    : `Negotiation reached an impasse after ${history.length} rounds. Buyer ceiling was $${params.buyer.maxSpendCap}.`;

  return {
    status: dealStruck ? "deal_struck" : "impasse",
    productTitle: params.productTitle,
    basePrice: params.basePrice,
    finalPrice: finalAgreedPrice,
    totalDiscountPct: discountPct,
    roundsCount: history.length,
    history,
    totalLatencyMs: totalTime,
    summary,
  };
}
