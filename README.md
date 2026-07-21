# Projects Vault → DB & Mavat Status Automation

Tracking of construction/planning projects (תכניות) across Israeli neighborhoods, and the
automation that keeps their planning status up to date.

**Last Updated:** 2026-07-08

---

## What this is

A two-part system:

1. **Vault → DB pipeline** — an Obsidian vault (one Markdown file per neighborhood, one
   `#### <name>` block per project, Dataview inline fields `שדה:: ערך`) is parsed into a
   structured SQLite database (`projects.db`, ~10,507 projects). The vault is the **human
   source of truth**; the DB is the **analysis/automation layer**.

2. **Mavat status automation** (`mavat_scraper/`) — a daily job that looks up each project's
   plan number on מנהל התכנון (mavat.iplan.gov.il), reads the current planning status + date,
   and diffs it against what we last saw → flags plans that advanced a stage. Also intended to
   discover *new* plans in the projects' towns. See [docs/MAVAT_AUTOMATION.md](docs/MAVAT_AUTOMATION.md).

## Quick links

| Doc | Purpose |
|---|---|
| [docs/TRAINEE_GUIDE.md](docs/TRAINEE_GUIDE.md) | **Start here** — full walkthrough of what the system does and how the pieces fit together |
| [SETUP.md](SETUP.md) | Environment + how to run the pipeline and the scraper |
| [next_steps.md](next_steps.md) | Live task tracking / roadmap |
| [CLAUDE.md](CLAUDE.md) | Session notes, conventions, project history |
| [docs/DATA_FLOW.md](docs/DATA_FLOW.md) | End-to-end architecture (vault → DB → automation) |
| [docs/SCHEMAS.md](docs/SCHEMAS.md) | DB schema + the 33-code status vocabulary |
| [docs/MAVAT_AUTOMATION.md](docs/MAVAT_AUTOMATION.md) | Mavat scraper: findings, verdict, how to run |
| [docs/framework_spec.md](docs/framework_spec.md) | Authoritative spec (Hebrew): schema, parsing rules, source→field mapping |
| [docs/BUG_REFERENCE.md](docs/BUG_REFERENCE.md) | Known issues + root causes |
| [docs/VERSION_LOG.md](docs/VERSION_LOG.md) | Release/change history |

## Core files

Pipeline code lives in `scripts/`:
- `scripts/refresh_db.py` — the live pipeline: reads the structured vault → builds `projects.db`.
- `scripts/build_db.py` — core logic (stage vocabulary, date/tender/number parsing). Imported by `refresh_db.py`.
- `scripts/structure_vault.py` — one-time migration that produced the structured vault.

Outputs at repo root: `projects.db`, `projects.csv`, `projects.xlsx`.

> The `RefreshProjectsDB` scheduled task (daily 06:00) references `scripts\refresh_db.py` and
> `projects.db` by absolute path. If you move them, update the task in the same step — see
> [SETUP.md](SETUP.md).
