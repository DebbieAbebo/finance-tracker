# finance-tracker

A small personal finance tracker. Stores accounts, categories, and
transactions in a local SQLite database and exposes a CLI for entering,
reviewing, and reporting on data.

Built primarily for my own household budgeting. The data model is
generic enough to be useful for anyone who wants to track spending
without paying a SaaS subscription.

```
$ finance report balances
id  account   opening        activity        balance
--  --------  -------------  -------------   --------------
1   Checking  USD 2,000.00   -USD 2,557.82   -USD 557.82
2   Savings   USD 10,000.00  USD 0.00        USD 10,000.00

$ finance report monthly --from 2026-01-01 --to 2026-04-30
month    income        expense       net
-------  ------------  ------------  ------------
2026-01  USD 0.00      USD 1,500.00  -USD 1,500.00
2026-02  USD 0.00      USD 1,500.00  -USD 1,500.00
2026-03  USD 0.00      USD 1,500.00  -USD 1,500.00
2026-04  USD 3,500.00  USD 1,557.82  USD 1,942.18
```

## Design goals

- **No cloud.** Data lives in a single SQLite file.
- **Tiny dependency footprint.** `click` and `python-dateutil`. That's
  it at runtime.
- **Lossless CSV/JSON round-trips** so data isn't trapped here forever.
- **Reasonable reporting** without dropping into a spreadsheet —
  monthly summaries, category breakdowns that roll up across
  descendants, and account balances.

## Install

From source:

```bash
git clone <repo>
cd finance-tracker
pip install -e ".[dev]"   # editable install with test deps
```

The `finance` console script is installed as a `[project.scripts]`
entry point and is on `$PATH` after install.

## Concepts

- **Account** — a place where money lives: checking, savings, credit
  card, cash, brokerage, etc.
- **Category** — what the money is for. Hierarchical: `Food` can have
  `Food.Groceries` and `Food.Restaurants`. Each category has a `kind`
  (`income`, `expense`, or `transfer`) which determines whether reports
  treat its amounts as positive or negative.
- **Transaction** — a single dated movement of money in or out of one
  account, optionally tagged with a category.
- **Recurring transaction** — a template (rent, paycheck, subscription)
  that materializes into concrete transactions on a fixed cadence.

Money is stored internally as integer minor units (cents for USD) and
surfaced as `Decimal` so floating-point drift never affects balances.

## Quick tour

```bash
# Set up two accounts and a few categories
finance account add Checking --type checking --opening-balance 2000
finance account add Savings  --type savings  --opening-balance 10000
finance category add Food   --kind expense
finance category add Groceries --kind expense --parent Food
finance category add Salary --kind income

# Record a few transactions
finance transaction add 3500  --account Checking --category Salary    \
    --description "April salary" --date 2026-04-01
finance transaction add 45.32 --account Checking --category Groceries \
    --description "Whole Foods"  --date 2026-04-03
finance transaction add 12.50 --account Checking --category Food      \
    --description "Coffee"

# Set up rent as a recurring expense and materialize the back-fill
finance recurring add --name Rent --amount 1500 --account Checking \
    --category Food --cadence monthly --starts-on 2026-01-01
finance recurring run --through 2026-04-30

# See where you are
finance report balances
finance report monthly --from 2026-01-01 --to 2026-04-30
finance report category Food

# Search and filter
finance transaction list --account Checking --from 2026-04-01 --search Whole

# Round-trip via CSV
finance export /tmp/april.csv --account Checking \
    --from 2026-04-01 --to 2026-04-30
finance import-csv /tmp/april.csv --account Checking
```

### Category lookup is forgiving

If a category name is unique anywhere in the tree, the leaf name is
enough — `--category Groceries` resolves to `Food.Groceries`. If it's
ambiguous (two `Misc` categories under different parents), you have to
spell out the dotted path.

## Configuration

Environment variables, with defaults:

| Variable                | Default                                       | Purpose                                   |
| ----------------------- | --------------------------------------------- | ----------------------------------------- |
| `FINANCE_DATABASE_PATH` | `~/.local/share/finance-tracker/finance.db`   | Where the SQLite file lives               |
| `FINANCE_DEBUG`         | unset                                         | Enable extra diagnostic output            |
| `XDG_DATA_HOME`         | `~/.local/share`                              | Honored when computing the default path   |

## CSV format

The importer expects a header row with at minimum:

```
date,amount,description
```

Optional columns: `category` (a dotted path like `Food.Groceries`),
`notes`. Unknown categories cause a row to be skipped with an error
rather than silently created — that's an explicit choice so a typo
doesn't pollute the category tree.

The exporter emits `date,amount,description,category,notes,account` so
an export → import is lossless.

## Architecture

```
src/finance_tracker/
├── cli.py                  # Click commands
├── config.py               # Settings from env
├── db.py                   # Connection helper + migration runner
├── exceptions.py           # Domain exceptions
├── money.py                # Decimal ↔ integer-cents helpers
├── validation.py           # Input validation
├── models/                 # Dataclasses mirroring tables
│   ├── account.py
│   ├── category.py
│   ├── transaction.py
│   └── recurring.py
├── repositories/           # SQL data access, one per entity
│   ├── _helpers.py
│   ├── accounts.py
│   ├── categories.py
│   ├── transactions.py
│   └── recurring.py
└── services/               # Business logic on top of repositories
    ├── analytics.py
    ├── reporting.py
    ├── importer.py
    ├── exporter.py
    └── recurring.py
```

A **repository** owns the SQL for one entity. A **service** orchestrates
repositories and applies business rules (e.g. recurring materialization
walks templates forward, the importer validates rows then bulk-inserts,
analytics drops into SQL for set-based aggregation).

### Database

SQLite, migrated by a small inline runner in `db.py`. Each migration is
a `(version, sql)` tuple appended to a list — never edit a previous
entry. The runner records each version in a `schema_version` table and
applies them inside a transaction.

If you switch backends later, that one module owns the connection
factory, so it's the place to change.

## Development

```bash
make dev-install     # editable install + dev deps
make test            # full test suite
make test-verbose    # the same, with verbose output
make smoke           # end-to-end CLI run against a temp database
make clean           # remove build / cache artifacts
```

## Docker

```bash
docker compose run --rm finance --help
docker compose run --rm finance account add Checking --type checking
```

The image stores its database in the `/data` volume; `docker-compose.yml`
mounts a named volume `finance-data` to keep state across runs.

`.git` is intentionally **not** in `.dockerignore` so version-stamping
tooling has access to the history during builds.

## Tests

The suite uses stdlib `unittest` with a `TempDatabase` helper that gives
each test a fresh, fully migrated SQLite file. Run with:

```bash
PYTHONPATH=src python -m unittest discover -s tests -t .
```

Coverage spans models, all four repositories, validation, money
conversion, migrations, analytics, reporting, recurring materialization,
the CSV importer (including a round-trip through the exporter), and
end-to-end CLI workflows via `click.testing.CliRunner`.

## Status / roadmap

Working day-to-day for me. Things I'd still like to add:

- Multi-currency conversion in reports (currently amounts are added
  naively across accounts in different currencies).
- Budget targets per category and an "over budget" report.
- A simple HTML report exporter.

PRs welcome but I'm slow to review — this is a personal project.

## License

MIT.
