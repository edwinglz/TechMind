# Decisions

One entry per significant choice: what we decided, what else we considered, and why.

## Integer IDs plus a company `ref`
- **Decided:** every table uses an integer `id` primary key; imported records also keep `ref`, the company's own ID, unique per company.
- **Alternatives:** use the company's IDs directly as primary keys; composite keys of (company_id, ref).
- **Why:** two companies can both have a site "S01", so their IDs can't be global keys. Integer keys keep SQLModel simple, and `ref` lets CSV export reproduce the company's own IDs.

## `settings.csv` lives on the `companies` row
- **Decided:** labor rate, trip fee, and currency are columns on `companies`.
- **Alternatives:** a separate settings table.
- **Why:** there is exactly one set of settings per company.

## Fix-variant stats are computed, not stored
- **Decided:** `fix_variants` stores only the steps; attempts, successes, and average minutes are calculated from tickets.
- **Alternatives:** counter columns updated on every close.
- **Why:** counters can drift from the tickets they summarize. Computing them keeps one source of truth and is easy to explain. The data is small enough that this is fast.

## Chat messages are ticket events
- **Decided:** chat messages are rows in `ticket_events` with type `chat_message`.
- **Alternatives:** a separate chat table.
- **Why:** the spec already requires logging every chat message as an event; storing it twice would be redundant.

## Keyword search (FTS5) instead of embeddings
- **Decided:** manual sections and similar past tickets are found with SQLite FTS5 (BM25 ranking).
- **Alternatives:** vector embeddings.
- **Why:** required by the spec, no extra service or cost, and results are explainable.

## Trend "today" is configurable
- **Decided:** trend math uses `AS_OF_DATE` from `.env` if set, otherwise the real date.
- **Alternatives:** always the real date; shift demo dates at seed time.
- **Why:** the demo data covers May–October 2026. If the demo runs later, "rising in the last month" would silently stop being true.

