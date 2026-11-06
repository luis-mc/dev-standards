---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
The runner pool hands a repository's database to its jobs. `db.env` now has `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD` and `PGDATABASE` beside `DATABASE_URL`, and the new `pool-db-env` step loads them into the job and masks the secrets. `pool-add-agent --db-createdb` gives the login `CREATEDB` for repositories that create their own databases. Each login can connect only to its own database. A rerun of `pool-add-agent` for an existing agent refreshes its `db.env` and isolation and keeps the password.
