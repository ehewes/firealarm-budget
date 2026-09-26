/**
 * Rule Conflict Resolution & Invariant Defense Engine
 *
 * Enforces an immutable 4-Tier Precedence Order so that lower-tier optimization rules
 * (bundles, substitutions, discounts) can NEVER compromise higher-tier invariants
 * (exclusions, budget ceilings, and security guardrails).
 */

import { EdenRules, EdenProductItem } from "./eden";

export interface RuleEvaluationResult {
  passed: boolean;
  disqualificationTier?: "TIER_0_SECURITY" | "TIER_1_EXCLUSION" | "TIER_2_BOUNDS" | "TIER_3_QUALITY";
  disqualificationReason?: string;
}

export interface CheckoutPriceVerification {
  isValid: boolean;
  status: "verified" | "price_changed_acceptable" | "rule_violated_after_price_change";
  originalPrice: number;
  livePrice: number;
  newPerPiece: number;
  reason?: string;
}

/**
 * TIER 1 VETO: Negative Constraints are Absolute Kill-Switches
 * Evaluates whether an item matches any excluded category or negative intent.
 * An exclusion match instantly destroys the candidate, regardless of any inclusions!
 */
export function isExplicitlyExcluded(
  product: EdenProductItem,
  excludeCategories?: string[],
  negativeTerms?: string[]
): { isExcluded: boolean; matchedTerm?: string } {
  const haystack = [
    product.title,
    ...(product.tree_path || []),
    product.grade || "",
    ...(typeof product.attrs?.tags === "object" && Array.isArray(product.attrs.tags)
      ? (product.attrs.tags as string[])
      : []),
  ]
    .join(" ")
    .toLowerCase();

  // 1. Check exclude_categories
  if (excludeCategories && excludeCategories.length > 0) {
    for (const ex of excludeCategories) {
      const term = ex.trim().toLowerCase();
      if (term && haystack.includes(term)) {
        return { isExcluded: true, matchedTerm: ex };
      }
    }
  }

  // 2. Check negative terms (e.g. "not navy", "no polyester")
  if (negativeTerms && negativeTerms.length > 0) {
    for (const neg of negativeTerms) {
      const term = neg.trim().toLowerCase();
      if (term && haystack.includes(term)) {
        return { isExcluded: true, matchedTerm: neg };
      }
    }
  }

  return { isExcluded: false };
}

/**
 * Comprehensive 4-Tier Candidate Evaluator
 * Guarantees zero compromise across all rule levels.
 */
export function evaluateProductWithPrecedence(
  product: EdenProductItem,
  rules: EdenRules
): RuleEvaluationResult {
  // -------------------------------------------------------------------------
  // TIER 1: ABSOLUTE NEGATIVE VETO (0ms)
  // Must execute BEFORE any inclusion checks to avoid taxonomy paradoxes!
  // (e.g. Shorts being included because 'bottoms' was selected)
  // -------------------------------------------------------------------------
  const exclusionCheck = isExplicitlyExcluded(product, rules.exclude_categories);
  if (exclusionCheck.isExcluded) {
    return {
      passed: false,
      disqualificationTier: "TIER_1_EXCLUSION",
      disqualificationReason: `Violates hard exclusion: matched forbidden term '${exclusionCheck.matchedTerm}'.`,
    };
  }

  // -------------------------------------------------------------------------
  // TIER 2: HARD MATHEMATICAL BOUNDS (Strict Inequality)
  // Notes or discounts can NEVER rescue an item that violates these bounds!
  // -------------------------------------------------------------------------
  if (rules.max_per_piece !== undefined && product.per_piece > rules.max_per_piece) {
    return {
      passed: false,
      disqualificationTier: "TIER_2_BOUNDS",
      disqualificationReason: `Exceeds max per piece: $${product.per_piece.toFixed(
        2
      )} > cap $${rules.max_per_piece.toFixed(2)}.`,
    };
  }

  if (rules.max_total !== undefined && product.price > rules.max_total) {
    return {
      passed: false,
      disqualificationTier: "TIER_2_BOUNDS",
      disqualificationReason: `Exceeds max total budget: $${product.price.toFixed(
        2
      )} > budget $${rules.max_total.toFixed(2)}.`,
    };
  }

  if (rules.min_pieces !== undefined && product.pieces < rules.min_pieces) {
    return {
      passed: false,
      disqualificationTier: "TIER_2_BOUNDS",
      disqualificationReason: `Below minimum piece requirement: ${product.pieces} pcs < required ${rules.min_pieces} pcs.`,
    };
  }

  // -------------------------------------------------------------------------
  // TIER 3: QUALITY FLOOR INVARIANT
  // Price discounts can NEVER buy down physical condition/grade!
  // -------------------------------------------------------------------------
  if (rules.grades && rules.grades.length > 0) {
    const haystack = [product.grade, product.title, ...product.tree_path]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();

    const matchesQuality = rules.grades.some((g) => haystack.includes(g.toLowerCase()));
    if (!matchesQuality) {
      return {
        passed: false,
        disqualificationTier: "TIER_3_QUALITY",
        disqualificationReason: `Fails quality floor: does not match requested grade(s): [${rules.grades.join(
          ", "
        )}].`,
      };
    }
  }

  // -------------------------------------------------------------------------
  // TIER 4: POSITIVE INCLUSION FILTERS
  // -------------------------------------------------------------------------
  if (rules.include_categories && rules.include_categories.length > 0) {
    const haystack = [product.title, ...product.tree_path].join(" ").toLowerCase();
    const matchesInclusion = rules.include_categories.some((inc) =>
      haystack.includes(inc.toLowerCase())
    );
    if (!matchesInclusion) {
      return {
        passed: false,
        disqualificationReason: `Does not match included category requirements: [${rules.include_categories.join(
          ", "
        )}].`,
      };
    }
  }

  return { passed: true };
}

