"""
mavat_discover_units.py — fetch real unit counts for mavat_discovery.db candidates by
loading each plan's actual SV4 detail page, instead of relying on the site's search-side
"units >= N" filter (mavat_discover.py --tag-units).

Why this exists (2026-07-15): the --tag-units sweep is a one-off snapshot — it was run
once on 2026-07-12 and never since. Any plan whose real unit count only became visible on
Mavat's structured quantities table AFTER that date permanently sits at units_ge10=0 and
gets silently auto-excluded by auto_rules.py's R3 ("<10 units") even when the real count
is large (302-1493931: tagged units_ge10=0 from the stale sweep, actually 300 units per
the SV4 detail page — a real bug, not a policy edge case). Detail-page parsing (reusing
MavatSession.fetch_detail + mavat_diff.parse_quantities, the same machinery already used
for the daily MavatStatusDiff units baseline) gives a real, current number per plan
instead of a coarse boolean snapshot from whenever the last backfill happened.

This targets TWO groups of discovered rows, in this priority order:
  1. Candidates auto-excluded by R3 (exclude_reason starts with the units-rule text) —
     re-check and un-exclude any that turn out to have >=10 units after all.
  2. Open (not excluded, not kept) candidates in an early submission-stage status that
     have never had a detail fetch (units_at IS NULL) — get them a real number before R3
     ever has to guess from a stale flag.

Since 2026-07-16: also reads the plan's actual "דברי הסבר" (recExplanation.EXPLANATION on
the SV4 detail JSON — same fetch, no extra request) and un-excludes an R3-excluded
candidate even with units<10 when the text itself signals a sizeable project despite no
parseable unit count — e.g. 259-1374917 ("...רובע מגורים ותעסוקה... 106 ד' שטח חקלאי...")
had zero units on Mavat's structured quantities table, but its explanation clearly
describes a large residential-quarter proposal. Two independent signals, either is enough:
  - SIZEABLE_SIGNAL_RX: keyword phrases approved by the user 2026-07-16 (see the regex
    below for the exact list — quarter/new-neighborhood language, mixed residential+
    employment framing, expansion/population-growth framing, explicit "hundreds/thousands
    of units" prose).
  - a stated land area over 10 dunam (e.g. "106 ד'" / "50 דונם").
This runs as an ONGOING piece of the daily MavatDiscovery sweep (wired into
run_discovery.bat, after auto_rules.py so it sees that run's fresh R3 exclusions) — no
one-time catch-up sweep over the existing backlog was requested.

Does NOT re-run auto_rules.py itself — that's a separate, explicit step, so a human can
review what changed before candidates disappear from view again.

Usage:
  venv\\Scripts\\python.exe mavat_discover_units.py --limit 25              # both groups, batch of 25
  venv\\Scripts\\python.exe mavat_discover_units.py --limit 25 --headed
  venv\\Scripts\\python.exe mavat_discover_units.py --plan 302-1493931       # one specific plan
"""
import argparse
import re
import sqlite3
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from mavat_status import MavatSession
from mavat_diff import parse_quantities

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
MAVAT_DB = HERE / "mavat_discovery.db"
DELAY_S = 2.0
UNITS_LT10_REASON_PREFIX = 'אוטומטי: פחות מ-10'
EARLY_STATUSES = ("בבדיקה תכנונית", "בבדיקת תנאי סף")

# Approved 2026-07-16 — keyword signals of a sizeable residential/mixed development even
# when the description states no parseable unit count.
SIZEABLE_SIGNAL_RX = re.compile(
    r"רובע מגורים|שכונה חדשה|שכונת מגורים|עיר חדשה|הקמת שכונה|אזור מגורים חדש|"
    r"מגורים ותעסוקה|מתחם מגורים|הרחבת ה?ישוב|הרחבת ה?עיר|הגדלת האוכלוסייה|"
    r"תוכנית אזורית|מאות יח\"?ד|אלפי יח\"?ד|מרכז הייטק|פארק תעסוקה")
# Land-area figures ("106 ד'" / "50 דונם" / "12 דונמים") over 10 dunam.
DUNAM_RX = re.compile(r"(\d{1,6})\s*ד(?:ונ(?:ם|מים)|['׳])")

# Approved 2026-07-20 — a low confirmed residential unit count should still exclude via R3
# (auto_rules.py) even when the name matches POSITIVE_SIGNAL (e.g. "תוספת זכויות"), UNLESS
# the plan carries a substantial commercial/employment/hotel component — checked here via the
# plan's own quantities table (rsQuantities) and description text, not just name keywords.
COMMERCIAL_HOTEL_RX = re.compile(r"מסחר|תעסוקה|משרדים|מלון|חדרי מלון|תיירות|מרכז מסחרי")


def parse_explanation(detail):
    """Extract the plan's דברי הסבר free text from an SV4 detail JSON, or None."""
    rec = (detail or {}).get("recExplanation") or {}
    return rec.get("EXPLANATION") or None


def commercial_or_hotel_signal(quantities, explanation):
    """Return a short human-readable reason if the plan carries a real commercial/
    employment/hotel component (a non-zero quantity row, or a mention in the description),
    else None. A confirmed low residential-unit count only excludes a plan when this is
    also None — see classify() in auto_rules.py."""
    for item in quantities or []:
        desc = str(item.get("desc") or "")
        if COMMERCIAL_HOTEL_RX.search(desc) and (item.get("total") or 0) > 0:
            return f'{desc}: {item["total"]} {item.get("unit") or ""}'.strip()
    m = COMMERCIAL_HOTEL_RX.search(explanation or "")
    if m:
        return f'ביטוי בדברי ההסבר: "{m.group(0)}"'
    return None


