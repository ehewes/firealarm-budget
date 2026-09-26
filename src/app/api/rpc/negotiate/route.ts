import { NextRequest, NextResponse } from "next/server";
import { cascadeNegotiation } from "@/lib/orchestrator";

export const runtime = "nodejs";

/**
 * POST /api/rpc/negotiate
 *
 * Machine RPC endpoint for autonomous agents to negotiate price on a product/variant.
 * Uses System-1 Jev for sub-100ms standard approvals and cascades to System-2 Grok for counter-proposals.
 */
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();

    const {
      variantId,
      productTitle = "Product",
      basePrice,
      targetPrice,
      qty = 1,
      stockRemaining = 20,
      sellerPolicy,
    } = body;

    if (!targetPrice || !basePrice) {
      return NextResponse.json(
        { error: "basePrice and targetPrice are required fields." },
        { status: 400 }
      );
    }

    const result = await cascadeNegotiation({
      productTitle,
      basePrice: Number(basePrice),
      offeredPrice: Number(targetPrice),
      quantity: Number(qty),
      stockRemaining: Number(stockRemaining),
      policy: sellerPolicy,
    });

    return NextResponse.json({
      status: "success",
      variantId,
      negotiation: result.data,
      tier: result.tierUsed,
      confidence: result.confidence,
      telemetry: {
        totalLatencyMs: result.totalLatencyMs,
        system1LatencyMs: result.system1LatencyMs,
        system2LatencyMs: result.system2LatencyMs,
        tokensSavedEstimate: result.tokensSavedEstimate,
        costSavedEstimateUsd: result.costSavedEstimateUsd,
      },
      nextActions: {
        reserveEndpoint: "/api/rpc/reserve",
        checkoutEndpoint: "/api/rpc/checkout",
      },
    });
  } catch (err: unknown) {
    const error = err as Error;
    return NextResponse.json(
      {
        status: "error",
        error: error.message,
      },
      { status: 500 }
    );
  }
}
