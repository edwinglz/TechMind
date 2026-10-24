\# Project: TechMind: AI diagnostic prep for equipment service technicians

> **Amendments agreed with the product owner (2026-10-24).** These override the text below; details are in docs/DECISIONS.md.
> - The demo company runs a full range of quick-service equipment, not just fountain machines: beverage dispensers, fryers, griddles, ice machines, walk-in coolers, and rooftop HVAC. The fountain dispenser is the subject of the demo report only.
> - Historical tickets have no photos.



\## Context

Hackathon project. Hard limits:

\- About 10 hours of build time, but take as least as possible.

\- The team works in Python.

\- The demo is a 3-minute live pitch.



Priorities: a reliable, polished end-to-end demo beats breadth. When in doubt, choose the simpler implementation. API budget is about $5, so be frugal with model calls (see "Cost control").



\## The problem

Companies that maintain equipment or products lose time and money every time something breaks:

\- Reports arrive vague ("it's not working", "it makes a weird noise").

\- Technicians show up or start work without knowing what's wrong, then look up manuals and past fixes while the clock runs.

\- Many reports are simple problems that the person reporting could fix themselves with guidance, which would save a technician trip entirely.



Our app turns each problem report into a diagnostic brief before anyone is dispatched:

\- likely causes with step-by-step fixes

\- cost estimates

\- the questions to ask to narrow down the cause

\- safe fixes the reporter can try first



It also keeps the company's knowledge base current. Every resolved ticket updates which issues are most common and which fixes work best.



\## General-purpose design (IMPORTANT)

This is a general-purpose platform for any company that services equipment or products: restaurant equipment, game consoles, laptops, HVAC, vehicles, and so on. The demo uses a fictional fast-food chain's fountain drink machines, but that is \*\*only demo data\*\*.



Rules:

\- \*\*No domain knowledge in code or in the base AI prompt.\*\* Everything domain-specific comes from the company's imported data:

&#x20; - manuals, known issues, parts, and history

&#x20; - its \*\*domain profile\*\* (see "Company import")

\- \*\*Generic names everywhere\*\* in code, database tables, and AI schema fields: `sites`, `assets`, `reporter`, `reporter\_self\_fix`, `questions\_for\_reporter`.

\- The UI displays the company's own terms from its profile: "store" instead of "site", "machine" instead of "asset", "store staff" instead of "reporter".

\- The import format must work for any industry.



\## Users

\- \*\*Service manager\*\* (desktop). Problem reports come in through the company's existing support channel (phone, email, a support line). The manager enters each report into our app:

&#x20; - the site and asset (the model is optional, but preferred)

&#x20; - the issue description, typed or dictated

&#x20; - a photo (preferred)



&#x20; The manager reviews the AI brief, approves or rejects any reporter self-fix, dispatches a technician, and chats with technicians.

\- \*\*Technician\*\* (phone, so the views must be mobile-first). Sees assigned tickets, the brief, and the questions to ask the reporter. Chats with the manager about a ticket. Closes the ticket with what was actually wrong and what fixed it.

\- \*\*Reporter\*\*: the person with the broken item. In the demo, store staff; in other industries, a customer. Reporters never use the app.



\## Company import (CSV + JSON)

A company sets itself up by uploading its data on an Import page. The page validates the files, shows a preview with row counts and errors, then loads them.

\- `sites.csv`: site\_id, name, address, region

\- `products.csv`: model\_id, manufacturer, model\_name, category, manual\_file

\- `assets.csv`: asset\_id, model\_id, site\_id, serial, install\_date, last\_service\_date

\- `parts.csv`: part\_id, name, compatible\_models (semicolon-separated), unit\_price, in\_stock

\- `known\_issues.csv`: issue\_id, model\_id, title, symptoms, root\_cause, fix\_steps (pipe-separated), part\_ids, avg\_minutes, reporter\_fixable (y/n)

\- `ticket\_history.csv`: ticket\_id, date, site\_id, asset\_id, model\_id, reported\_description, issue\_id, fix\_steps\_used, part\_ids, minutes, resolved (y/n), resolved\_by\_reporter (y/n)

\- `settings.csv`: labor\_rate\_per\_hour, trip\_fee, currency

\- `profile.json`, the domain profile:

&#x20; ```json

&#x20; {

&#x20;   "industry": "fast-food beverage equipment",

&#x20;   "labels": {"reporter": "store staff", "site": "store", "asset": "machine"},

&#x20;   "self\_fix\_allowed": \["tasks a non-technician may safely do"],

&#x20;   "self\_fix\_forbidden": \["tasks they must never attempt"],

