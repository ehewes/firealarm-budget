import { NextRequest, NextResponse } from "next/server";
import { getEdenSession } from "@/lib/eden";

export const runtime = "nodejs";

/**
 * GET /v1/sessions/[code]/tree
 *
 * Streams / returns the live category taxonomy tree for this session.
 */
export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ code: string }> }
) {
  const { code } = await params;
  const session = getEdenSession(code);

  if (!session) {
    return NextResponse.json(
      { error: { code: "session_not_found", message: `Session ${code} not found.` } },
      { status: 404 }
    );
  }

  return NextResponse.json({
    tree: session.tree,
  });
}
