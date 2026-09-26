// Standalone CLI test script for Jev System-1 & Grok System-2 Cascading
// Run via: npm run test:jev

import fs from "node:fs";
import path from "node:path";

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
const JEV_MODEL = process.env.JEV_MODEL || "typesafe/jev-1.13";
const GROK_MODEL = process.env.GROK_MODEL || "x-ai/grok-2-1212";

console.log("=================================================================");
console.log("⚡ TESTING JEV SYSTEM-1 + GROK SYSTEM-2 MODEL CASCADE");
console.log(`Jev Model:  ${JEV_MODEL}`);
console.log(`Grok Model: ${GROK_MODEL}`);
console.log("=================================================================\n");

if (!OPENROUTER_API_KEY) {
  console.error("❌ ERROR: OPENROUTER_API_KEY is not set in .env.local!");
  console.log("Please add your key to .env.local:");
  console.log("OPENROUTER_API_KEY=sk-or-v1-...");
  process.exit(1);
}

// 1. Direct Jev Decisions API test
async function testJevSystem1() {
  console.log("▶ [Test 1] Jev System-1 Micro-Decisions (Variant Match + Policy Gate)...");

  const payload = {
    model: JEV_MODEL,
    state: {
      user_intent: "Size 10 Stealth Black, budget $95",
      product_title: "Nike Air Zoom Alphafly",
      base_price: 110,
      offered_price: 95,
      stock_remaining: 14,
      merchant_rules: [
        "Max allowable discount is 15%",
        "Never discount if stock < 5",
        "Offer must be in USD",
      ],
    },
    questions: {
      variant_resolution: {
        type: "choice",
        instructions: "Which variant ID matches the requested size 10 in black?",
        criteria: {
          "var_10_blk": "Size 10 / Stealth Black - $110 (In Stock: 14)",
          "var_10_wht": "Size 10 / White Cloud - $110 (In Stock: 8)",
          "var_09_blk": "Size 9 / Stealth Black - $110 (In Stock: 4)",
        },
      },
      margin_approval: {
        type: "noul",
        instructions:
          "Does offering $95 on a $110 base price comply with the merchant's 15% discount limit?",
      },
    },
  };

  const t0 = Date.now();
  try {
    const res = await fetch("https://openrouter.ai/api/alpha/decisions", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${OPENROUTER_API_KEY}`,
        "Content-Type": "application/json",
        "HTTP-Referer": "https://agent-gateway.dev",
        "X-Title": "Agent Gateway Test",
      },
      body: JSON.stringify(payload),
    });

    const elapsed = Date.now() - t0;
    const data = await res.json();

    if (!res.ok) {
      console.error(`❌ Jev Failed (${res.status}):`, data);
      return;
    }

    console.log(`✅ Jev System-1 completed in ${elapsed}ms!`);
    console.log("Output:", JSON.stringify(data, null, 2));
  } catch (err) {
    console.error("Network error on Jev:", err);
  }
}

// 2. Cascade Test to Grok
async function testGrokSystem2Cascade() {
  console.log("\n▶ [Test 2] Grok System-2 Escalation (Borderline Negotiation Compromise)...");

  const prompt = `
You are the autonomous negotiation agent for 'Nike Air Zoom Alphafly'.
Base Price: $110
Buyer Offer: $90
Quantity: 1
Stock: 6 units remaining

Merchant Policy:
- Base discount cap: 15% (Min acceptable price: $93.50)
- Low stock: 6 units

Escalation Reason from Jev:
Buyer offered $90 (18.1% discount), which exceeds the 15% cap by $3.50. Borderline bid.

Task:
Formulate a smart win-win counter-offer (e.g. $94 or free express shipping).
Return valid JSON only:
{
  "action": "counter_offer",
  "counterPrice": 94,
  "reasoning": "Explain margin compromise",
  "messageToBuyer": "Short message to buyer agent"
}
`;

  const t0 = Date.now();
  try {
    const res = await fetch("https://openrouter.ai/api/v1/chat/completions", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${OPENROUTER_API_KEY}`,
        "Content-Type": "application/json",
        "HTTP-Referer": "https://agent-gateway.dev",
        "X-Title": "Agent Gateway Test",
      },
      body: JSON.stringify({
        model: GROK_MODEL,
        messages: [
          { role: "system", content: "You are an autonomous commerce bot. Output JSON only." },
          { role: "user", content: prompt },
        ],
        response_format: { type: "json_object" },
        temperature: 0.2,
      }),
    });

    const elapsed = Date.now() - t0;
    const data = await res.json();

    if (!res.ok) {
      console.error(`❌ Grok Failed (${res.status}):`, data);
      return;
    }

    console.log(`✅ Grok System-2 completed in ${elapsed}ms!`);
    console.log("Grok Counter-Proposal:", data.choices?.[0]?.message?.content);
  } catch (err) {
    console.error("Network error on Grok:", err);
  }
}

async function main() {
  await testJevSystem1();
  await testGrokSystem2Cascade();
  console.log("\n=================================================================");
  console.log("🎉 Test complete! System-1 + System-2 Cascade is operational.");
  console.log("=================================================================");
}

main();
