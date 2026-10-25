"""Company registration with data import, and the team page.

Registration happens in two steps so nothing is written until the data checks out:

1. /register: the manager enters the company name and their own account, and
   uploads the company's files (CSVs, profile.json, manuals, or one zip).
   The files are parsed and validated (app/importer/parse.py) and kept in a
   pending folder under UPLOAD_DIR/imports/<token>, together with the account
   details (password already hashed).
2. The review page shows every file with its row count, errors and warnings.
   If anything is wrong, the manager uploads corrected files (same token). When
   everything is valid, "Create company" loads the data (app/importer/load.py),
   creates the manager account, logs them in, and sends them to the team page
   to add technicians.
"""

import io
import json
import re
import secrets
import shutil
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlmodel import Session, select

from app.auth import COOKIE_NAME, Current, hash_password, require_login, session_cookie_value
from app.config import settings
from app.db import get_session
from app.importer.load import load_company
from app.importer.parse import COLUMNS, OPTIONAL_FILES, REQUIRED_FILES, parse_bundle
from app.models import User
from app.templating import render

router = APIRouter()

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,30}$")
ACCEPTED = (".csv", ".json", ".md", ".zip", ".txt")


def _pending_dir(token: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{24}", token or ""):
        raise HTTPException(404)
    return settings.upload_dir / "imports" / token


async def _read_uploads(files: list[UploadFile]) -> tuple[dict[str, bytes], list[str]]:
    data, problems, total = {}, [], 0
    for f in files:
        if not f or not f.filename:
            continue
        name = Path(f.filename.replace("\\", "/")).name
        if not name.lower().endswith(ACCEPTED):
            problems.append(f"{name}: not a CSV, JSON, Markdown or zip file, so it was skipped.")
            continue
        content = await f.read()
        total += len(content)
        data[name] = content
    if total > MAX_UPLOAD_BYTES:
        return {}, ["The upload is larger than 25 MB. Leave out photos or other large files."]
    return data, problems


def _save_files(folder: Path, files: dict[str, bytes]) -> None:
    files_dir = folder / "files"
    if files_dir.exists():
        shutil.rmtree(files_dir)
    files_dir.mkdir(parents=True)
    for name, content in files.items():
        (files_dir / name).write_bytes(content)


def _load_files(folder: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted((folder / "files").glob("*")) if p.is_file()}


def _summary(bundle) -> dict:
    """What the review page shows about the company, in its own words."""
    labels = (bundle.profile.get("labels") or {}) if isinstance(bundle.profile, dict) else {}
    rows = bundle.rows
    return {"industry": bundle.profile.get("industry", "") if isinstance(bundle.profile, dict) else "",
            "labels": labels, "settings": bundle.settings,
            "counts": {name: len(rows.get(name, [])) for name in COLUMNS if name != "settings.csv"},
            "manuals": len(bundle.manuals)}


def _review(request: Request, token: str, pending: dict, bundle, upload_notes: list[str]):
    return render(request, "register_review.html", token=token, pending=pending, bundle=bundle,
                  summary=_summary(bundle), upload_notes=upload_notes, required=REQUIRED_FILES,
                  optional=OPTIONAL_FILES)


# ---------- step 1: account + files ----------

@router.get("/register")
def register_form(request: Request):
    return render(request, "register.html", columns=COLUMNS, required=REQUIRED_FILES, values={})


@router.post("/register")
async def register(request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    values = {k: str(form.get(k, "")).strip() for k in ("company_name", "your_name", "username")}
    values["username"] = values["username"].lower()
    password = str(form.get("password", ""))
    errors = []
    if not values["company_name"]:
        errors.append("Enter your company's name.")
    if not values["your_name"]:
        errors.append("Enter your name.")
    if not USERNAME_RE.fullmatch(values["username"]):
        errors.append("Usernames are 3 to 30 characters: lowercase letters, numbers, dots, dashes or underscores.")
    elif session.exec(select(User).where(User.username == values["username"])).first():
        errors.append(f"The username “{values['username']}” is taken. Pick another one.")
    if len(password) < 8:
        errors.append("Use a password of at least 8 characters.")
    files, notes = await _read_uploads(form.getlist("files"))
    if not files and not notes:
        errors.append("Upload your company's files (or the sample files) to continue.")
    errors += [n for n in notes if "25 MB" in n]
    if errors:
        return render(request, "register.html", columns=COLUMNS, required=REQUIRED_FILES, values=values,
                      errors=errors, status_code=400)

    token = secrets.token_hex(12)
    folder = _pending_dir(token)
    _save_files(folder, files)
    pending = {**values, "password_hash": hash_password(password)}
    (folder / "pending.json").write_text(json.dumps(pending))
    return _review(request, token, pending, parse_bundle(files), notes)


# ---------- step 2: review, fix, create ----------

@router.get("/register/{token}")
def review(request: Request, token: str):
    folder = _pending_dir(token)
    if not (folder / "pending.json").exists():
        return RedirectResponse("/register", status_code=303)
    pending = json.loads((folder / "pending.json").read_text())
    return _review(request, token, pending, parse_bundle(_load_files(folder)), [])


@router.post("/register/{token}/files")
async def replace_files(request: Request, token: str):
    """Upload corrected files. Files with the same name replace the earlier ones; others are added."""
    folder = _pending_dir(token)
    if not (folder / "pending.json").exists():
        return RedirectResponse("/register", status_code=303)
    form = await request.form()
    files, notes = await _read_uploads(form.getlist("files"))
    merged = {**_load_files(folder), **files}
    _save_files(folder, merged)
    pending = json.loads((folder / "pending.json").read_text())
    return _review(request, token, pending, parse_bundle(merged), notes)


@router.post("/register/{token}/create")
def create(token: str, session: Session = Depends(get_session)):
    folder = _pending_dir(token)
    if not (folder / "pending.json").exists():
        return RedirectResponse("/register", status_code=303)
    pending = json.loads((folder / "pending.json").read_text())
    bundle = parse_bundle(_load_files(folder))
    if not bundle.ok:
        return RedirectResponse(f"/register/{token}", status_code=303)
    if session.exec(select(User).where(User.username == pending["username"])).first():
        raise HTTPException(409, "That username was taken in the meantime. Start again with another one.")
    company = load_company(session, bundle, pending["company_name"])
    user = User(company_id=company.id, username=pending["username"], password_hash=pending["password_hash"],
                name=pending["your_name"], role="manager")
    session.add(user)
    session.commit()
    shutil.rmtree(folder, ignore_errors=True)
    response = RedirectResponse("/app/team?welcome=1", status_code=303)
    response.set_cookie(COOKIE_NAME, session_cookie_value(user.id), httponly=True, samesite="lax",
                        max_age=60 * 60 * 24 * 7)
    return response


@router.get("/register-sample.zip")
def sample_zip():
    """The demo company's files, so anyone can see (and try) the import format."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(settings.demo_data_dir.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(settings.demo_data_dir).as_posix())
    return StreamingResponse(iter([buffer.getvalue()]), media_type="application/zip",
                             headers={"Content-Disposition": "attachment; filename=techmind-sample-company.zip"})


# ---------- team ----------

@router.get("/app/team")
def team(request: Request, welcome: int = 0, cur: Current = Depends(require_login),
         session: Session = Depends(get_session)):
    if not cur.is_manager:
        raise HTTPException(403)
    return _team(request, cur, session, welcome=bool(welcome))


def _team(request, cur, session, **context):
    users = session.exec(select(User).where(User.company_id == cur.company.id).order_by(User.role, User.name)).all()
    return render(request, "team.html", user=cur.user, company=cur.company, users=users, nav="team", **context)


@router.post("/app/team")
def add_member(request: Request, name: str = Form(""), username: str = Form(""), password: str = Form(""),
               role: str = Form("technician"), cur: Current = Depends(require_login),
               session: Session = Depends(get_session)):
    if not cur.is_manager:
        raise HTTPException(403)
    username = username.strip().lower()
    errors = []
    if not name.strip():
        errors.append("Enter their name.")
    if not USERNAME_RE.fullmatch(username):
        errors.append("Usernames are 3 to 30 characters: lowercase letters, numbers, dots, dashes or underscores.")
    elif session.exec(select(User).where(User.username == username)).first():
        errors.append(f"The username “{username}” is taken.")
    if len(password) < 8:
        errors.append("Use a password of at least 8 characters.")
    if errors:
        return _team(request, cur, session, errors=errors, values={"name": name, "username": username, "role": role})
    session.add(User(company_id=cur.company.id, username=username, password_hash=hash_password(password),
                     name=name.strip(), role="manager" if role == "manager" else "technician"))
    session.commit()
    return _team(request, cur, session, added=name.strip())


