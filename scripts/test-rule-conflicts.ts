// Test Runner for Rule Conflict Resolution & Invariant Defense
// Run via: npm run test:conflicts

import {
  evaluateProductWithPrecedence,
  verifyCheckoutPriceConsistency,
  calculateSafeCardLimit,
  resolveInventoryVsVolumeConflict,
} from "../src/lib/rule-resolver";
import { EdenProductItem } from "../src/lib/eden";

console.log("=======================================================================");
console.log("⚖️ TESTING RULE CONFLICT RESOLUTION & INVARIANT PRECEDENCE");
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

function runTests() {
  // ---------------------------------------------------------------------------
  // TEST 1: The Taxonomy Paradox (Inclusion vs Exclusion)
  // ---------------------------------------------------------------------------
  console.log("▶ [Test 1] Taxonomy Paradox: Exclusion Vetoes Inclusion");
  const trackShorts: EdenProductItem = {
    id: "prod_shorts_1",
    title: "Nike Athletic Mesh Shorts",
    price: 60,
    per_piece: 6,
    pieces: 10,
    currency: "USD",
    tree_path: ["bottoms", "shorts", "vintage"],
    image_url: "",
    source_url: "",
    grade: "premium",
    in_stock: true,
  };

  // User included 'bottoms', but explicitly excluded 'shorts'
  const taxonomyResult = evaluateProductWithPrecedence(trackShorts, {
    include_categories: ["bottoms"],
    exclude_categories: ["shorts"],
  });

  assert(
    taxonomyResult.passed === false && taxonomyResult.disqualificationTier === "TIER_1_EXCLUSION",
    "Exclusion kills item despite matching include_categories ('bottoms')",
    `Result: ${JSON.stringify(taxonomyResult)}`
  );

  // ---------------------------------------------------------------------------
  // TEST 2: Stale Price Drift at Checkout (Time-of-Check vs Time-of-Use)
  // ---------------------------------------------------------------------------
  console.log("\n▶ [Test 2] Stale Price Drift at Checkout (Rule Re-Verification)");
  // Item was scraped at $130 ($13/pc) -> user has cap $14/pc
  // At checkout, live price moved to $150 ($15/pc)
  const driftBreach = verifyCheckoutPriceConsistency({
    originalPrice: 130,
    livePrice: 150,
    pieces: 10,
    rules: { max_per_piece: 14.0 },
  });

  assert(
    driftBreach.status === "rule_violated_after_price_change",
    "Price drift breaching rule caught with 'rule_violated_after_price_change'",
    `Status: ${driftBreach.status}, Reason: ${driftBreach.reason}`
  );

  // But if price drifted from $120 to $130 ($13/pc), it's still <= $14 cap
  const driftAcceptable = verifyCheckoutPriceConsistency({
    originalPrice: 120,
    livePrice: 130,
    pieces: 10,
    rules: { max_per_piece: 14.0 },
  });

  assert(
    driftAcceptable.status === "price_changed_acceptable",
    "Price drift within rule marked as 'price_changed_acceptable'",
    `Status: ${driftAcceptable.status}`
  );

  // ---------------------------------------------------------------------------
  // TEST 3: Virtual Card Pre-Auth Ceiling Defense
  // ---------------------------------------------------------------------------
  console.log("\n▶ [Test 3] Virtual Card Hard Ceiling (Taxes/Shipping Cannot Breach max_total)");
  // Quoted total is $580. Standard 5% buffer would be $609.
  // But user set hard max_total = $600.
  const cardLimit = calculateSafeCardLimit(580, 600);

  assert(
    cardLimit === 600,
    "Virtual card limit capped strictly at max_total ($600 instead of $609)",
    `Card limit: $${cardLimit}`
  );

  // ---------------------------------------------------------------------------
  // TEST 4: Quality Floor Invariant (Price cannot buy down condition)
  // ---------------------------------------------------------------------------
  console.log("\n▶ [Test 4] Quality Floor Invariant: Grade vs Price");
  const cheapDistressedLot: EdenProductItem = {
    id: "prod_cheap_b",
    title: "Vintage Nike Distressed Pants",
    price: 30, // insane deal ($3/pc)
    per_piece: 3,
    pieces: 10,
    currency: "USD",
    tree_path: ["bottoms", "pants"],
    image_url: "",
    source_url: "",
    grade: "grade-b", // flawed
    in_stock: true,
  };

  const qualityResult = evaluateProductWithPrecedence(cheapDistressedLot, {
    max_per_piece: 14.0, // passed
    grades: ["premium"], // failed
  });

  assert(
    qualityResult.passed === false && qualityResult.disqualificationTier === "TIER_3_QUALITY",
    "Cheap $3/pc price rejected because it failed the 'premium' quality floor",
    `Result: ${JSON.stringify(qualityResult)}`
  );

  // ---------------------------------------------------------------------------
  // TEST 5: Inventory Scarcity vs Volume Incentives (Seller Invariant)
  // ---------------------------------------------------------------------------
  console.log("\n▶ [Test 5] Seller Inventory Scarcity vs Volume Incentives");
  // Buyer asks for 3 units (eligible for +5% volume bonus)
  // But seller only has 3 units remaining (minStockForDiscount = 5)
  const scarceConflict = resolveInventoryVsVolumeConflict({
    requestedQty: 3,
    stockRemaining: 3,
    minStockThreshold: 5,
    volumeBonusPct: 5,
    baseDiscountPct: 15,
  });

  assert(
    scarceConflict.effectiveDiscountPct === 0,
    "Inventory scarcity overrides volume incentive to 0% discount",
    `Discount: ${scarceConflict.effectiveDiscountPct}%, Reason: ${scarceConflict.reason}`
  );

  console.log("\n=======================================================================");
  console.log(`🏁 TEST RESULTS: ${passed} PASSED | ${failed} FAILED`);
  console.log("=======================================================================\n");
  process.exit(failed > 0 ? 1 : 0);
}

runTests();
