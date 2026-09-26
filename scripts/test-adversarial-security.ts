/**
 * Adversarial Security & Threat Vector Verification Suite
 *
 * Verifies that the Eden Matrix platform defends against:
 * 1. SSRF & Cloud Metadata Extraction (169.254.169.254, localhost, private IPs)
 * 2. Unbounded Heap & Session Memory Exhaustion (LRU Store Eviction)
 * 3. Prompt Injection & Financial Policy Subversion (LLM Margin Floor Clamping)
 * 4. Wholesale Lot Spoofing via Promotional Trinkets & Swag
 */

import { isSafeTargetUrl, transpileStorefront } from "../src/lib/transpiler";
import {
  setSessionWithEviction,
  setPurchaseIntentWithEviction,
  getEdenSessionStoreCount,
  getEdenIntentsStoreCount,
  _dangerouslyClearEdenStores,
  MAX_SESSIONS_CAP,
  MAX_INTENTS_CAP,
  EdenSession,
  PurchaseIntent,
} from "../src/lib/eden";
import { cascadeNegotiation } from "../src/lib/orchestrator";
import { extractLotPieceCount } from "../src/lib/messy-cleaner";

let passed = 0;
let failed = 0;

function assert(condition: boolean, testName: string, detail?: string) {
  if (condition) {
    console.log(`✅ [PASS] ${testName}`);
    passed++;
  } else {
    console.error(`❌ [FAIL] ${testName}`);
    if (detail) console.error(`   Details: ${detail}`);
    failed++;
  }
}

