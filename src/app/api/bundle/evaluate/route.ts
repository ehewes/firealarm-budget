import { NextRequest, NextResponse } from "next/server";
import { evaluateBundleUpsell, BundleAddOnItem } from "@/lib/bundler";

export const runtime = "nodejs";

const DEFAULT_CATALOG_ADDONS: BundleAddOnItem[] = [
  {
    id: "addon_socks_01",
    title: "Aero Cushion Anti-Blister Running Socks (3-Pack)",
    category: "Apparel & Accessories",
    basePrice: 18.0,
    costPrice: 4.5,
    stockRemaining: 45,
  },
  {
    id: "addon_cap_02",
    title: "Ultralight Breathable Running Cap",
    category: "Apparel & Accessories",
    basePrice: 24.0,
    costPrice: 6.0,
    stockRemaining: 18,
  },
  {
    id: "addon_cleaner_03",
    title: "Carbon Shield Foam Shoe Cleaning Kit",
    category: "Shoe Care",
    basePrice: 15.0,
    costPrice: 3.0,
    stockRemaining: 22,
  },
];

/**
 * POST /api/bundle/evaluate
 *
 * Evaluates whether an unapproved single-item discount can be transformed
 * into an approved multi-item basket upsell.
 */
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();

    const {
      primaryProduct,
      catalogAddOns = DEFAULT_CATALOG_ADDONS,
      sellerBundlePolicy,
    } = body;

    if (!primaryProduct || !primaryProduct.basePrice || !primaryProduct.offeredPrice) {
      return NextResponse.json(
        { error: "primaryProduct with basePrice and offeredPrice is required." },
        { status: 400 }
      );
    }

    const proposal = await evaluateBundleUpsell({
      primaryProduct,
      catalogAddOns,
      sellerBundlePolicy,
    });

    return NextResponse.json({
      status: "success",
      bundleProposal: proposal,
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
