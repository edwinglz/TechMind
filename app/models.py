"""Database tables (SQLModel).

Naming is deliberately generic (sites, assets, reporter) so the same code works
for any industry; the words shown to users come from the company's profile.

Conventions:
- Every table except `companies` has `company_id`, so several companies can
  share one database without seeing each other's data.
- `id` is our internal key. `ref` is the company's own ID from its import files
  (for example "S04"); it is unique within a company and is what CSV export
  writes back out.
- JSON columns hold small lists/dicts. SQLAlchemy does not notice in-place
  changes to them, so always assign a new list/dict instead of mutating.
"""

from datetime import date, datetime, timezone

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def json_list():
    return Field(default_factory=list, sa_column=Column(JSON, nullable=False))


def json_dict():
    return Field(default_factory=dict, sa_column=Column(JSON, nullable=False))


class TicketStatus:
    NEW = "new"
    BRIEFED = "briefed"
    AWAITING_SELF_FIX = "awaiting_self_fix"
    ASSIGNED = "assigned"
    CLOSED = "closed"


class Company(SQLModel, table=True):
    __tablename__ = "companies"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    # The domain profile: industry, UI labels, self-fix allowed/forbidden, safety topics.
    profile: dict = json_dict()
    labor_rate_per_hour: float
    trip_fee: float
    currency: str = "USD"
    created_at: datetime = Field(default_factory=utcnow)


class User(SQLModel, table=True):
    """A person who logs in. Usernames are unique across all companies, since
    the login page doesn't ask which company you belong to."""

    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    company_id: int = Field(foreign_key="companies.id", index=True)
    username: str = Field(unique=True, index=True)
    password_hash: str
    name: str
    role: str  # "manager" or "technician"


class Site(SQLModel, table=True):
    __tablename__ = "sites"
    __table_args__ = (UniqueConstraint("company_id", "ref"),)

    id: int | None = Field(default=None, primary_key=True)
    company_id: int = Field(foreign_key="companies.id", index=True)
    ref: str
    name: str
    address: str = ""
    region: str = ""


class Product(SQLModel, table=True):
    """An equipment model (the company's `model_id`)."""

    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("company_id", "ref"),)

    id: int | None = Field(default=None, primary_key=True)
    company_id: int = Field(foreign_key="companies.id", index=True)
    ref: str
    manufacturer: str = ""
    model_name: str
    category: str = ""
    manual_file: str = ""


class Asset(SQLModel, table=True):
    """One physical unit installed at a site."""

    __tablename__ = "assets"
    __table_args__ = (UniqueConstraint("company_id", "ref"),)

    id: int | None = Field(default=None, primary_key=True)
    company_id: int = Field(foreign_key="companies.id", index=True)
    ref: str
    product_id: int = Field(foreign_key="products.id", index=True)
    site_id: int = Field(foreign_key="sites.id", index=True)
    serial: str = ""
    install_date: date | None = None
    last_service_date: date | None = None


class Part(SQLModel, table=True):
    __tablename__ = "parts"
    __table_args__ = (UniqueConstraint("company_id", "ref"),)

    id: int | None = Field(default=None, primary_key=True)
    company_id: int = Field(foreign_key="companies.id", index=True)
    ref: str
    name: str
    compatible_model_refs: list = json_list()
    unit_price: float = 0.0
    in_stock: int = 0


class KnownIssue(SQLModel, table=True):
    __tablename__ = "known_issues"
    __table_args__ = (UniqueConstraint("company_id", "ref"),)

    id: int | None = Field(default=None, primary_key=True)
    company_id: int = Field(foreign_key="companies.id", index=True)
    ref: str
    product_id: int = Field(foreign_key="products.id", index=True)
    title: str
    symptoms: str = ""
    root_cause: str = ""
    part_refs: list = json_list()
    avg_minutes: int = 0
    reporter_fixable: bool = False


class FixVariant(SQLModel, table=True):
    """One way of fixing a known issue.

    Success stats (attempts, successes, average minutes) are NOT stored here;
    they are computed from the tickets that point at this variant, so they can
    never drift out of sync with the ticket history.
    """

    __tablename__ = "fix_variants"

    id: int | None = Field(default=None, primary_key=True)
    company_id: int = Field(foreign_key="companies.id", index=True)
    known_issue_id: int = Field(foreign_key="known_issues.id", index=True)
    steps: list = json_list()
    # "import" = the fix listed in known_issues.csv
    # "history" = a different fix found in imported ticket history
    # "technician" = a new fix reported when closing a ticket in the app
    source: str = "import"
    created_at: datetime = Field(default_factory=utcnow)


class ManualChunk(SQLModel, table=True):
    """One section of a product manual. Searched through the manual_chunks_fts index."""

    __tablename__ = "manual_chunks"

    id: int | None = Field(default=None, primary_key=True)
    company_id: int = Field(foreign_key="companies.id", index=True)
    product_id: int = Field(foreign_key="products.id", index=True)
    manual_file: str
    position: int  # order within the manual
    section_title: str
    content: str


class Ticket(SQLModel, table=True):
    __tablename__ = "tickets"
    __table_args__ = (UniqueConstraint("company_id", "ref"),)

    id: int | None = Field(default=None, primary_key=True)
    company_id: int = Field(foreign_key="companies.id", index=True)
    ref: str
    site_id: int = Field(foreign_key="sites.id", index=True)
    asset_id: int | None = Field(default=None, foreign_key="assets.id", index=True)  # None = unknown
    product_id: int | None = Field(default=None, foreign_key="products.id", index=True)  # None = unknown
    description: str
    photo_path: str | None = None
    service_mode: str = "onsite"  # "remote" (guide the reporter by phone) or "onsite"
    status: str = TicketStatus.NEW
    source: str = "app"  # "app" or "imported"
    assigned_user_id: int | None = Field(default=None, foreign_key="users.id")
    answers: dict = json_dict()  # reporter answers keyed by question text
    created_at: datetime = Field(default_factory=utcnow)
    closed_at: datetime | None = None

    # Outcome, filled in when the ticket closes.
    known_issue_id: int | None = Field(default=None, foreign_key="known_issues.id", index=True)
    new_issue_text: str | None = None
    fix_variant_id: int | None = Field(default=None, foreign_key="fix_variants.id", index=True)
    used_recommended_fix: bool | None = None
    fix_description: str | None = None
    part_refs: list = json_list()
    minutes: int | None = None
    resolved: bool | None = None
    resolved_by_reporter: bool = False


class Brief(SQLModel, table=True):
    """One generated diagnostic brief. Every version is kept; the newest is shown."""

    __tablename__ = "briefs"

    id: int | None = Field(default=None, primary_key=True)
    company_id: int = Field(foreign_key="companies.id", index=True)
    ticket_id: int = Field(foreign_key="tickets.id", index=True)
    version: int = 1
    data: dict = json_dict()
    ai_mode: str = "mock"
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    is_fallback: bool = False
    created_at: datetime = Field(default_factory=utcnow)


class TicketEvent(SQLModel, table=True):
    """Append-only log of everything that happens to a ticket (chat messages included)."""

    __tablename__ = "ticket_events"

    id: int | None = Field(default=None, primary_key=True)
    company_id: int = Field(foreign_key="companies.id", index=True)
    ticket_id: int = Field(foreign_key="tickets.id", index=True)
    type: str  # created, brief_generated, brief_refined, self_fix_approved, ...
    actor_user_id: int | None = Field(default=None, foreign_key="users.id")
    payload: dict = json_dict()
    created_at: datetime = Field(default_factory=utcnow)
