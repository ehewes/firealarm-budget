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


# ---------------------------------------------------------------- accounts, agents, cards


class CardIn(BaseModel):
    spend_cap: float = Field(gt=0, le=5000, description="The most a single purchase may cost")
    currency: Literal["GBP", "USD", "EUR"] = "GBP"


class CardOut(BaseModel):
    provider: str = Field(description='"demo" until a real card provider is connected')
    label: str | None
    last4: str | None
    spend_cap: float | None
    currency: str


class AgentIn(BaseModel):
    name: str = Field("Grok Bot", min_length=1, max_length=60)


class AgentOut(BaseModel):
    id: UUID
    name: str
    token_hint: str = Field(description="The token's last 4 characters")
    created_at: datetime
    last_used_at: datetime | None


class AgentCreated(AgentOut):
    token: str = Field(description="Shown once: give it to your agent. Eden keeps only its hash")
    mcp_url: str
    mcp_config: dict = Field(description="Paste into Grok Bot's MCP servers JSON")
    connector_url: str = Field(
        description="For clients that only take a URL (grok.com custom connectors); holds the token"
    )


class WebhookIn(BaseModel):
    url: str = Field(max_length=500, pattern=r"^https://", description="The webhook's URL")
    key: str = Field(min_length=8, max_length=500, description="The automation's webhook key")


class WebhookOut(BaseModel):
    host: str = Field(description="The webhook URL's host; the key is never shown again")
    last_sent_at: datetime | None


class MeOut(BaseModel):
    id: UUID
    email: str | None
    is_anonymous: bool
    card: CardOut | None
    agents: list[AgentOut]
    grok_bot_webhook: WebhookOut | None


class PastSession(BaseModel):
    code: str
    store: str
    collection: str | None
    status: str
    product_count: int
    created_at: datetime
    expires_at: datetime
    session_url: str


# ---------------------------------------------------------------- purchases


class PurchaseItem(BaseModel):
    id: UUID
    title: str
    price: float | None
    currency: str | None
    image_url: str | None
    source_url: str
    in_stock: bool | None


class CardReady(BaseModel):
    status: Literal["card_ready"] = "card_ready"
    last4: str | None = Field(description="Never more than the last four digits")
    limit: float | None = Field(description="The most the card will pay")


class PurchaseOut(BaseModel):
    id: UUID
    status: str = Field(
        description="pending, price_changed, executing, completed, failed or cancelled"
    )
    store: str | None
    session_code: str | None
    items: list[PurchaseItem]
    total: float = Field(description="The total the shopper is asked to confirm")
    currency: str | None
    card: CardReady | None = Field(description="Set once the shopper has confirmed")
    confirm_url: str = Field(description="Where the shopper confirms or cancels, on Eden")
    expires_at: datetime
    order_ref: str | None = Field(description="The demo checkout's order reference")
    error: str | None
