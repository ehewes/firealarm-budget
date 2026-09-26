import { NextRequest, NextResponse } from "next/server";
import { runAgentNegotiationBattle } from "@/lib/agent-battle";

export const runtime = "nodejs";

/**
 * POST /api/negotiate/battle
 *
 * Runs an autonomous Agent-vs-Agent negotiation battle:
 * - Autonomous Buyer Bot (with target price and budget ceiling)
 * - Seller Gateway (with Jev System-1 margin engine and Grok System-2 counter-proposals)
 */
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();

    const {
      productTitle = "Aero Carbon 3000 Running Shoe",
      basePrice = 120,
      stockRemaining = 12,
      buyer = {
        buyerName: "Autonomous Buyer Agent #1",
        initialBid: 85,
        maxSpendCap: 100,
        urgency: "medium",
      },
      sellerPolicy = {
        maxDiscountPct: 15,
        minStockForDiscount: 5,
        bulkMinQuantity: 3,
        bulkExtraDiscountPct: 5,
      },
      maxRounds = 3,
    } = body;

    const result = await runAgentNegotiationBattle({
      productTitle,
      basePrice: Number(basePrice),
      stockRemaining: Number(stockRemaining),
      buyer,
      sellerPolicy,
      maxRounds: Number(maxRounds),
    });

    return NextResponse.json(result);
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