async function runAdversarialSecurityTests() {
  console.log("=======================================================================");
  console.log("🛡️  RUNNING ADVERSARIAL SECURITY & THREAT MITIGATION TEST SUITE");
  console.log("=======================================================================\n");

  // ---------------------------------------------------------------------------
  // ATTACK VECTOR 1: SSRF & Cloud Metadata / Internal Probe Attacks
  // ---------------------------------------------------------------------------
  console.log("▶ [Attack Vector 1] SSRF & Private Network / Cloud Metadata Defense");

  // AWS/GCP/Azure link-local metadata service
  assert(
    !isSafeTargetUrl("http://169.254.169.254/latest/meta-data/"),
    "1.1: Blocks AWS / Cloud link-local metadata IP (169.254.169.254)"
  );

  // Localhost & loopback
  assert(
    !isSafeTargetUrl("http://localhost:3000/api/admin"),
    "1.2: Blocks 'localhost' hostname access"
  );
  assert(
    !isSafeTargetUrl("http://127.0.0.1:8080/internal/metrics"),
    "1.3: Blocks loopback IPv4 range (127.0.0.1)"
  );
  assert(
    !isSafeTargetUrl("http://[::1]:8080/secret"),
    "1.4: Blocks IPv6 loopback (::1)"
  );

  // Private RFC 1918 subnets
  assert(
    !isSafeTargetUrl("http://10.0.0.5:9200/_cat/indices"),
    "1.5: Blocks private Class A subnet (10.0.0.0/8)"
  );
  assert(
    !isSafeTargetUrl("http://192.168.1.1/router-login"),
    "1.6: Blocks private Class C subnet (192.168.0.0/16)"
  );
  assert(
    !isSafeTargetUrl("http://172.20.0.1:5432/postgres"),
    "1.7: Blocks private Class B subnet (172.16.0.0/12)"
  );

  // Non-HTTP protocols
  assert(
    !isSafeTargetUrl("file:///etc/passwd"),
    "1.8: Blocks file:// scheme access"
  );
  assert(
    !isSafeTargetUrl("ftp://internal.vault.local/keys"),
    "1.9: Blocks ftp:// scheme access"
  );

  // Legitimate storefront URLs are preserved
  assert(
    isSafeTargetUrl("https://joinfleek.com/products/vintage-carhartt-jacket"),
    "1.10: Allows legitimate external e-commerce domains (joinfleek.com)"
  );
  assert(
    isSafeTargetUrl("https://store.steampowered.com"),
    "1.11: Allows standard public HTTPS web traffic"
  );

  // Test full transpiler refusal on dangerous URL
  const ssrfAttempt = await transpileStorefront("http://169.254.169.254/latest/user-data");
  assert(
    ssrfAttempt.telemetry.raw_html_bytes === 0 && ssrfAttempt.product.title.includes("Blocked Target"),
    "1.12: transpileStorefront safely halts without requesting blocked SSRF targets"
  );

  // ---------------------------------------------------------------------------
  // ATTACK VECTOR 2: Memory Exhaustion / Unbounded In-Memory Heap Attack
  // ---------------------------------------------------------------------------
  console.log("\n▶ [Attack Vector 2] Memory Exhaustion / LRU Cache Bounding");

  _dangerouslyClearEdenStores();

  // Create mock sessions exceeding MAX_SESSIONS_CAP
  const OVERFLOW_COUNT = 50;
  const TOTAL_TO_INSERT = MAX_SESSIONS_CAP + OVERFLOW_COUNT;

  for (let i = 0; i < TOTAL_TO_INSERT; i++) {
    const mockSession: EdenSession = {
      code: `EM-TEST-${i}`,
      store: "example.com",
      collection: "Test",
      status: "ready",
      product_count: 1,
      snapshot_at: new Date().toISOString(),
      rules: {},
      can_purchase: false,
      session_url: `https://edenmatrix.com/s/EM-TEST-${i}`,
      grok_url: "",
      products: [],
      tree: [],
    };
    setSessionWithEviction(mockSession.code, mockSession);
  }

  const currentSessionCount = getEdenSessionStoreCount();
  assert(
    currentSessionCount === MAX_SESSIONS_CAP,
    "2.1: Session store strictly adheres to MAX_SESSIONS_CAP under high volume creation",
    `Store size: ${currentSessionCount}, Expected: ${MAX_SESSIONS_CAP}`
  );

  // Verify purchase intent eviction as well
  for (let i = 0; i < TOTAL_TO_INSERT; i++) {
    const mockIntent: PurchaseIntent = {
      intent_id: `pi_test_${i}`,
      session_code: `EM-TEST-${i}`,
      product_ids: ["p1"],
      quoted_total: 100,
      status: "pending",
      confirm_url: "https://edenmatrix.com/confirm",
      created_at: new Date().toISOString(),
    };
    setPurchaseIntentWithEviction(mockIntent.intent_id, mockIntent);
  }

  const currentIntentCount = getEdenIntentsStoreCount();
  assert(
    currentIntentCount === MAX_INTENTS_CAP,
    "2.2: Purchase intent store strictly adheres to MAX_INTENTS_CAP under high volume insertion",
    `Store size: ${currentIntentCount}, Expected: ${MAX_INTENTS_CAP}`
  );

  // ---------------------------------------------------------------------------
  // ATTACK VECTOR 3: Prompt Injection & Adversarial Discount Manipulation
  // ---------------------------------------------------------------------------
  console.log("\n▶ [Attack Vector 3] Prompt Injection & Invariant Margin Defense");

  // Adversary attempts prompt injection: offers $5 on a $100 jacket with 15% max seller discount
  // The LLM (or mock) is pressured or injected, but our code-level invariant MUST intervene
  const maliciousNegotiation = await cascadeNegotiation({
    productTitle: "Vintage Leather Biker Jacket",
    basePrice: 100,
    offeredPrice: 5, // 95% discount requested
    quantity: 1,
    stockRemaining: 15,
    policy: {
      maxDiscountPct: 15, // Floor is $85.00
    },
  });

  assert(
    maliciousNegotiation.data.finalPrice >= 85.0,
    "3.1: Code-level invariant prevents selling below merchant margin floor ($85.00 on $100 base)",
    `Final Price: $${maliciousNegotiation.data.finalPrice}, Action: ${maliciousNegotiation.data.action}`
  );
  assert(
    maliciousNegotiation.data.action !== "accept",
    "3.2: Hostile below-margin offer is NOT accepted (counter_offer or reject enforced)",
    `Action was: ${maliciousNegotiation.data.action}`
  );
  assert(
    maliciousNegotiation.data.discountPct <= 15.01,
    "3.3: Effective discount percentage is clamped to seller's max discount ceiling",
    `Discount: ${maliciousNegotiation.data.discountPct}%`
  );

  // ---------------------------------------------------------------------------
  // ATTACK VECTOR 4: Wholesale Lot Spoofing via Promotional Trinkets
  // ---------------------------------------------------------------------------
  console.log("\n▶ [Attack Vector 4] Wholesale Lot Spoofing Defense");

  // Attack 4.1: Adversary lists a single $150 hoodie with "pack of 50 stickers" to look like $3/pc
  const spoofed1 = extractLotPieceCount("Rare Stussy Hoodie + Pack of 50 Stickers");
  assert(
    spoofed1 === 1,
    "4.1: Ignores promotional '+ Pack of 50 Stickers' and evaluates to 1 garment piece",
    `Got: ${spoofed1}`
  );

  // Attack 4.2: Adversary appends "includes 100 pins"
  const spoofed2 = extractLotPieceCount("Vintage Carhartt Canvas Jacket (includes 100 pins)");
  assert(
    spoofed2 === 1,
    "4.2: Ignores promotional '(includes 100 pins)' and evaluates to 1 garment piece",
    `Got: ${spoofed2}`
  );

  // Attack 4.3: Adversary appends "box of 200 trading cards"
  const spoofed3 = extractLotPieceCount("90s Nike Graphic Tee with box of 200 trading cards");
  assert(
    spoofed3 === 1,
    "4.3: Ignores promotional 'with box of 200 trading cards' and evaluates to 1 garment piece",
    `Got: ${spoofed3}`
  );

  // Legitimacy check: Genuine wholesale lots still resolve accurately
  const legitWholesale = extractLotPieceCount("Vintage Ralph Lauren Crewnecks (Box of 20)");
  assert(
    legitWholesale === 20,
    "4.4: Genuine wholesale lots ('Box of 20') resolve correctly",
    `Got: ${legitWholesale}`
  );

  // ---------------------------------------------------------------------------
  // SUMMARY
  // ---------------------------------------------------------------------------
  console.log("\n=======================================================================");
  console.log(`🏁 ADVERSARIAL SECURITY RESULTS: ${passed} PASSED | ${failed} FAILED`);
  console.log("=======================================================================\n");

  if (failed > 0) {
    process.exit(1);
  }
}

runAdversarialSecurityTests().catch((err) => {
  console.error("Test runner encountered an error:", err);
  process.exit(1);
});