&#x20;   "safety\_topics": \["hazards to always warn about in this industry"]

&#x20; }

&#x20; ```

\- `manuals.zip`: Markdown manuals referenced by manual\_file.



The profile is stored per company and injected into the AI prompt. The labels are used throughout the UI.



\## Demo dataset (fountain machines; data only)

Generate realistic demo data in `/demo\_data/` using exactly the import format above. Use a fictional fast-food chain with 6–8 stores. Machines come from fictional manufacturers, so we don't misdescribe real products.



\### Products and assets

4–5 fountain equipment models, for example:

\- a countertop ice/beverage dispenser

\- a drop-in dispenser

\- a self-serve touchscreen dispenser

\- a remote carbonator unit



Install 1–3 units at each store.



\### Manuals

Fake but realistic service manuals, written as Markdown with these sections:

\- system overview (water supply, CO2 and regulator, carbonator pump, bag-in-box syrup pumps, cold plate/ice bin, valves and nozzles)

\- installation and pressures

\- brix (syrup-to-water ratio) calibration

\- daily and weekly cleaning

\- troubleshooting tables (no carbonation, watery or syrupy drinks, no flow on one valve or all valves, foaming, warm drinks, leaks, no ice)

\- error codes for the touchscreen model

\- safety



\### Domain profile (`profile.json`)

\- \*\*self\_fix\_allowed:\*\*

&#x20; - replacing an empty bag-in-box

&#x20; - checking that the CO2 tank valve is open and the gauge isn't in the red

&#x20; - checking the ice level

&#x20; - cleaning or soaking nozzles

&#x20; - checking the power and breaker

\- \*\*self\_fix\_forbidden:\*\*

&#x20; - adjusting the regulator

&#x20; - opening panels

&#x20; - electrical work

\- \*\*safety\_topics:\*\*

&#x20; - CO2 asphyxiation in enclosed spaces (ventilate and leave if a leak is suspected)

&#x20; - high-pressure gas

&#x20; - water near electrical parts

&#x20; - sanitation (mold in nozzles, dirty ice bin)



\### Records

\- Parts price list, labor rate, and trip fee.

\- Known issues, plus about 120 historical resolved tickets spread over May–October. Include these deliberate patterns:

&#x20; - \*\*fading:\*\* warm drinks and ice problems that peaked in summer and are now declining

&#x20; - \*\*rising:\*\* valve and nozzle leaks spiking in the last month, from a bad batch of parts

&#x20; - \*\*repeat failures:\*\* one machine with 3 or more tickets in 60 days

&#x20; - \*\*better fix:\*\* one issue where a newer fix succeeds more often than the original recommended fix

&#x20; - \*\*self-fixes:\*\* about 30% of tickets were resolved by store staff with phone guidance

\- Placeholder images for historical tickets.



\## Golden path (build this end to end first)

1\. \*\*Intake (manager, desktop).\*\*

&#x20;  - Pick the site. An asset dropdown then lists that site's assets and fills in the model automatically. The dropdown includes an "Unknown" option.

&#x20;  - Issue description: a textarea with a 🎤 dictation button using the browser Web Speech API. Typing always works as a fallback.

&#x20;  - Photo upload.

&#x20;  - Service mode: remote (guide the reporter by phone) or on-site.

2\. \*\*Brief generation.\*\*

&#x20;  - Retrieve relevant manual sections for the model, using keyword search over manual chunks with SQLite FTS5.

&#x20;  - Retrieve that model's known issues, ranked by recent frequency, and the most similar resolved past tickets.

&#x20;  - Retrieve this asset's recent ticket history.

&#x20;  - Make one Claude call with vision, passing the company's domain profile, then validate the JSON output (schema below) and store it.

&#x20;  - Show progress steps while it runs: "Reading manual… Checking past tickets… Analyzing photo…"

&#x20;  - If the asset has had 3 or more tickets in 60 days, show a "Repeat failure" banner.

&#x20;  - If the model is unknown, the brief covers likely causes across the product category and lists "confirm the model" as the first question.

3\. \*\*Manager review.\*\* The manager sees the brief.

&#x20;  - If it includes a reporter self-fix, the manager can approve it. The ticket moves to "Awaiting reporter self-fix", and the manager contacts the reporter outside the app. The manager then records the outcome:

&#x20;    - resolved: the ticket closes as resolved by the reporter, and the dispatch avoided is logged

&#x20;    - not resolved: the ticket continues to dispatch

&#x20;  - Otherwise the manager assigns a technician.

4\. \*\*Technician (phone).\*\* The ticket page shows:

