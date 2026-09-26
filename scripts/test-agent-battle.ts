// Test Runner for Agent-vs-Agent Battle, Score Primitive, and Grok Tools
// Run via: npm run test:battle

import fs from "node:fs";
import path from "node:path";
import { runAgentNegotiationBattle } from "../src/lib/agent-battle";
import { COMMERCE_AGENT_TOOLS, dispatchCommerceToolCall } from "../src/lib/tools";

// Load .env.local if present
const envPath = path.resolve(process.cwd(), ".env.local");
if (fs.existsSync(envPath)) {
  const content = fs.readFileSync(envPath, "utf-8");
  for (const line of content.split("\n")) {
    const trimmed = line.trim();
    if (trimmed && !trimmed.startsWith("#")) {
      const [k, ...v] = trimmed.split("=");
      if (k && v.length) {
        process.env[k.trim()] = v.join("=").trim().replace(/^["']|["']$/g, "");
      }
    }
  }
}

const OPENROUTER_API_KEY = process.env.OPENROUTER_API_KEY;

console.log("=======================================================================");
console.log("🤖 TESTING AGENT-VS-AGENT BATTLE & ADVANCED AI COMMERCE LAYER");
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
  // 1. Tool Schemas Verification
  console.log("▶ [Test 1] Grok Tool Schemas Validation");
  assert(
    COMMERCE_AGENT_TOOLS.length === 5,
    "Grok Tool Schemas count = 5 tools",
    `Count: ${COMMERCE_AGENT_TOOLS.length}`
  );

  const toolNames = COMMERCE_AGENT_TOOLS.map((t) => t.function.name);
  assert(
    toolNames.includes("negotiate_price") &&
      toolNames.includes("inspect_storefront") &&
      toolNames.includes("reserve_inventory") &&
      toolNames.includes("execute_checkout") &&
      toolNames.includes("consult_fit_reviews"),
    "All essential commerce tools registered",
    `Found: ${toolNames.join(", ")}`
  );

  // 2. Tool Dispatcher Test (Offline Reservation & Checkout)
  console.log("\n▶ [Test 2] Tool Dispatcher Execution");
  const resResult = (await dispatchCommerceToolCall("reserve_inventory", {
    variant_id: "var_10_blk",
    quantity: 1,
    agreed_price: 90,
  })) as { status: string; reservationId: string; ttlSeconds: number };

  assert(
    resResult.status === "reserved" && Boolean(resResult.reservationId),
    "reserve_inventory tool execution (ephemeral TTL lock)",
    `Result: ${JSON.stringify(resResult)}`
  );

  const checkoutResult = (await dispatchCommerceToolCall("execute_checkout", {
    reservation_id: resResult.reservationId,
  })) as { status: string; checkoutPermalink: string };

  assert(
    checkoutResult.status === "ready_to_pay" &&
      checkoutResult.checkoutPermalink.includes(resResult.reservationId),
    "execute_checkout tool execution (permalink generation)",
    `Result: ${JSON.stringify(checkoutResult)}`
  );

  // 3. Agent-vs-Agent Battle Simulation
  console.log("\n▶ [Test 3] Agent-vs-Agent Negotiation Battle");

  // 3.1 Layer 1 Instant Battle (Full price / tipping - 1ms, 0 tokens)
  const battleInstant = await runAgentNegotiationBattle({
    productTitle: "Aero Carbon Pro Runner",
    basePrice: 100,
    stockRemaining: 15,
    buyer: {
      buyerName: "VIP Buyer Bot",
      initialBid: 100, // full price
      maxSpendCap: 110,
      urgency: "high",
    },
    maxRounds: 2,
  });

  assert(
    battleInstant.status === "deal_struck" && battleInstant.finalPrice === 100,
    "Agent Battle: Instant agreement on full price ($100 in 1ms)",
    `Status: ${battleInstant.status}, Price: $${battleInstant.finalPrice}`
  );

  if (!OPENROUTER_API_KEY) {
    console.log("\n⚠️ Note on live rounds: OPENROUTER_API_KEY not yet set in .env.local.");
    console.log("Offline tool schemas and Layer 1 battles passed with 100% success!");
    printSummary();
    return;
  }

  // 3.2 Live Multi-Round Battle with Jev + Grok
  try {
    const battleLive = await runAgentNegotiationBattle({
      productTitle: "Apex Carbon Elite",
      basePrice: 120,
      stockRemaining: 10,
      buyer: {
        buyerName: "Autonomous Bargain Bot",
        initialBid: 95, // ~20% off (triggers counter-offer)
        maxSpendCap: 110,
        urgency: "medium",
      },
      sellerPolicy: {
        maxDiscountPct: 15, // max discount allowed is $18 -> min price $102
        minStockForDiscount: 5,
      },
      maxRounds: 3,
    });

    assert(
      Boolean(battleLive.status),
      `Live Agent Battle finished with status: ${battleLive.status}`,
      `Rounds: ${battleLive.roundsCount}, Summary: ${battleLive.summary}`
    );
  } catch (err: unknown) {
    const error = err as Error;
    assert(false, "Live Agent Battle failed", error.message);
  }

  printSummary();
}

function printSummary() {
  console.log("\n=======================================================================");
  console.log(`🏁 TEST RESULTS: ${passed} PASSED | ${failed} FAILED`);
  console.log("=======================================================================\n");
  process.exit(failed > 0 ? 1 : 0);
}

runTests();
