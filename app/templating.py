"""Jinja2 setup and the helpers every page template can use.

Labels: templates never hardcode industry words like "store" or "machine".
They use `L.site`, `L.assets`, `L.reporter`, ... which come from the company's
profile, so a laptop repair shop's UI says "customer" and "laptop" instead.
"""

from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates
from jinja2 import pass_context

from app.auth import display_name
from app.models import Company, User

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

GENERIC_LABELS = {"site": "site", "asset": "asset", "reporter": "reporter"}
CURRENCY_SYMBOLS = {"USD": "$", "CAD": "$", "AUD": "$", "MXN": "$", "EUR": "€", "GBP": "£"}


def _plural(word: str) -> str:
    """Plain English plural, used only when the profile doesn't give one."""
    if word.endswith(("s", "x", "ch", "sh")):
        return word + "es"
    if word.endswith("y") and word[-2:-1] not in "aeiou":
        return word[:-1] + "ies"
    return word + "s"


def labels_for(company: Company | None) -> dict[str, str]:
    """Singular and plural UI words, e.g. {"site": "store", "sites": "stores", ...}."""
    raw = (company.profile.get("labels") or {}) if company else {}
    labels = {}
    for key, default in GENERIC_LABELS.items():
        singular = (raw.get(key) or default).strip()
        labels[key] = singular
        labels[key + "s"] = (raw.get(key + "s") or _plural(singular)).strip()
    return labels


def _cap(value: str) -> str:
    """Capitalize the first letter only ("store staff" -> "Store staff")."""
    return value[:1].upper() + value[1:] if value else value


@pass_context
def _money(context, amount) -> str:
    company = context.get("company")
    currency = company.currency if company else "USD"
    symbol = CURRENCY_SYMBOLS.get(currency)
    text = f"{amount or 0:,.2f}"
    return f"{symbol}{text}" if symbol else f"{text} {currency}"


templates.env.filters["cap"] = _cap
templates.env.filters["money"] = _money
templates.env.globals["display_name"] = display_name


def render(request: Request, name: str, user: User | None = None, company: Company | None = None,
           status_code: int = 200, **context):
    return templates.TemplateResponse(
        request, name, {"user": user, "company": company, "L": labels_for(company), **context},
        status_code=status_code,
    )
