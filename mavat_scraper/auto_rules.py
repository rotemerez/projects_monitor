r"""
auto_rules.py — automatic exclusion rules for discovery candidates, derived from the
user's review decisions. Rules only touch OPEN candidates: rows the user already decided
(kept=1 or manually excluded) are never overridden, and every auto exclusion is tagged
'אוטומטי: ...' so it can be audited / reverted in the review page.

Applies to BOTH discovery sources:
  - mavat_discovery.db (this folder) — nationwide Mavat sweep candidates.
  - committee_scraper/committee_state.db — local-committee scraper candidates.
Before 2026-07-14 this only ran against mavat_discovery.db; committee candidates never got
any automatic exclusion, even though the same content-based rules (R1/Bedouin/energy) apply
there just as well, and the committee side has its own dominant pattern the Mavat side
doesn't: local-committee scrapers frequently surface national/regional plans (תמ"א, תמ"ל,
old municipal numbering like בי/###, חל/#/#) that are correctly tracked via the Mavat
discovery sweep instead — 83% of the open committee queue matched this pattern on
2026-07-14. R4 below encodes that as an automatic rule instead of requiring the user to
reject the same shape of candidate one by one every session. This rule is committee-only:
old-format/national plan numbers surfacing directly from a Mavat sweep are still legitimate
national plans worth tracking there (the user has explicitly kept several), so R4 must not
apply to mavat_discovery.db.

Round-1 rules (from decision comments, 2026-07-12):
  R1 name patterns — technical plans with no real development content:
     שינוי קו/קווי בניין, הסדרת מצב קיים, חלוקת מגרשים / איחוד וחלוקה ללא שינוי זכויות,
     שינויים מינוריים במצב מאושר (בריכות, מיקום חניות, חומרי גמר).
  R2 Bedouin settlements — only whole-neighborhood plans are of interest:
     town in the Bedouin list AND name does not contain 'שכונ' -> exclude.
  (R3 units<10 requires the units-tagging sweep — see mavat_discover.py --tag-units.)

Round-2 rules (2026-07-14, committee-only):
  R4 non-local plan-number format — plan number doesn't match the standard local-plan
     shape NNN-NNNNNNN (e.g. תמ"א/75/ב, בי/857/שופרסל, חל/1/ד-22) -> exclude, tracked via
     the Mavat discovery sweep instead of at the committee level.
  R5 test/placeholder entries — plan number is a run of one repeated digit, or the plan
     name/number contains 'בדיקה' / 'ניסיון' / 'נסיון' -> exclude as a scraper test row.

NOTE (2026-07-15): a batch of ~84 candidates with status "הכנת הודעה 77/78" (§77-78
pre-planning notice) were manually rejected on 2026-07-14, and it briefly looked like a
good auto-rule candidate. It is NOT: the user rejected those specific ones because they'd
already been reviewed before (stale duplicates resurfacing), not because the 77/78 notice
stage itself is uninteresting. The opposite is true — the user wants to keep seeing NEW
77/78-status candidates going forward, since that stage is an early signal of planning
intent. Do not add a status/name-based exclusion for "77-78" / "הכנת הודעה" here.

Usage:
  venv\Scripts\python.exe auto_rules.py                 # apply to both sources
  venv\Scripts\python.exe auto_rules.py --dry-run       # show what would be excluded
  venv\Scripts\python.exe auto_rules.py --revert        # undo ALL automatic exclusions (both sources)
  venv\Scripts\python.exe auto_rules.py --mavat-only    # skip committee_state.db
  venv\Scripts\python.exe auto_rules.py --committee-only
"""
import argparse
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
MAVAT_DB = HERE / "mavat_discovery.db"
COMMITTEE_DB = HERE.parent / "committee_scraper" / "committee_state.db"

