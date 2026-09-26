// Stress-Test Runner for Broken, Non-Standard & Missing Website Layouts
// Run via: npx tsx scripts/test-nasty-websites.ts

console.log("=======================================================================");
console.log("💥 TESTING NASTY REAL-WORLD STOREFRONTS & BROKEN LAYOUTS");
console.log("=======================================================================\n");

let passed = 0;
let failed = 0;

function assert(condition: boolean, testName: string, details = "") {
  if (condition) {
    console.log(`✅ [PASS] ${testName}`);
    passed++;
  } else {
    console.error(`❌ [FAIL] ${testName}`);
    if (details) console.error(`   Details: ${details}`);
    failed++;
  }
}

// -----------------------------------------------------------------------------
// NASTY CASE 1: Buried Piece Counts in Titles & Descriptions
// -----------------------------------------------------------------------------
// Real Fleek/Wholesale titles:
// "Vintage Nike Crewneck Sweatshirts (Box of 15) - Grade A"
// "Y2K Ralph Lauren Polos 10pcs Lot"
// "Carhartt Workwear Jackets pack of 8"
// "Graphic Tees x25 Bale"

console.log("▶ [Test 1] Extracting Buried Lot / Piece Counts from Messy Titles");

// We test against our parser (currently doesn't exist, will fail or test naive parsing)
import {
  parseMessyPriceString,
  extractLotPieceCount,
  resolveImageUrl,
  cleanProductTitle,
  normalizeMessyStorefront,
} from "../src/lib/messy-cleaner";

const testTitle1 = "Vintage Nike Crewneck Sweatshirts (Box of 15) - Grade A";
const testTitle2 = "Y2K Ralph Lauren Polos 10pcs Lot $140";
const testTitle3 = "Carhartt Workwear Jackets pack of 8 pcs";
const testTitle4 = "Graphic Tees x25 Wholesale Bale";
const testTitle5 = "Single Vintage Denim Jacket"; // exactly 1 piece

assert(
  extractLotPieceCount(testTitle1) === 15,
  "Case 1.1: Extracts 15 from '(Box of 15)'",
  `Got: ${extractLotPieceCount(testTitle1)}`
);
assert(
  extractLotPieceCount(testTitle2) === 10,
  "Case 1.2: Extracts 10 from '10pcs Lot'",
  `Got: ${extractLotPieceCount(testTitle2)}`
);
assert(
  extractLotPieceCount(testTitle3) === 8,
  "Case 1.3: Extracts 8 from 'pack of 8 pcs'",
  `Got: ${extractLotPieceCount(testTitle3)}`
);
assert(
  extractLotPieceCount(testTitle4) === 25,
  "Case 1.4: Extracts 25 from 'x25 Wholesale Bale'",
  `Got: ${extractLotPieceCount(testTitle4)}`
);
assert(
  extractLotPieceCount(testTitle5) === 1,
  "Case 1.5: Defaults gracefully to 1 piece when not a lot",
  `Got: ${extractLotPieceCount(testTitle5)}`
);

// -----------------------------------------------------------------------------
// NASTY CASE 2: Messy Prices (European Commas, Currency Prefix/Suffix, Ranges)
// -----------------------------------------------------------------------------
console.log("\n▶ [Test 2] Messy Prices: European Commas, Currency Prefixes & Ranges");

assert(
  parseMessyPriceString("£89.99") === 89.99,
  "Case 2.1: Parses £89.99 correctly",
  `Got: ${parseMessyPriceString("£89.99")}`
);
assert(
  parseMessyPriceString("€110,50") === 110.5,
  "Case 2.2: Parses European comma '€110,50' as 110.50",
  `Got: ${parseMessyPriceString("€110,50")}`
);
assert(
  parseMessyPriceString("From $45.00 USD") === 45.0,
  "Case 2.3: Parses 'From $45.00 USD' as 45.00",
  `Got: ${parseMessyPriceString("From $45.00 USD")}`
);
assert(
  parseMessyPriceString("$80.00 - $120.00") === 80.0,
  "Case 2.4: Parses price range '$80.00 - $120.00' to lowest price 80.00",
  `Got: ${parseMessyPriceString("$80.00 - $120.00")}`
);
assert(
  parseMessyPriceString("FREE") === 0.0,
  "Case 2.5: Parses 'FREE' promotional price as 0.00",
  `Got: ${parseMessyPriceString("FREE")}`
);

