import { NextRequest, NextResponse } from "next/server";
import { getEdenSession, applyEdenRules } from "@/lib/eden";

export const runtime = "nodejs";

/**
 * GET /v1/sessions/[code]/products
 *
 * Returns ranked products with session rules applied server-side.
 * Includes a human & agent-friendly 'why' justification per item.
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

  // Parse query filters
  const searchParams = req.nextUrl.searchParams;
  const query = searchParams.get("q")?.toLowerCase();
  const category = searchParams.get("category")?.toLowerCase();
  const maxPerPiece = searchParams.get("max_per_piece")
    ? parseFloat(searchParams.get("max_per_piece")!)
    : undefined;
  const limit = Math.min(25, parseInt(searchParams.get("limit") || "10", 10));

  // Merge session rules with query overrides
  const effectiveRules = {
    ...session.rules,
    ...(maxPerPiece !== undefined ? { max_per_piece: maxPerPiece } : {}),
  };

  let candidates = session.products;

  // Optional category filter
  if (category) {
    candidates = candidates.filter((p) =>
      p.tree_path.some((seg) => seg.toLowerCase().includes(category))
    );
  }

  // Optional search query
  if (query) {
    candidates = candidates.filter(
      (p) =>
        p.title.toLowerCase().includes(query) ||
        p.tree_path.some((seg) => seg.toLowerCase().includes(query))
    );
  }

  // Apply server-side rules (hard filters + Jev fuzzy scoring)
  const rankedItems = await applyEdenRules(candidates, effectiveRules);
  const items = rankedItems.slice(0, limit);

  return NextResponse.json({
    items,
    session_url: session.session_url,
    total_matching: rankedItems.length,
    rules_applied: effectiveRules,
  });
}
