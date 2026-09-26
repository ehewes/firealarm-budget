// Test Suite for Real-World Website Layouts, Missing Information & Broken Markup
// Run via: npx tsx scripts/test-messy-layouts.ts

import {
  parseHtmlStorefront,
  transpileStorefront,
  TranspiledStorefront,
} from "../src/lib/transpiler";
import {
  createEdenSession,
  applyEdenRules,
  EdenProductItem,
} from "../src/lib/eden";
import {
  parseMessyPriceString,
  extractLotPieceCount,
  resolveImageUrl,
  cleanProductTitle,
  normalizeMessyStorefront,
} from "../src/lib/messy-cleaner";

console.log("=======================================================================");
console.log("🧪 STRESS-TESTING DISPARATE STOREFRONT LAYOUTS & MISSING INFORMATION");
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
  // TEST 1: Schema.org JSON-LD with Array Offers & AggregateOffer
  // ---------------------------------------------------------------------------
  console.log("▶ [Test 1] Schema.org with Array Offers & AggregateOffer");

  // Layout 1A: offers as an Array of variants
  const htmlArrayOffers = `
    <!DOCTYPE html>
    <html>
      <head>
        <script type="application/ld+json">
        {
          "@context": "https://schema.org/",
          "@type": "Product",
          "name": "Vintage Carhartt Detroit Jacket (Lot of 6)",
          "description": "Heavyweight duck canvas, blanket lined.",
          "image": ["https://cdn.example.com/carhartt.jpg"],
          "offers": [
            {
              "@type": "Offer",
              "price": "240.00",
              "priceCurrency": "USD",
              "availability": "https://schema.org/InStock",
              "sku": "CH-01"
            },
            {
              "@type": "Offer",
              "price": "260.00",
              "priceCurrency": "USD",
              "availability": "https://schema.org/InStock",
              "sku": "CH-02"
            }
          ]
        }
        </script>
      </head>
      <body><h1>Storefront</h1></body>
    </html>
  `;

  // Layout 1B: AggregateOffer with lowPrice / highPrice
  const htmlAggregateOffer = `
    <!DOCTYPE html>
    <html>
      <head>
        <script type="application/ld+json">
        {
          "@context": "https://schema.org/",
          "@type": "Product",
          "name": "Vintage Band Tees Bundle (20 pcs)",
          "description": "Rock, metal, and 90s rap tees.",
          "offers": {
            "@type": "AggregateOffer",
            "lowPrice": "180.00",
            "highPrice": "220.00",
            "priceCurrency": "GBP"
          }
        }
        </script>
      </head>
      <body><h1>Storefront</h1></body>
    </html>
  `;

  const parsed1A = parseHtmlStorefront(htmlArrayOffers, "https://wholesale-workwear.com/products/carhartt-lot");
  assert(
    !isNaN(parsed1A.product.base_price) && parsed1A.product.base_price === 240.0,
    "1.1: Correctly extracts price from Array-based Schema.org offers without producing NaN",
    `Price: ${parsed1A.product.base_price}`
  );
  assert(
    parsed1A.product.title.includes("Vintage Carhartt Detroit Jacket"),
    "1.2: Correctly extracts product title from Array-based Schema.org",
    `Title: ${parsed1A.product.title}`
  );

  const parsed1B = parseHtmlStorefront(htmlAggregateOffer, "https://vintage-bale.co.uk/products/band-tees");
  assert(
    !isNaN(parsed1B.product.base_price) && parsed1B.product.base_price === 180.0,
    "1.3: Extracts lowPrice from AggregateOffer instead of producing NaN",
    `Price: ${parsed1B.product.base_price}`
  );
  assert(
    parsed1B.product.currency === "GBP",
    "1.4: Retains correct currency from AggregateOffer",
    `Currency: ${parsed1B.product.currency}`
  );

  // ---------------------------------------------------------------------------
  // TEST 2: HTML with NO JSON-LD and NO OpenGraph — Pure Table / Grid Layout
  // ---------------------------------------------------------------------------
  console.log("\n▶ [Test 2] Plain HTML Table/Card Scrape with NO JSON-LD or OpenGraph");

  const rawHtmlTable = `
    <!DOCTYPE html>
    <html lang="en">
      <head>
        <title>Vintage Ralph Lauren Sweaters (Box of 12) - EuroWholesale</title>
      </head>
      <body>
        <div class="product-container">
          <h1 class="product-title">Vintage Ralph Lauren Sweaters (Box of 12)</h1>
          <div class="pricing-box">
            <span class="currency">€</span>
            <span class="price-value">156,00</span>
            <span class="vat-note">excl. VAT</span>
          </div>
          <div class="product-details">
            <p>Grade A condition wool and cotton knitwear. Assorted sizes S to XL.</p>
          </div>
          <div class="gallery">
            <img class="main-photo" data-src="//cdn.eurowholesale.de/img/rl_sweaters.jpg" src="/assets/placeholder.svg" />
          </div>
        </div>
      </body>
    </html>
  `;

  const parsed2 = parseHtmlStorefront(rawHtmlTable, "https://eurowholesale.de/catalog/rl-sweaters");
  assert(
    parsed2.store.platform === "html_microdata" || parsed2.store.platform === "schema_org",
    "2.1: Accurately parses plain HTML table/card without falling back to synthetic dummy data",
    `Platform: ${parsed2.store.platform}`
  );
  assert(
    parsed2.product.title.includes("Vintage Ralph Lauren Sweaters"),
    "2.2: Extracts clean title from <h1> or <title> in plain HTML",
    `Title: ${parsed2.product.title}`
  );
  assert(
    parsed2.product.base_price === 156.0,
    "2.3: Parses European comma price '156,00' from plain DOM span to 156.00",
    `Price: ${parsed2.product.base_price}`
  );
  assert(
    parsed2.product.currency === "EUR",
    "2.4: Detects EUR currency from € symbol in markup",
    `Currency: ${parsed2.product.currency}`
  );

  // ---------------------------------------------------------------------------
  // TEST 3: Lazy-Loaded & SVG Placeholder Images Healing
  // ---------------------------------------------------------------------------
  console.log("\n▶ [Test 3] Lazy-Loaded Images, Data-Src & Protocol-Relative URLs");

  assert(
    parsed2.product.variants[0]?.id !== undefined,
    "3.1: Automatically constructs at least one valid variant from HTML layout",
    `Variant: ${JSON.stringify(parsed2.product.variants[0])}`
  );

  const healedImg1 = resolveImageUrl("//cdn.myshop.com/photo.jpg", "https://myshop.com");
  const healedImg2 = resolveImageUrl("data:image/svg+xml;base64,PHN2Zy...", "https://myshop.com", "tops");
  const healedImg3 = resolveImageUrl(undefined, "https://myshop.com", "footwear");

  assert(
    healedImg1 === "https://cdn.myshop.com/photo.jpg",
    "3.2: Heals protocol-relative '//cdn...' to 'https://cdn...'",
    `Image: ${healedImg1}`
  );
  assert(
    !healedImg2.startsWith("data:image/svg") && healedImg2.startsWith("https://"),
    "3.3: Replaces dummy SVG data URI placeholders with high-res curated imagery",
    `Image: ${healedImg2}`
  );
  assert(
    healedImg3.startsWith("https://"),
    "3.4: Replaces completely missing image with category footwear fallback",
    `Image: ${healedImg3}`
  );

  // ---------------------------------------------------------------------------
  // TEST 4: European Thousand Dot & Comma Decimal Numbers (Price Catastrophe Defense)
  // ---------------------------------------------------------------------------
  console.log("\n▶ [Test 4] Resilient Price Number Parsing Against Catastrophic Division Errors");

  // In Europe, 1.450,00 is 1450.00. Naive parseFloat("1.450,00") gives 1.45!
  const messyEuroThousand = "1.450,00 €";
  const messyUSThousand = "$1,450.00";
  const messyYen = "¥ 18,500";
  const messyPoundRange = "£85.00 - £110.00";
  const contactForPrice = "Price on Application / Call for Quote";

  assert(
    parseMessyPriceString(messyEuroThousand) === 1450.0,
    "4.1: Correctly parses European thousand dot '1.450,00 €' as 1450.00 (NOT 1.45)",
    `Got: ${parseMessyPriceString(messyEuroThousand)}`
  );
  assert(
    parseMessyPriceString(messyUSThousand) === 1450.0,
    "4.2: Correctly parses US thousand comma '$1,450.00' as 1450.00",
    `Got: ${parseMessyPriceString(messyUSThousand)}`
  );
  assert(
    parseMessyPriceString(messyYen) === 18500.0,
    "4.3: Correctly parses Japanese Yen '¥ 18,500' as 18500.00",
    `Got: ${parseMessyPriceString(messyYen)}`
  );
  assert(
    parseMessyPriceString(messyPoundRange) === 85.0,
    "4.4: Parses price range '£85.00 - £110.00' to lower bound 85.00",
    `Got: ${parseMessyPriceString(messyPoundRange)}`
  );
  assert(
    parseMessyPriceString(contactForPrice) === 0.0,
    "4.5: Non-numeric 'Price on Application' safely returns 0.00 without throwing or returning NaN",
    `Got: ${parseMessyPriceString(contactForPrice)}`
  );

  // ---------------------------------------------------------------------------
  // TEST 5: Accurate Piece Count Extraction & Real Rules Engine Budgeting
  // ---------------------------------------------------------------------------
  console.log("\n▶ [Test 5] Accurate Piece Count Discovery (No Hardcoded Modulo Flukes)");

  // A 10-piece bundle at $120.00 is $12.00/pc.
  // Under rule max_per_piece = 14.00, this MUST PASS.
  // Under rule max_per_piece = 10.00, this MUST FAIL.
  const lotTitle = "Vintage Graphic Tees (Lot of 10) - Grade A";
  const lotCount = extractLotPieceCount(lotTitle);

  assert(
    lotCount === 10,
    "5.1: Accurately identifies 10 pieces from '(Lot of 10)'",
    `Count: ${lotCount}`
  );

  // Single item check
  const singleTitle = "Vintage Leather Biker Jacket";
  assert(
    extractLotPieceCount(singleTitle) === 1,
    "5.2: Accurately identifies 1 piece for non-lot item",
    `Count: ${extractLotPieceCount(singleTitle)}`
  );

  // Test full Eden Session ingestion of a 10-piece lot
  const mockProductItem: EdenProductItem = {
    id: "item_test_10pc",
    title: lotTitle,
    price: 120.0,
    per_piece: 12.0, // 120 / 10
    pieces: 10,
    currency: "USD",
    tree_path: ["tops", "t-shirts", "vintage"],
    image_url: "https://images.unsplash.com/photo-1521572267360-ee0c2909d518",
    source_url: "https://fleek.com/item/tees-10",
    in_stock: true,
  };

  const passingFilter = await applyEdenRules([mockProductItem], {
    max_per_piece: 14.0, // $12 <= $14 -> should pass!
  });
  assert(
    passingFilter.length === 1,
    "5.3: Rules engine accepts $12.00/pc against $14.00/pc budget cap",
    `Accepted: ${passingFilter.length}`
  );

  const failingFilter = await applyEdenRules([mockProductItem], {
    max_per_piece: 10.0, // $12 > $10 -> should fail!
  });
  assert(
    failingFilter.length === 0,
    "5.4: Rules engine strictly rejects $12.00/pc against $10.00/pc budget cap",
    `Remaining: ${failingFilter.length}`
  );

  // ---------------------------------------------------------------------------
  // TEST 6: Dirty SEO Injections, HTML Tags & Encoded Entities
  // ---------------------------------------------------------------------------
  console.log("\n▶ [Test 6] Stripping Malicious / Dirty HTML & SEO Noise");

  const nastyTitle =
    "   <h1>HOT DEAL!</h1> Vintage <b>Nike</b> Sweatshirt (Box of 15) &amp; Hoodies &trade; - Buy Online | Official Outlet   ";
  const cleanedTitle = cleanProductTitle(nastyTitle);

  assert(
    !cleanedTitle.includes("<h1>") && !cleanedTitle.includes("<b>") && !cleanedTitle.includes("</b>"),
    "6.1: Strips raw HTML tags completely",
    `Title: '${cleanedTitle}'`
  );
  assert(
    cleanedTitle.includes("&") && !cleanedTitle.includes("&amp;") && !cleanedTitle.includes("&trade;"),
    "6.2: Decodes HTML entities (&amp; -> &, removes &trade;)",
    `Title: '${cleanedTitle}'`
  );
  assert(
    !cleanedTitle.includes("Buy Online | Official Outlet"),
    "6.3: Strips SEO spam suffix",
    `Title: '${cleanedTitle}'`
  );

  // ---------------------------------------------------------------------------
  // TEST 7: Total Garbage Scrape Recovery (Empty variants, missing everything)
  // ---------------------------------------------------------------------------
  console.log("\n▶ [Test 7] Full Storefront Recovery on Incomplete Scrapes");

  const partialScrape = {
    title: "",
    offers: "€ 89,90",
    description: "<script>alert('pwned')</script>Bundle of 5 heavy flannels.",
    image: "//assets.store.com/flannel.jpg",
  };

  const recovered = normalizeMessyStorefront(partialScrape, "https://wholesale-flannels.com/lots/heavy-flannel-pack");

  assert(
    recovered.title === "Heavy Flannel Pack" || recovered.title.includes("Flannel"),
    "7.1: Derives clean human-readable title from URL slug when title is missing",
    `Title: ${recovered.title}`
  );
  assert(
    recovered.base_price === 89.9,
    "7.2: Successfully extracts price from 'offers' string with European comma",
    `Price: ${recovered.base_price}`
  );
  assert(
    recovered.pieces === 5 && recovered.per_piece === 17.98,
    "7.3: Extracts piece count 5 from description and calculates accurate per_piece (17.98)",
    `Pieces: ${recovered.pieces}, Per piece: ${recovered.per_piece}`
  );
  assert(
    !recovered.description.includes("<script>") && !recovered.description.includes("alert"),
    "7.4: Sanitizes script tags and malicious code from description",
    `Description: ${recovered.description}`
  );
  assert(
    recovered.image_url.startsWith("https://assets.store.com/"),
    "7.5: Heals protocol-relative image URL",
    `Image: ${recovered.image_url}`
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
