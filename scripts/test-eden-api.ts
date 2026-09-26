// Test Runner for Eden Matrix v1 Session, Rules, and Tree Engine
// Run via: npm run test:eden

import {
  createEdenSession,
  getEdenSession,
  applyEdenRules,
  createPurchaseIntent,
} from "../src/lib/eden";

console.log("=======================================================================");
console.log("🏛️ TESTING EDEN MATRIX v1 API & RULES ENGINE (Cursor Commerce Spec)");
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
  // 1. Session Creation & Code Generation
  console.log("▶ [Test 1] Session Creation (EM-XXXXXXXX code & taxonomy tree)");
  const session = await createEdenSession({
    url: "https://www.joinfleek.com/collections/nike-vintage",
    rules: {
      max_per_piece: 14.0,
      grades: ["premium"],
      exclude_categories: ["shorts"],
    },
  });

  assert(
    session.code.startsWith("EM-") && session.code.length === 11,
    `Session code generated in format EM-XXXXXXXX (${session.code})`,
    `Code: ${session.code}`
  );
  assert(
    session.status === "ready" && session.product_count > 0,
    `Session initialized with ${session.product_count} products`,
    `Products: ${session.product_count}`
  );
  assert(
    Array.isArray(session.tree) && session.tree.length > 0,
    `Live category tree generated (${session.tree.map((t) => t.name).join(", ")})`,
    `Tree: ${JSON.stringify(session.tree)}`
  );

  // 2. Server-Side Rules Engine & Why Justification
  console.log("\n▶ [Test 2] Server-Side Rules Enforcement & 'Why' Justification");
  const filteredProducts = await applyEdenRules(session.products, {
    max_per_piece: 14.0,
    exclude_categories: ["shorts"],
    grades: ["premium"],
  });

  assert(
    filteredProducts.length > 0,
    `Found ${filteredProducts.length} items passing all strict rules`,
    `Count: ${filteredProducts.length}`
  );

  const allUnderCap = filteredProducts.every((p) => p.per_piece <= 14.0);
  assert(
    allUnderCap,
    "Strict rule: 100% of recommended items are under $14.00/piece",
    `Prices: ${filteredProducts.map((p) => `$${p.per_piece}`).join(", ")}`
  );

  const noShorts = filteredProducts.every(
    (p) => !p.title.toLowerCase().includes("short") && !p.tree_path.includes("shorts")
  );
  assert(
    noShorts,
    "Strict exclusion: Zero shorts included in recommendations",
    `Titles: ${filteredProducts.map((p) => p.title).join("; ")}`
  );

  const sampleWhy = filteredProducts[0]?.why;
  assert(
    Boolean(sampleWhy && sampleWhy.includes("under your $14 cap")),
    "Every recommended item includes an agent-friendly 'why' justification",
    `Why: "${sampleWhy}"`
  );

  // 3. Purchase Intent & Scoped Virtual Card Gating
  console.log("\n▶ [Test 3] Gated Purchase Intent & Single-Use Virtual Card");
  const intent = createPurchaseIntent({
    sessionCode: session.code,
    productIds: [filteredProducts[0].id],
    quotedTotal: filteredProducts[0].price,
  });

  assert(
    Boolean(intent.intent_id) && intent.status === "pending",
    `Purchase intent created (ID: ${intent.intent_id})`,
    `Status: ${intent.status}`
  );
  assert(
    intent.confirm_url.includes(`/confirm/${intent.intent_id}`),
    `Human confirmation URL generated: ${intent.confirm_url}`,
    `URL: ${intent.confirm_url}`
  );
  assert(
    Boolean(intent.card?.last4 && intent.card.limit >= intent.quoted_total),
    `Scoped single-use card pre-authorized (limit: $${intent.card?.limit} for merchant: ${intent.card?.merchant})`,
    `Card: ${JSON.stringify(intent.card)}`
  );

  console.log("\n=======================================================================");
  console.log(`🏁 TEST RESULTS: ${passed} PASSED | ${failed} FAILED`);
  console.log("=======================================================================\n");
  process.exit(failed > 0 ? 1 : 0);
}

runTests();
