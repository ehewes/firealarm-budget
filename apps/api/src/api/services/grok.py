"""The Continue in Grok link.

`grok.com/?q=` pre-fills (and usually sends) a prompt. It is community-documented
rather than an official API, so it is built in exactly one place, and the session
page also offers the prompt to copy.
"""

from urllib.parse import urlencode

GROK_URL = "https://grok.com/"


def grok_prompt(*, domain: str, title: str | None, context_url: str) -> str:
    about = f"{domain} ({title[:80]})" if title else domain
    return (
        f"I'm shopping on {about}. Read this snapshot of the page I was on first: "
        f"{context_url} . It lists the items on the page and the links to related pages. "
        "Then help me with it, using only what the snapshot or the shop's own pages say."
    )


def grok_url(prompt: str) -> str:
    return GROK_URL + "?" + urlencode({"q": prompt})
