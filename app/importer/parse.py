"""Read and validate a company's import files without touching the database.

Input is a mapping of file name -> raw bytes, so it works the same for files
uploaded through the browser and for the demo_data folder read from disk. Zip
files are unpacked; Markdown files become manuals.

Output is an ImportBundle: cleaned, typed rows for every file plus a report per
file (row count, errors, warnings). Errors block loading; warnings don't.
Row numbers in messages match what a spreadsheet shows (header = row 1).
"""

import csv
import io
import json
import zipfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path, PurePosixPath

# Columns each CSV must have, in the documented order (also used by CSV export).
COLUMNS = {
    "sites.csv": ["site_id", "name", "address", "region"],
    "products.csv": ["model_id", "manufacturer", "model_name", "category", "manual_file"],
    "assets.csv": ["asset_id", "model_id", "site_id", "serial", "install_date", "last_service_date"],
    "parts.csv": ["part_id", "name", "compatible_models", "unit_price", "in_stock"],
    "known_issues.csv": ["issue_id", "model_id", "title", "symptoms", "root_cause", "fix_steps",
                         "part_ids", "avg_minutes", "reporter_fixable"],
    "ticket_history.csv": ["ticket_id", "date", "site_id", "asset_id", "model_id", "reported_description",
                           "issue_id", "fix_steps_used", "part_ids", "minutes", "resolved",
                           "resolved_by_reporter"],
    "settings.csv": ["labor_rate_per_hour", "trip_fee", "currency"],
}
REQUIRED_FILES = ["profile.json", "settings.csv", "sites.csv", "products.csv", "assets.csv"]
OPTIONAL_FILES = ["parts.csv", "known_issues.csv", "ticket_history.csv"]
REQUIRED_LABELS = ["reporter", "site", "asset"]
PROFILE_LISTS = ["self_fix_allowed", "self_fix_forbidden", "safety_topics"]


@dataclass
class FileReport:
    name: str
    rows: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ImportBundle:
    profile: dict = field(default_factory=dict)
    settings: dict = field(default_factory=dict)
    # Typed rows per CSV, e.g. rows["sites.csv"] = [{"site_id": "S01", ...}, ...]
    rows: dict[str, list[dict]] = field(default_factory=dict)
    manuals: dict[str, str] = field(default_factory=dict)  # file name -> Markdown text
    reports: dict[str, FileReport] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not any(r.errors for r in self.reports.values())

    def all_errors(self) -> list[str]:
        return [f"{r.name}: {e}" for r in self.reports.values() for e in r.errors]


class RowError(ValueError):
    """A problem with one value in one row."""


# ---------- reading files ----------

def read_folder(folder: Path) -> dict[str, bytes]:
    """Collect import files from a folder (manuals may sit in a subfolder)."""
    return {p.name: p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


def _expand(files: dict[str, bytes]) -> dict[str, bytes]:
    """Flatten zips and folder paths so every file is keyed by its bare name."""
    flat: dict[str, bytes] = {}
    for name, data in files.items():
        base = PurePosixPath(name.replace("\\", "/")).name
        if base.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                for info in zf.infolist():
                    inner = PurePosixPath(info.filename).name
                    if not info.is_dir() and inner and not inner.startswith("."):
                        flat[inner] = zf.read(info)
        else:
            flat[base] = data
    return flat


def _decode(data: bytes) -> str:
    # utf-8-sig strips the byte-order mark Excel adds when saving "CSV UTF-8".
    return data.decode("utf-8-sig")


# ---------- value converters (raise RowError with a readable message) ----------

def _text(row, col, required=False):
    value = (row.get(col) or "").strip()
    if required and not value:
        raise RowError(f"'{col}' is required")
    return value


def _yes_no(row, col):
    value = _text(row, col).lower()
    if value in ("y", "yes", "true", "1"):
        return True
    if value in ("n", "no", "false", "0", ""):
        return False
    raise RowError(f"'{col}' must be y or n, got {value!r}")


def _number(row, col, kind=float, required=False, default=None):
    value = _text(row, col, required)
    if not value:
        return default
    try:
        number = kind(float(value)) if kind is int else kind(value)
    except ValueError:
        raise RowError(f"'{col}' must be a number, got {value!r}") from None
    if number < 0:
        raise RowError(f"'{col}' can't be negative")
    return number


def _date(row, col, required=False):
    value = _text(row, col, required)
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise RowError(f"'{col}' must be a date like 2026-05-31, got {value!r}") from None


def _split(row, col, sep):
    return [part.strip() for part in _text(row, col).split(sep) if part.strip()]


# ---------- per-file validation ----------

def _read_csv(name, files, report):
    """Return the CSV's rows as dicts, or None if the file is missing/unreadable."""
    if name not in files:
        if name in REQUIRED_FILES:
            report.errors.append("file is missing")
        return None
    try:
        reader = csv.DictReader(io.StringIO(_decode(files[name])))
        header = [h.strip() for h in (reader.fieldnames or [])]
        reader.fieldnames = header
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error) as exc:
        report.errors.append(f"could not read file ({exc})")
        return None
    missing = [c for c in COLUMNS[name] if c not in header]
    if missing:
        report.errors.append(f"missing column(s): {', '.join(missing)}")
        return None
    extra = [c for c in header if c not in COLUMNS[name]]
    if extra:
        report.warnings.append(f"ignoring unknown column(s): {', '.join(extra)}")
    report.rows = len(rows)
    return rows