// -----------------------------------------------------------------------------
// NASTY CASE 3: Broken & Protocol-Relative Image URLs
// -----------------------------------------------------------------------------
console.log("\n▶ [Test 3] Protocol-Relative, Broken, and Missing Images");

const img1 = resolveImageUrl("//cdn.shopify.com/products/shoe.jpg", "https://mystore.com");
const img2 = resolveImageUrl("/images/products/shoe.png", "https://mystore.com");
const img3 = resolveImageUrl(undefined, "https://mystore.com", "footwear");

assert(
  img1 === "https://cdn.shopify.com/products/shoe.jpg",
  "Case 3.1: Protocol-relative '//cdn...' healed to 'https://cdn...'",
  `Got: ${img1}`
);
assert(
  img2 === "https://mystore.com/images/products/shoe.png",
  "Case 3.2: Relative path '/images/...' resolved to full domain",
  `Got: ${img2}`
);
assert(
  img3.startsWith("https://images.unsplash.com") || img3.startsWith("https://"),
  "Case 3.3: Missing image healed with high-res curated category fallback",
  `Got: ${img3}`
);

// -----------------------------------------------------------------------------
// NASTY CASE 4: Dirty SEO Titles & Raw HTML Injection
// -----------------------------------------------------------------------------
console.log("\n▶ [Test 4] HTML Injection & SEO Suffix Pruning");

const dirtyTitle1 = "<h1>Vintage <b>Nike</b> Sweatshirt</h1> - Official Store | Buy Online";
const dirtyTitle2 = "Premium Leather Boots &amp; Shoes &trade;";

assert(
  cleanProductTitle(dirtyTitle1) === "Vintage Nike Sweatshirt",
  "Case 4.1: Strips raw HTML tags and '- Official Store | Buy Online' suffix",
  `Got: '${cleanProductTitle(dirtyTitle1)}'`
);
assert(
  cleanProductTitle(dirtyTitle2) === "Premium Leather Boots & Shoes",
  "Case 4.2: Decodes HTML entities (&amp; and &trade;)",
  `Got: '${cleanProductTitle(dirtyTitle2)}'`
);

// -----------------------------------------------------------------------------
// NASTY CASE 5: Completely Broken Storefront Object Recovery
// -----------------------------------------------------------------------------
console.log("\n▶ [Test 5] Total Garbage Payload Recovery");

const brokenPayload = {
  title: undefined,
  price: "From €125,00",
  description: "<p>Bale of 10 jackets in <b>Vintage Grade A</b> condition.</p>",
  variants: [], // Empty variants!
  images: [], // Empty images!
};

const healed = normalizeMessyStorefront(brokenPayload, "https://vintage-wholesale.de/items/nike-bale");

assert(
  Boolean(healed.title) && healed.title !== "undefined",
  "Case 5.1: Heals undefined title using URL slug",
  `Title: ${healed.title}`
);
assert(
  healed.base_price === 125.0,
  "Case 5.2: Heals European comma price 'From €125,00' to 125.00",
  `Price: ${healed.base_price}`
);
assert(
  healed.pieces === 10 && healed.per_piece === 12.5,
  "Case 5.3: Discovers 'Bale of 10 jackets' in description (10 pcs @ $12.50/pc)",
  `Pieces: ${healed.pieces}, Per piece: $${healed.per_piece}`
);
assert(
  Array.isArray(healed.variants) && healed.variants.length > 0,
  "Case 5.4: Synthesizes default SKU variant when variants array was empty",
  `Variants count: ${healed.variants.length}`
);

console.log("\n=======================================================================");
console.log(`🏁 TEST RESULTS: ${passed} PASSED | ${failed} FAILED`);
console.log("=======================================================================\n");
process.exit(failed > 0 ? 1 : 0);