NAME_RULES = [
    # accepts both קווי (double vav) and the equally common single-vav spelling קוי
    ("שינוי קו בניין", re.compile(r"שינוי קו(וי|י)? ה?בני[יי]ן|הקטנת קו(וי|י)? בני[יי]ן")),
    ("הסדרת מצב קיים", re.compile(r"הסדרת (ה?)מצב (ה?)קיים|לגליזציה")),
    ("חלוקה ללא שינוי זכויות", re.compile(
        r"איחוד ו?חלוקה|חלוקת מגרש(ים)?|פיצול מגרש")),
    ("שינויים מינוריים", re.compile(r"בריכ(ת|ות) שח[יי]ה|חומרי גמר|מיקום חני(ה|ות)")),
    # user round-2 (2026-07-12): single religious/public-building sites are not of interest
    ("מבנה דת נקודתי", re.compile(r"בית ה?כנסת|מקוו?ה|בית מדרש")),
    # found 2026-07-20 (605-1546118, בא"ש): a single detached/duplex-home lot's rights change.
    # Originally required "צמוד קרקע" + "דו/חד משפחתי" together, but a second case (422-
    # 0907329, אלעד — "...במגרש לבית צמוד קרקע") showed "צמוד קרקע" alone, without any family-
    # type qualifier, is already a strong enough single-dwelling signal on its own — broadened
    # same day. A genuine detached-home NEIGHBORHOOD/multi-unit plan still stays open
    # regardless, via the POSITIVE_SIGNAL override below ("תוספת יח\"ד"/"שכונ"/"מתחם").
    ("בית פרטי (צמוד קרקע)", re.compile(r"צמוד קרקע")),
]

# a name that signals real added development overrides any exclusion rule — such plans
# stay open for human review even if a technical-plan pattern also matches
POSITIVE_SIGNAL = re.compile(
    r"תוספת (יח\"?ד|זכויות|קומות|שטח)|הגדלת (זכויות|צפיפות|שטח)|שינוי י[יע]עוד|"
    r"פינוי ?[- ]?בינוי|התחדשות עירונית|מתחם|שכונ")

# Bedouin localities in the Negev (incl. Abu Basma / Neve Midbar / Al-Kasom villages)
BEDOUIN_TOWNS = ["רהט", "תל שבע", "חורה", "לקיה", "כסיפה", "ערערה בנגב", "שגב שלום",
                 "אבו בסמה", "נווה מדבר", "אל קסום", "ביר הדאג'", "אבו קורינאת",
                 "אבו קרינאת", "קסר אל סר", "קסר א-סר", "מכחול", "תראבין", "אום בטין",
                 "אל סייד", "מולדה", "דריג'את", "כוכלה", "אבו תלול", "סעוה", "חוואשלה"]

# R3 (units rule, needs the --tag-units sweep): exclude plans with neither >=10 housing
# units nor an interesting non-residential component. Interest list per user 2026-07-12:
# תעסוקה ומסחר, and also roads / railroads / parks ("maybe others" — shield broadly, the
# review page catches the rest). Applied ONLY to submission-stage statuses where unit
# quantities are declared — very early stages (77/78, Pre-Ruling, תסקיר) often have no
# quantities yet, so a missing tag there means nothing.
UNITS_RULE_STATUSES = {"בבדיקה תכנונית", "בבדיקת תנאי סף"}
INTEREST_SIGNAL = re.compile(
    r"תעסוקה|מסחר|תעשי[יה]|מלו[נן]|לוגיסט|משרדים|תיירות|מרכז אזרחי|"
    r"דרך|כביש|מחלף|רחוב|מסיל|רכבת|מטרו|תחבורה|"
    r"פארק|גן ציבורי|שצ.?פ|ציבור|חינוך|ספורט")

# Actively NOT of interest regardless of size (user 2026-07-12): solar energy fields,
# energy corridors and the like.
ENERGY_RULE = ("אנרגיה/תשתית חשמל", re.compile(
    r"סול[אר]רי|פוטו.?וולט|אגירת אנרגיה|מסדרון (תשתיות |)אנרגיה|אנרגיה מתחדשת|"
    r"קו מתח|מתח עליון|תחנת כוח|טורבינ|תחנת טרנספורמציה"))

# R4 (committee-only, 2026-07-14): standard local-plan number shape is NNN-NNNNNNN
# (e.g. 603-1218759). Anything else — תמ"א/תמ"ל/תת"ל national plans, old municipal
# numbering like בי/857/שופרסל or חל/1/ד-22 — is out of scope at the committee level;
# it's tracked (or trackable) via the Mavat discovery sweep instead.
LOCAL_PLAN_FORMAT_RX = re.compile(r"^\d{3}-\d{6,8}$")

