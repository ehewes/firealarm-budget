/**
 * Grok System-2 Deep Reasoning Engine
 *
 * Invoked during Model Cascading when Jev System-1 confidence is low (< threshold)
 * or when multi-turn negotiation / complex reasoning is required.
 *
 * Supports:
 * - Counter-proposal generation for rejected or borderline bids
 * - Complex, fuzzy multi-attribute variant synthesis
 * - Agent-to-Agent trade negotiation
 */

export interface GrokNegotiationRequest {
  productTitle: string;
  basePrice: number;
  offeredPrice: number;
  quantity: number;
  stockRemaining: number;
  sellerRules: string[];
  escalationReason?: string;
}

export interface GrokNegotiationResponse {
  action: "accept" | "counter_offer" | "reject";
  counterPrice?: number;
  reasoning: string;
  messageToBuyer: string;
  latencyMs: number;
  model: string;
}

export interface GrokVariantClarificationRequest {
  userIntent: string;
  productTitle: string;
  variants: Array<{ id: string | number; title: string; price?: string | number }>;
  escalationReason?: string;
}

export interface GrokVariantClarificationResponse {
  bestMatchVariantId?: string;
  confidence: number;
  reasoning: string;
  clarifyingQuestionForBuyer?: string;
  latencyMs: number;
  model: string;
}

const DEFAULT_GROK_MODEL = process.env.GROK_MODEL || "x-ai/grok-2-1212";
const OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions";

/**
 * 1. Grok System-2: Formulate Smart Counter-Offers & Negotiation Compromise
 */
export async function grokNegotiateCounterOffer(
  params: GrokNegotiationRequest,
  apiKey?: string
): Promise<GrokNegotiationResponse> {
  const token = apiKey || process.env.OPENROUTER_API_KEY;
  if (!token) {
    throw new Error("OPENROUTER_API_KEY is required to invoke Grok System-2.");
  }

  const model = DEFAULT_GROK_MODEL;
  const startTime = Date.now();

  const prompt = `
You are the autonomous merchant negotiation agent representing the seller for: "${params.productTitle}".
Base Unit Price: $${params.basePrice}
Buyer Offer: $${params.offeredPrice} each
Quantity Requested: ${params.quantity} units
Current Stock Remaining: ${params.stockRemaining} units

Merchant Rules:
${params.sellerRules.map((r, i) => `${i + 1}. ${r}`).join("\n")}

Escalation Reason from System-1:
${params.escalationReason || "Borderline bid requiring System-2 compromise reasoning."}

Task:
Analyze this bid against the merchant rules. If the bid is slightly below allowable margin, formulate a win-win counter-offer (e.g. slight price compromise, bundling, or volume incentive).
Return strictly valid JSON matching this schema:
{
  "action": "accept" | "counter_offer" | "reject",
  "counterPrice": number (null if reject),
  "reasoning": "Internal seller reasoning explaining the margin calculus",
  "messageToBuyer": "Concise, professional message for the buyer agent"
}
`;

  const response = await fetch(OPENROUTER_CHAT_URL, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${token}`,
      "Content-Type": "application/json",
      "HTTP-Referer": "https://agent-gateway.dev",
      "X-Title": "Agent Gateway - Grok System-2",
    },
    body: JSON.stringify({
      model,
      messages: [
        {
          role: "system",
          content:
            "You are an autonomous commerce negotiation engine. Output valid JSON only, no markdown backticks, no prose.",
        },
        { role: "user", content: prompt },
      ],
      response_format: { type: "json_object" },
      temperature: 0.2,
    }),
  });

  const latencyMs = Date.now() - startTime;

  if (!response.ok) {
    const errorBody = await response.text();
    throw new Error(`Grok API Error (${response.status}): ${errorBody}`);
  }

  const data = await response.json();
  const rawContent = data.choices?.[0]?.message?.content || "{}";

  let parsed: Partial<GrokNegotiationResponse> = {};
  try {
    parsed = JSON.parse(rawContent);
  } catch {
    // Clean potential markdown if returned
    const cleaned = rawContent.replace(/```json/g, "").replace(/```/g, "").trim();
    parsed = JSON.parse(cleaned);
  }

  return {
    action: (parsed.action as "accept" | "counter_offer" | "reject") || "counter_offer",
    counterPrice: parsed.counterPrice,
    reasoning: parsed.reasoning || "Compromise evaluated to maximize merchant margin and close deal.",
    messageToBuyer: parsed.messageToBuyer || "Counter offer submitted.",
    latencyMs,
    model,
  };
}

/**
 * 2. Grok System-2: Resolve Ambiguous or Multi-Attribute Variant Intent
 */
export async function grokResolveAmbiguity(
  params: GrokVariantClarificationRequest,
  apiKey?: string
): Promise<GrokVariantClarificationResponse> {
  const token = apiKey || process.env.OPENROUTER_API_KEY;
  if (!token) {
    throw new Error("OPENROUTER_API_KEY is required to invoke Grok System-2.");
  }

  const model = DEFAULT_GROK_MODEL;
  const startTime = Date.now();

  const prompt = `
You are the autonomous product matching intelligence for: "${params.productTitle}".
Customer Search/Intent: "${params.userIntent}"

Available Variants:
${JSON.stringify(params.variants, null, 2)}

System-1 Escalation Note:
${params.escalationReason || "Low confidence variant match; ambiguous attributes."}

Task:
Perform deep semantic matching. If a variant clearly fits the buyer intent despite terminology differences, select it.
If the request is truly ambiguous, provide a targeted clarifying question.
Return strictly valid JSON:
{
  "bestMatchVariantId": "variant id string or null",
  "confidence": number between 0.0 and 1.0,
  "reasoning": "Reasoning explaining why this SKU was selected",
  "clarifyingQuestionForBuyer": "Question string if ambiguous, else null"
}
`;

  const response = await fetch(OPENROUTER_CHAT_URL, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${token}`,
      "Content-Type": "application/json",
      "HTTP-Referer": "https://agent-gateway.dev",
      "X-Title": "Agent Gateway - Grok System-2",
    },
    body: JSON.stringify({
      model,
      messages: [
        {
          role: "system",
          content:
            "You are an autonomous e-commerce product matcher. Output valid JSON only, no markdown formatting.",
        },
        { role: "user", content: prompt },
      ],
      response_format: { type: "json_object" },
      temperature: 0.2,
    }),
  });

  const latencyMs = Date.now() - startTime;

  if (!response.ok) {
    const errorBody = await response.text();
    throw new Error(`Grok API Error (${response.status}): ${errorBody}`);
  }

  const data = await response.json();
  const rawContent = data.choices?.[0]?.message?.content || "{}";

  let parsed: Partial<GrokVariantClarificationResponse> = {};
  try {
    parsed = JSON.parse(rawContent);
  } catch {
    const cleaned = rawContent.replace(/```json/g, "").replace(/```/g, "").trim();
    parsed = JSON.parse(cleaned);
  }

  return {
    bestMatchVariantId: parsed.bestMatchVariantId ? String(parsed.bestMatchVariantId) : undefined,
    confidence: parsed.confidence ?? 0.85,
    reasoning: parsed.reasoning || "Deep semantic match completed by Grok.",
    clarifyingQuestionForBuyer: parsed.clarifyingQuestionForBuyer,
    latencyMs,
    model,
  };
}