&#x20;  - the report, photo, site address, and asset history

&#x20;  - probable causes as expandable cards, each with a likelihood badge, how to confirm it, step-by-step fix, parts, and cost estimate

&#x20;  - the questions for the reporter, as a checklist with answer fields

&#x20;  - a "Refine diagnosis" button that regenerates the brief using the answers

&#x20;  - a chat thread with the manager for this ticket (HTMX polling every few seconds; no websockets)

5\. \*\*Close ticket (technician).\*\*

&#x20;  - Pick the actual issue from a dropdown of that model's known issues, pre-selected to the AI's top cause, or choose "New issue" and describe it.

&#x20;  - Answer "Did you use the recommended fix?" If not, describe the fix used.

&#x20;  - Record parts used, minutes spent, and whether the problem was resolved.

6\. \*\*Knowledge update\*\* runs automatically on close (see "Adaptability").



\## Diagnostic brief schema (validate with Pydantic; retry once on failure)

```json

{

&#x20; "summary": "string",

&#x20; "symptom\_interpretation": "what the vague report most likely means",

&#x20; "image\_findings": \["string"],

&#x20; "probable\_causes": \[{

&#x20;   "issue\_id": "known issue id, or null if not a known issue",

&#x20;   "cause": "string",

&#x20;   "likelihood": "high | medium | low",

&#x20;   "evidence": "why: from report, photo, manual, or history",

&#x20;   "sources": \[{"type": "manual | past\_ticket | known\_issue | asset\_history", "ref": "string"}],

&#x20;   "confirm\_steps": \["string"],

&#x20;   "fix\_steps": \["string"],

&#x20;   "part\_ids": \["ONLY ids from the provided parts list"],

&#x20;   "estimated\_minutes": 0

&#x20; }],

&#x20; "reporter\_self\_fix": {

&#x20;   "applicable": true,

&#x20;   "steps": \["string"],

&#x20;   "risk\_note": "string"

&#x20; },

&#x20; "questions\_for\_reporter": \[{

&#x20;   "question": "string",

&#x20;   "why": "string",

&#x20;   "rules\_in\_or\_out": \["cause names"]

&#x20; }],

&#x20; "safety\_warnings": \["string"],

&#x20; "missing\_info": \["string"]

}

```



\### Rules for the diagnosis prompt

Keep this prompt in `app/ai/prompts.py` so we can tune it separately. These rules are generic; the domain specifics come from the injected profile.

\- Ground causes in the provided manual excerpts, known issues, past tickets, and asset history, and cite them.

\- Label general-knowledge reasoning as such.

\- Never invent part ids or manual sections.

\- Put the questions that eliminate the most causes first.

\- Write questions so a non-technical reporter can answer them over the phone in seconds.

\- Reporter self-fix steps may only come from the profile's `self\_fix\_allowed`, and must never include anything in `self\_fix\_forbidden`.

\- Always include safety warnings for any of the profile's `safety\_topics` that are relevant to a cause.

\- When a known issue has a recommended fix, use that fix.



\### Cost estimates

The AI only selects part\_ids and estimated\_minutes. Python computes the cost for each cause:

`cost = sum(part prices) + minutes / 60 × labor\_rate + trip\_fee (if on-site)`



The page shows the cost per cause, plus "$X saved if the self-fix works".



\## Adaptability (core to the pitch; no model training)

Everything happens in plain, explainable code over the database.



\### Every event is logged

Write each one to an append-only `ticket\_events` table:

\- created

\- brief generated or refined

\- self-fix approved

\- self-fix outcome

\- assigned

\- chat message

\- question answered

\- closed



\### Fix variants

Each known issue can have several fix variants. For each variant, track attempts, successes, and average minutes.

\- The \*\*recommended fix\*\* is the variant with the highest success rate among variants with at least 3 attempts. Ties go to the lower average time.

\- When a technician reports a different fix that works, it becomes a new variant.

\- Use `claude-haiku-5-5` to decide whether a described fix matches an existing variant or is new.

\- Once a new variant outperforms the old one, it becomes the recommended fix automatically, and briefs start using it.



\### Common issues

\- Rank common issues per model by recency-weighted frequency: occurrences in the last 90 days, weighted toward recent ones.

\- Mark an issue \*\*rising\*\* if its last-30-days count exceeds the prior 30 days. Mark it \*\*fading\*\* if the reverse is true.

\- These rankings feed straight into retrieval, so briefs shift as conditions change.



\### Asset history

\- Every asset has a page showing its tickets.

\- Repeat failures are flagged on that page and in the brief.



\### History page

\- Filterable ticket and work history.

