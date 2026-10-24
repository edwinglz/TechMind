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


# ---------- ticket display helpers ----------

def status_info(ticket, labels: dict) -> dict:
    """How a ticket's status is shown: words, chip style, and the tag's band color."""
    from app.models import TicketStatus

    if ticket.status in (TicketStatus.NEW, TicketStatus.BRIEFED):
        return {"label": "Needs a decision", "chip": "", "band": "band-new", "lane": "decide"}
    if ticket.status == TicketStatus.AWAITING_SELF_FIX:
        return {"label": f"{_cap(labels['reporter'])} trying a fix", "chip": "staff", "band": "band-staff", "lane": "staff"}
    if ticket.status == TicketStatus.ASSIGNED:
        return {"label": "Technician on it", "chip": "tech", "band": "band-tech", "lane": "tech"}
    if ticket.resolved_by_reporter:
        return {"label": f"Fixed by {labels['reporter']}", "chip": "closed", "band": "band-closed", "lane": "closed"}
    if ticket.resolved is False:
        return {"label": "Closed, not fixed", "chip": "danger", "band": "band-danger", "lane": "closed"}
    return {"label": "Closed", "chip": "closed", "band": "band-closed", "lane": "closed"}


def _age(when) -> str:
    from app.services.tickets import age_text

    return age_text(when) if when else ""


def _minutes(value) -> str:
    value = int(value or 0)
    if value < 60:
        return f"{value} min"
    hours, rest = divmod(value, 60)
    return f"{hours} h {rest} min" if rest else f"{hours} h"


def _clock(when) -> str:
    """Event time in the server's local time zone: "14:05" today, "Oct 21" before that."""
    from datetime import datetime, timezone

    local = when.replace(tzinfo=timezone.utc).astimezone()
    return local.strftime("%H:%M") if local.date() == datetime.now().astimezone().date() else local.strftime("%b %d")


def midcase(name: str) -> str:
    """Lowercase a name for use mid-sentence, but keep acronyms like CO2 or HVAC."""
    first = (name or "").split(" ")[0]
    return name if first[:2].isupper() else name[:1].lower() + name[1:]


templates.env.filters["midcase"] = midcase
templates.env.filters["clock"] = _clock
templates.env.filters["age"] = _age
templates.env.filters["minutes"] = _minutes
templates.env.globals["status_info"] = status_info
