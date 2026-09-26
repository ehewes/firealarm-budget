"""Container entrypoint: refuse unsafe production settings, then serve on :8000.

Failing before uvicorn starts puts the reason in the deploy log and keeps the
healthcheck red, instead of serving with a guessable IP salt or fake scrapes.
"""

import logging
import re
import sys

import uvicorn

from app.config import get_settings

_AGENT_TOKEN = re.compile(r"em_agent_[A-Za-z0-9_-]+")


class _RedactAgentTokens(logging.Filter):
    """Connector URLs carry the agent token (`/v1/mcp?key=em_agent_...`); keep it out of logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(
                _AGENT_TOKEN.sub("em_agent_[redacted]", a) if isinstance(a, str) else a
                for a in record.args
            )
        return True


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    # httpx logs full request URLs at INFO; keep keys and tokens out of the logs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").addFilter(_RedactAgentTokens())
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