\- A known-issues table showing frequency, trend, and the current recommended fix with its success rate.

\- A counter of dispatches avoided and the estimated savings.

\- "Export CSV", which uses the same format as the import, so the company keeps its updated data.

\- This page is for the company's own use. No big analytics dashboard is needed.



\## Tech stack

\- Python 3.11+ and FastAPI.

\- Jinja2 templates, HTMX, and Tailwind via CDN. No JavaScript framework and no build step.

\- SQLite via SQLModel. Use FTS5 for manual search. Every table has `company\_id`.

\- The `anthropic` Python SDK:

&#x20; - `claude-sonnet-5-5` for briefs, with images resized with Pillow to at most 1200px before sending

&#x20; - `claude-haiku-5-5` for small matching tasks

\- `ANTHROPIC\_API\_KEY` lives in `.env` and is never committed.

\- Auth: none. A simple "Log in as" picker (Manager, Tech: Ana, Tech: Luis) sets a cookie.

\- Deployment:

&#x20; - Make it deployable to Render or Railway with a start command.

&#x20; - Seed the demo company on startup if the database is empty.

&#x20; - Running locally is the fallback.



\## Cost control

\- `AI\_MODE=mock|live` in `.env`. Mock mode returns realistic fixture briefs from `/fixtures` instead of calling the API. Use mock mode for all development; switch to live only to test prompts and for the demo.

\- Never regenerate a brief on page load. Briefs are generated on submit or on "Refine" only, then stored.

\- Log token usage for each call to the console.

\- If a live call fails during the demo, fall back to the stored brief for that ticket and show a small notice.



\## Out of scope

Real authentication, reporter access, email/SMS, payments, Spanish/i18n (later), native apps, IoT sensor integration (a good "future work" slide).



\## Stretch goals (only after the golden path works)

1\. A second tiny demo company loaded through the same import, to prove generality during Q\&A: a laptop repair shop with 2 models, a short manual, a few known issues, and its own profile.

2\. Insights across a product family ("this failure appears in 3 related models").



\## Schedule (about 10 hours; tell me if we're slipping)

1\. \*\*Hour 0–1:\*\* project setup, data model, demo-data files, and manuals.

2\. \*\*Hour 1–2.5:\*\* import with preview, plus sites, assets, products, and known issues pages.

3\. \*\*Hour 2.5–5:\*\* intake form with dictation and photo, retrieval, brief generation (mock, then live), and brief view.

4\. \*\*Hour 5–7:\*\*

&#x20;  - mobile technician view, questions checklist, Refine diagnosis

&#x20;  - manager chat

&#x20;  - self-fix approval flow

&#x20;  - close-ticket form

5\. \*\*Hour 7–8:\*\* adaptability logic (fix variants, trends, asset history), history page, CSV export.

6\. \*\*Hour 8–9:\*\* deploy, polish, and the fallback brief.

7\. \*\*Hour 9–10:\*\* buffer and demo rehearsal.



\## Demo script (3 minutes; build the seed data to support it)

1\. The manager gets a call from Store #4. They dictate "Coke and Sprite are coming out flat, kind of watery", pick the store's machine, and upload a photo.

2\. The brief appears. Causes include a CO2 tank that is empty or has its valve closed, a carbonator pump failure, and the cold plate running warm. Each cause shows its cost, and the brief includes questions for store staff and a CO2 safety warning.

&#x20;  - The staff self-fix is "check that the CO2 tank valve is open and the gauge isn't in the red". The card shows the trip fee saved if it works.

&#x20;  - The manager approves the self-fix and calls the store. The tank is full, so they mark it not resolved.

&#x20;  - The manager dispatches Ana.

3\. Switch to the phone view. Ana sees the store address, a repeat-failure flag on this machine, and the questions. She checks one off, taps Refine, and the carbonator pump moves to the top. She messages the manager.

4\. Ana closes the ticket with a fix that differs from the recommended one.

5\. Show the History page:

&#x20;  - valve leaks marked rising and summer ice issues marked fading

&#x20;  - the recommended fix updated, because the seed data was set up for this ticket to tip it over

&#x20;  - the dispatches-avoided counter

6\. Closing line: "Any company loads its own manuals, history, and profile, and the same system adapts to them."



\## How to work

1\. Read this spec. Reply with a phased plan, the data model, and any ambiguities. Don't write code until I confirm.

2\. Build the golden path end to end in mock mode before polishing anything.

3\. After each phase, run the app, fix errors, tell me exactly how to test it, and commit.

4\. Maintain a README with setup steps, the env vars, how to switch mock/live, and the demo script.