def _each_row(rows, report, id_col, convert):
    """Convert each row, collecting errors with row numbers and rejecting duplicate ids."""
    out, seen = [], set()
    for line, row in enumerate(rows, start=2):
        try:
            item = convert(row)
        except RowError as exc:
            report.errors.append(f"row {line}: {exc}")
            continue
        if id_col:
            if item[id_col] in seen:
                report.errors.append(f"row {line}: duplicate {id_col} {item[id_col]!r}")
                continue
            seen.add(item[id_col])
        item["_line"] = line
        out.append(item)
    return out


def _check_ref(item, col, valid, label):
    if item[col] and item[col] not in valid:
        raise RowError(f"{col} {item[col]!r} is not in {label}")


def _parse_profile(files, report):
    if "profile.json" not in files:
        report.errors.append("file is missing")
        return {}
    try:
        profile = json.loads(_decode(files["profile.json"]))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        report.errors.append(f"not valid JSON ({exc})")
        return {}
    if not isinstance(profile, dict):
        report.errors.append("must be a JSON object")
        return {}
    if not isinstance(profile.get("industry"), str) or not profile["industry"].strip():
        report.errors.append("'industry' must be a non-empty string")
    labels = profile.get("labels")
    if not isinstance(labels, dict):
        report.errors.append("'labels' must be an object like {\"site\": \"store\", ...}")
    else:
        for key in REQUIRED_LABELS:
            if not isinstance(labels.get(key), str) or not labels[key].strip():
                report.errors.append(f"'labels.{key}' is required")
    for key in PROFILE_LISTS:
        value = profile.get(key)
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            report.errors.append(f"'{key}' must be a list of strings")
    report.rows = 1
    return profile


def _parse_settings(files, report):
    rows = _read_csv("settings.csv", files, report)
    if rows is None:
        return {}
    if len(rows) != 1:
        report.errors.append(f"must have exactly one data row, found {len(rows)}")
        return {}
    try:
        return {
            "labor_rate_per_hour": _number(rows[0], "labor_rate_per_hour", required=True),
            "trip_fee": _number(rows[0], "trip_fee", required=True),
            "currency": _text(rows[0], "currency") or "USD",
        }
    except RowError as exc:
        report.errors.append(f"row 2: {exc}")
        return {}


