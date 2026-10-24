"""Generate demo_data/ticket_history.csv for the fictional fountain-machine company.

The history is not random noise: it is planned so the demo can show specific
patterns. This script builds ~120 resolved tickets from May to October 2026
using a fixed random seed (so every run produces the same file), then checks
that each planned pattern actually holds before writing the CSV:

- fading:  warm-drink and ice issues peaked in summer and are now declining
- rising:  valve/nozzle leaks spike in the last 30 days (a bad batch of seals)
- repeat:  machine A-0401 (Store #4) has 3 tickets in the last 60 days, no other machine does
- better fix: carbonator pump failure (KI-CI-03) has a newer fix that has worked
  2 out of 2 times; the original fix worked 5 out of 8. The newer fix needs one
  more success to reach the 3-attempt minimum and become the recommended fix,
  which is exactly what the live demo ticket does.
- self-fixes: about 30% of tickets were resolved by store staff over the phone

Run:  python scripts/generate_demo_history.py
"""

import csv
import random
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

DEMO = Path(__file__).resolve().parent.parent / "demo_data"
TODAY = date(2026, 10, 24)  # the "as of" date the patterns are designed around

# Four periods. The last two are the two 30-day windows the trend rule compares
# (counting back from TODAY), so per-period counts control rising/fading directly.
PERIODS = [
    (date(2026, 5, 1), date(2026, 6, 30)),
    (date(2026, 7, 1), date(2026, 8, 24)),
    (date(2026, 8, 25), date(2026, 9, 23)),  # prior 30 days
    (date(2026, 9, 24), date(2026, 10, 22)),  # last 30 days
]
WINDOW_60_START = TODAY - timedelta(days=60)

# Tickets per issue per period.
PLAN = {
    "KI-CI-01": [2, 1, 0, 1],
    "KI-CI-02": [3, 2, 1, 1],
    "KI-CI-03": [4, 4, 1, 1],  # periods 1-2: original fix; periods 3-4: the newer fix
    "KI-CI-04": [3, 5, 2, 1],  # fading
    "KI-CI-05": [2, 4, 2, 0],  # fading
    "KI-CI-06": [1, 1, 0, 3],  # rising
    "KI-CI-07": [1, 1, 0, 0],
    "KI-CI-08": [2, 1, 0, 0],
    "KI-DI-01": [1, 1, 0, 0],
    "KI-DI-02": [2, 2, 1, 0],
    "KI-DI-03": [3, 4, 2, 0],  # fading
    "KI-DI-04": [0, 1, 0, 3],  # rising
    "KI-DI-05": [1, 1, 0, 0],
    "KI-DI-06": [2, 1, 0, 1],
    "KI-TS-01": [1, 1, 0, 1],
    "KI-TS-02": [2, 1, 0, 0],
    "KI-TS-03": [1, 1, 1, 0],
    "KI-TS-04": [0, 0, 1, 3],  # rising
    "KI-TS-05": [2, 3, 0, 1],
    "KI-TS-06": [1, 3, 2, 0],  # fading
    "KI-RC-01": [2, 1, 1, 0],
    "KI-RC-02": [2, 2, 1, 1],
    "KI-RC-03": [1, 1, 0, 0],
    "KI-RC-04": [2, 2, 1, 0],
}

# Tickets fixed to a specific machine and date. These give A-0401 its repeat-failure
# history; they count toward the PLAN numbers above.
PINNED = [
    (date(2026, 9, 2), "A-0401", "KI-CI-04"),
    (date(2026, 9, 30), "A-0401", "KI-CI-02"),
    (date(2026, 10, 9), "A-0401", "KI-CI-06"),
]
REPEAT_ASSET = "A-0401"

