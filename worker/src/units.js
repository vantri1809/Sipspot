/**
 * Managed refill units: units a partner has bought or listed through SipSpot,
 * whose own staff check them by scanning a QR code on the unit.
 *
 * SipSpot does not check units itself. The Worker keeps the record, works out
 * whether a unit is due a check, hides it when something is wrong and alerts
 * the partner. This file holds the pure rules so they can be tested without D1.
 */

/* Report reasons that suggest the water may be unsafe. On a managed unit they
 * hide it from the map at once, until a member of staff checks it and clears it. */
export const URGENT_REASONS = new Set(["tampered", "taste_smell"]);

export const DEFAULT_CHECK_EVERY_HOURS = 24;
export const MIN_CHECK_EVERY_HOURS = 1;
export const MAX_CHECK_EVERY_HOURS = 24 * 7;

/* Re-send an overdue alert at most this often. */
export const OVERDUE_REALERT_SECONDS = 24 * 3600;

export function clampEveryHours(value) {
  const n = Math.floor(Number(value));
  if (!Number.isFinite(n)) return DEFAULT_CHECK_EVERY_HOURS;
  return Math.min(MAX_CHECK_EVERY_HOURS, Math.max(MIN_CHECK_EVERY_HOURS, n));
}

/**
 * Public status of a unit row at time nowS (unix seconds):
 *   "hidden"  - taken off the map (urgent report, staff found a problem, or
 *               missed checks for twice the interval)
 *   "overdue" - still shown, but flagged "Not checked recently"
 *   "ok"      - checked within its interval
 * A new unit that has never been checked counts from when it was registered.
 */
export function unitStatus(row, nowS) {
  if (!row) return null;
  if (row.status === "hidden") {
    return { status: "hidden", reason: row.hidden_reason || "reported" };
  }
  const everyS = clampEveryHours(row.check_every_hours) * 3600;
  const since = Number(row.last_check_at) || Number(row.created_at) || 0;
  const age = nowS - since;
  if (age > everyS * 2) return { status: "hidden", reason: "missed_checks" };
  if (age > everyS) return { status: "overdue" };
  return { status: "ok" };
}

/* Should the hourly job send (or re-send) an overdue alert for this unit? */
export function needsOverdueAlert(row, nowS) {
  const s = unitStatus(row, nowS);
  if (!s || (s.status !== "overdue" && !(s.status === "hidden" && s.reason === "missed_checks"))) return false;
  const last = Number(row.overdue_alerted_at) || 0;
  return nowS - last >= OVERDUE_REALERT_SECONDS;
}

export const HIDDEN_REASON_LABELS = {
  tampered: "Reported as looking tampered with",
  taste_smell: "Reported as tasting or smelling odd",
  staff: "Staff found a problem",
  missed_checks: "Not checked for too long",
  owner: "Taken off the map by SipSpot",
  reported: "Reported"
};

/* 128-bit random check key, hex. Only its SHA-256 is stored. */
export function newCheckKey() {
  const b = new Uint8Array(16);
  crypto.getRandomValues(b);
  return Array.from(b).map((x) => x.toString(16).padStart(2, "0")).join("");
}

export const CHECK_KEY_RE = /^[0-9a-f]{32}$/;
export const PARTNER_ID_RE = /^[a-z0-9][a-z0-9-]{0,59}$/;
export const EMAIL_RE = /^[^\s@<>"]{1,64}@[^\s@<>"]{1,190}\.[a-z]{2,24}$/i;
