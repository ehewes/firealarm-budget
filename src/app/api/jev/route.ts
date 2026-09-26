import { NextRequest, NextResponse } from "next/server";
import {
  executeJevDecisions,
  resolveVariant,
  evaluateMargin,
  checkPreFlightRisk,
} from "@/lib/jev";

export const runtime = "nodejs";

/**
 * GET /api/jev: Quick health check and sample mock/live decision
 */
export async function GET(req: NextRequest) {
  const hasKey = Boolean(process.env.OPENROUTER_API_KEY);

  if (!hasKey) {
    return NextResponse.json({
      status: "needs_key",
      message:
        "OPENROUTER_API_KEY is not set yet in .env.local. Add your key to test live Jev calls.",
      model: process.env.JEV_MODEL || "typesafe/jev-1.13",
      endpoint: "https://openrouter.ai/api/alpha/decisions",
    });
  }

  try {
    // Run a fast sample micro-decision
    const sample = await evaluateMargin({
      basePrice: 120,
      offeredPrice: 105,
      quantity: 2,
      maxDiscountPct: 15,
    });

    return NextResponse.json({
      status: "live",
      model: process.env.JEV_MODEL || "typesafe/jev-1.13",
      sampleTest: sample,
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

/**
 * POST /api/jev: Invoke specific Jev decision primitives
 * Body:
 * - action: "variant" | "margin" | "risk" | "raw"
 * - payload: parameters for the primitive
 */
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const action = body.action || "raw";

    if (action === "variant") {
      const { userIntent, productTitle, variants } = body;
      const res = await resolveVariant({
        userIntent,
        productTitle,
        variants,
      });
      return NextResponse.json(res);
    }

    if (action === "margin") {
      const { basePrice, offeredPrice, quantity, maxDiscountPct } = body;
      const res = await evaluateMargin({
        basePrice,
        offeredPrice,
        quantity,
        maxDiscountPct,
      });
      return NextResponse.json(res);
    }

    if (action === "risk") {
      const { basketTotal, spendCap, itemCount, merchantName } = body;
      const res = await checkPreFlightRisk({
        basketTotal,
        spendCap,
        itemCount,
        merchantName,
      });
      return NextResponse.json(res);
    }

    // Default: Raw custom questions
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
