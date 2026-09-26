/**
 * Preprocessing, Normalization & Defensive Guardrails (Layer 1 Defense)
 *
 * Runs before AI models to eliminate mathematical exploits, handle currency edge-cases,
 * normalize regional units/sizes, and detect semantic pitfalls (like negative intent).
 */

export interface PricingSanityCheck {
  isValid: boolean;
  immediateAction?: "accept" | "reject";
  reason?: string;
  sanitizedBasePrice: number;
  sanitizedOfferedPrice: number;
  sanitizedQuantity: number;
  effectiveDiscountPct: number;
}

/**
 * 1. Financial & Mathematical Guardrail
 * Guards against division-by-zero, negative prices, volume arbitrage, and tipping.
 */
export function validateAndSanitizePricing(params: {
  basePrice: number;
  offeredPrice: number;
  quantity?: number;
  stockRemaining?: number;
}): PricingSanityCheck {
  const base = Number(params.basePrice);
  const offered = Number(params.offeredPrice);
  const qty = Math.max(1, Math.floor(Number(params.quantity || 1)));
  const stock = params.stockRemaining !== undefined ? Number(params.stockRemaining) : 999;

  // Edge Case: Non-numeric or NaN
  if (isNaN(base) || isNaN(offered) || isNaN(qty)) {
    return {
      isValid: false,
      immediateAction: "reject",
      reason: "Malformed price or quantity: contains non-numeric values.",
      sanitizedBasePrice: 0,
      sanitizedOfferedPrice: 0,
      sanitizedQuantity: 0,
      effectiveDiscountPct: 0,
    };
  }

  // Edge Case: Negative or zero offered price
  if (offered <= 0) {
    return {
      isValid: false,
      immediateAction: "reject",
      reason: "Invalid offer: offered price must be strictly greater than $0.00.",
      sanitizedBasePrice: base,
      sanitizedOfferedPrice: offered,
      sanitizedQuantity: qty,
      effectiveDiscountPct: 100,
    };
  }

  // Edge Case: Free or zero base price
  if (base <= 0) {
    return {
      isValid: true,
      immediateAction: "accept",
      reason: "Item is complimentary / base price is zero.",
      sanitizedBasePrice: 0,
      sanitizedOfferedPrice: offered,
      sanitizedQuantity: qty,
      effectiveDiscountPct: 0,
    };
  }

  // Edge Case: Volume Arbitrage Exploit (Requested qty exceeds available inventory)
  if (qty > stock) {
    return {
      isValid: false,
      immediateAction: "reject",
      reason: `Inventory shortage: requested quantity (${qty}) exceeds remaining stock (${stock}). Bulk pricing rejected.`,
      sanitizedBasePrice: base,
      sanitizedOfferedPrice: offered,
      sanitizedQuantity: qty,
      effectiveDiscountPct: 0,
    };
  }

  // Edge Case: Buyer offering MORE than base price (Tipping / Premium)
  if (offered >= base) {
    return {
      isValid: true,
      immediateAction: "accept",
      reason: `Buyer offer ($${offered.toFixed(2)}) meets or exceeds base price ($${base.toFixed(2)}). Instant transaction approved.`,
      sanitizedBasePrice: base,
      sanitizedOfferedPrice: offered,
      sanitizedQuantity: qty,
      effectiveDiscountPct: 0,
    };
  }

  // Compute safe discount with 2 decimal precision (no floating point jitter)
  const discountPct = Math.round(((base - offered) / base) * 10000) / 100;

  return {
    isValid: true,
    sanitizedBasePrice: Math.round(base * 100) / 100,
    sanitizedOfferedPrice: Math.round(offered * 100) / 100,
    sanitizedQuantity: qty,
    effectiveDiscountPct: discountPct,
  };
}

/**
 * 2. Regional Shoe Sizing & Synonym Normalizer
 * Resolves UK/EU sizes to US equivalents so models don't miscalculate.
 */
export function normalizeShoeSize(input: string): {
  normalizedQuery: string;
  detectedRegionalSize?: { region: "UK" | "EU"; originalSize: number; usEquivalent: number };
} {
  const ukMatch = input.match(/\b(?:uk|u\.k\.)\s*(?:size\s*)?([0-9]+(?:\.[0-9]+)?)\b/i);
  if (ukMatch) {
    const ukSize = parseFloat(ukMatch[1]);
    const usEquivalent = ukSize + 1.0; // Standard Men's conversion (UK + 1 = US)
    const normalizedQuery = input.replace(
      ukMatch[0],
      `US ${usEquivalent} (equivalent to UK ${ukSize})`
    );
    return {
      normalizedQuery,
      detectedRegionalSize: { region: "UK", originalSize: ukSize, usEquivalent },
    };
  }

  const euMatch = input.match(/\b(?:eu|e\.u\.)\s*(?:size\s*)?([0-9]+(?:\.[0-9]+)?)\b/i);
  if (euMatch) {
    const euSize = parseFloat(euMatch[1]);
    // Approximate EU to US Men's conversion (EU 43 ~ US 10)
    const usEquivalent = Math.round((euSize - 33) * 10) / 10;
    const normalizedQuery = input.replace(
      euMatch[0],
      `US ${usEquivalent} (equivalent to EU ${euSize})`
    );
    return {
      normalizedQuery,
      detectedRegionalSize: { region: "EU", originalSize: euSize, usEquivalent },
    };
  }

  return { normalizedQuery: input };
}

/**
 * 3. Color & Attribute Synonyms Dictionary
 */
const COLOR_SYNONYMS: Record<string, string[]> = {
  black: ["noir", "triple noir", "stealth", "onyx", "obsidian", "dark shadow", "jet black"],
  white: ["glacier", "cloud", "triple white", "pure platinum", "chalk", "bone"],
  blue: ["navy", "midnight", "royal", "cobalt", "sapphire", "indigo", "ocean"],
  red: ["crimson", "scarlet", "ruby", "maroon", "burgundy", "fire"],
  green: ["pine", "forest", "emerald", "sage", "olive", "moss"],
};

export function enrichVariantAttributes(title: string): string {
  let enriched = title;
  const lower = title.toLowerCase();

  for (const [standardColor, aliases] of Object.entries(COLOR_SYNONYMS)) {
    for (const alias of aliases) {
      if (lower.includes(alias) && !lower.includes(standardColor)) {
        enriched += ` [Color Family: ${standardColor.toUpperCase()}]`;
        break;
      }
    }
  }

  return enriched;
}

/**
 * 4. Negative Intent ("NOT") Detector
 * Extracts explicit exclusions so Jev doesn't fall into the keyword trap.
 */
export function extractExclusions(userIntent: string): {
  hasExclusions: boolean;
  excludedTerms: string[];
  cleanIntent: string;
} {
  const excludedTerms: string[] = [];
  const notRegex = /\b(?:not|never|no|excluding|except|without)\s+([a-zA-Z0-9\s]+?)(?:,|\.|\sand\s|$)/gi;

  let match;
  while ((match = notRegex.exec(userIntent)) !== null) {
    const term = match[1].trim();
    if (term) {
      excludedTerms.push(term);
    }
  }

  return {
    hasExclusions: excludedTerms.length > 0,
    excludedTerms,
    cleanIntent: userIntent,
  };
}
