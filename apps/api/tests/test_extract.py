from pathlib import Path

import pytest

from app.services.extract import parse_listing, parse_product
from app.services.taxonomy import keyword_path

FIXTURES = Path(__file__).parent / "fixtures"
COLLECTION = "https://www.joinfleek.com/collections/april-eom-rl-drop"


def test_listing_uses_the_largest_product_list_in_next_data():
    listing = parse_listing((FIXTURES / "collection.html").read_text(), COLLECTION)
    assert listing.title == "April EOM RL Drop"
    assert listing.total_items == 61
    assert listing.next_url == COLLECTION + "?page=2"
    assert len(listing.items) == 6

    rugby = listing.items[0]
    assert rugby.title == "Polo Ralph Lauren Rugby T-shirts"
    # The slug URL (redirectUrl) is the canonical one, not the tracked /products/<id> link.
    assert (
        rugby.source_url == "https://www.joinfleek.com/products/polo-ralph-lauren-rugby-t-shirts-4"
    )
    assert rugby.external_id == "9475004989678"
    assert (rugby.price, rugby.pieces, rugby.per_piece, rugby.currency) == (312.0, 20, 15.6, "USD")
    assert rugby.attrs["description"] == "Mixed colours, sizes S–XL."
    assert rugby.attrs["position"] == 0

    swim = listing.items[1]
    assert swim.compare_at_price == 300.0  # 240 at 20% off


def test_listing_falls_back_to_product_links_without_page_json():
    html = """<html><body>
      <a href="/products/abc?click_source=X"><style>.x{}</style>
        <img alt="Blue Jeans" src="a.jpg"></a>
      <a href="/products/abc">duplicate</a>
      <a href="https://elsewhere.example/products/zzz"><img alt="Not this store"></a>
      <a href="/pages/about">About</a>
    </body></html>"""
    listing = parse_listing(html, "https://www.joinfleek.com/collections/x")
    assert [(i.title, i.source_url) for i in listing.items] == [
        ("Blue Jeans", "https://www.joinfleek.com/products/abc")
    ]


def test_product_page_reads_lowercase_json_ld_and_ignores_related_products():
    page = parse_product(
        (FIXTURES / "product.html").read_text(),
        "https://www.joinfleek.com/products/ralph-lauren-trousers-pant-rv-1273",
    )
    assert page.title == "Ralph Lauren Trousers/Pant RV # 1273"
    assert (page.price, page.currency, page.in_stock) == (275.0, "USD", True)
    assert page.brand == "Ralph Lauren"
    assert page.breadcrumbs == ["Home", "Bottoms", "Trousers"]
    assert page.description == "20 pieces of vintage Ralph Lauren trousers. Sizes 30–36."


def test_keyword_tree_places_the_fixture_items():
    assert keyword_path("Ralph Lauren Trousers/Pant RV # 1273") == [
        "bottoms",
        "trousers",
        "standard",
    ]
    assert keyword_path("Polo Ralph Lauren Rugby T-shirts") == ["tops", "t-shirts", "standard"]
    assert keyword_path("Ralph Lauren Swim Shorts (FNC 694)") == ["bottoms", "shorts", "standard"]
    assert keyword_path("Premium Ralph Lauren Cable Knit Jumpers") == [
        "tops",
        "knitwear",
        "premium",
    ]
    assert keyword_path("Nike Track Pants") == ["bottoms", "trackpants", "standard"]
    assert keyword_path("Something odd") == ["mixed", "mixed bundle", "standard"]


def test_brand_names_do_not_decide_the_type():
    assert keyword_path("Polo Ralph Lauren Shirts") == ["tops", "shirts", "standard"]
    assert keyword_path("Polo Ralph Lauren Polo Shirts") == ["tops", "polos", "standard"]


def test_the_title_outranks_breadcrumbs_and_descriptions():
    assert keyword_path("Polo Ralph Lauren Rugby T-shirts", "Home Bottoms Trousers") == [
        "tops",
        "t-shirts",
        "standard",
    ]
    assert keyword_path("Ralph Lauren Bundle 42", "Home Bottoms Jeans") == [
        "mixed",
        "mixed bundle",
        "standard",
    ]
    assert keyword_path("Ralph Lauren 42", "Home Bottoms Jeans premium grade") == [
        "bottoms",
        "jeans",
        "premium",
    ]


ZARA = "https://www.zara.com/uk/en/man-shirts-l737.html"


