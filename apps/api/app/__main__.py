"""Container entrypoint: refuse unsafe production settings, then serve on :8000.

Failing before uvicorn starts puts the reason in the deploy log and keeps the
healthcheck red, instead of serving with a guessable IP salt or fake scrapes.
"""

import logging
import sys

import uvicorn

from app.config import get_settings


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    # httpx logs full request URLs at INFO; keep keys and tokens out of the logs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    problems = get_settings().production_problems()
    for problem in problems:
        logging.getLogger("app").error("refusing to start: %s", problem)
    if problems:
        sys.exit(1)
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        # Caddy is the only thing in front of the API, so its forwarded headers are trusted.
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