/**
 * TIER 0 CHECKOUT INVARIANT: Time-of-Check vs Time-of-Use Verification
 *
 * Called during live purchase intent confirmation:
 * If the merchant increased the price between initial scrape and checkout,
 * verify that the new price STILL adheres to the user's hard budget rules!
 */
export function verifyCheckoutPriceConsistency(params: {
  originalPrice: number;
  livePrice: number;
  pieces: number;
  rules: EdenRules;
}): CheckoutPriceVerification {
  const originalPrice = Number(params.originalPrice);
  const livePrice = Number(params.livePrice);
  const pieces = Math.max(1, params.pieces);
  const newPerPiece = Math.round((livePrice / pieces) * 100) / 100;

  // Case 1: Price unchanged
  if (Math.abs(livePrice - originalPrice) < 0.01) {
    return {
      isValid: true,
      status: "verified",
      originalPrice,
      livePrice,
      newPerPiece,
    };
  }

  // Case 2: Price increased -> Re-run Tier 2 bounds against live price!
  if (params.rules.max_per_piece !== undefined && newPerPiece > params.rules.max_per_piece) {
    return {
      isValid: false,
      status: "rule_violated_after_price_change",
      originalPrice,
      livePrice,
      newPerPiece,
      reason: `Live price increased to $${newPerPiece}/piece, which breaches your $${params.rules.max_per_piece}/piece cap. Checkout aborted for safety.`,
    };
  }

  if (params.rules.max_total !== undefined && livePrice > params.rules.max_total) {
    return {
      isValid: false,
      status: "rule_violated_after_price_change",
      originalPrice,
      livePrice,
      newPerPiece,
      reason: `Live total increased to $${livePrice}, which breaches your $${params.rules.max_total} budget ceiling. Checkout aborted for safety.`,
    };
  }

  // Case 3: Price changed, but still within user's rules (requires human approval of the diff)
  return {
    isValid: true,
    status: "price_changed_acceptable",
    originalPrice,
    livePrice,
    newPerPiece,
    reason: `Price moved from $${originalPrice} to $${livePrice} ($${newPerPiece}/piece), but remains within your authorized budget rules.`,
  };
}

/**
 * TIER 0 VIRTUAL CARD LIMIT SAFETY CEILING
 *
 * Guarantees that single-use card pre-authorizations can NEVER exceed the user's max_total rule,
 * even with tax/shipping buffers.
 */
export function calculateSafeCardLimit(quotedTotal: number, maxTotalCap?: number): number {
  const standardLimit = Math.round(quotedTotal * 1.05 * 100) / 100; // 5% buffer
  if (maxTotalCap !== undefined && maxTotalCap > 0) {
    return Math.min(standardLimit, Math.round(maxTotalCap * 100) / 100);
  }
  return standardLimit;
}

/**
 * SELLER CONFLICT INVARIANT: Inventory Scarcity vs Volume Incentives
 *
 * When remaining stock < minStockForDiscount, stock protection strictly supersedes bulk bonuses.
 */
export function resolveInventoryVsVolumeConflict(params: {
  requestedQty: number;
  stockRemaining: number;
  minStockThreshold?: number;
  volumeBonusPct?: number;
  baseDiscountPct?: number;
}): { effectiveDiscountPct: number; reason: string } {
  const minStock = params.minStockThreshold ?? 5;
  const stock = params.stockRemaining;
  const volumeBonus = params.volumeBonusPct ?? 5;
  const baseDiscount = params.baseDiscountPct ?? 15;

  // Invariant: Inventory scarcity overrides all volume discounts
  if (stock < minStock) {
    return {
      effectiveDiscountPct: 0,
      reason: `Scarce inventory protection active (stock: ${stock} < threshold: ${minStock}). Volume discount overridden to 0%.`,
    };
  }

  const effective = baseDiscount + (params.requestedQty >= 3 ? volumeBonus : 0);
  return {
    effectiveDiscountPct: effective,
    reason: `Stock healthy (${stock} >= ${minStock}). Volume discount unlocked (${effective}%).`,
  };
}
