/**
 * Smart Basket & Bundle Upsell Engine
 *
 * Converts steep single-item discount requests into profitable multi-item bundles:
 * 1. Detects when a buyer's offer exceeds single-item discount limits (e.g. asking 20% off on 1 item).
 * 2. Cross-references store catalog for high-margin, relevant add-ons (socks, caps, insoles, cleaner).
 * 3. Uses Jev System-1 to evaluate bundle profitability and Grok System-2 to craft the proposal.
 */

import { executeJevDecisions } from "./jev";
import { grokNegotiateCounterOffer } from "./grok";

export interface BundleAddOnItem {
  id: string;
  title: string;
  category: string;
  basePrice: number;
  costPrice?: number;
  stockRemaining: number;
}

export interface BundleEvaluationParams {
  primaryProduct: {
    id: string;
    title: string;
    basePrice: number;
    offeredPrice: number;
    quantity: number;
  };
  catalogAddOns: BundleAddOnItem[];
  sellerBundlePolicy?: {
    maxSingleItemDiscountPct?: number; // e.g. 15%
    maxBundleDiscountPct?: number; // e.g. 22%
    minBundleOrderValue?: number; // e.g. $100
  };
}

export interface BundleProposal {
  canOfferBundle: boolean;
  reasoning: string;
  recommendedAddOn?: BundleAddOnItem;
  originalTotal: number;
  bundleTotalRetail: number;
  discountedBundlePrice: number;
  effectiveDiscountPct: number;
  buyerSavingsAmount: number;
  sellerIncrementalProfit: number;
  messageToBuyer: string;
  latencyMs: number;
}

/**
 * Evaluates whether a rejected or borderline single-item bid can be converted
 * into an approved multi-item basket upsell.
 */
export async function evaluateBundleUpsell(
  params: BundleEvaluationParams
): Promise<BundleProposal> {
  const startTime = Date.now();
  const policy = params.sellerBundlePolicy || {};
  const maxSingleDiscount = policy.maxSingleItemDiscountPct ?? 15;
  const maxBundleDiscount = policy.maxBundleDiscountPct ?? 22;

  const basePrice = params.primaryProduct.basePrice * params.primaryProduct.quantity;
  const offeredPrice = params.primaryProduct.offeredPrice * params.primaryProduct.quantity;
  const requestedDiscountPct = ((basePrice - offeredPrice) / basePrice) * 100;

  // If the single item discount is already within acceptable limits, no bundle needed
  if (requestedDiscountPct <= maxSingleDiscount) {
    return {
      canOfferBundle: false,
      reasoning: "Single item offer is already within standard margin policy.",
      originalTotal: basePrice,
      bundleTotalRetail: basePrice,
      discountedBundlePrice: offeredPrice,
      effectiveDiscountPct: requestedDiscountPct,
      buyerSavingsAmount: basePrice - offeredPrice,
      sellerIncrementalProfit: 0,
      messageToBuyer: "Offer accepted as single item.",
      latencyMs: Date.now() - startTime,
    };
  }

  // Filter available in-stock add-on items (stock >= 3)
  const availableAddOns = params.catalogAddOns.filter((a) => a.stockRemaining >= 3);

  if (availableAddOns.length === 0) {
    return {
      canOfferBundle: false,
      reasoning: "No eligible high-margin add-ons currently in stock.",
      originalTotal: basePrice,
      bundleTotalRetail: basePrice,
      discountedBundlePrice: basePrice,
      effectiveDiscountPct: 0,
      buyerSavingsAmount: 0,
      sellerIncrementalProfit: 0,
      messageToBuyer: `Cannot approve ${requestedDiscountPct.toFixed(1)}% discount on single item.`,
      latencyMs: Date.now() - startTime,
    };
  }

  // Step 1: Use Jev System-1 Choice primitive to select the most commercially synergistic add-on
  const criteria: Record<string, string> = {};
  for (const item of availableAddOns) {
    criteria[item.id] = `${item.title} ($${item.basePrice.toFixed(2)}) - Category: ${item.category}`;
  }

  let selectedAddOnId = availableAddOns[0].id;

  try {
    const jevChoice = await executeJevDecisions({
      state: {
        primary_product: params.primaryProduct.title,
        requested_discount_pct: requestedDiscountPct,
        available_add_ons: availableAddOns.map((a) => ({
          id: a.id,
          title: a.title,
          price: a.basePrice,
        })),
      },
      questions: {
        best_cross_sell: {
          type: "choice",
          instructions:
            "Select the most natural, high-attach companion accessory for this primary product to build a compelling discount bundle.",
          criteria,
        },
      },
    });

    if (jevChoice.decisions.best_cross_sell?.value) {
      selectedAddOnId = String(jevChoice.decisions.best_cross_sell.value);
    }
  } catch {
    // Fallback: pick the first relevant add-on
    selectedAddOnId = availableAddOns[0].id;
  }

  const chosenItem = availableAddOns.find((a) => a.id === selectedAddOnId) || availableAddOns[0];

  // Step 2: Compute Bundle Economics
  const combinedRetail = basePrice + chosenItem.basePrice;
  // Apply the target bundle discount (e.g. 18-20%)
  const bundleDiscountPct = Math.min(maxBundleDiscount, requestedDiscountPct);
  const discountedPrice = Math.round(combinedRetail * (1 - bundleDiscountPct / 100) * 100) / 100;
  const buyerSavings = Math.round((combinedRetail - discountedPrice) * 100) / 100;
  const incrementalRevenue = Math.round((discountedPrice - offeredPrice) * 100) / 100;

  const message = `We cannot discount the ${params.primaryProduct.title} by ${requestedDiscountPct.toFixed(
    0
  )}% alone. However, if you add the ${chosenItem.title} ($${chosenItem.basePrice}), we can unlock an exclusive ${bundleDiscountPct.toFixed(
    0
  )}% bundle discount. Total for both: $${discountedPrice.toFixed(2)} (Save $${buyerSavings.toFixed(2)}).`;

  return {
    canOfferBundle: true,
    reasoning: `Converted single-item margin deficit into a higher basket AOV ($${discountedPrice.toFixed(
      2
    )} vs $${offeredPrice.toFixed(2)}).`,
    recommendedAddOn: chosenItem,
    originalTotal: basePrice,
    bundleTotalRetail: combinedRetail,
    discountedBundlePrice: discountedPrice,
    effectiveDiscountPct: bundleDiscountPct,
    buyerSavingsAmount: buyerSavings,
    sellerIncrementalProfit: incrementalRevenue,
    messageToBuyer: message,
    latencyMs: Date.now() - startTime,
  };
}
