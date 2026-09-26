// Test Runner for Storefront Ingestion & Transpilation Proxy
// Run via: npm run test:proxy

import { transpileStorefront, sanitizeTargetUrl } from "../src/lib/transpiler";
import { dispatchCommerceToolCall } from "../src/lib/tools";

console.log("=======================================================================");
console.log("🌐 TESTING STOREFRONT TRANSPILATION PROXY & MACHINE CONTRACT ENGINE");
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
  // 1. URL Sanitization
  console.log("▶ [Test 1] URL Sanitization & Protocol Healing");
  const url1 = sanitizeTargetUrl("gymshark.com/products/runner");
  const url2 = sanitizeTargetUrl("https:/store.com/products/shoe");
  const url3 = sanitizeTargetUrl("https://nike.com/products/alphafly");

  assert(
    url1 === "https://gymshark.com/products/runner" &&
      url2 === "https://store.com/products/shoe" &&
      url3 === "https://nike.com/products/alphafly",
    "URL Sanitizer heals missing protocols and stripped slashes",
    `URL1: ${url1}, URL2: ${url2}`
  );

  // 2. Transpiler Machine Contract Generation
  console.log("\n▶ [Test 2] Transpiling Target Storefront into Machine Contract");
  const contract = await transpileStorefront("https://demo-athletics.com/products/pro-runner-carbon");

  assert(
    contract.protocol === "commerce/1.0",
    "Machine Contract specifies protocol = 'commerce/1.0'",
    `Protocol: ${contract.protocol}`
  );
  assert(
    Boolean(contract.product?.title) && contract.product.base_price > 0,
    "Transpiled product has title and base price",
    `Title: ${contract.product?.title}, Price: $${contract.product?.base_price}`
  );
  assert(
    Array.isArray(contract.product.variants) && contract.product.variants.length > 0,
    `Transpiled product includes ${contract.product.variants.length} clean variants`,
    `Variants: ${contract.product.variants.map((v) => v.title).join(", ")}`
  );
  assert(
    Boolean(contract.rpc?.negotiate && contract.rpc?.reserve && contract.rpc?.checkout),
    "Machine Contract embeds active RPC links (negotiate, reserve, checkout)",
    `RPC: ${JSON.stringify(contract.rpc)}`
  );

  // 3. Token Compression Verification
  console.log("\n▶ [Test 3] Token Compression & Telemetry");
  const compressionRatio = contract.telemetry.token_compression_ratio;
  const rawBytes = contract.telemetry.raw_html_bytes;
  const transpiledBytes = contract.telemetry.transpiled_bytes;

  assert(
    rawBytes > transpiledBytes,
    `Token compression successful: ${transpiledBytes} bytes vs ${rawBytes} raw bytes`,
    `Ratio: ${compressionRatio}`
  );
  assert(
    compressionRatio.includes("% tokens saved"),
    "Compression ratio telemetry computed and formatted correctly",
    `Value: ${compressionRatio}`
  );

  // 4. Grok inspect_storefront tool call
  console.log("\n▶ [Test 4] Grok inspect_storefront Tool Integration");
  const toolRes = (await dispatchCommerceToolCall("inspect_storefront", {
    store_url: "https://gymshark.com/products/speed-runner",
  })) as { status: string; machineContract: typeof contract };

  assert(
    toolRes.status === "success" && toolRes.machineContract.protocol === "commerce/1.0",
    "Grok inspect_storefront tool successfully returns machine contract",
    `Store: ${toolRes.machineContract.store.name}`
  );

  console.log("\n=======================================================================");
  console.log(`🏁 TEST RESULTS: ${passed} PASSED | ${failed} FAILED`);
  console.log("=======================================================================\n");
  process.exit(failed > 0 ? 1 : 0);
}

runTests();
