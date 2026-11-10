# dbt project for PL Analyst

This dbt project adds a transformation layer on top of the raw SQLite tables in `pl_data.db`.

## Project structure

```text
dbt/
├── dbt_project.yml
├── profiles.yml
├── README.md
├── models/
│   ├── staging/
│   │   ├── _sources.yml
│   │   ├── stg_standings.sql
│   │   ├── stg_fixtures.sql
│   │   ├── stg_player_xg.sql
│   │   ├── stg_match_xg.sql
│   │   ├── stg_fixture_stats.sql
│   │   └── stg_shots.sql
│   └── marts/
│       ├── player_performance_summary.sql
│       ├── team_form.sql
│       └── xg_over_under_performance.sql
└── tests/
    └── schema.yml
```

## Prerequisites

- Python environment
- dbt installed
- dbt-sqlite adapter installed
- SQLite database file at `../pl_data.db` relative to this folder

Install the adapter:

```bash
pip install dbt-sqlite
```

## Run dbt

From the project root:

```bash
cd dbt

dbt debug --profiles-dir .
dbt run --profiles-dir .
dbt test --profiles-dir .
```

If you want to run from the repository root instead:

```bash
dbt run --project-dir dbt --profiles-dir dbt
dbt test --project-dir dbt --profiles-dir dbt
```

## Notes

- SQLite uses the `main` schema.
- The raw project tables are mapped in `models/staging/_sources.yml`.
- Staging models standardize names, clean nulls, and cast types for downstream marts.
- Mart models are built for player analytics, team form, and xG over/under performance.
