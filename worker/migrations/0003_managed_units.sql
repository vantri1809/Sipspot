-- Managed units and staff check-ins. Apply once to the existing database
-- (schema.sql already includes this for new databases):
--   npx wrangler d1 execute sipspot-api --remote --file=./migrations/0003_managed_units.sql

-- 1. Allow the two new "Not working" reasons. SQLite cannot change a CHECK
--    constraint in place, so the reports table is rebuilt with its rows kept.
CREATE TABLE reports_new (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  point_id   TEXT NOT NULL,
  reason     TEXT NOT NULL CHECK (reason IN ('no_water', 'broken', 'dirty', 'locked', 'tampered', 'taste_smell', 'other')),
  created_at INTEGER NOT NULL
);
INSERT INTO reports_new (id, point_id, reason, created_at)
  SELECT id, point_id, reason, created_at FROM reports;
DROP TABLE reports;
ALTER TABLE reports_new RENAME TO reports;
CREATE INDEX IF NOT EXISTS reports_point_time ON reports (point_id, created_at);
CREATE INDEX IF NOT EXISTS reports_time ON reports (created_at);

-- 2. Partners that own managed units. alert_email gets "check overdue" and
--    "taken off the map" emails. This is business contact data, not visitor data.
CREATE TABLE IF NOT EXISTS partners (
  id          TEXT PRIMARY KEY,          -- e.g. three-spires
  name        TEXT NOT NULL,
  alert_email TEXT,
  created_at  INTEGER NOT NULL
);

-- 3. Managed units. point_id is the map id (partner:... or osm:...).
--    Only a SHA-256 of the staff check key is stored.
CREATE TABLE IF NOT EXISTS units (
  point_id           TEXT PRIMARY KEY,
  partner_id         TEXT NOT NULL REFERENCES partners(id),
  label              TEXT,               -- staff-facing name, e.g. "Unit 1, Market St entrance"
  check_key_hash     TEXT NOT NULL,
  check_every_hours  INTEGER NOT NULL DEFAULT 24,
  status             TEXT NOT NULL DEFAULT 'ok' CHECK (status IN ('ok', 'hidden')),
  hidden_reason      TEXT,
  hidden_at          INTEGER,
  last_check_at      INTEGER,
  overdue_alerted_at INTEGER,
  created_at         INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS units_partner ON units (partner_id);

-- 4. Staff check log: the record a partner can show that checks happened.
--    Unit, outcome and time only. Kept for two years.
CREATE TABLE IF NOT EXISTS checks (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  point_id   TEXT NOT NULL,
  outcome    TEXT NOT NULL CHECK (outcome IN ('ok', 'problem')),
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS checks_point_time ON checks (point_id, created_at);
