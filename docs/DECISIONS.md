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

## Demo data is committed
- **Decided:** `demo_data/` CSVs and manuals are committed, along with the script that generates the ticket history.
- **Alternatives:** generate at startup and gitignore.
- **Why:** they are the import files a company would upload, so they are source data, not build output. Committing them makes the seed reproducible and reviewable.

## Defaults for spec ambiguities
- **Repeat failure** counts the current ticket ("3 or more tickets in 60 days, including this one").
- **Unresolved closes** count as failed attempts for the fix variant used. Reporter self-fixes count toward issue frequency but not variant stats.
- **Savings if a self-fix works** = trip fee + labor for the targeted cause's estimated minutes.
- **Trip fee** applies when service mode is on-site or once a technician is assigned.
- **Unknown model:** an optional model picker; if still unknown, retrieval spans the models installed at that site and the first question is "confirm the model".
- **Roles:** managers see all tickets; technicians see only their assigned ones. Only technicians close tickets, except the self-fix "resolved" outcome.
- **Deployment:** Render (free tier wipes the disk, which is fine because the demo company is re-seeded on startup).