# The newer carbonator fix that technicians found works better than replacing the motor.
BETTER_FIX_ISSUE = "KI-CI-03"
BETTER_FIX_STEPS = (
    "Shut off water and CO2 to the carbonator|Clean the carbonator water inlet strainer"
    "|Replace the pump inlet check valve|Restore water then CO2 and test carbonation"
)
BETTER_FIX_PARTS = "P-CHKV;P-STRN"
BETTER_FIX_DATES = [date(2026, 9, 15), date(2026, 10, 6)]
ORIGINAL_FIX_FAILURES = 3  # of the 8 original-fix attempts, this many did not resolve it

# Tickets where no known issue matched.
UNMATCHED = [
    (date(2026, 5, 19), "DI-8", "Customers say the root beer tastes funny",
     "Sanitized syrup line and nozzle; no fault found", "", 30),
    (date(2026, 7, 22), "TS-500", "Touchscreen shows the wrong flavor names",
     "Reloaded flavor configuration from the service menu", "", 20),
]

# Vague, realistic phrasings of what the reporter said on the phone.
DESCRIPTIONS = {
    "CO2": ["All the sodas are flat", "Drinks have no fizz at all", "Everything tastes flat, even the Sprite"],
    "BIB": ["Coke is coming out clear", "Diet tastes like soda water", "One of the flavors is really watery"],
    "PUMP": ["Drinks are flat and kind of watery", "Machine keeps humming and the soda is flat", "No carbonation, motor sounds weird"],
    "WARM": ["Drinks are coming out warm", "Soda is not cold anymore", "Drinks are lukewarm and foamy"],
    "ICE": ["Ice won't come out", "No ice, machine makes a grinding noise", "Ice is stuck in one big block"],
    "LEAK": ["Machine is leaking on the counter", "Nozzle keeps dripping after pouring", "Puddle under the soda machine"],
    "BRIX": ["Sprite tastes too sweet", "Customers say the lemonade is weak", "Dr Pepper tastes off"],
    "NOZZLE": ["Soda sprays everywhere when pouring", "Weak stream on the Coke valve", "Nozzle looks slimy"],
    "POWER": ["Screen is completely black", "Self-serve machine is dead", "Nothing turns on"],
    "E21": ["Screen says E-21 and drinks are flat", "Error E-21 on the self-serve", "Flat drinks, some error code"],
    "E34": ["Error E-34, Fanta won't pour", "One flavor stopped working, clicking noise", "Screen says E-34"],
    "E12": ["Screen says Coke is sold out", "E-12 on the self-serve", "Lemonade button is greyed out"],
    "E40": ["Self-serve drinks are warm, error E-40", "Screen shows E-40", "Drinks warm, fan is really loud"],
    "WATER": ["Weak flow on all the sodas", "Drinks are watery and pouring slow", "All valves pour really slow"],
    "RELIEF": ["Water spraying from the carbonator in the back", "Hissing and dripping from the tank in the back room", "Carbonator is leaking"],
}
ISSUE_KIND = {
    "KI-CI-01": "CO2", "KI-DI-01": "CO2", "KI-RC-04": "CO2",
    "KI-CI-02": "BIB", "KI-DI-02": "BIB",
    "KI-CI-03": "PUMP", "KI-RC-01": "PUMP",
    "KI-CI-04": "WARM", "KI-DI-03": "WARM",
    "KI-CI-05": "ICE",
    "KI-CI-06": "LEAK", "KI-DI-04": "LEAK", "KI-TS-04": "LEAK", "KI-RC-03": "RELIEF",
    "KI-CI-07": "BRIX", "KI-DI-05": "BRIX",
    "KI-CI-08": "NOZZLE", "KI-DI-06": "NOZZLE",
    "KI-TS-01": "POWER", "KI-TS-02": "E21", "KI-TS-03": "E34", "KI-TS-05": "E12", "KI-TS-06": "E40",
    "KI-RC-02": "WATER",
}

# Roughly 1 in 7 reporter-fixable tickets still needed a technician (the store
# could not do it), which brings the self-fix share to about 30%.
TECH_NEEDED_EVERY = 7