# R5 (both sources): obvious scraper test/placeholder rows.
TEST_ROW_RX = re.compile(r"בדיקה|ני?סיון|^(\d)\1{3,}$")


def classify(name, location, status, units_ge10, units_rule, explanation=None,
             confirmed=False, commercial_signal=None):
    """Shared content-based classification (R1/R2/R3/energy). Returns a rule label or None.

    `explanation` (mavat_discovery.db only, via mavat_discover_units.py's detail fetch) is
    folded into the same text the name-pattern rules scan — some plans carry only a
    developer/company name (e.g. "ק.ב.ש יזמות בע"מ...") with the real content ("שינויים
    מינוריים במצב מאושר...") visible only in the description text, so name-only matching
    misses them (found 2026-07-16 from manually-excluded rows the rules should have caught).

    `confirmed`/`commercial_signal` (2026-07-20, from 102-1625912: "תוספת זכויות בניה"..., a
    single-lot addition confirmed at 1 unit that stayed open indefinitely): a REAL, fetched
    unit count under 10 excludes the plan even when POSITIVE_SIGNAL matches its name — a
    confirmed number is stronger evidence than a name heuristic — UNLESS the plan also carries
    a substantial commercial/employment/hotel component (`commercial_signal` set by
    mavat_discover_units.py from the plan's own quantities table or description).

    R3 NEVER fires without `confirmed=True` (2026-07-21, from 416-1448794: real units=15,
    excluded on its very first day off a meaningless default `units_ge10=0` placeholder,
    before mavat_discover_units.py ever got a chance to fetch its real count — every newly
    discovered row starts at units_ge10=0 by default, which is indistinguishable from a real
    confirmed low count unless `units_at`/`confirmed` says otherwise). An unconfirmed low
    `units_ge10` flag now does nothing at all — the plan just stays open until confirmed one
    way or the other, instead of being silently pre-excluded on a guess.
    """
    nm = name or ""
    text = f"{nm} {explanation}" if explanation else nm
    loc = location or ""
    if (units_rule and confirmed and not units_ge10 and status in UNITS_RULE_STATUSES
            and not commercial_signal and not INTEREST_SIGNAL.search(text)):
        return 'פחות מ-10 יח"ד וללא רכיב מעניין'
    if ENERGY_RULE[1].search(text):
        return ENERGY_RULE[0]
    if POSITIVE_SIGNAL.search(text):
        return None
    for label, rx in NAME_RULES:
        if rx.search(text):
            return label
    if any(t in loc for t in BEDOUIN_TOWNS):
        return "יישוב בדואי - לא תכנית שכונה"
    return None


def apply_to_mavat(dry_run, units_rule):
    con = sqlite3.connect(MAVAT_DB)
    cur = con.cursor()

    cols = {r[1] for r in cur.execute("PRAGMA table_info(discovered)")}
    if units_rule and "units_ge10" not in cols:
        sys.exit("R3 requested but no units_ge10 column — run "
                 "mavat_discover.py --tag-units 10 first")

    units_col = ", COALESCE(units_ge10,0)" if "units_ge10" in cols else ", 0"
    expl_col = ", explanation" if "explanation" in cols else ", NULL"
    units_at_col = ", units_at" if "units_at" in cols else ", NULL"
    comm_col = ", commercial_signal" if "commercial_signal" in cols else ", NULL"
    cur.execute(f"""SELECT plan, name, location, status{units_col}{expl_col}{units_at_col}
                           {comm_col} FROM discovered
                    WHERE target_status=1 AND in_vault=0 AND excluded=0
                      AND COALESCE(kept,0)=0""")
    rows = cur.fetchall()
    hits = {}
    for plan, name, location, status, units_ge10, explanation, units_at, commercial_signal in rows:
        rule = None
        if TEST_ROW_RX.search(name or "") or TEST_ROW_RX.match(plan or ""):
            rule = "רשומת בדיקה/דמה"
        else:
            rule = classify(name, location, status, units_ge10, units_rule, explanation,
                            confirmed=units_at is not None, commercial_signal=commercial_signal)
        if rule:
            hits[plan] = rule

    print(f"\n== mavat_discovery.db: {len(hits)} of {len(rows)} open candidates match ==")
    for rule, n in Counter(hits.values()).most_common():
        print(f"  {n:5d}  {rule}")

    if not dry_run:
        for plan, rule in hits.items():
            cur.execute("UPDATE discovered SET excluded=1, exclude_reason=? WHERE plan=?",
                        (f"אוטומטי: {rule}", plan))
        con.commit()

    cur.execute("SELECT COUNT(*) FROM discovered WHERE target_status=1 AND in_vault=0 "
                "AND excluded=0")
    remaining = cur.fetchone()[0]
    con.close()
    return len(hits), remaining


