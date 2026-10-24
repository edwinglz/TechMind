# Progress

## Phases

- [x] **Phase 0: Repo setup.** Git, `.gitignore`, `.env.example`, private GitHub repo, README and docs.
- [x] **Phase 1: Skeleton, data model, demo data.** FastAPI app, SQLModel tables, FTS5, demo company data and manuals, importer core used for seeding, "Log in as" picker, home page with counts.
- [ ] **Phase 2: Import and catalog.** Import page with preview and errors; sites, assets, products, known issues pages.
- [ ] **Phase 3: Intake and brief.** Intake form (dictation, photo, service mode), retrieval, brief generation (mock, then live), brief view with costs, progress steps, repeat-failure banner, unknown-model handling.
- [ ] **Phase 4: Review, technician, close.** Self-fix approval flow, assignment, mobile technician view, questions checklist, Refine, chat, close-ticket form.
- [ ] **Phase 5: Adaptability.** Fix variants with Haiku matching, trends, asset pages, history page, dispatches-avoided counter, CSV export.
- [ ] **Phase 6: Deploy and polish.** Render deploy, live-call fallback, demo rehearsal.
- [ ] Stretch: second demo company (laptop repair shop); cross-model insights.

## What works now

- `uvicorn app.main:app --reload` starts the app. On first start it creates `data/techmind.db` and loads the demo company:
  - 8 stores, 22 machines, 4 models, 16 parts
  - 24 known issues, 25 fix variants
  - 78 manual sections (indexed for search), 120 past tickets (indexed for search)
- "Log in as" picker (Manager, Tech: Ana, Tech: Luis) with a cookie; pages redirect to it when nobody is logged in.
- The home page shows the company's counts and profile in its own words ("Stores", "Machines", "Fixed by store staff").
- The importer validates every file and reports errors with row numbers. It is used for seeding now and gets its own upload page in Phase 2.
- The demo history generator plus checks for every planned pattern (`pytest` runs them).
- 15 tests pass.

## Next

- Phase 2: the Import page (upload, preview with row counts and errors, load) and the catalog pages.

## Known issues

- The demo patterns (rising/fading, repeat failure) are computed relative to 2026-10-24. If the demo runs much later, set `AS_OF_DATE=2026-10-24` in `.env`.
- Tailwind is loaded from its CDN "play" build, which logs a "not for production" console warning. This is expected (the spec asks for no build step).
