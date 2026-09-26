"""Container entrypoint: refuse unsafe production settings, then serve.

Failing here, before uvicorn starts, puts the reason in the deploy log and keeps
the healthcheck red, instead of serving with a guessable IP salt or unverifiable
sign-ins.
"""

import logging
import sys

import uvicorn

from api.settings import get_settings
from eden_core.logs import setup_logging


def main() -> None:
    setup_logging()
    settings = get_settings()
    problems = settings.production_problems()
    for problem in problems:
        logging.getLogger("api").error("refusing to start: %s", problem)
    if problems:
        sys.exit(1)
    uvicorn.run(
        "api.main:create_app",
        factory=True,
        host="0.0.0.0",
        port=8000,
        # Caddy is the only thing in front, so its forwarded headers are trusted.
        proxy_headers=True,
        forwarded_allow_ips="*",
        log_config=None,
    )


if __name__ == "__main__":
    main()
