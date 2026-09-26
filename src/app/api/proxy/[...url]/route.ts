import { NextRequest, NextResponse } from "next/server";
import { transpileStorefront } from "@/lib/transpiler";

export const runtime = "nodejs";

/**
 * GET /api/proxy/[...url]
 *
 * Edge Reverse Proxy for Autonomous Agents:
 * Intercepts visual human-facing URLs, extracts structured product graph,
 * strips 95%+ of visual DOM bloat, and returns the Machine Contract.
 *
 * Examples:
 * - GET /api/proxy/https://gymshark.com/products/pro-runner
 * - GET /api/proxy/https://store.myshopify.com/products/carbon-shoe
 */
export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ url: string[] }> }
) {
  try {
    const resolvedParams = await params;
    const urlSegments = resolvedParams?.url || [];

    // Reconstruct target URL from catch-all segments
    // Next.js splits by '/' so ['https:', '', 'store.com', 'products', 'shoe']
    let targetUrlString = urlSegments.join("/");

    // Also check if passed via query param e.g. /api/proxy?url=https://...
    const queryUrl = req.nextUrl.searchParams.get("url");
    if (queryUrl) {
      targetUrlString = queryUrl;
    }

    if (!targetUrlString) {
      return NextResponse.json(
        {
          error: "Missing target URL parameter.",
          usage: "GET /api/proxy/https://store.com/products/product-name or GET /api/proxy?url=https://...",
        },
        { status: 400 }
      );
    }

    const transpiled = await transpileStorefront(targetUrlString);

    return NextResponse.json(transpiled, {
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "public, s-maxage=300, stale-while-revalidate=600",
        "X-Agent-Gateway-Protocol": "commerce/1.0",
        "X-Tokens-Saved": transpiled.telemetry.token_compression_ratio,
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
