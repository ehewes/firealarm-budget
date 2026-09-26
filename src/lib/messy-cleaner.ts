/**
 * Real-World Messy Storefront Normalizer & Data Healing Engine
 *
 * Handles broken layouts, missing fields, foreign price formats (European commas),
 * buried wholesale lot counts, protocol-relative images, and dirty SEO titles.
 */

import { TranspiledVariant } from "./transpiler";

/**
 * 1. Buried Piece Count & Wholesale Lot Extractor
 * Discovers hidden lot sizes inside titles, descriptions, and tags.
 * e.g. "Box of 15", "10pcs Lot", "pack of 8", "x25 Bale", "(20 pieces)"
 */
export function extractLotPieceCount(...texts: (string | undefined | null)[]): number {
  const combined = texts.filter(Boolean).join(" ");
  if (!combined) return 1;

  // Pattern 1: "box of 15", "lot of 10", "pack of 8", "bale of 25", "set of 4"
  const boxOfMatch = combined.match(/\b(?:box|lot|pack|bale|bundle|set)\s+of\s+(\d+)\b/i);
  if (boxOfMatch) {
    const count = parseInt(boxOfMatch[1], 10);
    if (count > 0 && count < 10000) return count;
  }

  // Pattern 2: "10pcs", "15 pieces", "20 units", "10-pack"
  const pcsMatch = combined.match(/\b(\d+)\s*(?:pcs|pieces|units|items|-pack)\b/i);
  if (pcsMatch) {
    const count = parseInt(pcsMatch[1], 10);
    if (count > 0 && count < 10000) return count;
  }

  // Pattern 3: "x25" or "25x"
  const xMatch = combined.match(/(?:\bx(\d+)\b|\b(\d+)x\b)/i);
  if (xMatch) {
    const count = parseInt(xMatch[1] || xMatch[2], 10);
    if (count > 1 && count < 10000) return count;
  }

  // Pattern 4: "(15)" or "(15 items)"
  const parenMatch = combined.match(/\((\d+)(?:\s*(?:items|pcs|pieces))?\)/i);
  if (parenMatch) {
    const count = parseInt(parenMatch[1], 10);
    if (count > 1 && count < 10000) return count;
  }

  return 1; // Default to single piece
}

/**
 * 2. Resilient Messy Price Parser
 * Handles:
 * - Currency prefixes: "£89.99", "US $95.00", "CAD 120"
 * - European commas: "€110,50" -> 110.50
 * - Price ranges: "$80.00 - $120.00" -> 80.00
 * - Prefixes: "From $45.00", "Starting at $30"
 * - Promotional text: "FREE" -> 0.00
 */
export function parseMessyPriceString(raw: unknown): number {
  if (typeof raw === "number") {
    return isNaN(raw) ? 0 : Math.round(raw * 100) / 100;
  }

  if (!raw || typeof raw !== "string") {
    return 0;
  }

  const trimmed = raw.trim();
  if (/^free$/i.test(trimmed)) {
    return 0.0;
  }

  // Handle price ranges: "$80.00 - $120.00" -> extract first price
  const rangeSplit = trimmed.split(/\s*[-–—]\s*/);
  const targetStr = rangeSplit[0];

  const isZeroDecimalCurrency = /[¥₩]|(?:jpy|krw|vnd)/i.test(targetStr);

  // Extract the numeric candidate token including dots, commas, spaces: e.g. "1.450,00" or "156,00"
  const numTokenMatch = targetStr.match(/(\d+(?:[.,\s]\d+)*)/);
  if (!numTokenMatch) return 0;

  let cleaned = numTokenMatch[1].replace(/\s+/g, "");

  // Handle European comma vs thousands comma formatting: e.g. "110,50", "18,500", "1.250,50"
  if (cleaned.includes(",") && !cleaned.includes(".")) {
    if (isZeroDecimalCurrency) {
      // JPY, KRW have no cents: "18,500" -> "18500"
      cleaned = cleaned.replace(/,/g, "");
    } else if (/,\d{3}$/.test(cleaned)) {
      // Thousands separator with 3 digits at end: "18,500" or "1,450" -> 18500 / 1450
      cleaned = cleaned.replace(/,/g, "");
    } else {
      // Decimal separator: "110,50" -> "110.50"
      cleaned = cleaned.replace(",", ".");
    }
  } else if (cleaned.includes(".") && cleaned.includes(",")) {
    if (cleaned.indexOf(".") < cleaned.indexOf(",")) {
      // European thousand dot, comma decimal: "1.250,50" -> "1250.50"
      cleaned = cleaned.replace(/\./g, "").replace(",", ".");
    } else {
      // Standard US: "1,250.50" -> "1250.50"
      cleaned = cleaned.replace(/,/g, "");
    }
  }

  const val = parseFloat(cleaned);
  return isNaN(val) ? 0 : Math.round(val * 100) / 100;
}

