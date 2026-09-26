import { NextRequest, NextResponse } from "next/server";
import { dispatchCommerceToolCall } from "@/lib/tools";

export const runtime = "nodejs";

/**
 * POST /api/rpc/checkout
 *
 * Machine RPC endpoint for autonomous agents to obtain a live payable checkout permalink.
 */
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { reservation_id, reservationId } = body;

    const targetReservationId = reservation_id || reservationId;

    if (!targetReservationId) {
      return NextResponse.json(
        { error: "reservation_id is required to generate checkout permalink." },
        { status: 400 }
      );
    }

    const result = await dispatchCommerceToolCall("execute_checkout", {
      reservation_id: targetReservationId,
    });

    return NextResponse.json({
      status: "success",
      checkout: result,
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
