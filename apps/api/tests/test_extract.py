from pathlib import Path

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
