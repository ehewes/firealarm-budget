// Standalone test script for Jev on OpenRouter
// Run via: node scripts/test-jev.mjs

import fs from "node:fs";
import path from "node:path";

// Load .env.local manually if present
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
const MODEL = process.env.JEV_MODEL || "typesafe/jev-1.13";

console.log("=== Testing Jev System-1 Decision via OpenRouter ===");
console.log(`Model: ${MODEL}`);

if (!OPENROUTER_API_KEY) {
  console.error("❌ ERROR: OPENROUTER_API_KEY is not set in .env.local or environment!");
  console.log("Please add your key to .env.local: OPENROUTER_API_KEY=sk-or-v1-...");
  process.exit(1);
}

async function runTest() {
  const payload = {
    model: MODEL,
    state: {
      user_intent: "Need size 10 black running shoes, budget $90",
      item_name: "Velocity Aero Carbon Runner",
      base_price: 110,
      offered_price: 89,
    },
    questions: {
      match_variant: {
        type: "choice",
        instructions: "Which variant matches the buyer's requested size and color?",
        criteria: {
          "sku_10_blk": "Size 10 / Stealth Black - $110 (In Stock)",
          "sku_10_wht": "Size 10 / Glacier White - $110 (In Stock)",
          "sku_9_blk": "Size 9 / Stealth Black - $110 (In Stock)",
        },
      },
      is_acceptable_discount: {
        type: "noul",
        instructions: "Is an offer of $89 on a $110 base price within acceptable 20% discount policy?",
      },
    },
  };

  console.log("\nSending decision request to OpenRouter /api/alpha/decisions...");
  const t0 = Date.now();

  try {
    const response = await fetch("https://openrouter.ai/api/alpha/decisions", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${OPENROUTER_API_KEY}`,
        "Content-Type": "application/json",
        "HTTP-Referer": "https://agent-gateway.dev",
        "X-Title": "Agent Gateway",
      },
      body: JSON.stringify(payload),
    });

    const elapsed = Date.now() - t0;
    const data = await response.json();

    if (!response.ok) {
      console.error(`\n❌ Request Failed (${response.status}):`, data);
      return;
    }

    console.log(`\n✅ Success! Latency: ${elapsed}ms`);
    console.log("\nDecisions Result:");
    console.dir(data, { depth: null });
  } catch (err) {
    console.error("❌ Network or Execution Error:", err);
  }
}

runTest();
