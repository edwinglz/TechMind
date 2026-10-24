"""Generate demo_data/assets.csv and demo_data/ticket_history.csv for the demo company.

The demo company is a fictional burger chain whose stores each run a typical mix
of quick-service equipment (beverage dispensers, fryers, griddles, ice machines,
walk-in coolers, rooftop HVAC). The ticket history is not random noise: it is
planned so the demo can show specific patterns. This script builds ~125 resolved
tickets from May to October 2026 using a fixed random seed (every run produces
the same files), then checks each planned pattern before writing anything:

- fading:  summer cooling problems (warm drinks, ice, walk-in, HVAC) peaked in
           summer and are now declining
- rising:  beverage valve/nozzle leaks spike in the last 30 days (a bad batch of seals)
- repeat:  A-0401 (the countertop beverage dispenser at Store #4) has 3 tickets in
           the last 60 days; no other unit does
- better fix: carbonator pump failure (KI-CI-03) has a newer fix that has worked
           2 out of 2 times; the original fix worked 5 out of 8. The newer fix needs
           one more success to reach the 3-attempt minimum and become the
           recommended fix, which is exactly what the live demo ticket does.
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

# ---------- equipment at each store ----------

# Models per store, in asset-number order. The countertop beverage dispenser is
# listed first where a store has one, so Store #4's is A-0401 (the demo unit).
STORE_LAYOUT = {
    "S01": ["CI-200", "EF-40", "EF-40", "FG-36", "IM-500", "WC-810", "RT-5"],
    "S02": ["CI-200", "TS-500", "EF-40", "FG-36", "IM-500", "WC-810", "RT-5"],
    "S03": ["CI-200", "TS-500", "EF-40", "EF-40", "FG-36", "IM-500", "WC-810", "RT-5", "RT-5"],
    "S04": ["CI-200", "TS-500", "EF-40", "EF-40", "FG-36", "IM-500", "WC-810", "RT-5"],
    "S05": ["CI-200", "EF-40", "FG-36", "IM-500", "WC-810", "RT-5"],
    "S06": ["CI-200", "TS-500", "EF-40", "EF-40", "FG-36", "IM-500", "WC-810", "RT-5"],
    "S07": ["TS-500", "EF-40", "FG-36", "IM-500", "WC-810", "RT-5"],
    "S08": ["CI-200", "EF-40", "EF-40", "FG-36", "IM-500", "WC-810", "RT-5"],
}
STORE_OPENED = {"S01": 2019, "S02": 2020, "S03": 2021, "S04": 2018, "S05": 2022, "S06": 2020,
                "S07": 2023, "S08": 2024}
SERIAL_PREFIX = {"CI-200": "GPC2", "TS-500": "FZT5", "EF-40": "EMF4", "FG-36": "EMG3",
                 "IM-500": "PCI5", "WC-810": "CVW8", "RT-5": "AMR5"}

# ---------- ticket plan ----------

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
    # beverage
    "KI-CI-01": [1, 1, 0, 1],
    "KI-CI-02": [2, 1, 1, 1],
    "KI-CI-03": [4, 4, 1, 1],  # periods 1-2: original fix; periods 3-4: the newer fix
    "KI-CI-04": [2, 3, 2, 1],  # fading
    "KI-CI-05": [1, 2, 2, 0],  # fading
    "KI-CI-06": [1, 1, 0, 3],  # rising
    "KI-CI-07": [1, 0, 0, 0],
    "KI-CI-08": [1, 1, 0, 0],
    "KI-TS-01": [1, 1, 0, 0],
    "KI-TS-02": [1, 1, 0, 0],
    "KI-TS-03": [1, 1, 0, 0],
    "KI-TS-04": [0, 0, 1, 3],  # rising
    "KI-TS-05": [2, 2, 0, 1],
    "KI-TS-06": [1, 2, 2, 0],  # fading
    # fryers and griddles
    "KI-EF-01": [1, 2, 1, 1],
    "KI-EF-02": [1, 0, 1, 0],
    "KI-EF-03": [2, 1, 1, 1],
    "KI-EF-04": [1, 1, 0, 0],
    "KI-FG-01": [1, 1, 0, 1],
    "KI-FG-02": [1, 1, 1, 0],
    "KI-FG-03": [1, 0, 0, 0],
    # ice machines
    "KI-IM-01": [2, 2, 1, 0],
    "KI-IM-02": [2, 3, 2, 0],  # fading
    "KI-IM-03": [1, 0, 0, 1],
    # walk-in coolers
    "KI-WC-01": [1, 3, 2, 0],  # fading
    "KI-WC-02": [1, 2, 1, 1],
    "KI-WC-03": [1, 1, 1, 0],
    # rooftop HVAC
    "KI-RT-01": [2, 2, 1, 0],
    "KI-RT-02": [1, 3, 2, 0],  # fading
    "KI-RT-03": [1, 1, 0, 0],
    "KI-RT-04": [1, 1, 0, 0],
}
EXPECTED_RISING = {"KI-CI-06", "KI-TS-04"}
EXPECTED_FADING = {"KI-CI-04", "KI-CI-05", "KI-TS-06", "KI-IM-02", "KI-WC-01", "KI-RT-02"}

# Tickets fixed to a specific unit and date. These give A-0401 its repeat-failure
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
ORIGINAL_FIX_FAILED_ATTEMPTS = (2, 5, 7)  # which of the 8 original-fix attempts did not resolve it

# Tickets where no known issue matched.
UNMATCHED = [
    (date(2026, 5, 19), "CI-200", "Customers say the root beer tastes funny",
     "Sanitized syrup line and nozzle; no fault found", "", 30),
    (date(2026, 7, 22), "WC-810", "Light inside the walk-in is out",
     "Replaced the vapor-proof light fixture lamp", "", 20),
]

# Vague, realistic phrasings of what the reporter said on the phone.
DESCRIPTIONS = {
    "CO2": ["All the sodas are flat", "Drinks have no fizz at all", "Everything tastes flat, even the Sprite"],
    "BIB": ["Coke is coming out clear", "Diet tastes like soda water", "One of the flavors is really watery"],
    "PUMP": ["Drinks are flat and kind of watery", "Soda machine keeps humming and the soda is flat",
             "No carbonation, motor sounds weird"],
    "WARM": ["Drinks are coming out warm", "Soda is not cold anymore", "Drinks are lukewarm and foamy"],
    "ICE": ["Ice won't come out of the dispenser", "No ice, dispenser makes a grinding noise",
            "Ice is stuck in one big block in the dispenser"],
    "LEAK": ["Soda machine is leaking on the counter", "Nozzle keeps dripping after pouring",
             "Puddle under the soda machine"],
    "BRIX": ["Sprite tastes too sweet", "Customers say the lemonade is weak", "Dr Pepper tastes off"],
    "NOZZLE": ["Soda sprays everywhere when pouring", "Weak stream on the Coke valve", "Nozzle looks slimy"],
    "TSPOWER": ["Self-serve screen is completely black", "Self-serve drink machine is dead"],
    "E21": ["Self-serve says E-21 and drinks are flat", "Error E-21 on the self-serve"],
    "E34": ["Error E-34, Fanta won't pour", "One flavor stopped working on the self-serve, clicking noise"],
    "E12": ["Self-serve says Coke is sold out", "E-12 on the self-serve", "Lemonade button is greyed out"],
    "E40": ["Self-serve drinks are warm, error E-40", "Self-serve shows E-40, fan is really loud"],
    "PILOT": ["Fryer keeps going out", "Pilot light on fryer 2 won't stay on", "Fryer won't light"],
    "SLOWHEAT": ["Fryer takes forever to heat up", "Oil not getting hot enough, fries are soggy"],
    "FRYPOWER": ["Fryer is completely dead", "Fryer won't turn on after cleaning"],
    "HIGHLIMIT": ["Fryer shut off by itself and won't restart", "Fryer oil was smoking and then it shut off"],
    "GRIDCOLD": ["Griddle has cold spots", "Patties cooking unevenly on the flat top"],
    "GRIDIGN": ["Griddle burner won't light", "Left side of the griddle won't come on"],
    "GRIDTEMP": ["Griddle runs way too hot", "Flat top burning everything even on low"],
    "ICEFILTER": ["Ice machine making less ice", "Ice bin never fills up"],
    "ICESCALE": ["Ice machine barely making ice", "Ice cubes small and cloudy, not much ice"],
    "ICEWATER": ["Ice machine not making any ice", "Ice machine runs but no ice comes out"],
    "WALKWARM": ["Walk-in is warm", "Walk-in cooler reading 48 degrees", "Cooler not keeping temp"],
    "WALKDOOR": ["Walk-in door won't shut right", "Walk-in door keeps popping open"],
    "WALKFAN": ["Walk-in warm, loud noise from the unit outside", "Cooler warm and the fan outside isn't spinning"],
    "HVACFILTER": ["AC is weak in the dining room", "Not much air coming out of the vents"],
    "HVACCOOL": ["AC blowing warm air", "Restaurant is really hot, AC not cooling", "Kitchen is boiling, AC is off"],
    "HVACSTAT": ["Thermostat screen is blank", "Can't change the temperature, thermostat is dead"],
    "HVACFAN": ["AC unit on the roof making a grinding noise", "AC keeps cutting out in the afternoon"],
}
ISSUE_KIND = {
    "KI-CI-01": "CO2", "KI-CI-02": "BIB", "KI-CI-03": "PUMP", "KI-CI-04": "WARM", "KI-CI-05": "ICE",
    "KI-CI-06": "LEAK", "KI-CI-07": "BRIX", "KI-CI-08": "NOZZLE",
    "KI-TS-01": "TSPOWER", "KI-TS-02": "E21", "KI-TS-03": "E34", "KI-TS-04": "LEAK", "KI-TS-05": "E12",
    "KI-TS-06": "E40",
    "KI-EF-01": "PILOT", "KI-EF-02": "SLOWHEAT", "KI-EF-03": "FRYPOWER", "KI-EF-04": "HIGHLIMIT",
    "KI-FG-01": "GRIDCOLD", "KI-FG-02": "GRIDIGN", "KI-FG-03": "GRIDTEMP",
    "KI-IM-01": "ICEFILTER", "KI-IM-02": "ICESCALE", "KI-IM-03": "ICEWATER",
    "KI-WC-01": "WALKWARM", "KI-WC-02": "WALKDOOR", "KI-WC-03": "WALKFAN",
    "KI-RT-01": "HVACFILTER", "KI-RT-02": "HVACCOOL", "KI-RT-03": "HVACSTAT", "KI-RT-04": "HVACFAN",
}

# Roughly 1 in 10 reporter-fixable tickets still needed a technician (the store
# could not do it), which brings the self-fix share to about 30%.
TECH_NEEDED_EVERY = 10


def read_csv(name):
    with open(DEMO / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def random_date(rng, start, end):
    return start + timedelta(days=rng.randint(0, (end - start).days))


def generate_assets():
    rng = random.Random(7)
    rows = []
    for site_id, models in STORE_LAYOUT.items():
        opened = STORE_OPENED[site_id]
        for n, model in enumerate(models, start=1):
            # Installed when the store opened or a year or two later, never after 2025.
            year = min(opened + rng.choice([0, 0, 1, 2]), 2025)
            installed = date(year, rng.randint(1, 12), rng.randint(1, 28))
            rows.append({
                "asset_id": f"A-{site_id[1:]}{n:02d}",
                "model_id": model,
                "site_id": site_id,
                "serial": f"{SERIAL_PREFIX[model]}-{installed.year % 100:02d}-{rng.randint(100, 9999):05d}",
                "install_date": installed.isoformat(),
                "last_service_date": date(2026, rng.randint(3, 4), rng.randint(1, 28)).isoformat(),
            })
    return rows


def generate(assets):
    rng = random.Random(42)
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
            if issue_id == BETTER_FIX_ISSUE:
                # The newer fix only appears in the last two periods, on fixed dates.
                for d in BETTER_FIX_DATES:
                    if start <= d <= end:
                        slots.append({"date": d, "issue": issue_id, "asset": None, "variant": "better"})
                        remaining -= 1
            for _ in range(remaining):
                slots.append({"date": random_date(rng, start, end), "issue": issue_id, "asset": None,
                              "variant": "original"})
    for d, model, desc, fix, parts, minutes in UNMATCHED:
        slots.append({"date": d, "issue": "", "model": model, "asset": None, "variant": None,
                      "desc": desc, "fix": fix, "parts": parts, "minutes": minutes})
    slots.sort(key=lambda s: (s["date"], s["issue"]))

    # Step 2: assign units. Only REPEAT_ASSET may reach 3 tickets in the last
    # 60 days; every other unit is capped at 2 so the repeat flag is unique.
    recent = Counter(a for d, a, _ in PINNED if d >= WINDOW_60_START)
    for s in slots:
        if s["asset"]:
            continue
        model = s.get("model") or issues[s["issue"]]["model_id"]
        candidates = [a["asset_id"] for a in assets_by_model[model] if a["asset_id"] != REPEAT_ASSET]
        if s["date"] >= WINDOW_60_START:
            candidates = [a for a in candidates if recent[a] < 2]
            if not candidates:
                raise SystemExit(f"No unit left for {s['issue']} on {s['date']}; lower PLAN counts")
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
        tech_minutes = max(5, round(int(issue["avg_minutes"]) * rng.uniform(0.8, 1.25)))

        if s["variant"] == "better":
            row.update(fix_steps_used=BETTER_FIX_STEPS, part_ids=BETTER_FIX_PARTS,
                       minutes=round(35 * rng.uniform(0.9, 1.1)))
        elif issue["reporter_fixable"] == "y":
            fixable_seen += 1
            if fixable_seen % TECH_NEEDED_EVERY == 0:
                row.update(fix_steps_used=issue["fix_steps"], part_ids=issue["part_ids"], minutes=tech_minutes)
            else:
                # Phone guidance time, not a site visit.
                row.update(fix_steps_used=issue["fix_steps"], part_ids="",
                           minutes=rng.randint(5, 15), resolved_by_reporter="y")
        else:
            row.update(fix_steps_used=issue["fix_steps"], part_ids=issue["part_ids"], minutes=tech_minutes)
            if s["issue"] == BETTER_FIX_ISSUE:
                original_fix_seen += 1
                if original_fix_seen in ORIGINAL_FIX_FAILED_ATTEMPTS:
                    row["resolved"] = "n"
        rows.append(row)
    return rows


def check_patterns(rows, today=TODAY):
    """Return a list of problems; empty means every planned pattern holds."""
    problems = []
    last30, prior30, recent60 = Counter(), Counter(), Counter()
    for r in rows:
        age = (today - date.fromisoformat(r["date"])).days
        if 0 <= age < 30:
            last30[r["issue_id"]] += 1
        elif 30 <= age < 60:
            prior30[r["issue_id"]] += 1
        if 0 <= age < 60:
            recent60[r["asset_id"]] += 1

    # Same rule the app uses: the busier window needs at least 2 tickets so a
    # single ticket (1 vs 0) is not reported as a trend.
    issues = {r["issue_id"] for r in rows if r["issue_id"]}
    rising = {i for i in issues if last30[i] >= 2 and last30[i] > prior30[i]}
    fading = {i for i in issues if prior30[i] >= 2 and prior30[i] > last30[i]}
    if rising != EXPECTED_RISING:
        problems.append(f"rising issues are {sorted(rising)}")
    if fading != EXPECTED_FADING:
        problems.append(f"fading issues are {sorted(fading)}")

    repeat = {a for a, c in recent60.items() if c >= 3}
    if repeat != {REPEAT_ASSET}:
        problems.append(f"repeat-failure units are {sorted(repeat)}")

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

    if not 115 <= len(rows) <= 130:
        problems.append(f"{len(rows)} tickets")
    return problems


def write_csv(name, rows):
    with open(DEMO / name, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


TICKET_FIELDS = ["ticket_id", "date", "site_id", "asset_id", "model_id", "reported_description",
                 "issue_id", "fix_steps_used", "part_ids", "minutes", "resolved", "resolved_by_reporter"]


def main():
    assets = generate_assets()
    rows = generate(assets)
    problems = check_patterns(rows)
    if problems:
        raise SystemExit("Pattern check failed:\n  " + "\n  ".join(problems))
    write_csv("assets.csv", assets)
    write_csv("ticket_history.csv", [{k: r[k] for k in TICKET_FIELDS} for r in rows])
    self_fix = sum(r["resolved_by_reporter"] == "y" for r in rows)
    print(f"Wrote {len(assets)} units and {len(rows)} tickets ({self_fix} self-fixed); all patterns OK.")


if __name__ == "__main__":
    main()
