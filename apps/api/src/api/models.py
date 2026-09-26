"""Request and response bodies. These are the API's public contract (see docs/api.md)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Entry = Literal["url_rewrite", "widget"]


class SessionCreate(BaseModel):
    url: str = Field(max_length=4096, description="The page to read, with or without https://")
    entry: Entry = "url_rewrite"
    referrer_origin: str | None = Field(
        default=None,
        max_length=300,
        description="Widget gate only: the origin the browser said the shopper came from.",
    )


class SessionCreated(BaseModel):
    code: str
    status: str
    reused: bool
    session_url: str
    context_url: str


class RuleState(BaseModel):
    text: str
    shown: int
    classified: bool


class SessionStatus(BaseModel):
    code: str
    # The scrape's status: pending, crawling, classifying, ready or failed.
    status: str
    # True once the requested page is read and the shopper's rule (if any) applied:
    # the moment Continue in Grok becomes useful.
    ready: bool
    target_url: str
    domain: str
    title: str | None
    product_count: int
    pages_done: int
    pages_planned: int
    rule: RuleState | None
    error: str | None
    context_url: str
    grok_url: str | None
    grok_prompt: str | None
    created_at: datetime
    expires_at: datetime


class RulesetIn(BaseModel):
    rule: str = Field(min_length=1, max_length=500, description='In plain words, e.g. "only pants"')


class RulesetOut(BaseModel):
    rule: str | None
