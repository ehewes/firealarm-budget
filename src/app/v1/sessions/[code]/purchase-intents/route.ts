import { NextRequest, NextResponse } from "next/server";
import { getEdenSession, createPurchaseIntent } from "@/lib/eden";

export const runtime = "nodejs";

/**
 * POST /v1/sessions/[code]/purchase-intents
 *
 * Generates an ephemeral purchase intent with quoted total and confirmation link.
 * Never charges automatically — gated behind explicit human confirmation.
 */
export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ code: string }> }
) {
  try {
    const { code } = await params;
    const session = getEdenSession(code);

    if (!session) {
      return NextResponse.json(
        { error: { code: "session_not_found", message: `Session ${code} not found.` } },
        { status: 404 }
      );
    }

    const body = await req.json();
    const productIds: string[] = body.product_ids || [];

    if (productIds.length === 0) {
      return NextResponse.json(
        { error: { code: "invalid_request", message: "product_ids array is required." } },
        { status: 400 }
      );
    }

    // Compute quoted total from session products
    const selectedProducts = session.products.filter((p) => productIds.includes(p.id));
    const quotedTotal = selectedProducts.reduce((sum, p) => sum + p.price, 0);

    const intent = createPurchaseIntent({
      sessionCode: code,
      productIds,
      quotedTotal: Math.round(quotedTotal * 100) / 100,
    });

    return NextResponse.json(
      {
        intent_id: intent.intent_id,
        quoted_total: intent.quoted_total,
        confirm_url: intent.confirm_url,
        card: intent.card,
      },
      { status: 201 }
    );
  } catch (err: unknown) {
    const error = err as Error;
    return NextResponse.json(
      { error: { code: "server_error", message: error.message } },
      { status: 500 }
    );
  }
}