## Historical tickets have no photos
- **Decided:** `ticket_history.csv` has no photo column and the demo data has no placeholder images. Only tickets created in the app can have a photo.
- **Alternatives:** an optional `photo_file` column with placeholder images (the spec's original suggestion).
- **Why:** product owner's call; keeps the import format and demo data simpler.

## The demo company runs many kinds of equipment
- **Decided:** each Kestrel Burger store has a realistic mix of quick-service equipment. That's 58 units across 7 models:
  - countertop and self-serve beverage dispensers
  - gas fryers and a griddle
  - an ice machine and a walk-in cooler
  - rooftop HVAC

  Ticket history covers all of them. The fountain dispenser at Store #4 only matters once the demo report comes in.
- **Alternatives:** the spec's original demo set (4–5 fountain models only).
- **Why:** product owner's call. TechMind is a general-purpose product, and a company typically maintains many kinds of equipment; a fountain-only demo made it look like a soda-machine tool. Bonus: the summer "fading" pattern is now natural (HVAC, walk-in, ice machine, and warm drinks all peak in summer).

## Demo data is committed
- **Decided:** `demo_data/` CSVs and manuals are committed, along with the script that generates the ticket history.
- **Alternatives:** generate at startup and gitignore.
- **Why:** they are the import files a company would upload, so they are source data, not build output. Committing them makes the seed reproducible and reviewable.

## Small, backward-compatible additions to the import format
- **Decided:**
  - `profile.json` may include `company_name` (otherwise the importer asks for one).
  - `labels` may include plurals (`sites`, `assets`, `reporters`). Without them, plurals follow plain English rules, which would turn "store staff" into "store staffs".
  - `in_stock` accepts a quantity or y/n.
- **Alternatives:** a separate company settings file; hardcoded plural rules.
- **Why:** every addition is optional, so any file that matches the spec still imports.

## Public product page plus username/password login
- **Decided:**
  - `/` is a TechMind product page with no company data and a **Log in** button.
  - Login takes a username and password. Everything inside the product lives under `/app`.
  - Passwords are stored as salted PBKDF2 hashes (standard library).
  - The session is a cookie holding the user id plus an HMAC signature made with `SECRET_KEY`.
  - Usernames are unique across all companies, so the login form doesn't need a company field.
- **Alternatives:**
  - the spec's "Log in as" picker (no passwords)
  - a full auth library (sessions table, password reset, sign-up)
- **Why:** product owner's call. TechMind is a product any company could buy, so the front door should present the product rather than list one company's people. Standard-library hashing and a signed cookie give real protection with no new dependencies. Sign-up, password reset, and rate limiting remain out of scope.

## Demo accounts are created by the seed, not the importer
- **Decided:** `app/seed.py` creates `manager`, `ana`, and `luis` for the demo company, all with `DEMO_PASSWORD` from `.env`. If that's blank, it generates a random password and logs it once. The importer never creates users.
- **Alternatives:** a users.csv in the import; a password hardcoded in the repo.
- **Why:** accounts aren't company equipment data, so they don't belong in the import format, and a password in the repo would be a committed secret.

## Trends need at least 2 tickets
- **Decided:** "rising" requires the last 30 days to have more tickets than the prior 30 *and* at least 2. "Fading" is the mirror image.
- **Alternatives:** the bare comparison from the spec.
- **Why:** with the bare rule, one ticket against zero labels an issue "rising", which is noise. Requiring 2 is still easy to explain.

## Demo history is generated by a checked script
- **Decided:** `scripts/generate_demo_history.py` does the following:
  - builds `assets.csv` from a store-by-store equipment layout
  - plans tickets per issue per period
  - assigns units under a cap, so only Store #4's beverage dispenser reaches the repeat-failure threshold
  - refuses to write anything unless every demo pattern holds

  Tests re-run those checks and confirm the committed files match a fresh run.
- **Alternatives:** hand-written CSV; purely random data.
- **Why:** the demo script depends on exact patterns (for example, Ana's ticket must tip the carbonator fix over). Hand-editing 120 rows would break them silently.

## Search uses Porter stemming
- **Decided:** both FTS5 indexes use the `porter unicode61` tokenizer.
- **Alternatives:** the default tokenizer.
- **Why:** reports and manuals use different word forms ("leaking", "leaks", "leak"); stemming matches them.

## Defaults for spec ambiguities
- **Repeat failure** counts the current ticket ("3 or more tickets in 60 days, including this one").
- **Unresolved closes** count as failed attempts for the fix variant used. Reporter self-fixes count toward issue frequency but not variant stats.
- **Savings if a self-fix works** = trip fee + labor for the targeted cause's estimated minutes.
- **Trip fee** applies when service mode is on-site or once a technician is assigned.
- **Unknown model:** an optional model picker; if still unknown, retrieval spans the models installed at that site and the first question is "confirm the model".
- **No migrations:** after a table changes, delete `data/techmind.db` and restart; the demo data is re-seeded. Startup detects an outdated database file (missing columns) and stops with that instruction rather than serving errors. Fine for a hackathon, and deploys start fresh anyway.
- **Roles:** managers see all tickets; technicians see only their assigned ones. Only technicians close tickets, except the self-fix "resolved" outcome.
- **Deployment:** Render (free tier wipes the disk, which is fine because the demo company is re-seeded on startup).

## A real mock engine instead of canned fixtures
- **Decided:** mock mode builds each brief from the company's own data (known issues matched to the report, ranked by frequency and trend, re-ranked by answers and failed self-fixes) rather than returning fixed JSON files.
- **Alternatives:** the spec's fixture briefs in `/fixtures`.
- **Why:** with about $5 of API budget and no key yet, the demo has to work without Claude. A data-driven mock gives a different, sensible brief for any report, and Refine visibly changes the ranking. Live mode uses the same retrieval and output shape.

## The manager board replaces the counts dashboard; the login page is the front door
- **Decided:** after login, managers land on a board of reports grouped by the next action; technicians land on My jobs. `/` shows the login page with a one-line pitch.
- **Alternatives:** the Phase 1 dashboard of counts plus a separate product page.
- **Why:** product owner's feedback that the app didn't feel like their idea. The core of the idea is the ticket flow, so it's the first thing anyone sees.

## Own stylesheet and bundled assets instead of Tailwind from a CDN
- **Decided:** one hand-written stylesheet (`app/static/app.css`) with a service-tag visual language; Barlow fonts and htmx are bundled in `app/static/`.
- **Alternatives:** Tailwind's CDN build.
- **Why:** a distinctive look for the pitch, and nothing to download at the venue, so the demo works on bad wifi.

## Closing picks a fix from a list
- **Decided:** the close form lists the issue's known fix variants with their success rates; the technician picks one or describes a different fix.
- **Alternatives:** free-text only, matched by Haiku (the spec's approach).
- **Why:** faster on a phone, no AI call needed in the common case, and the demo's "the recommended fix changes" moment is reliable. Free text is still matched by Haiku in live mode.

## A failed self-fix re-ranks the brief automatically
- **Decided:** when the manager records that the reporter's self-fix didn't work, the brief is regenerated with that information.
- **Alternatives:** wait for someone to press Refine.
- **Why:** the most useful moment for a new ranking is right before dispatching.
