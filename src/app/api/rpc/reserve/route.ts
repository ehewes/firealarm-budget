import { NextRequest, NextResponse } from "next/server";
import { dispatchCommerceToolCall } from "@/lib/tools";

export const runtime = "nodejs";

/**
 * POST /api/rpc/reserve
 *
 * Machine RPC endpoint for autonomous agents to lock in inventory and price.
 * Returns an ephemeral reservation ID with a 5-minute TTL lock.
 */
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { variant_id, variantId, quantity = 1, qty = 1, agreed_price, lockedPrice } = body;

    const targetVariantId = variant_id || variantId;
    const targetQuantity = quantity || qty;
    const targetPrice = agreed_price || lockedPrice;

    if (!targetVariantId) {
      return NextResponse.json(
        { error: "variant_id is required to reserve inventory." },
        { status: 400 }
      );
    }

    const result = await dispatchCommerceToolCall("reserve_inventory", {
      variant_id: targetVariantId,
      quantity: targetQuantity,
      agreed_price: targetPrice,
    });

    return NextResponse.json({
      status: "success",
      reservation: result,
      nextActions: {
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
