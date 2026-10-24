# Architecture

TechMind is a single FastAPI app that renders HTML pages with Jinja2 templates. HTMX adds small interactive bits (chat polling, partial page swaps) without a JavaScript framework. Everything is stored in one SQLite database. The only external service is the Claude API, and even that can be swapped for canned fixtures (`AI_MODE=mock`).

## The big idea: no domain knowledge in code

The code only knows generic concepts: **sites**, **assets**, **products** (models), **parts**, **known issues**, **tickets**, and a **reporter** (the person with the broken thing). Everything industry-specific comes from the company's imported data:

- manuals, known issues, parts, and ticket history (CSV + Markdown)
- a **domain profile** (`profile.json`) with the words the UI should use ("store" instead of "site"), what reporters may safely try themselves, what they must never do, and which safety topics matter

The profile is injected into the AI prompt and into every page template. Swapping in a laptop repair shop's data changes the app's vocabulary and advice without touching code.

## Code map

| Path | What it does |
|---|---|
| `app/main.py` | Creates the FastAPI app; on startup creates tables and seeds the demo company |
| `app/config.py` | Reads `.env` (AI mode, database, upload folder, `AS_OF_DATE`) |
| `app/models.py` | All database tables |
| `app/db.py` | Database engine, sessions, FTS5 search tables |
| `app/auth.py` | "Log in as" cookie; `require_login` dependency for pages |
| `app/templating.py` | Jinja2 setup; company labels (`L.site`, `L.assets`, …) and money formatting |
| `app/importer/` | `parse.py` validates import files into a preview; `load.py` writes them; `manuals.py` splits manuals into sections |
| `app/services/` | Shared logic: search-index writes, fix-variant helpers (more in later phases) |
| `app/routes/` | One module per page area |
| `app/templates/` | HTML pages (Tailwind + HTMX from CDNs, no build step) |
| `demo_data/` | The fictional demo company, in the import format |
| `scripts/generate_demo_history.py` | Builds and checks `demo_data/ticket_history.csv` |
| `tests/` | pytest suite |

## Import: how a company's data gets in

1. **Parse** (`app/importer/parse.py`). Files arrive as name → bytes, so uploads and the demo folder take the same path. Zips are unpacked and `.md` files become manuals. Each CSV is checked for required columns, values are converted (dates, numbers, y/n, `;`-lists, `|`-lists), and every reference is checked (an asset's `model_id` must exist in `products.csv`, and so on). Problems are reported with spreadsheet row numbers. Nothing is written yet.
2. **Load** (`app/importer/load.py`). This creates the company and its default users, then copies every row. Manuals are split at `##`/`###` headings into sections and indexed for search. Each known issue's documented fix becomes its first fix variant. Imported history tickets are grouped by the fix steps they used, so a different fix that technicians have been using becomes its own variant with its own track record.
3. **Seed** (`app/seed.py`). On startup, if there are no companies, the app parses and loads `demo_data/`.

## Ticket flow

```mermaid
flowchart TD
    A[Manager enters report<br/>site, asset, description, photo] --> B[Retrieval<br/>manual sections via FTS5<br/>known issues ranked by trend<br/>similar past tickets<br/>asset history]
    B --> C[One Claude call with vision<br/>+ domain profile]
    C --> D{Valid JSON brief?}
    D -- no, retry once --> C
    D -- yes --> E[Store brief + compute costs in Python]
    E --> F{Reporter self-fix<br/>suggested?}
    F -- manager approves --> G[Awaiting reporter self-fix<br/>manager phones reporter]
    G -- resolved --> H[Closed: resolved by reporter<br/>dispatch avoided logged]
    G -- not resolved --> I
    F -- no / skipped --> I[Manager assigns technician]
    I --> J[Technician on phone<br/>brief, questions checklist, chat]
    J -- answers + Refine --> C
    J --> K[Technician closes ticket<br/>actual issue, fix used, parts, minutes]
    H --> L[Knowledge update<br/>fix-variant stats, trends, asset history]
    K --> L
    L -.feeds future retrieval.-> B
```

Every step writes a row to the append-only `ticket_events` table.

## Data model

Every table has an integer `id` and a `company_id`, so several companies can share one database. Imported records also keep `ref`, the company's own ID (for example `S04`), which is unique per company and is what CSV export writes back out.

| Table | What it holds |
|---|---|
| `companies` | name, domain profile (JSON), labor rate, trip fee, currency |
| `users` | people in the "Log in as" picker, with role `manager` or `technician` |
| `sites` | where assets live (a store, a customer's home) |
| `products` | equipment models: manufacturer, name, category, manual file |
| `assets` | one physical unit: which product, at which site, serial, dates |
| `parts` | price list, which models each part fits, stock |
| `known_issues` | per product: symptoms, root cause, typical minutes, whether the reporter can fix it |
| `fix_variants` | the different ways a known issue has been fixed (steps + where they came from) |
| `manual_chunks` (+ FTS5 index) | manuals split into sections for keyword search |
| `tickets` | the report, status, assignment, reporter answers, and the closing outcome |
| `tickets_fts` | FTS5 index of ticket descriptions, for "similar past tickets" |
| `briefs` | every generated brief version for a ticket, with token usage |
| `ticket_events` | append-only log of everything that happened to a ticket, including chat messages |

Ticket status moves `new → briefed → awaiting_self_fix → assigned → closed` (the self-fix step is optional).

## Adaptability logic (planned, Phase 5)

All of this is plain SQL and Python over the tickets table; there is no model training.

- **Fix variants.** Each known issue can have several fixes. Success stats (attempts, successes, average minutes) are computed from the tickets that used each variant. The **recommended fix** is the variant with the best success rate among those with at least 3 attempts; ties go to the faster one. When a technician describes a different fix, a small Claude Haiku call decides whether it matches an existing variant or is new.
- **Common issues.** Each issue's recent frequency is a recency-weighted count over the last 90 days: a ticket from today counts 1, one from 30 days ago counts 0.5, from 60 days ago 0.25. An issue is **rising** if the last 30 days had more tickets than the 30 before, **fading** if fewer. The busier of the two windows needs at least 2 tickets, so a single ticket (1 vs 0) doesn't count as a trend. Retrieval ranks known issues by this score, so briefs shift as conditions change.
- **Repeat failures.** An asset with 3 or more tickets in 60 days is flagged in the brief and on its page.
