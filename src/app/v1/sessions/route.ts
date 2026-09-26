import { NextRequest, NextResponse } from "next/server";
import { createEdenSession, EdenRules } from "@/lib/eden";

export const runtime = "nodejs";

/**
 * POST /v1/sessions
 *
 * Starts a new Eden Matrix session and initiates background scraping.
 * Matches docs/API.md specification.
 */
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { url, rules } = body;

    if (!url) {
      return NextResponse.json(
        { error: { code: "invalid_url", message: "Target store URL is required." } },
        { status: 400 }
      );
    }

    const session = await createEdenSession({
      url,
      rules: rules as EdenRules,
    });

    // Returns 202 Accepted per API.md spec
    return NextResponse.json(
      {
        code: session.code,
        status: session.status,
        session_url: session.session_url,
        grok_url: session.grok_url,
      },
      { status: 202 }
    );
  } catch (err: unknown) {
    const error = err as Error;
    return NextResponse.json(
      { error: { code: "scrape_failed", message: error.message } },
      { status: 502 }
    );
  }
}