/**
 * Curated high-res fallback imagery by category
 */
const CATEGORY_FALLBACK_IMAGES: Record<string, string> = {
  footwear: "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=800&auto=format&fit=crop",
  bottoms: "https://images.unsplash.com/photo-1541099649105-f69ad21f3246?w=800&auto=format&fit=crop",
  outerwear: "https://images.unsplash.com/photo-1551028719-00167b16eac5?w=800&auto=format&fit=crop",
  tops: "https://images.unsplash.com/photo-1521572267360-ee0c2909d518?w=800&auto=format&fit=crop",
  vintage: "https://images.unsplash.com/photo-1556905055-8f358a7a47b2?w=800&auto=format&fit=crop",
  default: "https://images.unsplash.com/photo-1441986300917-64674bd600d8?w=800&auto=format&fit=crop",
};

/**
 * 3. Protocol-Relative & Broken Image Healer
 */
export function resolveImageUrl(
  rawImage?: string | null,
  originUrl?: string,
  categoryHint?: string
): string {
  if (!rawImage || typeof rawImage !== "string" || !rawImage.trim()) {
    const key = categoryHint?.toLowerCase() || "default";
    return CATEGORY_FALLBACK_IMAGES[key] || CATEGORY_FALLBACK_IMAGES.default;
  }

  const trimmed = rawImage.trim();

  // If it's a data URI placeholder (SVG/GIF blur) or svg placeholder file
  if (
    trimmed.startsWith("data:image/svg") ||
    trimmed.startsWith("data:image/gif") ||
    trimmed.includes("placeholder.svg") ||
    trimmed.includes("blank.gif")
  ) {
    const key = categoryHint?.toLowerCase() || "default";
    return CATEGORY_FALLBACK_IMAGES[key] || CATEGORY_FALLBACK_IMAGES.default;
  }

  // Fix protocol-relative URLs: "//cdn.shopify.com/..." -> "https://cdn.shopify.com/..."
  if (trimmed.startsWith("//")) {
    return `https:${trimmed}`;
  }

  // Fix root-relative URLs: "/images/products/..." -> "https://store.com/images/..."
  if (trimmed.startsWith("/")) {
    if (originUrl) {
      try {
        const origin = new URL(originUrl).origin;
        return `${origin}${trimmed}`;
      } catch {
        return `https://demo-store.com${trimmed}`;
      }
    }
  }

  // Already a full HTTP/HTTPS URL
  if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) {
    return trimmed;
  }

  return CATEGORY_FALLBACK_IMAGES.default;
}

/**
 * 4. Clean Dirty SEO Titles & Decode HTML Entities
 */