def apply_to_committee(dry_run):
    if not COMMITTEE_DB.exists():
        print("\n== committee_state.db not found, skipping ==")
        return 0, 0

    con = sqlite3.connect(COMMITTEE_DB)
    cur = con.cursor()
    cols = {r[1] for r in cur.execute("PRAGMA table_info(committee_candidates)")}
    obj_col = ", objectives" if "objectives" in cols else ", NULL"
    cur.execute(f"""SELECT id, plan_number, plan_name, status{obj_col} FROM committee_candidates
                   WHERE excluded=0 AND COALESCE(graduated,0)=0 AND COALESCE(kept,0)=0""")
    rows = cur.fetchall()
    hits = {}
    for cid, plan_number, plan_name, status, objectives in rows:
        pn = plan_number or ""
        rule = None
        if TEST_ROW_RX.search(plan_name or "") or TEST_ROW_RX.search(pn):
            rule = "רשומת בדיקה/דמה"
        elif not LOCAL_PLAN_FORMAT_RX.match(pn):
            rule = 'מספר תוכנית לא בפורמט מקומי (ארצי/ישן) - נעקב דרך סריקת מבא"ת'
        else:
            rule = classify(plan_name, "", status, False, False, explanation=objectives)
        if rule:
            hits[cid] = rule

    print(f"\n== committee_state.db: {len(hits)} of {len(rows)} open candidates match ==")
    for rule, n in Counter(hits.values()).most_common():
        print(f"  {n:5d}  {rule}")

    if not dry_run:
        for cid, rule in hits.items():
            cur.execute("""UPDATE committee_candidates SET excluded=1, exclude_reason=?
                           WHERE id=?""", (f"אוטומטי: {rule}", cid))
        con.commit()

    cur.execute("""SELECT COUNT(*) FROM committee_candidates
                   WHERE excluded=0 AND COALESCE(graduated,0)=0 AND COALESCE(kept,0)=0""")
    remaining = cur.fetchone()[0]
    con.close()
    return len(hits), remaining


def revert():
    n_mavat = n_committee = 0
    con = sqlite3.connect(MAVAT_DB)
    n_mavat = con.execute("UPDATE discovered SET excluded=0, exclude_reason=NULL "
                          "WHERE exclude_reason LIKE 'אוטומטי:%'").rowcount
    con.commit()
    con.close()
    if COMMITTEE_DB.exists():
        con = sqlite3.connect(COMMITTEE_DB)
        n_committee = con.execute(
            "UPDATE committee_candidates SET excluded=0, exclude_reason=NULL "
            "WHERE exclude_reason LIKE 'אוטומטי:%'").rowcount
        con.commit()
        con.close()
    print(f"[OK] reverted {n_mavat} mavat + {n_committee} committee automatic exclusions")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--units-rule", action="store_true",
                    help="also apply R3 (mavat only): exclude submission-stage residential "
                         "plans lacking the units_ge10 tag (requires --tag-units sweep)")
    ap.add_argument("--mavat-only", action="store_true")
    ap.add_argument("--committee-only", action="store_true")
    args = ap.parse_args()

    if args.revert:
        revert()
        return

    total_hits = 0
    if not args.committee_only:
        n, remaining_mavat = apply_to_mavat(args.dry_run, args.units_rule)
        total_hits += n
    if not args.mavat_only:
        n, remaining_committee = apply_to_committee(args.dry_run)
        total_hits += n

    label = "[DRY RUN] would exclude" if args.dry_run else "[OK] excluded"
    print(f"\n{label} {total_hits} candidates total across both sources")


if __name__ == "__main__":
    main()
