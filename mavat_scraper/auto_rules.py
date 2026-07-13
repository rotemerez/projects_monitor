r"""
auto_rules.py — automatic exclusion rules for discovery candidates, derived from the
user's review decisions (2026-07-12 round 1). Rules only touch OPEN candidates: rows the
user already decided (kept=1 or manually excluded) are never overridden, and every auto
exclusion is tagged 'אוטומטי: ...' so it can be audited / reverted in the review page.

Round-1 rules (from decision comments):
  R1 name patterns — technical plans with no real development content:
     שינוי קו/קווי בניין, הסדרת מצב קיים, חלוקת מגרשים / איחוד וחלוקה ללא שינוי זכויות,
     שינויים מינוריים במצב מאושר (בריכות, מיקום חניות, חומרי גמר).
  R2 Bedouin settlements — only whole-neighborhood plans are of interest:
     town in the Bedouin list AND name does not contain 'שכונ' -> exclude.
  (R3 units<10 requires the units-tagging sweep — see mavat_discover.py --tag-units.)

Usage:
  venv\Scripts\python.exe auto_rules.py            # apply
  venv\Scripts\python.exe auto_rules.py --dry-run  # show what would be excluded
  venv\Scripts\python.exe auto_rules.py --revert   # undo ALL automatic exclusions
"""
import argparse
import re
import sqlite3
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DB = Path(__file__).resolve().parent / "mavat_discovery.db"

NAME_RULES = [
    ("שינוי קו בניין", re.compile(r"שינוי קו(וי)? ה?בני[יי]ן|הקטנת קו(וי)? בני[יי]ן")),
    ("הסדרת מצב קיים", re.compile(r"הסדרת (ה?)מצב (ה?)קיים|לגליזציה")),
    ("חלוקה ללא שינוי זכויות", re.compile(
        r"איחוד ו?חלוקה|חלוקת מגרש(ים)?|פיצול מגרש")),
    ("שינויים מינוריים", re.compile(r"בריכ(ת|ות) שח[יי]ה|חומרי גמר|מיקום חני(ה|ות)")),
    # user round-2 (2026-07-12): single religious/public-building sites are not of interest
    ("מבנה דת נקודתי", re.compile(r"בית ה?כנסת|מקוו?ה|בית מדרש")),
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--units-rule", action="store_true",
                    help="also apply R3: exclude submission-stage residential plans "
                         "lacking the units_ge10 tag (requires --tag-units sweep)")
    args = ap.parse_args()

    con = sqlite3.connect(DB)
    cur = con.cursor()

    if args.revert:
        n = cur.execute("UPDATE discovered SET excluded=0, exclude_reason=NULL "
                        "WHERE exclude_reason LIKE 'אוטומטי:%'").rowcount
        con.commit()
        print(f"[OK] reverted {n} automatic exclusions")
        return

    has_units_col = any(r[1] == "units_ge10"
                        for r in cur.execute("PRAGMA table_info(discovered)"))
    if args.units_rule and not has_units_col:
        sys.exit("R3 requested but no units_ge10 column — run "
                 "mavat_discover.py --tag-units 10 first")

    units_col = ", COALESCE(units_ge10,0)" if has_units_col else ", 0"
    cur.execute(f"""SELECT plan, name, location, status{units_col} FROM discovered
                    WHERE target_status=1 AND in_vault=0 AND excluded=0
                      AND COALESCE(kept,0)=0""")
    rows = cur.fetchall()
    hits = {}   # plan -> rule label
    for plan, name, location, status, units_ge10 in rows:
        nm = name or ""
        loc = location or ""
        rule = None
        if ENERGY_RULE[1].search(nm):
            rule = ENERGY_RULE[0]   # not of interest regardless of size/signals
        elif not POSITIVE_SIGNAL.search(nm):
            for label, rx in NAME_RULES:
                if rx.search(nm):
                    rule = label
                    break
            if rule is None and any(t in loc for t in BEDOUIN_TOWNS):
                rule = "יישוב בדואי - לא תכנית שכונה"
            if (rule is None and args.units_rule and not units_ge10
                    and status in UNITS_RULE_STATUSES
                    and not INTEREST_SIGNAL.search(nm)):
                rule = 'פחות מ-10 יח"ד וללא רכיב מעניין'
        if rule:
            hits[plan] = rule

    from collections import Counter
    counts = Counter(hits.values())
    print(f"{'[DRY RUN] ' if args.dry_run else ''}auto-exclusion matches "
          f"({len(hits)} of {len(rows)} open candidates):")
    for rule, n in counts.most_common():
        print(f"  {n:5d}  {rule}")

    if args.dry_run:
        print("\nsample matches:")
        shown = Counter()
        for plan, rule in hits.items():
            if shown[rule] < 4:
                cur.execute("SELECT name, location FROM discovered WHERE plan=?", (plan,))
                nm, loc = cur.fetchone()
                print(f"  [{rule}] {plan}  {loc}  |  {nm}")
                shown[rule] += 1
        return

    for plan, rule in hits.items():
        cur.execute("UPDATE discovered SET excluded=1, exclude_reason=? WHERE plan=?",
                    (f"אוטומטי: {rule}", plan))
    con.commit()
    cur.execute("SELECT COUNT(*) FROM discovered WHERE target_status=1 AND in_vault=0 "
                "AND excluded=0")
    print(f"\n[OK] applied; open candidates remaining: {cur.fetchone()[0]}")


if __name__ == "__main__":
    main()