export function cleanProductTitle(rawTitle?: string | null): string {
  if (!rawTitle || typeof rawTitle !== "string") {
    return "Product";
  }

  let cleaned = rawTitle
    // Strip HTML tags: <h1>, <b>, <span>
    .replace(/<[^>]*>/g, "")
    // Decode common HTML entities
    .replace(/&amp;/g, "&")
    .replace(/&trade;/g, "")
    .replace(/&reg;/g, "")
    .replace(/&#39;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&bull;/g, "•")
    .replace(/&middot;/g, "•")
    // Remove SEO suffixes: " - Official Store | Buy Online", "| Free Shipping"
    .replace(/\s*[-–|•]\s*(?:official\s*(?:store|outlet|site)|buy\s*online|free\s*shipping|shop\s*now).*$/i, "")
    .trim();

  return cleaned || "Product";
}

/**
 * 5. Full Storefront Object Healer
 * Turns broken, partial, or missing web scraped objects into a guaranteed, clean contract
 */
export function normalizeMessyStorefront(
  rawPayload: Record<string, unknown>,
  sourceUrl: string
): {
  id: string;
  title: string;
  description: string;
  base_price: number;
  pieces: number;
  per_piece: number;
  currency: string;
  image_url: string;
  variants: TranspiledVariant[];
} {
  const urlObj = new URL(sourceUrl.startsWith("http") ? sourceUrl : `https://${sourceUrl}`);
  const slug = urlObj.pathname.split("/").filter(Boolean).pop() || "product";

  // 1. Clean Title
  const rawTitle = (rawPayload.title || rawPayload.name || rawPayload.ogTitle) as string;
  let title = cleanProductTitle(rawTitle);
  if (!title || title === "Product" || title === "undefined") {
    // Generate clean title from URL slug
    title = slug
      .replace(/[-_]/g, " ")
      .replace(/\b\w/g, (c) => c.toUpperCase());
  }

  // 2. Clean Description (Strip script/style tags and HTML)
  const rawDesc = (rawPayload.description || rawPayload.body_html || "") as string;
  const description = rawDesc
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, "")
    .replace(/<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>/gi, "")
    .replace(/<[^>]*>/g, "")
    .trim()
    .slice(0, 400);

  // 3. Clean Price
  const rawPrice = rawPayload.price || rawPayload.base_price || rawPayload.offers;
  let basePrice = parseMessyPriceString(rawPrice);
  if (basePrice <= 0) basePrice = 95.0; // Sensible default fallback

  // 4. Discover Lot / Pieces Count
  const pieces = extractLotPieceCount(title, description, rawPayload.tags as string);
  const perPiece = Math.round((basePrice / pieces) * 100) / 100;

  // 5. Clean Image
  const rawImg = (rawPayload.image || rawPayload.image_url || (Array.isArray(rawPayload.images) ? rawPayload.images[0] : null)) as string;
  const imageUrl = resolveImageUrl(rawImg, urlObj.origin);

  // 6. Ensure Variants Array is never empty
  const rawVariants = (rawPayload.variants as Array<Record<string, unknown>>) || [];
  let variants: TranspiledVariant[] = [];

  if (rawVariants.length > 0) {
    variants = rawVariants.map((v, i) => ({
      id: String(v.id || `var_${i + 1}`),
      title: cleanProductTitle(String(v.title || `Option ${i + 1}`)),
      price: parseMessyPriceString(v.price) || basePrice,
      available: Boolean(v.available !== false),
      inventoryQuantity: typeof v.inventory_quantity === "number" ? v.inventory_quantity : 10,
      sku: String(v.sku || `SKU-${i + 1}`),
    }));
  } else {
    // Synthesize single default SKU variant
    variants = [
      {
        id: `var_${slug}_default`,
        title: "Standard Edition",
        price: basePrice,
        available: true,
        inventoryQuantity: 12,
        sku: `SKU-${slug.toUpperCase()}`,
      },
    ];
  }

  return {
    id: String(rawPayload.id || `prod_${slug}`),
    title,
    description,
    base_price: basePrice,
    pieces,
    per_piece: perPiece,
    currency: String(rawPayload.currency || "USD"),
    image_url: imageUrl,
    variants,
  };
}
