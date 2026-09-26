import { NextRequest, NextResponse } from "next/server";
import { getEdenSession } from "@/lib/eden";

export const runtime = "nodejs";

/**
 * GET /v1/sessions/[code]
 *
 * Returns session metadata, status, rules, and purchasing permissions.
 */
export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ code: string }> }
) {
  const { code } = await params;
  const session = getEdenSession(code);

  if (!session) {
    return NextResponse.json(
      { error: { code: "session_not_found", message: `Session ${code} not found or expired.` } },
      { status: 404 }
    );
  }

  return NextResponse.json({
    code: session.code,
    store: session.store,
    collection: session.collection,
    status: session.status,
    product_count: session.product_count,
    snapshot_at: session.snapshot_at,
    rules: session.rules,
    can_purchase: session.can_purchase,
    session_url: session.session_url,
    grok_url: session.grok_url,
  });
}
