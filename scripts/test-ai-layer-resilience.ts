// Stress-Test Runner for AI Layer Resilience, Heuristic Degradation & Taxonomy
// Run via: npx tsx scripts/test-ai-layer-resilience.ts

import { resolveVariant, evaluateMargin, checkPreFlightRisk, executeJevDecisions } from "../src/lib/jev";
import { cascadeNegotiation, cascadeVariantMatch } from "../src/lib/orchestrator";
import { grokNegotiateCounterOffer, grokResolveAmbiguity } from "../src/lib/grok";
import { determineTreePath, applyEdenRules, EdenProductItem } from "../src/lib/eden";

console.log("=======================================================================");
console.log("🧠 TESTING AI LAYER RESILIENCE, FALLBACKS & EXPANDED TAXONOMY");
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

async function runTests() {
  // ---------------------------------------------------------------------------
  // TEST 1: Resilient Offline / Outage Fallback for Jev System-1
  // ---------------------------------------------------------------------------
  console.log("▶ [Test 1] Jev System-1 Resilient Offline Heuristic Fallback");

  // Call raw executeJevDecisions without an API key
  const jevRes = await executeJevDecisions({
    state: { query: "black running shoes" },
    questions: {
      pick_variant: {
        type: "choice",
        instructions: "Pick the best variant",
        criteria: {
          var_white: "White Runner",
          var_black: "Stealth Black Runner",
        },
      },
      check_margin: {
        type: "noul",
        instructions: "Is discount acceptable?",
      },
    },
  });

  assert(
    jevRes.decisions.pick_variant?.value === "var_black",
    "1.1: Jev heuristic fallback accurately matches 'var_black' from query tokens",
    `Got: ${jevRes.decisions.pick_variant?.value}`
  );
  assert(
    jevRes.decisions.check_margin?.type === "noul" && typeof jevRes.decisions.check_margin?.value === "boolean",
    "1.2: Jev noul fallback evaluates valid boolean margin without throwing",
    `Got: ${jevRes.decisions.check_margin?.value}`
  );

  // ---------------------------------------------------------------------------
  // TEST 2: Resilient Offline / Outage Fallback for Grok System-2
  // ---------------------------------------------------------------------------
  console.log("\n▶ [Test 2] Grok System-2 Resilient Counter-Offer & Ambiguity Fallback");

  const grokCounter = await grokNegotiateCounterOffer({
    productTitle: "Vintage Nike ACG Fleece",
    basePrice: 120,
    offeredPrice: 80,
    quantity: 1,
    stockRemaining: 15,
    sellerRules: ["Max discount 15%"],
  });

  assert(
    grokCounter.action === "counter_offer",
    "2.1: Grok fallback gracefully returns counter_offer action without crashing",
    `Action: ${grokCounter.action}`
  );
  assert(
    grokCounter.counterPrice === 100, // (120 + 80) / 2 = 100
    "2.2: Grok fallback splits the difference to $100 midpoint compromise",
    `Counter price: $${grokCounter.counterPrice}`
  );
  assert(
    Boolean(grokCounter.messageToBuyer) && grokCounter.messageToBuyer.includes("$100"),
    "2.3: Grok fallback generates user-facing counter message with price",
    `Message: ${grokCounter.messageToBuyer}`
  );

  const grokAmbiguity = await grokResolveAmbiguity({
    userIntent: "Size 10 stealth black",
    productTitle: "Runner 1.0",
    variants: [
      { id: "var_1", title: "US 10 / Stealth Black" },
      { id: "var_2", title: "US 9 / Glacier White" },
    ],
  });

  assert(
    grokAmbiguity.bestMatchVariantId === "var_1",
    "2.4: Grok ambiguity fallback identifies candidate variant",
    `Variant ID: ${grokAmbiguity.bestMatchVariantId}`
  );

  // ---------------------------------------------------------------------------
  // TEST 3: Model Cascading End-to-End Fallback (Zero 500 Errors)
  // ---------------------------------------------------------------------------
  console.log("\n▶ [Test 3] Model Cascade Orchestrator Graceful Execution");

  const cascadeRes = await cascadeNegotiation({
    productTitle: "Vintage Carhartt Canvas Jacket",
    basePrice: 150,
    offeredPrice: 110,
    quantity: 2,
    stockRemaining: 10,
    policy: { maxDiscountPct: 15 }, // 110 on 150 is 26.6% discount -> triggers cascade
  });

  assert(
    cascadeRes.data.action !== undefined && cascadeRes.data.finalPrice > 0,
    "3.1: Cascade negotiation resolves to valid action and price without throwing",
    `Action: ${cascadeRes.data.action}, Price: $${cascadeRes.data.finalPrice}`
  );
  assert(
    Number.isInteger(cascadeRes.data.finalPrice * 100),
    "3.2: Cascade finalPrice is strictly rounded to 2 decimal places (no float drift)",
    `Price: ${cascadeRes.data.finalPrice}`
  );

  // ---------------------------------------------------------------------------
  // TEST 4: Expanded Category Taxonomy (Accessories & Knitwear)
  // ---------------------------------------------------------------------------
  console.log("\n▶ [Test 4] Expanded Category Taxonomy (Accessories, Knitwear & Footwear)");

  const path1 = await determineTreePath("Vintage Carhartt Watch Beanie Hat");
  assert(
    path1[0] === "accessories" && path1[1] === "headwear",
    "4.1: Beanie/Hat correctly classified under accessories -> headwear",
    `Got: ${path1.join(" > ")}`
  );

  const path2 = await determineTreePath("Military Canvas Backpack Duffle Bag");
  assert(
    path2[0] === "accessories" && path2[1] === "bags",
    "4.2: Backpack/Bag correctly classified under accessories -> bags",
    `Got: ${path2.join(" > ")}`
  );

  const path3 = await determineTreePath("Vintage Ralph Lauren Cable Knit Wool Sweater");
  assert(
    path3[0] === "knitwear" && path3[1] === "sweaters",
    "4.3: Cable Knit Sweater correctly classified under knitwear -> sweaters",
    `Got: ${path3.join(" > ")}`
  );

  const path4 = await determineTreePath("Timberland 6-Inch Premium Waterproof Leather Boots");
  assert(
    path4[0] === "footwear" && path4[1] === "boots",
    "4.4: Boots correctly classified under footwear -> boots",
    `Got: ${path4.join(" > ")}`
  );

  // ---------------------------------------------------------------------------
  // TEST 5: Fuzzy User Notes Scoring & Ranking Affinity
  // ---------------------------------------------------------------------------
  console.log("\n▶ [Test 5] Free-Text User Notes Semantic Affinity Scoring");

  const testProducts: EdenProductItem[] = [
    {
      id: "prod_generic_hoodie",
      title: "Standard Cotton Hoodie (Navy Blue)",
      price: 100,
      per_piece: 10,
      pieces: 10,
      currency: "USD",
      tree_path: ["outerwear", "hoodies", "standard"],
      image_url: "https://images.unsplash.com/photo-1556905055",
      source_url: "https://fleek.com/item/1",
      in_stock: true,
    },
    {
      id: "prod_fleece_hoodie",
      title: "Vintage Heavyweight Thermal Fleece Pullover Hoodie",
      price: 100,
      per_piece: 10,
      pieces: 10,
      currency: "USD",
      tree_path: ["outerwear", "hoodies", "vintage"],
      image_url: "https://images.unsplash.com/photo-1556905056",
      source_url: "https://fleek.com/item/2",
      in_stock: true,
    },
  ];

  // User specifies fuzzy preference: "heavyweight fleece"
  const ranked = await applyEdenRules(testProducts, {
    max_per_piece: 14,
    notes: ["heavyweight fleece"],
  });

  assert(
    ranked[0].id === "prod_fleece_hoodie",
    "5.1: Product matching free-text note 'heavyweight fleece' ranks higher than generic hoodie",
    `First place: ${ranked[0].title} (Score: ${ranked[0].score} vs ${ranked[1].score})`
  );
  assert(
    Boolean(ranked[0].why?.includes('matches preferences: "heavyweight fleece"')),
    "5.2: Generated 'why' explanation includes matched note justification",
    `Why: ${ranked[0].why}`
  );

  console.log("\n=======================================================================");
  console.log(`🏁 TEST RESULTS: ${passed} PASSED | ${failed} FAILED`);
  console.log("=======================================================================\n");

  process.exit(failed > 0 ? 1 : 0);
}

runTests().catch((err) => {
  console.error("Test execution fatal error:", err);
  process.exit(1);
});
