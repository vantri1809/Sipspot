// Pure rules for managed units (no Worker needed): node --test test/units.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { unitStatus, needsOverdueAlert, clampEveryHours } from "../src/units.js";

const H = 3600;
const base = { status: "ok", check_every_hours: 24, created_at: 0, last_check_at: null };

test("status follows the check interval", () => {
  assert.equal(unitStatus(base, 23 * H).status, "ok");
  assert.equal(unitStatus(base, 25 * H).status, "overdue");
  assert.deepEqual(unitStatus(base, 49 * H), { status: "hidden", reason: "missed_checks" });
  assert.equal(unitStatus({ ...base, last_check_at: 40 * H }, 49 * H).status, "ok");
  assert.deepEqual(unitStatus({ ...base, status: "hidden", hidden_reason: "tampered" }, 1), { status: "hidden", reason: "tampered" });
});

test("overdue alerts are sent once a day at most", () => {
  assert.equal(needsOverdueAlert(base, 23 * H), false);
  assert.equal(needsOverdueAlert(base, 25 * H), true);
  assert.equal(needsOverdueAlert({ ...base, overdue_alerted_at: 25 * H }, 30 * H), false);
  assert.equal(needsOverdueAlert({ ...base, overdue_alerted_at: 25 * H }, 50 * H), true);
  assert.equal(needsOverdueAlert({ ...base, status: "hidden", hidden_reason: "tampered" }, 50 * H), false);
});

test("interval is clamped", () => {
  assert.equal(clampEveryHours("x"), 24);
  assert.equal(clampEveryHours(0), 1);
  assert.equal(clampEveryHours(9999), 168);
});