def parse_bundle(files: dict[str, bytes]) -> ImportBundle:
    files = _expand(files)
    bundle = ImportBundle()
    reports = bundle.reports
    for name in ["profile.json", "settings.csv", *[n for n in COLUMNS if n != "settings.csv"]]:
        reports[name] = FileReport(name)

    bundle.profile = _parse_profile(files, reports["profile.json"])
    bundle.settings = _parse_settings(files, reports["settings.csv"])
    bundle.manuals = {n: _decode(d) for n, d in files.items() if n.lower().endswith(".md")}
    reports["manuals"] = FileReport("manuals", rows=len(bundle.manuals))

    def rows_of(name):
        return _read_csv(name, files, reports[name]) or []

    # Order matters: later files reference ids from earlier ones.
    sites = _each_row(rows_of("sites.csv"), reports["sites.csv"], "site_id", lambda r: {
        "site_id": _text(r, "site_id", True), "name": _text(r, "name", True),
        "address": _text(r, "address"), "region": _text(r, "region"),
    })
    site_ids = {s["site_id"] for s in sites}

    products = _each_row(rows_of("products.csv"), reports["products.csv"], "model_id", lambda r: {
        "model_id": _text(r, "model_id", True), "manufacturer": _text(r, "manufacturer"),
        "model_name": _text(r, "model_name", True), "category": _text(r, "category"),
        "manual_file": _text(r, "manual_file"),
    })
    model_ids = {p["model_id"] for p in products}
    for p in products:
        if p["manual_file"] and p["manual_file"] not in bundle.manuals:
            reports["products.csv"].warnings.append(
                f"row {p['_line']}: manual {p['manual_file']!r} was not uploaded; "
                "briefs for this model won't cite a manual")

    def convert_asset(r):
        item = {
            "asset_id": _text(r, "asset_id", True), "model_id": _text(r, "model_id", True),
            "site_id": _text(r, "site_id", True), "serial": _text(r, "serial"),
            "install_date": _date(r, "install_date"), "last_service_date": _date(r, "last_service_date"),
        }
        _check_ref(item, "model_id", model_ids, "products.csv")
        _check_ref(item, "site_id", site_ids, "sites.csv")
        return item

    assets = _each_row(rows_of("assets.csv"), reports["assets.csv"], "asset_id", convert_asset)
    asset_model = {a["asset_id"]: a["model_id"] for a in assets}

    def convert_part(r):
        item = {
            "part_id": _text(r, "part_id", True), "name": _text(r, "name", True),
            "compatible_models": _split(r, "compatible_models", ";"),
            "unit_price": _number(r, "unit_price", required=True),
            "in_stock": _yes_no_or_count(r, "in_stock"),
        }
        unknown = [m for m in item["compatible_models"] if m not in model_ids]
        if unknown:
            raise RowError(f"compatible_models {', '.join(unknown)} not in products.csv")
        return item

    parts = _each_row(rows_of("parts.csv"), reports["parts.csv"], "part_id", convert_part)
    part_ids = {p["part_id"] for p in parts}

    def convert_issue(r):
        item = {
            "issue_id": _text(r, "issue_id", True), "model_id": _text(r, "model_id", True),
            "title": _text(r, "title", True), "symptoms": _text(r, "symptoms"),
            "root_cause": _text(r, "root_cause"), "fix_steps": _split(r, "fix_steps", "|"),
            "part_ids": _split(r, "part_ids", ";"),
            "avg_minutes": _number(r, "avg_minutes", int, default=0),
            "reporter_fixable": _yes_no(r, "reporter_fixable"),
        }
        _check_ref(item, "model_id", model_ids, "products.csv")
        unknown = [p for p in item["part_ids"] if p not in part_ids]
        if unknown:
            raise RowError(f"part_ids {', '.join(unknown)} not in parts.csv")
        return item

    issues = _each_row(rows_of("known_issues.csv"), reports["known_issues.csv"], "issue_id", convert_issue)
    issue_ids = {i["issue_id"] for i in issues}

    def convert_ticket(r):
        item = {
            "ticket_id": _text(r, "ticket_id", True), "date": _date(r, "date", True),
            "site_id": _text(r, "site_id", True), "asset_id": _text(r, "asset_id"),
            "model_id": _text(r, "model_id"),
            "reported_description": _text(r, "reported_description", True),
            "issue_id": _text(r, "issue_id"), "fix_steps_used": _split(r, "fix_steps_used", "|"),
            "part_ids": _split(r, "part_ids", ";"), "minutes": _number(r, "minutes", int),
            "resolved": _yes_no(r, "resolved"), "resolved_by_reporter": _yes_no(r, "resolved_by_reporter"),
        }
        _check_ref(item, "site_id", site_ids, "sites.csv")
        _check_ref(item, "asset_id", set(asset_model), "assets.csv")
        _check_ref(item, "model_id", model_ids, "products.csv")
        _check_ref(item, "issue_id", issue_ids, "known_issues.csv")
        unknown = [p for p in item["part_ids"] if p not in part_ids]
        if unknown:
            raise RowError(f"part_ids {', '.join(unknown)} not in parts.csv")
        # A ticket for a known asset always belongs to that asset's model.
        if item["asset_id"]:
            item["model_id"] = item["model_id"] or asset_model[item["asset_id"]]
            if item["model_id"] != asset_model[item["asset_id"]]:
                raise RowError(f"asset {item['asset_id']} is model {asset_model[item['asset_id']]}, "
                               f"not {item['model_id']}")
        return item

    tickets = _each_row(rows_of("ticket_history.csv"), reports["ticket_history.csv"], "ticket_id",
                        convert_ticket)

    bundle.rows = {
        "sites.csv": sites, "products.csv": products, "assets.csv": assets, "parts.csv": parts,
        "known_issues.csv": issues, "ticket_history.csv": tickets,
    }
    return bundle


def _yes_no_or_count(row, col):
    """in_stock may be a quantity or y/n; y/n become 1/0."""
    value = _text(row, col).lower()
    if value in ("y", "yes"):
        return 1
    if value in ("n", "no", ""):
        return 0
    return _number(row, col, int)
