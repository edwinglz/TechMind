# Progress

## Phases

- [x] **Phase 0: Repo setup.** Git, `.gitignore`, `.env.example`, private GitHub repo, README and docs.
- [x] **Phase 1: Skeleton, data model, demo data.** FastAPI app, SQLModel tables, FTS5, demo company data and manuals, importer core used for seeding, public product page, username/password login, company dashboard.
- [ ] **Phase 2: Import and catalog.** Import page with preview and errors; sites, assets, products, known issues pages.
- [x] **Phase 3: Intake and brief.** Intake form (dictation, photo, service mode), retrieval, brief generation (mock from company data; live via Claude, untested without a key), brief view with costs, progress steps, repeat-failure banner, unknown-model handling.
- [x] **Phase 4: Review, technician, close.** Self-fix approval flow, assignment, mobile technician view, questions checklist, Refine, chat, close-ticket form.
- [x] **Phase 5: Adaptability.** Fix variants with Haiku matching, trends, asset pages, history page, dispatches-avoided counter, CSV export.
- [ ] **Phase 6: Deploy and polish.** Render deploy, live-call fallback, demo rehearsal.
- [ ] Stretch: second demo company (laptop repair shop); cross-model insights.

## What works now

- Log in as `manager`, `ana` or `luis` (password from `DEMO_PASSWORD`). The demo company is seeded on first start.
- **Board** (managers): reports grouped into Needs a decision, Store staff trying a fix, Technician on it, Recently closed; plus rising issues, fixes that changed, and trips avoided.
- **New report**: store, then equipment at that store with its recent tickets; dictation (Chrome/Edge); photo; phone-first or on-site.
- **Brief**: "Preparing" steps, then summary, safety, repeat-failure warning, ranked causes (evidence, sources, confirm steps, recommended fix, parts with stock, cost), questions for the reporter, safe self-fix with savings. Every version is stored.
- **Decisions**: approve a self-fix and record the outcome (a failure re-ranks the brief; success closes the ticket with no trip), dispatch or reassign, per-ticket chat (refreshes every 4 seconds), event log.
- **Technician phone view**: My jobs, the brief, Yes/No/Not sure answers, Refine diagnosis, bottom bar with Close job.
- **Close job**: what was wrong (brief's top cause preselected, or a new issue), which fix (variants with success rates, or describe a new one), parts, minutes, fixed or not. This updates frequency, trends and the recommended fix immediately.
- **Insights**, **History**, unit pages, CSV export of ticket history in the import format.
- 25 tests pass, including the full demo flow.

## Next

- Phase 2: the Import page (upload, preview with row counts and errors, load) and catalog pages.
- Keep tuning `app/ai/prompts.py` with live runs.
- Phase 6: deploy and rehearse.

## Known issues

- The demo patterns (rising/fading, repeat failure) are computed relative to 2026-10-24. If the demo runs much later, set `AS_OF_DATE=2026-10-24` in `.env`.
- Live mode works (first test on 2026-10-24). A brief takes about 20 to 40 seconds; the page shows a progress bar and a busy button meanwhile.
- Mock safety warnings match on words, so they occasionally include a loosely related hazard; live mode judges relevance properly.