def sizeable_signal(text):
    """Return a short human-readable reason if the explanation text signals a sizeable
    project despite no unit count, else None."""
    if not text:
        return None
    m = SIZEABLE_SIGNAL_RX.search(text)
    if m:
        return f'ביטוי בדברי ההסבר: "{m.group(0)}"'
    dunams = [int(n) for n in DUNAM_RX.findall(text)]
    big = [n for n in dunams if n > 10]
    if big:
        return f"שטח קרקע בדברי ההסבר: {max(big)} דונם"
    return None


def ensure_columns(con):
    for ddl in ("ALTER TABLE discovered ADD COLUMN units INTEGER",
                "ALTER TABLE discovered ADD COLUMN units_at TEXT",
                "ALTER TABLE discovered ADD COLUMN explanation TEXT",
                "ALTER TABLE discovered ADD COLUMN commercial_signal TEXT"):
        try:
            con.execute(ddl)
        except sqlite3.OperationalError:
            pass  # column already exists


def pick_targets(con, limit):
    """Freshly-scraped (never_checked, newest first) plans are prioritized ahead of the
    stale_tagged backlog (2026-07-21): since auto_rules.py's R3 no longer excludes on an
    unconfirmed units_ge10 flag (see auto_rules.py:classify), new discoveries stay open and
    visible either way — but confirming them quickly still matters, both to genuinely
    auto-exclude real small plans and to keep the "open" queue meaningful rather than full of
    still-unconfirmed rows. Previously stale_tagged ran first, which meant a large pre-existing
    backlog could starve same-day discoveries of a check for days (found from 416-1448794:
    real units=15, sat unconfirmed on its first day behind a 1,298-row backlog)."""
    cur = con.cursor()
    status_ph = ",".join("?" * len(EARLY_STATUSES))
    never_checked = cur.execute(f"""
        SELECT plan, mid FROM discovered
        WHERE target_status=1 AND in_vault=0 AND excluded=0 AND COALESCE(kept,0)=0
          AND status IN ({status_ph}) AND mid IS NOT NULL AND units_at IS NULL
        ORDER BY first_seen DESC""", EARLY_STATUSES).fetchall()
    stale_tagged = cur.execute(f"""
        SELECT plan, mid FROM discovered
        WHERE excluded=1 AND exclude_reason LIKE '{UNITS_LT10_REASON_PREFIX}%'
          AND mid IS NOT NULL AND units_at IS NULL
        ORDER BY first_seen""").fetchall()
    seen = set()
    targets = []
    for plan, mid in never_checked + stale_tagged:
        if plan not in seen:
            seen.add(plan)
            targets.append((plan, mid))
        if len(targets) >= limit:
            break
    return targets, len(stale_tagged)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=25,
                    help="max plans to detail-check this run (politeness cap)")
    ap.add_argument("--plan", help="check one specific plan number instead of a batch")
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()

    con = sqlite3.connect(MAVAT_DB)
    ensure_columns(con)

    if args.plan:
        row = con.execute("SELECT plan, mid FROM discovered WHERE plan=?",
                          (args.plan,)).fetchone()
        if not row or not row[1]:
            sys.exit(f"[!] {args.plan}: not found or has no mid")
        targets, stale_n = [row], 0
    else:
        targets, stale_n = pick_targets(con, args.limit)

    if not targets:
        print("[OK] nothing to check")
        return

    print(f"[..] checking {len(targets)} plans ({stale_n} were stale <10-unit exclusions)")

    now = time.strftime("%Y-%m-%d %H:%M:%S")
    checked = flipped = 0
    with sync_playwright() as p:
        session = MavatSession(p, headless=not args.headed)
        try:
            for i, (plan, mid) in enumerate(targets):
                if i:
                    time.sleep(DELAY_S)
                try:
                    detail = session.fetch_detail(mid)
                except Exception as e:
                    print(f"  [!] {plan}: fetch failed ({type(e).__name__}), reconnecting")
                    session.close()
                    session = MavatSession(p, headless=not args.headed)
                    continue
                if not detail:
                    print(f"  [!] {plan}: no detail response")
                    continue
                units, quantities = parse_quantities(detail)
                explanation = parse_explanation(detail)
                commercial_signal = commercial_or_hotel_signal(quantities, explanation)
                checked += 1
                con.execute("""UPDATE discovered SET units=?, units_at=?,
                               units_ge10=?, explanation=?, commercial_signal=? WHERE plan=?""",
                            (units, now, 1 if (units or 0) >= 10 else 0, explanation,
                             commercial_signal, plan))
                row = con.execute("""SELECT excluded, exclude_reason FROM discovered
                                     WHERE plan=?""", (plan,)).fetchone()
                is_r3_excluded = (row[0] == 1 and row[1]
                                  and row[1].startswith(UNITS_LT10_REASON_PREFIX))
                if is_r3_excluded and (units or 0) >= 10:
                    con.execute("""UPDATE discovered SET excluded=0, exclude_reason=NULL
                                   WHERE plan=?""", (plan,))
                    flipped += 1
                    print(f"  [FLIP] {plan}: real units={units} (was tagged <10) -> "
                          f"un-excluded")
                elif is_r3_excluded:
                    reason = sizeable_signal(explanation)
                    if reason:
                        con.execute("""UPDATE discovered SET excluded=0, exclude_reason=NULL
                                       WHERE plan=?""", (plan,))
                        flipped += 1
                        print(f"  [FLIP] {plan}: no unit count, but {reason} -> "
                              f"un-excluded")
                con.commit()
        finally:
            session.close()

    print(f"\n[OK] detail-checked {checked}/{len(targets)} plans; "
          f"{flipped} un-excluded (real units>=10 or a sizeable-project signal in the "
          f"description)")


if __name__ == "__main__":
    main()
