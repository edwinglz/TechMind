# Progress

## Phases

- [x] **Phase 0: Repo setup.** Git, `.gitignore`, `.env.example`, private GitHub repo, README and docs.
- [x] **Phase 1: Skeleton, data model, demo data.** FastAPI app, SQLModel tables, FTS5, demo company data and manuals, importer core used for seeding, public product page, username/password login, company dashboard.
- [ ] **Phase 2: Import and catalog.** Import page with preview and errors; sites, assets, products, known issues pages.
- [ ] **Phase 3: Intake and brief.** Intake form (dictation, photo, service mode), retrieval, brief generation (mock, then live), brief view with costs, progress steps, repeat-failure banner, unknown-model handling.
- [ ] **Phase 4: Review, technician, close.** Self-fix approval flow, assignment, mobile technician view, questions checklist, Refine, chat, close-ticket form.
- [ ] **Phase 5: Adaptability.** Fix variants with Haiku matching, trends, asset pages, history page, dispatches-avoided counter, CSV export.
- [ ] **Phase 6: Deploy and polish.** Render deploy, live-call fallback, demo rehearsal.
- [ ] Stretch: second demo company (laptop repair shop); cross-model insights.

## What works now

- `uvicorn app.main:app --reload` starts the app. On first start it creates `data/techmind.db` and loads the demo company:
  - 8 stores, 58 units of equipment, 7 models (beverage, fryer, griddle, ice machine, walk-in, HVAC), 34 parts
  - 31 known issues, 32 fix variants
  - manual sections and 121 past tickets, both indexed for search
- `/` is a public TechMind product page (how it works, features, any-industry, setup) with a **Log in** button. No company data is shown there.
- Username/password login. Demo accounts are `manager`, `ana`, and `luis`, with the password from `DEMO_PASSWORD`. The cookie is signed so it can't be forged; wrong passwords get a generic error. Log out returns to the product page.
- `/app` dashboard shows the company's counts in its own words ("Stores", "Equipment", "Fixed by store staff"), equipment by category, and the company profile (collapsed).
- The importer validates every file and reports errors with row numbers. It is used for seeding now and gets its own upload page in Phase 2.
- The demo history generator plus checks for every planned pattern (`pytest` runs them).
- 20 tests pass.

## Next

- Phase 2: the Import page (upload, preview with row counts and errors, load) and the catalog pages.

## Known issues

- The demo patterns (rising/fading, repeat failure) are computed relative to 2026-10-24. If the demo runs much later, set `AS_OF_DATE=2026-10-24` in `.env`.
- Tailwind is loaded from its CDN "play" build, which logs a "not for production" console warning. This is expected (the spec asks for no build step).
