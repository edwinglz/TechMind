# TechMind

TechMind turns vague equipment problem reports ("it's not working", "the drinks are flat") into a diagnostic brief before anyone is dispatched: likely causes with step-by-step fixes, cost estimates, questions to ask the reporter, and safe fixes the reporter can try first. Every closed ticket updates the company's knowledge base, so the most common issues and the best-performing fixes stay current. It works for any company that services equipment; the demo uses a fictional fast-food chain's fountain drink machines.

> Status: early build. See [docs/PROGRESS.md](docs/PROGRESS.md) for what works today.

## Setup

Requires Python 3.11+.

```powershell
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env          # macOS/Linux: cp .env.example .env
```

## Run

```powershell
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000. On first start the demo company is loaded from `demo_data/` into a fresh SQLite database (`data/techmind.db`). Delete that file to reset everything.

## Environment variables

| Variable | Purpose |
|---|---|
| `AI_MODE` | `mock` (default) returns canned briefs from `fixtures/`; `live` calls Claude |
| `ANTHROPIC_API_KEY` | Needed only in live mode |
| `DATABASE_URL` | SQLite location, default `sqlite:///./data/techmind.db` |
| `UPLOAD_DIR` | Where photos and import files are stored, default `uploads` |
| `AS_OF_DATE` | Optional `YYYY-MM-DD` "today" for trend math; blank = real date |

## Mock vs live mode

Develop in **mock** mode: briefs come from JSON fixtures in `fixtures/briefs/`, so no API budget is spent. Switch to **live** by setting `AI_MODE=live` and `ANTHROPIC_API_KEY` in `.env`, then restart. Live mode uses `claude-sonnet-5-5` for briefs and `claude-haiku-5-5` for fix matching, and logs token usage to the console. If a live call fails, the app falls back to the ticket's stored brief and shows a notice.

## Demo script (3 minutes)

1. **Intake.** The manager gets a call from Store #4, dictates "Coke and Sprite are coming out flat, kind of watery", picks the store's machine, and uploads a photo.
2. **Brief.** Causes include an empty or closed CO2 tank, a carbonator pump failure, and a warm cold plate, each with a cost, plus questions for store staff and a CO2 safety warning.
   - The staff self-fix is "check that the CO2 tank valve is open and the gauge isn't in the red", showing the savings if it works.
   - The manager approves it, calls the store, the tank is full, and marks it not resolved.
   - The manager dispatches Ana.
3. **Technician (phone).** Ana sees the store address, a repeat-failure flag on this machine, and the questions. She checks one off, taps **Refine**, and the carbonator pump moves to the top. She messages the manager.
4. **Close.** Ana closes the ticket with a fix that differs from the recommended one.
5. **History page.** Valve leaks are marked rising, summer ice issues fading, the recommended fix has updated because of Ana's ticket, and the dispatches-avoided counter shows savings.
6. **Closing line:** "Any company loads its own manuals, history, and profile, and the same system adapts to them."

## Docs

- [docs/SPEC.md](docs/SPEC.md): product spec (source of truth)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): how the pieces fit together
- [docs/DECISIONS.md](docs/DECISIONS.md): why things are the way they are
- [docs/PROGRESS.md](docs/PROGRESS.md): phase checklist and known issues
