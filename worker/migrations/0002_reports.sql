-- 12 Nov 2026: "Not working" reports. Apply once to the database created on
-- 11 Nov 2026 (schema.sql already includes this for new databases):
--   npx wrangler d1 execute sipspot-api --remote --file=./migrations/0002_reports.sql
ALTER TABLE point_stats ADD COLUMN last_here_at INTEGER;

CREATE TABLE IF NOT EXISTS reports (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  point_id   TEXT NOT NULL,
  reason     TEXT NOT NULL CHECK (reason IN ('no_water', 'broken', 'dirty', 'locked', 'other')),
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS reports_point_time ON reports (point_id, created_at);
CREATE INDEX IF NOT EXISTS reports_time ON reports (created_at);