def test_inline_page_data_matched_to_the_stores_own_links():
    listing = parse_listing((FIXTURES / "zara_listing.html").read_text(), ZARA)
    by_url = {item.source_url: item for item in listing.items}
    assert len(listing.items) == 4 and len(by_url) == 4  # 3 from page data + 1 link-only, no dupes
    tuxedo = by_url["https://www.zara.com/uk/en/contrast-print-tuxedo-style-shirt-p06085001.html"]
    # Minor units divided by 100 (currencyDecimals -2), page currency applied, image from link.
    assert (tuxedo.title, tuxedo.price, tuxedo.per_piece, tuxedo.currency) == (
        "TUXEDO-STYLE CONTRAST PRINT SHIRT",
        69.99,
        69.99,
        "GBP",
    )
    assert tuxedo.in_stock is True and tuxedo.image_url == "https://static.example.test/a.jpg"
    assert tuxedo.attrs["category"] == "SHIRT"
    pocket = by_url["https://www.zara.com/uk/en/relaxed-fit-pocket-shirt-p04391804.html"]
    assert pocket.in_stock is False
    link_only = by_url["https://www.zara.com/uk/en/acid-wash-relaxed-fit-shirt-p06987323.html"]
    assert link_only.title == "Acid wash relaxed fit shirt" and link_only.price is None


@pytest.mark.parametrize(
    "path",
    [
        "/uk/en/linen-shirt-p04347111.html",  # Zara
        "/en_gb/productpage.1234567001.html",  # H&M
        "/prd/203944411",  # ASOS
        "/itm/1234567890",  # eBay
        "/listing/987654321/handmade-mug",  # Etsy
        "/t/air-max-90-mens-shoes/DM0029-100",  # Nike
        "/products/rugby-shirt",  # Shopify / Fleek
        "/mens/linen-blend-shirt-4455667.html",  # slug + long numeric id
    ],
)
def test_product_url_shapes(path):
    from app.services.extract import _PRODUCT_PATH

    assert _PRODUCT_PATH.search(path)


def test_store_chrome_is_never_a_product_or_a_candidate():
    from app.services.extract import _NOT_PRODUCT, candidate_links

    assert _NOT_PRODUCT.search("/uk/en/shop/cart") and _NOT_PRODUCT.search("/help/returns")
    html = """<html><body><a href="/help">Help centre</a><a href="/cart">Your bag</a>
      <a href="/collections/new-in">New in this week</a>
      <a href="/other-shop.com">x</a></body></html>"""
    links = candidate_links(html, "https://shop.example.com/")
    assert links == [("https://shop.example.com/collections/new-in", "New in this week")]


def test_prices_printed_in_the_tile_and_product_page_fallbacks():
    html = """<html><body><div class="tile"><a href="/p/blue-tee"><img alt="Blue Tee"></a>
      <span>£12.50</span></div></body></html>"""
    item = parse_listing(html, "https://shop.example.com/c/tees").items[0]
    assert (item.title, item.price, item.currency, item.per_piece) == (
        "Blue Tee",
        12.5,
        "GBP",
        12.5,
    )

    page = parse_product(
        """<html><head><meta property="og:title" content="Blue Tee">
        <meta property="product:price:amount" content="12.50">
        <meta property="product:price:currency" content="GBP"></head></html>""",
        "https://shop.example.com/p/blue-tee",
    )
    assert (page.title, page.price, page.currency) == ("Blue Tee", 12.5, "GBP")
    ranged = parse_product(
        """<script type="application/ld+json">{"@type":"Product","name":"Mug",
        "image":["https://x/m.jpg"],
        "offers":{"@type":"AggregateOffer","lowPrice":"8.00","priceCurrency":"EUR"}}</script>""",
        "https://shop.example.com/p/mug",
    )
    assert (ranged.price, ranged.currency, ranged.image) == (8.0, "EUR", "https://x/m.jpg")


def test_a_tile_price_never_comes_from_the_neighbouring_product():
    html = """<html><body><ul class="grid">
      <li><a href="/uk/en/linen-shirt-p01234567.html"><img alt="Linen shirt" src="/i/1.jpg"></a>
        <span class="price">£29.99</span></li>
      <li><a href="/uk/en/oxford-shirt-p07654321.html"><img alt="Oxford shirt"
        src="data:image/gif;base64,R0lGOD" data-src="/i/2.jpg"></a></li>
      <li><a href="/uk/en/work-shirt-p05555555.html"><h3 class="name">Work shirt 3 pcs</h3></a>
        <span>£45.00</span></li>
    </ul></body></html>"""
    linen, oxford, work = parse_listing(
        html, "https://www.zara.com/uk/en/man-shirts-l737.html"
    ).items
    assert (linen.price, linen.currency, linen.image_url) == (
        29.99,
        "GBP",
        "https://www.zara.com/i/1.jpg",
    )
    # No price in its own card: the grid's first price belongs to the linen shirt.
    assert oxford.price is None
    assert oxford.image_url == "https://www.zara.com/i/2.jpg"  # the lazy image, not the placeholder
    assert (work.title, work.pieces, work.per_piece) == ("Work shirt 3 pcs", 3, 15.0)
