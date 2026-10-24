"""The prompt for the live diagnostic brief.

Kept in its own file so we can tune it without touching the rest of the code.

The base prompt is industry-neutral on purpose. Everything specific to a
company's equipment (what store staff may try, which hazards matter, the
manuals, the history) is injected from its data, so the same prompt works for a
burger chain, a laptop repair shop or an HVAC contractor.
"""

import json

from app.services.retrieval import Context

SYSTEM = """You are the diagnostic assistant inside TechMind, a tool that prepares equipment service technicians before a job.

A {reporter} reported a problem with a piece of {industry} equipment. Using ONLY the company data provided (manual excerpts, known issues with their history, similar past tickets, this unit's own history, the parts list) plus the report, any photo and any answers already collected, write a diagnostic brief.

Rules:
- Rank 2 to 4 probable causes. Ground each one in the provided data and cite it in `sources` (manual section titles, known issue ids, past ticket ids, asset history ticket ids). If you rely on general knowledge, say so in `evidence`.
- When a cause is one of the known issues, set `issue_id` to its id and use its CURRENT RECOMMENDED FIX as `fix_steps`.
- `part_ids` must only contain ids from the provided parts list. Never invent part numbers, manual sections or ticket ids.
- `estimated_minutes` should follow the known issue's typical time when there is one.
- Questions for the {reporter}: 3 to 5, short, answerable over the phone in seconds by a non-technical person. Put the question that separates the most likely causes first. `rules_in_or_out` lists the cause names each answer helps confirm or eliminate.
- Self-fix: only steps from this allowed list, adapted to the situation: {allowed}. NEVER include anything from this forbidden list: {forbidden}. Set `applicable` to false if no allowed step fits. `targets` lists the known issue ids the self-fix could resolve.
- Safety: include a warning for every one of these company safety topics that is relevant to a likely cause: {safety}.
- If the photo shows something relevant, describe it in `image_findings`; otherwise leave it empty.
- If answers or a failed self-fix rule causes out, lower them or drop them and say why in `evidence`.
- `missing_info`: what would help that we don't have yet.

Reply with ONE JSON object and nothing else, matching this shape:
{{
  "summary": "two sentences a manager can read in five seconds",
  "symptom_interpretation": "what the vague report most likely means in technical terms",
  "image_findings": ["..."],
  "probable_causes": [{{"issue_id": "KI-.. or null", "cause": "...", "likelihood": "high|medium|low", "evidence": "...",
      "sources": [{{"type": "manual|past_ticket|known_issue|asset_history", "ref": "..."}}],
      "confirm_steps": ["..."], "fix_steps": ["..."], "part_ids": ["..."], "estimated_minutes": 30}}],
  "reporter_self_fix": {{"applicable": true, "steps": ["..."], "risk_note": "...", "targets": ["KI-.."]}},
  "questions_for_reporter": [{{"question": "...", "why": "...", "rules_in_or_out": ["cause name"]}}],
  "safety_warnings": ["..."],
  "missing_info": ["..."]
}}"""


def system_prompt(ctx: Context, labels: dict) -> str:
    profile = ctx.company.profile
    return SYSTEM.format(
        reporter=labels["reporter"],
        industry=profile.get("industry", "service"),
        allowed=json.dumps(profile.get("self_fix_allowed", [])),
        forbidden=json.dumps(profile.get("self_fix_forbidden", [])),
        safety=json.dumps(profile.get("safety_topics", [])),
    )


def _steps(steps: list[str]) -> str:
    return " | ".join(steps)


def user_prompt(ctx: Context, labels: dict, answers: dict, self_fix_note: str | None) -> str:
    t = ctx.ticket
    lines = [f"REPORT from the {labels['reporter']} at {ctx.site.name}: \"{t.description}\""]
    lines.append(f"Service mode: {'remote (guide the ' + labels['reporter'] + ' by phone)' if t.service_mode == 'remote' else 'on-site visit'}")
    if ctx.asset and ctx.product:
        lines.append(f"Equipment: {ctx.product.manufacturer} {ctx.product.model_name} (model {ctx.product.ref}, "
                     f"unit {ctx.asset.ref}, serial {ctx.asset.serial}, installed {ctx.asset.install_date})")
    else:
        lines.append("Equipment: UNKNOWN. Candidate models installed at this site: "
                     + ", ".join(f"{p.ref} {p.model_name}" for p in ctx.products)
                     + ". Make confirming the model the first question.")
    if ctx.repeat_failure:
        lines.append(f"REPEAT FAILURE: this unit has {ctx.repeat_count} tickets in 60 days including this one.")

    if answers:
        lines.append("\nANSWERS COLLECTED SO FAR:")
        for q, a in answers.items():
            note = f" ({a.get('note')})" if a.get("note") else ""
            lines.append(f"- {q} -> {a.get('answer')}{note}")
    if self_fix_note:
        lines.append(f"\nSELF-FIX ALREADY TRIED: {self_fix_note}")

    lines.append("\nKNOWN ISSUES (with history from the last 90 days and the current recommended fix):")
    for m in ctx.issues[:10]:
        s, i = m.stat, m.stat.issue
        rec = s.recommended
        rate = f"{rec.successes}/{rec.attempts} successful" if rec and rec.attempts else "no attempts logged"
        lines.append(f"- {i.ref} [{m.product.ref}] {i.title}. Symptoms: {i.symptoms}. Root cause: {i.root_cause}. "
                     f"Seen {s.last90}x in 90 days, trend: {s.trend or 'steady'}. "
                     f"{labels['reporter'].capitalize()} can fix: {'yes' if i.reporter_fixable else 'no'}. "
                     f"Typical {i.avg_minutes} min. Parts: {', '.join(i.part_refs) or 'none'}. "
                     f"RECOMMENDED FIX ({rate}): {_steps(rec.variant.steps) if rec else 'n/a'}")

    lines.append("\nMANUAL EXCERPTS:")
    for chunk in ctx.manual:
        lines.append(f"## {chunk.section_title}\n{chunk.content[:1200]}")

    lines.append("\nSIMILAR PAST TICKETS:")
    for past, issue in ctx.similar:
        lines.append(f"- {past.ref} ({past.created_at:%Y-%m-%d}): \"{past.description}\" -> "
                     f"{issue.ref + ' ' + issue.title if issue else 'unclassified'}, resolved: {past.resolved}")

    if ctx.asset_history:
        lines.append("\nTHIS UNIT'S HISTORY (last 180 days):")
        for past, issue in ctx.asset_history:
            lines.append(f"- {past.ref} ({past.created_at:%Y-%m-%d}): \"{past.description}\" -> "
                         f"{issue.ref + ' ' + issue.title if issue else 'open'}")

    lines.append("\nPARTS LIST (id, name, price):")
    for part in ctx.parts.values():
        lines.append(f"- {part.ref}: {part.name}, {part.unit_price:.2f}")
    return "\n".join(lines)
