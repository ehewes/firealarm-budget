import { NextRequest, NextResponse } from "next/server";
import {
  executeJevDecisions,
  resolveVariant,
  evaluateMargin,
  checkPreFlightRisk,
} from "@/lib/jev";
import { cascadeVariantMatch, cascadeNegotiation } from "@/lib/orchestrator";

export const runtime = "nodejs";

/**
 * GET /api/jev: Health check and quick status
 */
export async function GET() {
  const hasKey = Boolean(process.env.OPENROUTER_API_KEY);

  return NextResponse.json({
    status: hasKey ? "ready" : "needs_key",
    jevModel: process.env.JEV_MODEL || "typesafe/jev-1.13",
    grokModel: process.env.GROK_MODEL || "x-ai/grok-2-1212",
    capabilities: [
      "system_1_choice_variant_resolution",
      "system_1_noul_margin_gate",
      "system_1_noul_spend_risk_gate",
      "system_2_grok_cascade_escalation",
    ],
  });
}

/**
 * POST /api/jev: Invoke Jev primitives or the full Model Cascade
 *
 * Body Actions:
 * - "variant": Standard Jev System-1 variant matcher
 * - "margin": Standard Jev System-1 margin engine with rules
 * - "risk": Pre-flight spend cap risk gate
 * - "cascade_variant": Full cascade (Jev -> Grok if confidence < threshold)
 * - "cascade_negotiate": Full cascade negotiation (Jev -> Grok counter-offer if borderline)
 * - "raw": Raw Jev decision payload
 */
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const action = body.action || "raw";

    // 1. Full Cascade: Variant Resolution
    if (action === "cascade_variant") {
      const { userIntent, productTitle, variants, confidenceThreshold } = body;
      const res = await cascadeVariantMatch({
        userIntent,
        productTitle,
        variants,
        confidenceThreshold,
      });
      return NextResponse.json(res);
    }

    // 2. Full Cascade: Negotiation
    if (action === "cascade_negotiate") {
      const {
        productTitle,
        basePrice,
        offeredPrice,
        quantity,
        stockRemaining,
        policy,
        confidenceThreshold,
      } = body;
      const res = await cascadeNegotiation({
        productTitle,
        basePrice,
        offeredPrice,
        quantity,
        stockRemaining,
        policy,
        confidenceThreshold,
      });
      return NextResponse.json(res);
    }

    // 3. System-1 Primitive: Variant Resolution
    if (action === "variant") {
      const { userIntent, productTitle, variants, confidenceThreshold } = body;
      const res = await resolveVariant({
        userIntent,
        productTitle,
        variants,
        confidenceThreshold,
      });
      return NextResponse.json(res);
    }

    // 4. System-1 Primitive: Margin Evaluation
    if (action === "margin") {
      const {
        basePrice,
        offeredPrice,
        quantity,
        stockRemaining,
        policy,
        confidenceThreshold,
      } = body;
      const res = await evaluateMargin({
        basePrice,
        offeredPrice,
        quantity,
        stockRemaining,
        policy,
        confidenceThreshold,
      });
      return NextResponse.json(res);
    }

    // 5. System-1 Primitive: Pre-Flight Risk Check
    if (action === "risk") {
      const { basketTotal, spendCap, itemCount, merchantName, userPolicy } = body;
      const res = await checkPreFlightRisk({
        basketTotal,
        spendCap,
        itemCount,
        merchantName,
        userPolicy,
      });
      return NextResponse.json(res);
    }

    // 6. System-1 Primitive: Score Deal Quality
    if (action === "score") {
      const { scoreDealQuality } = await import("@/lib/jev");
      const { basePrice, offeredPrice, quantity, stockRemaining, customerTier } = body;
      const res = await scoreDealQuality({
        basePrice,
        offeredPrice,
        quantity,
        stockRemaining,
        customerTier,
      });
      return NextResponse.json(res);
    }

    // 7. System-1 Primitive: Review Intelligence
    if (action === "reviews") {
      const { distillProductReviews } = await import("@/lib/jev");
      const { productTitle, reviews, targetSize } = body;
      const res = await distillProductReviews({
        productTitle,
        reviews: reviews || [],
        targetSize,
      });
      return NextResponse.json(res);
    }

    // 8. Default: Raw custom questions to Jev
    const res = await executeJevDecisions({
      model: body.model,
      state: body.state || {},
      questions: body.questions || {},
    });

    return NextResponse.json(res);
  } catch (err: unknown) {
    const error = err as Error;
    return NextResponse.json(
      {
        error: error.message,
      },
      { status: 500 }
    );
  }
}
