-- SipSpot API schema (Cloudflare D1) for a NEW database. Safe to run more than once.
-- Existing databases: apply migrations/ in order instead (see README).
-- No personal data is stored. Throttle keys are HMAC hashes that rotate
-- daily and are deleted shortly after they expire.

CREATE TABLE IF NOT EXISTS point_stats (
  point_id   TEXT PRIMARY KEY,           -- e.g. osm:node:123 or partner:partner-foo-ab12cd
  refills    INTEGER NOT NULL DEFAULT 0, -- "I filled up here" taps
  here       INTEGER NOT NULL DEFAULT 0, -- "Still here" votes
  gone       INTEGER NOT NULL DEFAULT 0, -- "Gone" votes
  last_here  TEXT,                       -- YYYY-MM-DD of the latest "Still here" vote
  last_gone  TEXT,                       -- YYYY-MM-DD of the latest "Gone" vote
  last_here_at INTEGER                   -- unix seconds of the latest "Still here" vote
);

-- Running refill totals, kept up to date on every write:
-- scope = 'uk' or 'city:<slug>'.
CREATE TABLE IF NOT EXISTS totals (
  scope   TEXT PRIMARY KEY,
  refills INTEGER NOT NULL DEFAULT 0
);

-- Short-lived anti-spam keys. key = kind:hash:... (hash = HMAC of IP + day).
CREATE TABLE IF NOT EXISTS throttle (
  key        TEXT PRIMARY KEY,
  hits       INTEGER NOT NULL DEFAULT 1,
  expires_at INTEGER NOT NULL            -- unix seconds
);
CREATE INDEX IF NOT EXISTS throttle_expires ON throttle (expires_at);

-- Anonymous "Not working" reports. Only the point, the reason and the time:
-- no IP address and no hash. Kept for a year, then deleted by the cron.
CREATE TABLE IF NOT EXISTS reports (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  point_id   TEXT NOT NULL,
  reason     TEXT NOT NULL CHECK (reason IN ('no_water', 'broken', 'dirty', 'locked', 'other')),
  created_at INTEGER NOT NULL            -- unix seconds
);
CREATE INDEX IF NOT EXISTS reports_point_time ON reports (point_id, created_at);
CREATE INDEX IF NOT EXISTS reports_time ON reports (created_at);