def read_csv(name):
    with open(DEMO / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def random_date(rng, start, end):
    return start + timedelta(days=rng.randint(0, (end - start).days))


def generate():
    rng = random.Random(42)
    assets = read_csv("assets.csv")
    issues = {row["issue_id"]: row for row in read_csv("known_issues.csv")}
    assets_by_model = defaultdict(list)
    for a in assets:
        assets_by_model[a["model_id"]].append(a)
    site_of = {a["asset_id"]: a["site_id"] for a in assets}

    # Step 1: decide (date, issue, pinned asset or None) for every ticket.
    slots = []
    for issue_id, counts in PLAN.items():
        pinned = [(d, a) for d, a, i in PINNED if i == issue_id]
        for (start, end), count in zip(PERIODS, counts):
            in_period = [(d, a) for d, a in pinned if start <= d <= end]
            for d, a in in_period:
                slots.append({"date": d, "issue": issue_id, "asset": a, "variant": "original"})
            remaining = count - len(in_period)
            if issue_id == BETTER_FIX_ISSUE and start >= PERIODS[2][0]:
                # The newer fix only appears in the last two periods, on fixed dates.
                for d in BETTER_FIX_DATES:
                    if start <= d <= end:
                        slots.append({"date": d, "issue": issue_id, "asset": None, "variant": "better"})
                        remaining -= 1
            for _ in range(remaining):
                slots.append({"date": random_date(rng, start, end), "issue": issue_id, "asset": None, "variant": "original"})
    for d, model, desc, fix, parts, minutes in UNMATCHED:
        slots.append({"date": d, "issue": "", "model": model, "asset": None, "variant": None,
                      "desc": desc, "fix": fix, "parts": parts, "minutes": minutes})
    slots.sort(key=lambda s: (s["date"], s["issue"]))

    # Step 2: assign machines. Only REPEAT_ASSET may reach 3 tickets in the last
    # 60 days; every other machine is capped at 2 so the repeat flag is unique.
    recent = Counter(a for d, a, _ in PINNED if d >= WINDOW_60_START)
    for s in slots:
        if s["asset"]:
            continue
        model = s.get("model") or issues[s["issue"]]["model_id"]
        candidates = [a["asset_id"] for a in assets_by_model[model]]
        if s["date"] >= WINDOW_60_START:
            candidates = [a for a in candidates if a != REPEAT_ASSET and recent[a] < 2]
            if not candidates:
                raise SystemExit(f"No machine left for {s['issue']} on {s['date']}; lower PLAN counts")
            fewest = min(recent[a] for a in candidates)
            candidates = [a for a in candidates if recent[a] == fewest]
        s["asset"] = rng.choice(candidates)
        if s["date"] >= WINDOW_60_START:
            recent[s["asset"]] += 1

    # Step 3: fill in outcomes.
    rows, fixable_seen, original_fix_seen = [], 0, 0
    for n, s in enumerate(slots, start=1):
        row = {
            "ticket_id": f"T-{n:04d}",
            "date": s["date"].isoformat(),
            "site_id": site_of[s["asset"]],
            "asset_id": s["asset"],
            "model_id": s.get("model") or issues[s["issue"]]["model_id"],
            "issue_id": s["issue"],
            "resolved": "y",
            "resolved_by_reporter": "n",
        }
        if not s["issue"]:
            row.update(reported_description=s["desc"], fix_steps_used=s["fix"],
                       part_ids=s["parts"], minutes=s["minutes"])
            rows.append(row)
            continue

        issue = issues[s["issue"]]
        row["reported_description"] = rng.choice(DESCRIPTIONS[ISSUE_KIND[s["issue"]]])
        avg = int(issue["avg_minutes"])
        tech_minutes = max(5, round(avg * rng.uniform(0.8, 1.25)))

        if s["variant"] == "better":
            row.update(fix_steps_used=BETTER_FIX_STEPS, part_ids=BETTER_FIX_PARTS,
                       minutes=round(35 * rng.uniform(0.9, 1.1)))
        elif issue["reporter_fixable"] == "y":
            fixable_seen += 1
            if fixable_seen % TECH_NEEDED_EVERY == 0:
                row.update(fix_steps_used=issue["fix_steps"], part_ids="", minutes=tech_minutes)
            else:
                # Phone guidance time, not a site visit.
                row.update(fix_steps_used=issue["fix_steps"], part_ids="",
                           minutes=rng.randint(5, 15), resolved_by_reporter="y")
        else:
            row.update(fix_steps_used=issue["fix_steps"], part_ids=issue["part_ids"], minutes=tech_minutes)
            if s["issue"] == BETTER_FIX_ISSUE:
                original_fix_seen += 1
                # Spread the failures out (attempts 2, 5, 7) rather than bunching them.
                if original_fix_seen in (2, 5, 7)[:ORIGINAL_FIX_FAILURES]:
                    row["resolved"] = "n"
        rows.append(row)
    return rows, assets


def check_patterns(rows, today=TODAY):
    """Return a list of problems; empty means every planned pattern holds."""
    problems = []
    last30 = Counter()
    prior30 = Counter()
    recent60 = Counter()
    for r in rows:
        age = (today - date.fromisoformat(r["date"])).days
        if 0 <= age < 30:
            last30[r["issue_id"]] += 1
        elif 30 <= age < 60:
            prior30[r["issue_id"]] += 1
        if 0 <= age < 60:
            recent60[r["asset_id"]] += 1

    # Same rule the app uses: the higher window needs at least 2 tickets so a
    # single ticket (1 vs 0) is not reported as a trend.
    issues = {r["issue_id"] for r in rows if r["issue_id"]}
    rising = {i for i in issues if last30[i] >= 2 and last30[i] > prior30[i]}
    fading = {i for i in issues if prior30[i] >= 2 and prior30[i] > last30[i]}
    if rising != {"KI-CI-06", "KI-DI-04", "KI-TS-04"}:
        problems.append(f"rising issues are {sorted(rising)}")
    if fading != {"KI-CI-04", "KI-CI-05", "KI-DI-03", "KI-TS-06"}:
        problems.append(f"fading issues are {sorted(fading)}")

    repeat = {a for a, c in recent60.items() if c >= 3}
    if repeat != {REPEAT_ASSET}:
        problems.append(f"repeat-failure machines are {sorted(repeat)}")

    self_fix = sum(r["resolved_by_reporter"] == "y" for r in rows) / len(rows)
    if not 0.27 <= self_fix <= 0.33:
        problems.append(f"self-fix share is {self_fix:.0%}")

    variants = defaultdict(lambda: [0, 0])
    for r in rows:
        if r["issue_id"] == BETTER_FIX_ISSUE:
            v = variants[r["fix_steps_used"]]
            v[0] += 1
            v[1] += r["resolved"] == "y"
    if sorted(variants.values()) != [[2, 2], [8, 5]]:
        problems.append(f"carbonator fix variants are {dict(variants)}")

    if not 115 <= len(rows) <= 125:
        problems.append(f"{len(rows)} tickets")
    return problems


def main():
    rows, _ = generate()
    problems = check_patterns(rows)
    if problems:
        raise SystemExit("Pattern check failed:\n  " + "\n  ".join(problems))
    fields = ["ticket_id", "date", "site_id", "asset_id", "model_id", "reported_description",
              "issue_id", "fix_steps_used", "part_ids", "minutes", "resolved", "resolved_by_reporter"]
    with open(DEMO / "ticket_history.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    self_fix = sum(r["resolved_by_reporter"] == "y" for r in rows)
    print(f"Wrote {len(rows)} tickets ({self_fix} self-fixed) to {DEMO / 'ticket_history.csv'}; all patterns OK.")


if __name__ == "__main__":
    main()
