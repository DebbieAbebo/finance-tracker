"""Command-line interface.

Built with Click. Each subcommand opens a connection via the standard
:func:`finance_tracker.db.connection_scope` context manager so we get
migrations + cleanup for free.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Optional

import click

from .config import load_settings
from .db import connection_scope
from .exceptions import DuplicateError, FinanceTrackerError, NotFoundError, ValidationError
from .models import (
    Account,
    AccountType,
    Cadence,
    Category,
    CategoryKind,
    RecurringTransaction,
    Transaction,
)
from .money import format_amount, from_cents
from .repositories.accounts import AccountRepository
from .repositories.categories import CategoryRepository
from .repositories.recurring import RecurringTransactionRepository
from .repositories.transactions import TransactionFilter, TransactionRepository
from .services.analytics import AnalyticsService
from .services.exporter import TransactionExporter
from .services.importer import CsvImporter
from .services.recurring import RecurringMaterializer
from .services.reporting import ReportingService
from .validation import (
    validate_account_name,
    validate_amount,
    validate_category_name,
    validate_currency,
    validate_date,
    validate_description,
    validate_notes,
)


# --- helpers --------------------------------------------------------------


def _abort(message: str) -> "click.NoReturn":
    click.echo(f"error: {message}", err=True)
    sys.exit(1)


def _print_table(rows: list[list[str]], headers: list[str]) -> None:
    if not rows:
        click.echo("(no rows)")
        return
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    click.echo(fmt.format(*headers))
    click.echo("  ".join("-" * w for w in widths))
    for row in rows:
        click.echo(fmt.format(*row))


def _resolve_account(repo: AccountRepository, name: str) -> Account:
    found = repo.find_by_name(name)
    if found is None:
        raise NotFoundError(f"account {name!r} not found")
    return found


def _resolve_category(repo: CategoryRepository, path: Optional[str]) -> Optional[Category]:
    if not path:
        return None
    found = repo.find_by_path(path)
    if found is None:
        raise NotFoundError(f"category {path!r} not found")
    return found


# --- root group -----------------------------------------------------------


@click.group()
@click.version_option(package_name="finance-tracker")
@click.pass_context
def main(ctx: click.Context) -> None:
    """Personal finance tracker."""
    ctx.ensure_object(dict)


# --- account commands -----------------------------------------------------


@main.group()
def account() -> None:
    """Manage accounts."""


@account.command("add")
@click.argument("name")
@click.option(
    "--type",
    "account_type",
    type=click.Choice([t.value for t in AccountType]),
    required=True,
)
@click.option("--currency", default="USD", show_default=True)
@click.option("--opening-balance", default="0", show_default=True)
def account_add(name: str, account_type: str, currency: str, opening_balance: str) -> None:
    """Create a new account."""
    try:
        clean_name = validate_account_name(name)
        clean_currency = validate_currency(currency)
        opening = validate_amount(opening_balance, allow_zero=True)
    except ValidationError as exc:
        _abort(str(exc))

    with connection_scope() as conn:
        try:
            saved = AccountRepository(conn).create(
                Account(
                    name=clean_name,
                    type=AccountType(account_type),
                    currency=clean_currency,
                    opening_balance_cents=opening,
                )
            )
        except DuplicateError as exc:
            _abort(str(exc))
    click.echo(f"created account {saved.name!r} (id={saved.id})")


@account.command("list")
@click.option("--all", "include_archived", is_flag=True, help="Include archived accounts")
def account_list(include_archived: bool) -> None:
    """List accounts and current balances."""
    with connection_scope() as conn:
        accounts = AccountRepository(conn).list(include_archived=include_archived)
        analytics = AnalyticsService(conn)
        rows = []
        for a in accounts:
            bal = analytics.account_balance(a.id)
            rows.append(
                [
                    str(a.id),
                    a.name,
                    a.type.value,
                    format_amount(bal.balance_cents, a.currency),
                    "yes" if a.archived else "",
                ]
            )
        _print_table(rows, ["id", "name", "type", "balance", "archived"])


@account.command("archive")
@click.argument("name")
def account_archive(name: str) -> None:
    """Archive an account by name."""
    with connection_scope() as conn:
        repo = AccountRepository(conn)
        try:
            a = _resolve_account(repo, name)
            repo.archive(a.id)
        except FinanceTrackerError as exc:
            _abort(str(exc))
    click.echo(f"archived {name!r}")


# --- category commands ---------------------------------------------------


@main.group()
def category() -> None:
    """Manage categories."""


@category.command("add")
@click.argument("name")
@click.option(
    "--kind",
    type=click.Choice([k.value for k in CategoryKind]),
    required=True,
)
@click.option("--parent", help="Dotted path of parent category")
def category_add(name: str, kind: str, parent: Optional[str]) -> None:
    try:
        clean_name = validate_category_name(name)
    except ValidationError as exc:
        _abort(str(exc))
    with connection_scope() as conn:
        repo = CategoryRepository(conn)
        try:
            parent_cat = _resolve_category(repo, parent)
            saved = repo.create(
                Category(
                    name=clean_name,
                    kind=CategoryKind(kind),
                    parent_id=parent_cat.id if parent_cat else None,
                )
            )
            full = repo.full_path(saved)
        except (DuplicateError, NotFoundError) as exc:
            _abort(str(exc))
    click.echo(f"created category {full} (id={saved.id})")


@category.command("list")
@click.option("--kind", type=click.Choice([k.value for k in CategoryKind]))
def category_list(kind: Optional[str]) -> None:
    with connection_scope() as conn:
        repo = CategoryRepository(conn)
        cats = repo.list(kind=CategoryKind(kind) if kind else None)
        rows = [
            [str(c.id), repo.full_path(c), c.kind.value]
            for c in cats
        ]
        _print_table(rows, ["id", "path", "kind"])


# --- transaction commands ------------------------------------------------


@main.group()
def transaction() -> None:
    """Manage individual transactions."""


@transaction.command("add")
@click.argument("amount")
@click.option("--account", "account_name", required=True)
@click.option("--category", "category_path")
@click.option("--description", default="")
@click.option("--notes")
@click.option("--date", "occurred_on", default=None, help="ISO date; defaults to today")
def transaction_add(
    amount: str,
    account_name: str,
    category_path: Optional[str],
    description: str,
    notes: Optional[str],
    occurred_on: Optional[str],
) -> None:
    try:
        amount_cents = abs(validate_amount(amount))
        occurred_date = validate_date(occurred_on) if occurred_on else date.today()
        clean_desc = validate_description(description)
        clean_notes = validate_notes(notes)
    except ValidationError as exc:
        _abort(str(exc))

    with connection_scope() as conn:
        accounts = AccountRepository(conn)
        cats = CategoryRepository(conn)
        try:
            account_ = _resolve_account(accounts, account_name)
            cat = _resolve_category(cats, category_path)
        except NotFoundError as exc:
            _abort(str(exc))

        saved = TransactionRepository(conn).create(
            Transaction(
                occurred_on=occurred_date,
                amount_cents=amount_cents,
                description=clean_desc,
                notes=clean_notes,
                account_id=account_.id,
                category_id=cat.id if cat else None,
            )
        )
    click.echo(f"created transaction id={saved.id}")


@transaction.command("list")
@click.option("--account", "account_name")
@click.option("--category", "category_path")
@click.option("--from", "date_from")
@click.option("--to", "date_to")
@click.option("--search")
@click.option("--limit", default=20, show_default=True, type=int)
def transaction_list(
    account_name: Optional[str],
    category_path: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
    search: Optional[str],
    limit: int,
) -> None:
    with connection_scope() as conn:
        accounts = AccountRepository(conn)
        cats = CategoryRepository(conn)
        try:
            account_ids = [_resolve_account(accounts, account_name).id] if account_name else None
            category_ids = None
            if category_path:
                cat = _resolve_category(cats, category_path)
                category_ids = cats.descendants_of(cat.id)
            d_from = validate_date(date_from, field="from") if date_from else None
            d_to = validate_date(date_to, field="to") if date_to else None
        except (NotFoundError, ValidationError) as exc:
            _abort(str(exc))

        criteria = TransactionFilter(
            account_ids=account_ids,
            category_ids=category_ids,
            date_from=d_from,
            date_to=d_to,
            search=search,
            limit=limit,
        )
        txns = TransactionRepository(conn).list(criteria)
        rows = []
        for t in txns:
            cat_name = ""
            if t.category_id is not None:
                try:
                    cat_name = cats.full_path(cats.get(t.category_id))
                except NotFoundError:
                    cat_name = ""
            rows.append(
                [
                    str(t.id),
                    t.occurred_on.isoformat(),
                    format_amount(t.amount_cents),
                    t.description[:40],
                    cat_name,
                ]
            )
        _print_table(rows, ["id", "date", "amount", "description", "category"])


@transaction.command("delete")
@click.argument("transaction_id", type=int)
def transaction_delete(transaction_id: int) -> None:
    with connection_scope() as conn:
        try:
            TransactionRepository(conn).delete(transaction_id)
        except NotFoundError as exc:
            _abort(str(exc))
    click.echo(f"deleted transaction {transaction_id}")


# --- report commands -----------------------------------------------------


@main.group()
def report() -> None:
    """Reports and analytics."""


@report.command("monthly")
@click.option("--from", "date_from", required=True)
@click.option("--to", "date_to", required=True)
def report_monthly(date_from: str, date_to: str) -> None:
    try:
        d_from = validate_date(date_from, field="from")
        d_to = validate_date(date_to, field="to")
    except ValidationError as exc:
        _abort(str(exc))

    with connection_scope() as conn:
        summaries = ReportingService(conn).monthly_summaries(start=d_from, end=d_to)

    rows = [
        [
            s.label,
            format_amount(s.income_cents),
            format_amount(s.expense_cents),
            format_amount(s.net_cents),
        ]
        for s in summaries
    ]
    _print_table(rows, ["month", "income", "expense", "net"])


@report.command("category")
@click.argument("path")
@click.option("--from", "date_from")
@click.option("--to", "date_to")
def report_category(path: str, date_from: Optional[str], date_to: Optional[str]) -> None:
    try:
        d_from = validate_date(date_from, field="from") if date_from else None
        d_to = validate_date(date_to, field="to") if date_to else None
    except ValidationError as exc:
        _abort(str(exc))
    with connection_scope() as conn:
        cats = CategoryRepository(conn)
        try:
            parent = _resolve_category(cats, path)
        except NotFoundError as exc:
            _abort(str(exc))
        breakdown = ReportingService(conn).category_breakdown(
            parent.id if parent else None, date_from=d_from, date_to=d_to
        )
    click.echo(f"{breakdown.parent_name}")
    click.echo(f"  own:    {format_amount(breakdown.own_total_cents)}")
    click.echo(f"  rolled: {format_amount(breakdown.rolled_up_total_cents)}")
    if breakdown.children:
        click.echo("  children:")
        rows = [
            [c.category_name, format_amount(c.total_cents), str(c.transaction_count)]
            for c in breakdown.children
        ]
        for row in rows:
            click.echo(f"    {row[0]:<20} {row[1]:>15}  ({row[2]} txn)")


@report.command("balances")
def report_balances() -> None:
    with connection_scope() as conn:
        balances = AnalyticsService(conn).all_balances()
    rows = [
        [
            str(b.account_id),
            b.account_name,
            format_amount(b.opening_balance_cents),
            format_amount(b.activity_cents),
            format_amount(b.balance_cents),
        ]
        for b in balances
    ]
    _print_table(rows, ["id", "account", "opening", "activity", "balance"])


# --- import / export -----------------------------------------------------


@main.command("import-csv")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, readable=True))
@click.option("--account", "account_name", required=True)
def import_csv(path: str, account_name: str) -> None:
    """Import transactions from a CSV file."""
    with connection_scope() as conn:
        try:
            result = CsvImporter(conn).import_file(Path(path), account_name=account_name)
        except (NotFoundError, ValidationError) as exc:
            _abort(str(exc))
    click.echo(f"imported: {result.imported}, skipped: {result.skipped}")
    for err in result.errors[:20]:
        click.echo(f"  {err}")
    if len(result.errors) > 20:
        click.echo(f"  ... and {len(result.errors) - 20} more")


@main.command("export")
@click.argument("path")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["csv", "json"]),
    default="csv",
    show_default=True,
)
@click.option("--account", "account_name")
@click.option("--from", "date_from")
@click.option("--to", "date_to")
def export(
    path: str,
    fmt: str,
    account_name: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
) -> None:
    """Export transactions to CSV or JSON."""
    with connection_scope() as conn:
        accounts = AccountRepository(conn)
        try:
            account_ids = [_resolve_account(accounts, account_name).id] if account_name else None
            d_from = validate_date(date_from, field="from") if date_from else None
            d_to = validate_date(date_to, field="to") if date_to else None
        except (NotFoundError, ValidationError) as exc:
            _abort(str(exc))

        criteria = TransactionFilter(
            account_ids=account_ids, date_from=d_from, date_to=d_to
        )
        exporter = TransactionExporter(conn)
        if fmt == "csv":
            n = exporter.to_csv(path, criteria=criteria)
        else:
            n = exporter.to_json(path, criteria=criteria)
    click.echo(f"exported {n} transactions to {path}")


# --- recurring -----------------------------------------------------------


@main.group()
def recurring() -> None:
    """Manage recurring (scheduled) transactions."""


@recurring.command("add")
@click.option("--name", required=True)
@click.option("--amount", required=True)
@click.option("--account", "account_name", required=True)
@click.option("--category", "category_path")
@click.option(
    "--cadence",
    type=click.Choice([c.value for c in Cadence]),
    required=True,
)
@click.option("--interval", default=1, show_default=True, type=int)
@click.option("--starts-on", required=True)
@click.option("--ends-on")
@click.option("--description", default="")
def recurring_add(
    name: str,
    amount: str,
    account_name: str,
    category_path: Optional[str],
    cadence: str,
    interval: int,
    starts_on: str,
    ends_on: Optional[str],
    description: str,
) -> None:
    try:
        amount_cents = abs(validate_amount(amount))
        starts_date = validate_date(starts_on, field="starts-on")
        ends_date = validate_date(ends_on, field="ends-on") if ends_on else None
        clean_desc = validate_description(description)
    except ValidationError as exc:
        _abort(str(exc))
    with connection_scope() as conn:
        accounts = AccountRepository(conn)
        cats = CategoryRepository(conn)
        try:
            account_ = _resolve_account(accounts, account_name)
            cat = _resolve_category(cats, category_path)
        except NotFoundError as exc:
            _abort(str(exc))
        saved = RecurringTransactionRepository(conn).create(
            RecurringTransaction(
                name=name,
                amount_cents=amount_cents,
                account_id=account_.id,
                category_id=cat.id if cat else None,
                cadence=Cadence(cadence),
                interval=interval,
                starts_on=starts_date,
                ends_on=ends_date,
                description=clean_desc,
            )
        )
    click.echo(f"created recurring {saved.name!r} (id={saved.id})")


@recurring.command("list")
def recurring_list() -> None:
    with connection_scope() as conn:
        items = RecurringTransactionRepository(conn).list()
    rows = [
        [
            str(r.id),
            r.name,
            format_amount(r.amount_cents),
            f"{r.cadence.value} x{r.interval}",
            r.starts_on.isoformat(),
            r.ends_on.isoformat() if r.ends_on else "",
            r.last_materialized_on.isoformat() if r.last_materialized_on else "",
            "yes" if r.active else "no",
        ]
        for r in items
    ]
    _print_table(
        rows,
        ["id", "name", "amount", "cadence", "starts", "ends", "last run", "active"],
    )


@recurring.command("run")
@click.option("--through", "through", help="ISO date; defaults to today")
def recurring_run(through: Optional[str]) -> None:
    """Materialize all due recurring transactions up through a date."""
    try:
        through_date = validate_date(through) if through else date.today()
    except ValidationError as exc:
        _abort(str(exc))
    with connection_scope() as conn:
        results = RecurringMaterializer(conn).run(through=through_date)
    if not results:
        click.echo("nothing to materialize")
        return
    for r in results:
        click.echo(f"  {r.template_name}: created {r.created} transactions")


# --- entry point ---------------------------------------------------------


if __name__ == "__main__":  # pragma: no cover
    main()
