"""The messages on the `scrape` queue: the contract between the API and the scraper.

Versioned (`v`) so a message written by one release can still be read by the
next during a deploy, when an old API and a new worker briefly overlap.
"""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, TypeAdapter


class PageJob(BaseModel):
    """Fetch and parse one page of a scrape. At depth 0 it also plans the crawl."""

    v: Literal[1] = 1
    kind: Literal["page"] = "page"
    scrape_id: UUID
    url: str
    depth: int = 0
    parent_url: str | None = None
    # 'root' for the requested page; otherwise who chose it: 'jev' or 'heuristic'.
    reason: str = "root"


class ClassifyJob(BaseModel):
    """Apply a new session's rule to a scrape that already has products."""

    v: Literal[1] = 1
    kind: Literal["classify"] = "classify"
    session_id: UUID


Job = Annotated[PageJob | ClassifyJob, Field(discriminator="kind")]
_adapter: TypeAdapter[PageJob | ClassifyJob] = TypeAdapter(Job)


def parse_job(data: object) -> PageJob | ClassifyJob:
    """Validate a queue message. Raises `pydantic.ValidationError` if it is not a job."""
    return _adapter.validate_python(data)
