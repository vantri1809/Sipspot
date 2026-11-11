-- SipSpot API schema (Cloudflare D1). Safe to run more than once.
-- No personal data is stored. Throttle keys are HMAC hashes that rotate
-- daily and are deleted shortly after they expire.

CREATE TABLE IF NOT EXISTS point_stats (
  point_id   TEXT PRIMARY KEY,           -- e.g. osm:node:123 or partner:partner-foo-ab12cd
  refills    INTEGER NOT NULL DEFAULT 0, -- "I filled up here" taps
  here       INTEGER NOT NULL DEFAULT 0, -- "Still here" votes
  gone       INTEGER NOT NULL DEFAULT 0, -- "Gone" votes
  last_here  TEXT,                       -- YYYY-MM-DD of the latest "Still here" vote
  last_gone  TEXT                        -- YYYY-MM-DD of the latest "Gone" vote
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
