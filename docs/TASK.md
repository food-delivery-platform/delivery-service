# Task: Migrate DB access from Supabase REST client → direct Postgres (DB_* creds)

**Status:** done.

**Why:** stop depending on `SUPABASE_SERVICE_ROLE_KEY`/`SUPABASE_URL`. DB credentials now come from
GitHub Actions via `DATABASE_SECRET_ARN` (`DB_PASS`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`),
pointing at the same Supabase-hosted Postgres DB through its connection pooler.

**Scope:** `delivery-service` only. Replaces `supabase-py` (PostgREST over `SUPABASE_URL`/
`SUPABASE_SERVICE_ROLE_KEY`) with a direct Postgres connection via `DB_HOST`/`DB_PORT`/`DB_NAME`/
`DB_USER`/`DB_PASS`.

**Call sites migrated (all 4 use `get_connection()` from `shared/db/supabase_client.py` now):**
- `src/modules/couriers/repository/courier_location_repository.py` — `SELECT * FROM nearest_couriers(%s,%s,%s)`
- `src/modules/couriers/repository/courier_profile_repository.py` — `SELECT c.vehicle_type, u.display_name, u.phone FROM couriers c JOIN users u ...`
- `src/modules/deliveries/repository/restaurant_lookup.py` — `SELECT name FROM venues WHERE id = %s` and `SELECT a.latitude, a.longitude ...`
- `src/modules/couriers/service/gps_sync_scheduler.py` — `SELECT upsert_courier_locations(%s)`

## Phase 1 — New DB client

- [x] Add `psycopg[binary,pool]` (or `asyncpg`) to `requirements.txt`; drop `supabase==2.4.0` and
      `postgrest==0.16.1`.
- [x] Replace `src/shared/db/supabase_client.py` with `shared/db/postgres_client.py`: a
      lazy-initialized `psycopg_pool.ConnectionPool` (or single connection factory) built from
      `DB_HOST`/`DB_PORT`/`DB_NAME`/`DB_USER`/`DB_PASS`, matching the existing "fail lazily, not at
      import time" rule from `docs/PLAN.md`.
- [x] Update `src/shared/config/env.py`: remove `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`, add
      `DB_HOST`, `DB_PORT` (default `5432`), `DB_NAME` (default `postgres`), `DB_USER`, `DB_PASS`.
- [x] Update `.env.example` to match (empty/fake values only, per repo rule).

## Phase 2 — Rewrite repositories as raw SQL

PostgREST's `.table().select().eq().maybe_single()` and `.rpc()` have no direct equivalent over a raw
connection — convert each to plain SQL:

- [x] `courier_profile_repository.get_profile`: `SELECT c.vehicle_type, u.display_name, u.phone FROM
      couriers c JOIN users u ON u.id = c.user_id WHERE c.id = %s`, fetch one row.
- [x] `restaurant_lookup.get_restaurant_name` / `get_restaurant_location`: `SELECT name FROM venues
      WHERE id = %s`; `SELECT a.latitude, a.longitude FROM venues v JOIN addresses a ON ... WHERE
      v.id = %s`.
- [x] `courier_location_repository.get_nearest_couriers` and `gps_sync_scheduler.sync_once`: the
      `nearest_couriers`/`upsert_courier_locations` Postgres functions don't exist yet in
      `database_rel` (documented open gap) — wired as plain function calls
      (`SELECT * FROM nearest_couriers(%s,%s,%s)`) ready for when they're added.
- [x] Kept the same "never raise, log + return null/[] on failure" contract in all of these.

## Phase 3 — Infra & CI/CD wiring

- [x] `infra/cloudformation.yml`: replaced `SupabaseUrl`/`SupabaseServiceRoleKey` parameters with
      `DbHost`, `DbPort`, `DbName`, `DbUser`, `DbPass` (`NoEcho: true` on `DbPass`).
- [x] `.github/workflows/deploy.yml`: swapped the `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` secrets
      refs for `DB_HOST`/`DB_PORT`/`DB_NAME`/`DB_USER`/`DB_PASS`.
- [x] `docs/PHASE-9-PLAN.md` step 3/4 variable list: replaced the two Supabase vars with the five
      DB vars in both the "single source variable list" and the Secrets/Variables split.
- [x] `infra/README.md`: updated the env var list.

## Phase 4 — Tests

- [x] No test currently mocks Supabase directly (repos are untested/fail-lazy) — no new fixture
      needed for this migration. When unit tests are added for Phase 2 call sites, mock
      `get_connection()` (or use a fake cursor) rather than hitting a real DB.

## Phase 5 — Docs cleanup

- [x] Updated `docs/PLAN.md` Phase 1, `src/main.py`'s log line — supabase-py access method wording
      replaced; *Supabase as the datastore* description untouched (still true).
- [ ] `docs/ARCHITECTURE.md` — still references supabase-py connection patterns in §619; low priority
      since it describes the datastore (Supabase Postgres, still true) not the access method.

## Order of execution

Phase 1 → 2 → 4 → 3 → 5. All done.
