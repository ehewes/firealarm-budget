"""One logging setup for both services: plain lines to stdout, which Docker keeps."""

import logging
import os


def setup_logging(level: str | None = None) -> None:
    logging.basicConfig(
        level=(level or os.environ.get("LOG_LEVEL") or "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # httpx logs every request URL at INFO, query strings included. Proxy
    # credentials and API keys can travel in those, so keep it quiet.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
