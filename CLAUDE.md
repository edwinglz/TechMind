\# Project rules



The full product spec is in docs/SPEC.md. It is the source of truth. Read it before planning any phase.



\## Git and GitHub

\- Use the `gh` CLI for anything GitHub-related. The user is already logged in.

\- Commit after every working step. Never commit broken code.

\- Commit message format: `type: short summary` (feat, fix, docs, data, chore), plus a body explaining what changed and why.

\- Push to GitHub after every commit.

\- Never commit secrets or generated files. `.gitignore` must cover:

&#x20; - `.env`

&#x20; - the SQLite database

&#x20; - `uploads/`

&#x20; - `\_\_pycache\_\_/`

&#x20; - `.venv/`

\- Commit `.env.example` with placeholder values instead of `.env`.



\## Documentation (keep it current; a new teammate should understand the project in 10 minutes)

\- `README.md`: what the app does (2–3 sentences), setup, how to run it, mock/live mode, and the demo script.

\- `docs/ARCHITECTURE.md`: a plain-language explanation of how the pieces fit together. Include:

&#x20; - a Mermaid diagram of the ticket flow

&#x20; - the data model

&#x20; - how the adaptability logic works

\- `docs/DECISIONS.md`: one short entry per significant choice, covering what was decided, what the alternatives were, and why.

\- `docs/PROGRESS.md`: a checklist of the phases from the spec, covering what works now, what's next, and any known issues. Update it at the end of every phase.

\- Every Python module starts with a docstring explaining its purpose.

\- Comment the \*why\* of non-obvious logic, especially the retrieval, fix-variant, and trend code. Write for a reader who is not an expert.

\- Update the docs in the same commit as the code they describe.



\## Working style

\- Develop in `AI\_MODE=mock`. Only use live mode when I ask.

\- After each phase:

&#x20; - run the app and fix errors

&#x20; - tell me exactly how to test the phase in the browser

&#x20; - update `docs/PROGRESS.md`

&#x20; - commit and push

