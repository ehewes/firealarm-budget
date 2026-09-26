# Docs

For anyone building on EdenMatrix "go". Start with architecture, then whichever area you are changing.

| Doc | Read it when |
| --- | --- |
| [architecture.md](architecture.md) | You want the whole picture: services, request flow, key decisions |
| [local-development.md](local-development.md) | Setting up a machine, running things, working offline |
| [database.md](database.md) | Touching the schema, the queue, or row level security |
| [api.md](api.md) | Adding endpoints, or changing what Grok reads (the context format) |
| [scraper.md](scraper.md) | Fetching, extraction, Jev decisions, crawl limits, spend caps |
| [widget.md](widget.md) | Embedding the vendor button, or changing it |
| [deployment.md](deployment.md) | The VPS, CI/CD, Cloudflare, rollbacks, the runbook |
| [secrets.md](secrets.md) | Adding, rotating or finding a credential |
| [roadmap.md](roadmap.md) | What is deliberately not built yet, and where it would go |

## Glossary

- **Entry gate**: a way into the service. There are two: the URL rewrite (`go.edenmatrix.xyz/<site>/<path>`)
  and the vendor widget (`/go?url=…`). Both end in the same session.
- **Scrape**: one fetch of a requested page plus the pages the crawler chose to follow from it (`scrapes`
  table). A fresh scrape of the same URL is reused rather than fetched again.
- **Session**: a public, read-only view of one scrape for one shopper, addressed by a code like
  `EM-7K2Q9X4M`. It carries a snapshot of the shopper's rules and expires after 24 hours.
- **Context**: the plain-text (Markdown) or JSON rendering of a session that Grok fetches.
- **Jev**: `typesafe/jev-1.13`, a decision model reached through OpenRouter. It answers typed questions
  (pick one, yes/no) with probabilities; we use it to choose which links to follow and to test items
  against a shopper's rule. It never writes text.
- **Ruleset**: a signed-in shopper's rule in plain words ("only pants"). Items that pass become the
  session's **picks**; when a session has a rule, only picks reach Grok.
