"""Request and response models. They generate the OpenAPI spec Grok Bot reads, so every
field says plainly what it is."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class Rules(BaseModel):
    """A shopper's rules. All optional: `notes` are preferences, the rest are hard filters."""

    max_per_piece: float | None = Field(None, description="Maximum price per piece", ge=0)
    max_total: float | None = Field(None, description="Maximum total price of one listing", ge=0)
    min_pieces: int | None = Field(None, description="Minimum pieces in a bundle", ge=0)
    grades: list[str] = Field(default_factory=list, description='Allowed tiers, e.g. ["premium"]')
    include_categories: list[str] = Field(
        default_factory=list, description="Only these categories or types (any level of the tree)"
    )
    exclude_categories: list[str] = Field(
        default_factory=list, description="Never these categories or types"
    )
    notes: list[str] = Field(
        default_factory=list, description="Free-text preferences, used to rank matching items"
    )

    def is_empty(self) -> bool:
        return self == Rules()


class SessionCreate(BaseModel):
    url: str = Field(
        description="The store page to read, e.g. https://www.joinfleek.com/collections/nike"
    )
    rules: Rules | None = None
    ruleset_id: UUID | None = Field(
        None, description="Start from one of the caller's saved rulesets"
    )
    entry: Literal["prefix", "widget"] = Field(
        "prefix", description="How the shopper arrived: our domain as a prefix, or a vendor widget"
    )
    referrer_origin: str | None = Field(
        None, max_length=300, description="Widget only: the origin the browser reported"
    )


class SessionCreated(BaseModel):
    code: str
    status: str
    session_url: str
    grok_url: str
    scrape_id: UUID


class SessionOut(BaseModel):
    code: str = Field(description="The session code, e.g. EM-7K2Q9X4M")
    store: str = Field(description="The store's domain")
    collection: str | None = Field(description="The page's title, e.g. Nike Vintage Wholesale")
    status: str = Field(description="pending, crawling, classifying, ready or failed")
    error: str | None = Field(
        None, description="Why the page couldn't be read, when status is failed"
    )
    product_count: int
    snapshot_at: datetime = Field(description="When the page was scraped")
    rules: Rules
    can_purchase: bool = Field(description="Whether purchases are possible for this session")
    session_url: str
    scrape_id: UUID
    expires_at: datetime


class TreeNode(BaseModel):
    name: str
    count: int
    children: list["TreeNode"] = Field(default_factory=list)


class TreeOut(BaseModel):
    tree: list[TreeNode]


class ProductItem(BaseModel):
    id: UUID
    title: str
    price: float | None = Field(description="Total price of the listing")
    per_piece: float | None = Field(description="Price per piece")
    pieces: int | None = Field(description="Pieces in the bundle")
    currency: str | None
    tree_path: list[str] = Field(description="Category path: category, type, tier")
    image_url: str | None
    source_url: str = Field(description="The product's page on the store")
    why: str = Field(description="Why this item matches the session's rules")


class ProductsOut(BaseModel):
    items: list[ProductItem]
    total_matching: int = Field(description="How many items match before `limit`")
    session_url: str


class ProductDetail(ProductItem):
    external_id: str | None
    compare_at_price: float | None
    in_stock: bool | None
    attrs: dict
    updated_at: datetime


class RefreshOut(BaseModel):
    product: ProductDetail
    changed: dict[str, list] = Field(description='What moved, e.g. {"price": [129.0, 141.0]}')


class RulesetIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    rules: Rules
    is_default: bool = False


class RulesetPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=80)
    rules: Rules | None = None
    is_default: bool | None = None


class RulesetOut(BaseModel):
    id: UUID
    name: str
    rules: Rules
    is_default: bool
    created_at: datetime


class RulesParseIn(BaseModel):
    text: str = Field(
        min_length=1, max_length=500, description='e.g. "premium only under 14 a piece"'
    )
