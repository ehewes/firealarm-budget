# Roadmap: Eden Matrix

## Overview

One-day build, worked strictly top-down. Phase 1 delivers the core value (prefix → scrape → live tree → products endpoint Grok can call). Phase 2 adds rules and the Grok Bot handoff. Phase 3 adds accounts and the session page. Phase 4 (stretch) adds gated purchasing on a dev store.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

- [ ] **Phase 1: Scrape to Products API** - Prefix URL → background scrape → live tree → public products endpoint
- [ ] **Phase 2: Rules + Grok Handoff** - Plain-language rules applied server-side; Grok Bot recommends via the API
- [ ] **Phase 3: Sessions + Accounts** - Session page with picks, anonymous auth, saved rulesets, past sessions
- [ ] **Phase 4: Gated Purchasing (stretch)** - Purchase intent → confirm on Eden → single-use card → dev-store checkout

## Phase Details

### Phase 1: Scrape to Products API
**Goal**: Visiting `/<store-url>` starts a scrape, renders a live category tree, and `GET /v1/sessions/{code}/products` returns ranked products from the DB.
**Mode:** mvp
**Depends on**: Nothing (first phase)
**Requirements**: SCRP-01, SCRP-02, SCRP-03, SCRP-04, SCRP-05, SCRP-06, SCRP-07, API-01, API-02, API-03, API-04, API-05, API-06, API-07, WEB-01, WEB-02
**Success Criteria** (what must be TRUE):
  1. `POST /v1/sessions` with a Fleek collection URL returns `202` and a session code; a non-allowlisted URL returns `400 domain_not_allowed`
  2. Within a minute, `products` rows exist with title, price, per-piece price, image and tree path taken from the page (fixture or Bright Data)
  3. `GET /v1/sessions/{code}/products` and `/tree` return compact JSON matching `docs/API.md`
  4. Visiting `localhost:3000/https://www.joinfleek.com/collections/nike` shows the tree filling in live
**Plans**: TBD
**UI hint**: yes

### Phase 2: Rules + Grok Handoff
**Goal**: User types rules, clicks "Continue to Grok", and Grok Bot returns recommendations that respect those rules by calling the Eden API.
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: RULE-01, RULE-02, RULE-03, GROK-01, GROK-02
**Success Criteria** (what must be TRUE):
  1. "premium only under 14 a piece" parses into a structured rules object shown as chips
  2. Products endpoint never returns an item that violates a hard-filter rule
  3. Grok Bot, given a session code, calls the API through the public tunnel URL and lists matching products with reasons
**Plans**: TBD
**UI hint**: yes

### Phase 3: Sessions + Accounts
**Goal**: Guests and signed-in users see their picks on the session page; signed-in users keep rulesets and past sessions.
**Mode:** mvp
**Depends on**: Phase 2
**Requirements**: SESS-01, SESS-02, SESS-03, AUTH-01, AUTH-02
**Success Criteria** (what must be TRUE):
  1. `/s/{code}` shows Grok's picks as preview cards with prices from the DB
  2. A guest's rules survive a page reload; after sign-up their sessions and rules are still there
  3. Signed-in dashboard lists saved rulesets and past sessions
**Plans**: TBD
**UI hint**: yes

### Phase 4: Gated Purchasing (stretch)
**Goal**: A signed-in user can ask Grok to buy, confirm on Eden, and a single-use card completes checkout on the dev store.
**Mode:** mvp
**Depends on**: Phase 3
**Requirements**: BUY-01, BUY-02, BUY-03, BUY-04, BUY-05
**Success Criteria** (what must be TRUE):
  1. Purchase intent from an anonymous session returns `403 purchase_not_allowed`
  2. Changed price at confirm time returns `409 price_changed` and requires re-confirmation
  3. Confirmed intent completes checkout on the dev store; no card number appears in any LLM request or response
**Plans**: TBD
**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Scrape to Products API | 0/TBD | Not started | - |
| 2. Rules + Grok Handoff | 0/TBD | Not started | - |
| 3. Sessions + Accounts | 0/TBD | Not started | - |
| 4. Gated Purchasing (stretch) | 0/TBD | Not started | - |
