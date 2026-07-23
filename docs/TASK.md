In case of not using SUPABASE_SERVICE_ROLE_KEY

Move from SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY logic to Supabase DB credentials:
DB_PASS=
DB_HOST=aws-1-ap-northeast-1.pooler.supabase.com
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres.eofjqxfsnpytsbonyvqs

## Migration plan: Supabase REST client → direct Postgres (DB_* creds)

**Scope:** `delivery-service` only. Replaces `supabase-py` (PostgREST over `SUPABASE_URL`/
`SUPABASE_SERVICE_ROLE_KEY`) with a direct Postgres connection to the same Supabase-hosted DB via
its connection pooler (`DB_HOST`/`DB_PORT`/`DB_NAME`/`DB_USER`/`DB_PASS`).

**Call sites affected (4 files use `supabase_client.get_client()`):**
- `src/modules/couriers/repository/courier_location_repository.py` — `.rpc("nearest_couriers", ...)`
- `src/modules/couriers/repository/courier_profile_repository.py` — `.table("couriers").select(...).maybe_single()`
- `src/modules/deliveries/repository/restaurant_lookup.py` — two `.table("venues").select(...).maybe_single()` calls
- `src/modules/couriers/service/gps_sync_scheduler.py` — `.rpc("upsert_courier_locations", ...)`

### Phase 1 — New DB client
- Add `psycopg[binary,pool]` (or `asyncpg`) to `requirements.txt`; drop `supabase==2.4.0` and
  `postgrest==0.16.1`.
- Replace `src/shared/db/supabase_client.py` with `shared/db/postgres_client.py`: a lazy-initialized
  `psycopg_pool.ConnectionPool` (or single connection factory) built from
  `DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASS`, matching the existing "fail lazily, not at import time"
  rule from `docs/PLAN.md`.
- Update `src/shared/config/env.py`: remove `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`, add `DB_HOST`,
  `DB_PORT` (default `5432`), `DB_NAME` (default `postgres`), `DB_USER`, `DB_PASS`.
- Update `.env.example` to match (empty/fake values only, per repo rule).

### Phase 2 — Rewrite repositories as raw SQL
PostgREST's `.table().select().eq().maybe_single()` and `.rpc()` have no direct equivalent over a raw
connection — convert each to plain SQL:
- `courier_profile_repository.get_profile`: `SELECT c.vehicle_type, u.display_name, u.phone FROM
  couriers c JOIN users u ON u.id = c.user_id WHERE c.id = %s` (confirm actual FK column name against
  `database_rel` migrations), fetch one row.
- `restaurant_lookup.get_restaurant_name` / `get_restaurant_location`: `SELECT name FROM venues WHERE
  id = %s`; `SELECT a.latitude, a.longitude FROM venues v JOIN addresses a ON ... WHERE v.id = %s`.
- `courier_location_repository.get_nearest_couriers` and `gps_sync_scheduler.sync_once`: the
  `nearest_couriers`/`upsert_courier_locations` Postgres functions don't exist yet in `database_rel`
  (documented open gap) — call them as plain functions (`SELECT * FROM nearest_couriers(%s,%s,%s)`)
  once they're added, or inline the PostGIS query directly instead of waiting on an RPC wrapper.
- Keep the same "never raise, log + return null/[] on failure" contract in all of these — just swap
  `except Exception` around PostgREST calls for the same around `cursor.execute`.

### Phase 3 — Infra & CI/CD wiring
- `infra/cloudformation.yml`: replace `SupabaseUrl`/`SupabaseServiceRoleKey` parameters with `DbHost`,
  `DbPort`, `DbName`, `DbUser`, `DbPass` (`NoEcho: true` on `DbPass`), pass through to the task
  definition's environment/secrets block.
- `.github/workflows/deploy.yml`: swap the `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` secrets refs for
  `DB_HOST`/`DB_PORT`/`DB_NAME`/`DB_USER`/`DB_PASS`.
- `docs/PHASE-9-PLAN.md` step 3/4 variable list: replace the two Supabase vars with the five DB vars in
  both the "single source variable list" and the Secrets/Variables split (`DB_PASS` → Secret;
  `DB_HOST/DB_PORT/DB_NAME/DB_USER` → Secret or Variable, no real values in repo).
- `infra/README.md`: update the env var list.

### Phase 4 — Tests
- No test currently mocks Supabase directly (repos are untested/fail-lazy), so `tests/conftest.py`
  needs no new fixture unless Phase 2 adds unit tests — if it does, mock the new
  `postgres_client.get_connection()` (or use a fake cursor) rather than hitting a real DB.

### Phase 5 — Docs cleanup (low priority, do last)
- Update remaining Supabase-client-specific wording in `docs/ARCHITECTURE.md`, `docs/PLAN.md` Phase 1,
  `README.md`, and `src/main.py`'s log line — note these describe *Supabase as the datastore* (still
  true) vs *supabase-py as the access method* (changing); only the latter needs rewording.

**Order of execution:** Phase 1 → 2 → 4 (so nothing breaks at import time) → 3 (infra, can land
independently) → 5.
