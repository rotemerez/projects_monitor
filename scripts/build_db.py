#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build a normalized SQLite DB from projects.csv (output of parse_vault.py).

Tables:
  projects        one row per project (core + derived project_type)
  status_events   (stage_code, date) events parsed from the status line
  tenders         RMI land tenders (number/district/dates/winner)
  signatures      urban-renewal consent % time-series
  value_history   superseded (struck-through) values

Usage:
  python -X utf8 build_db.py "<projects.csv>" "<out.db>"
"""

import os, re, sys, csv, sqlite3

CSV_PATH = sys.argv[1] if len(sys.argv) > 1 else "projects.csv"
DB_PATH  = sys.argv[2] if len(sys.argv) > 2 else "projects.db"

# ----------------------------------------------------------------------
# controlled stage vocabulary: canonical code -> list of text variants
# (order matters: matched longest-variant-first)
# ----------------------------------------------------------------------
STAGE_VOCAB = [
    ("owner_engagement",  ["התקשרות עם בעלי זכויות", "התקשרות בהסכם", "מכתב כוונות", "השגת רוב",
                            "רוב הדיירים", "רוב דרוש", "הגעה לרוב", "מו\"מ", "משא ומתן",
                            "טרום החתמה", "תחילת החתמות", "תחילת החתמה", "החתמות", "החתמה"]),
    ("developer_selection",["זכייה במכרז בעלי זכויות", "זכייה במכרז דיירים", "מכרז דיירים",
                            "בחירה על ידי בעלי זכויות", "בחירה לביצוע על ידי בעלים",
                            "בחירה על ידי בעלים", "בחירה על ידי דיירים", "בחירה על ידי נציגות",
                            "נבחרה ע\"י נציגות דיירים", "בחירה ע\"י בעלי זכויות", "בחירה כיזם",
                            "בחירה ע\"י נציגות", "בחירה ע\"י בעלים", "בחירה ע\"י", "בחירת יזם"]),
    ("combination_deal",  ["עסקת קומבינציה", "הסכם קומבינציה", "חתימת הסכם קומבינציה", "קומבינציה"]),
    ("acquisition",       ["רכישה מ", "רכישת זכויות", "רכישה", "מכירת 50%", "מכירה של 50%",
                            "מכירת זכויות", "סיחור זכויות", "סיחור", "מכירת", "מכירה"]),
    ("renewal_area_declared",["הכרזת מתחם", "הוכרזה כמתחם", "מתחם מועדף", "הכרזת ועדת שרים", "הכרזה"]),
    ("track_declared",    ["הוכרז מסלול מיסוי", "תכנית במסלול רשויות", "תב\"ע מקודמת ע\"י הרשות",
                            "מיועד לעבור לסמכות ותמ\"ל", "מסלול רשויות", "מסלול מיסוי",
                            "הכרה כיזם", "יזם מוביל", "מקודמת ע\"י הרשות"]),
    ("thresholds",        ["קיום תנאי סף", "עמידה בתנאי סף", "בדיקת תנאי סף", "תנאי סף",
                            "קליטת תכנית", "קליטה במקומית", "קליטה"]),
    ("pre_ruling",        ["פרה רולינג", "פרה-רולינג"]),
    ("round_table",       ["שולחן עגול"]),
    ("planning_review",   ["בדיקה תכנונית"]),
    ("submitted",         ["הוגש לועדה מחוזית", "הגשה למחוזית", "הוגש למחוזית", "הוגשה למחוזית",
                            "הוגש לועדה", "קבלת תכנית", "הוגשה", "הוגש", "הגשה"]),
    ("local_recommend",   ["דיון מקומית להמלצת הפקדה במחוזית", "אישור מקומית להעברה למחוזית",
                            "החלטת המלצת אישור במקומית", "דיון מקומית בהמלצה למחוזית",
                            "דיון בהמלצה למחוזית", "המלצת מקומית", "דיון חוזר", "דיון עקרוני", "דיון מקומית"]),
    ("pre_deposit",       ["טרום הפקדה"]),
    ("deposit_conditioned",["הפקדה בתנאים", "החלטה להפקדה", "דיון בהפקדה", "דיון הפקדה"]),
    ("amendment_106b",    ["פרסום תיקון לפי 106ב", "הפקדה לפי 106ב", "פרסום לפי 106ב", "106ב"]),
    ("publication_77_78", ["פרסום לפי 77-78", "הודעת 77", "דיון להודעת 77", "הודעה לפי 77",
                            "77-78", "77/78", "77 & 78", "77&78", "77 78", "77 ו-78"]),
    ("objections",        ["דיון בהתנגדויות", "דיון התנגדויות", "הפקדה להתנגדויות"]),
    ("deposited",         ["פרסום הפקדה", "בתהליך הפקדה", "הופקדה", "הפקדה"]),
    ("approved_conditioned",["אישור בתנאים", "אושרה בתנאים במקומית", "אישור מקומית"]),
    ("validity_extension",["הפקדת הארכת תוקף", "אישור הארכה", "דיון הארכת תוקף", "הארכת תוקף"]),
    ("plan_stopped",      ["משיכת התכנית", "סגירת תכנית", "התכנית נדחתה", "נדחתה", "נדחה",
                            "הוחלט לא לאשר", "החלטה לא לאשר", "לא לאשר", "אין הצעות",
                            "החברה הפסיקה", "הפסיקה לקדם", "הפסקת קידום", "מוקפא", "מוקפאת",
                            "סגירה", "דחייה", "ערר"]),
    ("approved",          ["פרסום אישור", "התכנית אושרה", "מתן תוקף", "תב\"ע בתוקף", "בתוקף",
                            "אושרה", "אישרו", "אישור", "אושר"]),
    ("info_file",         ["תיקי מידע", "בקשת מידע", "בקשה למידע", "תיק מידע"]),
    ("permit_conditioned",["היתר בתנאים"]),
    ("permit_request",    ["בקשה להיתר", "הגשת בקשה", "בקשה לפני ועדה", "הליך לקבלת היתר",
                            "תהליך רישוי", "הליך רישוי", "רישוי", "בקשה"]),
    ("permit_granted",    ["היתר בנייה מלא", "היתר לשלב", "היתר"]),
    ("design_plan",       ["תכנית עיצוב", "דיון תכנית בינוי", "דיון בתכנית בינוי", "תכנית בינוי"]),
    ("site_prep",         ["חפירה ודיפון", "חפירה", "דיפון", "עבודות עפר", "בוצעה הריסה", "הריסה"]),
    ("under_construction",["תחילת בנייה", "פרויקט בהקמה", "בהקמה", "שלד", "הקמה", "בנייה"]),
    ("completed",         ["סיום בנייה", "תעודת גמר", "טופס 4", "אכלוס"]),
    ("tender_won",        ["זכייה", "זוכה"]),
    ("tender_published",  ["פרסום מכרז", "מנכרז", "מכרז"]),
    ("preservation_committee",["ועדת שימור"]),
    ("pre_planning",      ["תכנון ראשוני לתב\"ע", "בשלבי תכנון ראשוניים", "בהליכי תכנון ראשוניים",
                            "בבחינת חלופות תכנון", "הוצגה חלופה", "חלופה תכנונית", "מקדמים תב\"ע",
                            "תב\"ע חדשה בהכנה", "תב\"ע בהליכים", "הכנת מסמכי תב\"ע", "תב\"ע בהכנה",
                            "שלבים ראשוניים", "מול הוועדה", "בשלבי בחינה", "לקראת פגישה", "בבחינה",
                            "העצמת זכויות", "פרוגרמה", "פרסום הכנה", "קדם סטטוטורי", "מקדמים",
                            "קידום תב\"ע", "הכנת תב\"ע", "הכנת תכנית", "תחילת תכנון", "בהכנה",
                            "ייזום", "תכנון"]),
]

# stage codes that indicate urban-renewal origin
UR_STAGES = {"owner_engagement", "developer_selection", "track_declared", "renewal_area_declared"}

# canonical Hebrew label per stage code (display name)
STAGE_LABEL = {
    "owner_engagement": "התקשרות עם בעלי זכויות",
    "developer_selection": "בחירת יזם ע\"י בעלי הזכויות",
    "combination_deal": "עסקת קומבינציה",
    "acquisition": "רכישה/מכירה",
    "renewal_area_declared": "הכרזת מתחם מועדף",
    "track_declared": "מסלול תכנון",
    "thresholds": "עמידה בתנאי סף",
    "pre_ruling": "פרה רולינג",
    "round_table": "שולחן עגול",
    "planning_review": "בדיקה תכנונית",
    "preservation_committee": "ועדת שימור",
    "submitted": "הגשה למחוזית",
    "local_recommend": "המלצת מקומית להפקדה",
    "pre_deposit": "טרום הפקדה",
    "deposit_conditioned": "הפקדה בתנאים",
    "amendment_106b": "תיקון לפי 106ב",
    "publication_77_78": "פרסום לפי 77-78",
    "objections": "דיון בהתנגדויות",
    "deposited": "פרסום הפקדה",
    "approved_conditioned": "אישור בתנאים",
    "validity_extension": "הארכת תוקף",
    "approved": "אישור",
    "plan_stopped": "עצירת/דחיית תכנית",
    "info_file": "תיק מידע",
    "permit_conditioned": "היתר בתנאים",
    "permit_request": "בקשה להיתר",
    "permit_granted": "היתר בנייה",
    "design_plan": "תכנית עיצוב/בינוי",
    "site_prep": "הריסה/עבודות הכנה",
    "under_construction": "בנייה",
    "completed": "סיום בנייה",
    "tender_won": "זכייה במכרז",
    "tender_published": "פרסום מכרז",
    "pre_planning": "תכנון מוקדם",
}

DATE_FULL = re.compile(r"(\d{1,2})[./](\d{1,2})[./](\d{4})")
DATE_MY   = re.compile(r"(?<!\d[./])(\d{1,2})[./](\d{4})(?!\d)")
DATE_Q    = re.compile(r"[Qq]([1-4])[/ ]?(\d{4})")
DATE_Y    = re.compile(r"(?<!\d)(20\d{2})(?!\d)")
FUZZY     = re.compile(r"(סוף|אמצע|תחילת|ראשית)\s*(20\d{2})")
SIGN_RE   = re.compile(r"(\d{1,3})\s*%\s*(?:חתימות|החתמות)")
SIGN2_RE  = re.compile(r"(\d{1,3})\s*%")   # bare percent fallback (per-building consent)
TENDER_NO = re.compile(r"([א-ת]{1,4})[/](\d+)[/](\d{4})")          # ים/212/2025
TENDER_NO2= re.compile(r"(?<![\d/])(\d{2,4})[/](\d{4})(?!\d)")     # 144/2024
STRIKE    = re.compile(r"~~(.+?)~~", re.DOTALL)

# --- enrichment (numeric fields parsed from description) ---
UNIT_ANY  = re.compile(r'([\d,]+)\s*יח(?:["״\']?ד|ידות)')
# existing (demolished) units: פינוי/הריסה only — NOT חיזוק (reinforced-in-place, a separate category).
# Allow descriptive text between verb and number, but stop at a construction verb.
EXIST_RE     = re.compile(r'(?:פינוי|הריסת|הריסה)(?:(?!הקמת|הקמה|בניית|בנייה|תוספת).){0,35}?([\d,]+)\s*יח')
# reinforced-in-place units (חיזוק): excluded from both existing and new counts
REINFORCE_RE = re.compile(r'חיזוק(?:(?!הקמת|הקמה|בניית|בנייה|תוספת|פינוי).){0,35}?([\d,]+)\s*יח')
# grand-total figure: number right before מתוכם/מהם, or right after כולל/הכולל,
# or a number directly followed by a parenthetical numeric breakdown "N יח"ד (92 מגדלי, 85 מרקמי)"
GRAND_BEFORE = re.compile(r'([\d,]+)\s*יח(?:["״\']?ד|ידות)[^\d]{0,20}(?:מתוכם|מהם)')
GRAND_AFTER  = re.compile(r'(?:כולל|הכולל)\s*(?:כ-?\s*)?([\d,]+)\s*יח')
GRAND_PAREN  = re.compile(r'([\d,]+)\s*יח(?:["״\']?ד|ידות)\s*\([^)]*\d')
# cut point: units after these belong to another plan (בנוסף) or are alternatives (ו/או)
CUT_RE    = re.compile(r'(בנוסף|ו/או|ו\\או|או לחלופין|לחלופין)')
SQM_RE    = re.compile(r'([\d,]+)\s*מ["״\']ר(?![א-ת])')   # require the quote; avoid מרכז/מרפאה etc.
FLOORS_RE = re.compile(r'(\d+)\s*קומ(?:ות|ה)')


def _to_int(s):
    try:
        return int(s.replace(",", "").strip())
    except ValueError:
        return 0


def parse_numbers(desc):
    """Return (existing_units, new_units, commercial, office, public, industrial, floors_max)."""
    clean = STRIKE.sub("", desc)   # current values only (drop superseded)
    # unit counting scope: drop other-plan (בנוסף) and alternative (ו/או) unit mentions
    cut = CUT_RE.search(clean)
    scope = clean[:cut.start()] if cut else clean
    existing = sum(_to_int(m.group(1)) for m in EXIST_RE.finditer(scope))
    reinforced = sum(_to_int(m.group(1)) for m in REINFORCE_RE.finditer(scope))
    gm = GRAND_BEFORE.search(scope) or GRAND_AFTER.search(scope) or GRAND_PAREN.search(scope)
    if gm:
        new = _to_int(gm.group(1))                 # grand total stated -> ignore sub-parts
    else:
        total = sum(_to_int(x) for x in UNIT_ANY.findall(scope))
        new = total - existing - reinforced        # additive; חיזוק counts as neither
        if new < 0:
            new = total
    def _cats(text):
        cs = []
        if "מסחר" in text:
            cs.append("com")
        if "משרד" in text or "תעסוק" in text:
            cs.append("off")
        if "תעשי" in text or "מלאכה" in text or "לוגיסט" in text or "אחסנ" in text:
            cs.append("ind")
        if "מבנ" in text or "ציבור" in text:
            cs.append("pub")
        return cs

    com = off = pub = ind = mixed = 0
    for m in SQM_RE.finditer(clean):
        n = _to_int(m.group(1))
        # look right after the מ"ר first (narrow, avoids catching the next figure's keyword);
        # fall back to the text just before the number
        cats = _cats(clean[m.end():m.end() + 15])
        if not cats:
            cats = _cats(clean[max(0, m.start() - 15):m.start()])
        if len(cats) >= 2:          # figure spans 2+ uses -> mixed
            mixed += n
        elif len(cats) == 1:
            c0 = cats[0]
            if c0 == "com":
                com += n
            elif c0 == "off":
                off += n
            elif c0 == "ind":
                ind += n
            else:
                pub += n
    floors = [int(x) for x in FLOORS_RE.findall(clean)]
    fmax = max(floors) if floors else None
    return (existing or None, new or None, com or None, off or None,
            pub or None, ind or None, mixed or None, fmax)

DISTRICT = {"ים":"ירושלים","מר":"מרכז","תא":"תל אביב","חי":"חיפה","צפ":"צפון",
            "דר":"דרום","בש":"דרום","יוש":"יו\"ש"}


def norm_date(seg):
    """Return (iso_or_label, precision) or (None,None)."""
    m = DATE_FULL.search(seg)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return (f"{y:04d}-{mo:02d}-{d:02d}", "day")
    m = DATE_Q.search(seg)
    if m:
        q, y = int(m.group(1)), int(m.group(2))
        return (f"{y:04d}-Q{q}", "quarter")
    m = DATE_MY.search(seg)
    if m:
        mo, y = int(m.group(1)), int(m.group(2))
        return (f"{y:04d}-{mo:02d}", "month")
    m = FUZZY.search(seg)
    if m:
        return (f"{m.group(2)}~{m.group(1)}", "fuzzy")
    m = DATE_Y.search(seg)
    if m:
        return (f"{m.group(1)}", "year")
    return (None, None)


def sort_key(iso):
    """Chronological key from a normalized date string; None -> very small."""
    if not iso:
        return (0, 0, 0)
    y = int(iso[:4])
    rest = iso[5:]
    if rest.startswith("Q"):
        return (y, int(rest[1]) * 3, 0)          # quarter -> mid month
    if "~" in rest or rest == "":
        return (y, 13, 0)                         # year/fuzzy -> end of year-ish
    parts = rest.split("-")
    mo = int(parts[0]) if parts and parts[0].isdigit() else 12
    d = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 15
    return (y, mo, d)


def map_stage(text):
    t = text.strip()
    for code, variants in STAGE_VOCAB:
        for v in variants:
            if v in t:
                return code
    return None


def split_segments(status):
    """Split a status blob into segments on commas and newlines."""
    segs = []
    for line in status.split("\n"):
        for part in line.split(","):
            p = part.strip()
            if p:
                segs.append(p)
    return segs


def parse_tender_no(seg):
    m = TENDER_NO.search(seg)
    if m:
        return (f"{m.group(1)}/{m.group(2)}/{m.group(3)}", m.group(1), int(m.group(2)), int(m.group(3)))
    m = TENDER_NO2.search(seg)
    if m:
        return (f"{m.group(1)}/{m.group(2)}", None, int(m.group(1)), int(m.group(2)))
    return (None, None, None, None)


def derive_type(row, has_rmi_tender, has_ur_stage, has_signatures, has_combination):
    text = " ".join([row["status"], row["description"], row["extra"]])
    devs = row["developers"]
    if has_rmi_tender or "מחיר למשתכן" in text or "מחיר מטרה" in text:
        return "state_land"
    if (has_ur_stage or has_signatures or "בעלי זכויות" in text or "דיירים" in text
            or "פינוי" in text or "תמ\"א" in text or "תמא" in text or "התחדשות" in text):
        return "urban_renewal"
    if has_combination or "קומבינציה" in text:
        return "combination"
    if "ועדה מקומית" in devs or "עיריי" in devs or "עירית" in devs:
        return "municipal"
    return "unknown"


def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    con = sqlite3.connect(DB_PATH)
    c = con.cursor()
    c.executescript("""
    CREATE TABLE projects(
      project_id INTEGER PRIMARY KEY, city TEXT, note TEXT, project_name TEXT,
      plan_current TEXT, plan_raw TEXT, tender_raw TEXT, request TEXT, developers TEXT, description TEXT,
      status_raw TEXT, exec_forecast TEXT, occupancy_forecast TEXT, extra TEXT,
      relpath TEXT, project_type TEXT,
      existing_units INTEGER, new_units INTEGER, commercial_sqm INTEGER,
      office_sqm INTEGER, public_sqm INTEGER, industrial_sqm INTEGER,
      mixed_use_sqm INTEGER, floors_max INTEGER);
    CREATE TABLE status_events(
      id INTEGER PRIMARY KEY, project_id INTEGER, seq INTEGER, raw TEXT,
      stage_code TEXT, stage_label TEXT, date_norm TEXT, date_precision TEXT, is_current INTEGER);
    CREATE TABLE tenders(
      id INTEGER PRIMARY KEY, project_id INTEGER, tender_no TEXT, district_code TEXT,
      district TEXT, serial INTEGER, year INTEGER, status TEXT,
      date_published TEXT, date_awarded TEXT, winner TEXT, raw TEXT);
    CREATE TABLE signatures(
      id INTEGER PRIMARY KEY, project_id INTEGER, percent INTEGER,
      date_norm TEXT, date_precision TEXT, raw TEXT);
    CREATE TABLE value_history(
      id INTEGER PRIMARY KEY, project_id INTEGER, field TEXT, old_value TEXT, raw_context TEXT);
    """)

    stats = {"projects":0,"events":0,"mapped":0,"unmapped":0,"tenders":0,
             "signatures":0,"value_history":0}
    enr_stats = {}
    unmapped_samples = set()
    type_dist = {}

    with open(CSV_PATH, encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        # map Hebrew headers -> internal keys by position
        for pid, r in enumerate(reader, 1):
            vals = list(r.values())
            row = {
                "city":vals[0], "note":vals[1], "project":vals[2],
                "plan_current":vals[3], "plan_raw":vals[4], "tender":vals[5],
                "request":vals[6], "status":vals[7], "developers":vals[8],
                "description":vals[9], "exec_forecast":vals[10],
                "occupancy_forecast":vals[11], "extra":vals[12], "relpath":vals[13],
            }
            stats["projects"] += 1

            # ---- status_events + signatures + tender-from-status ----
            events = []
            has_ur_stage = False
            has_combination = False
            has_signatures = False
            tender_rows = []
            segs = split_segments(STRIKE.sub("", row["status"]))   # struck status -> history only, not live events
            for seg in segs:
                sm = SIGN_RE.search(seg)
                if sm:
                    d, prec = norm_date(seg)
                    c.execute("INSERT INTO signatures(project_id,percent,date_norm,date_precision,raw) VALUES(?,?,?,?,?)",
                              (pid, int(sm.group(1)), d, prec, seg))
                    stats["signatures"] += 1
                    has_signatures = True
                    continue
                code = map_stage(seg)
                d, prec = norm_date(seg)
                if code:
                    stats["mapped"] += 1
                    if code in UR_STAGES:
                        has_ur_stage = True
                    if code == "combination_deal":
                        has_combination = True
                    if code in ("tender_published","tender_won"):
                        tno, dc, ser, yr = parse_tender_no(seg)
                        if tno or code == "tender_won":
                            tender_rows.append((code, seg, tno, dc, ser, yr, d))
                else:
                    sm2 = SIGN2_RE.search(seg)
                    if sm2:
                        d, prec = norm_date(seg)
                        c.execute("INSERT INTO signatures(project_id,percent,date_norm,date_precision,raw) VALUES(?,?,?,?,?)",
                                  (pid, int(sm2.group(1)), d, prec, seg))
                        stats["signatures"] += 1
                        has_signatures = True
                        continue
                    stats["unmapped"] += 1
                    if len(unmapped_samples) < 60 and len(seg) < 40:
                        unmapped_samples.add(seg)
                events.append([seg, code, d, prec])
                stats["events"] += 1

            # is_current = latest by date
            if events:
                idx = max(range(len(events)), key=lambda i: sort_key(events[i][2]))
                for i, ev in enumerate(events):
                    c.execute("INSERT INTO status_events(project_id,seq,raw,stage_code,stage_label,date_norm,date_precision,is_current) VALUES(?,?,?,?,?,?,?,?)",
                              (pid, i, ev[0], ev[1], STAGE_LABEL.get(ev[1]), ev[2], ev[3], 1 if i == idx else 0))

            # ---- tenders (from status + tender field) ----
            tender_field = row["tender"]
            if tender_field.strip():
                tno, dc, ser, yr = parse_tender_no(tender_field)
                if tno:
                    tender_rows.append(("tender_published", tender_field, tno, dc, ser, yr, None))
            # consolidate by tender_no
            by_no = {}
            for code, raw, tno, dc, ser, yr, d in tender_rows:
                key = tno or raw
                t = by_no.setdefault(key, {"tender_no":tno,"dc":dc,"ser":ser,"yr":yr,
                                           "pub":None,"awd":None,"raw":raw,"status":"published"})
                if code == "tender_published" and d: t["pub"] = d
                if code == "tender_won":
                    t["status"] = "won"
                    if d: t["awd"] = d
            has_rmi = False
            for key, t in by_no.items():
                if t["tender_no"]:
                    has_rmi = True
                c.execute("""INSERT INTO tenders(project_id,tender_no,district_code,district,serial,year,status,date_published,date_awarded,winner,raw)
                             VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                          (pid, t["tender_no"], t["dc"], DISTRICT.get(t["dc"]), t["ser"], t["yr"],
                           t["status"], t["pub"], t["awd"], row["developers"], t["raw"]))
                stats["tenders"] += 1

            # ---- value_history from strikethrough ----
            for field in ("plan_raw","description","exec_forecast","occupancy_forecast","status"):
                for m in STRIKE.finditer(row[field]):
                    c.execute("INSERT INTO value_history(project_id,field,old_value,raw_context) VALUES(?,?,?,?)",
                              (pid, field, m.group(1).strip(), row[field][:120]))
                    stats["value_history"] += 1

            # ---- project_type ----
            ptype = derive_type(row, has_rmi, has_ur_stage, has_signatures, has_combination)
            type_dist[ptype] = type_dist.get(ptype, 0) + 1

            eu, nu, com, off, pub, ind, mix, fmax = parse_numbers(row["description"])
            for _f, _v in (("existing_units",eu),("new_units",nu),("commercial_sqm",com),
                           ("office_sqm",off),("public_sqm",pub),("industrial_sqm",ind),
                           ("mixed_use_sqm",mix),("floors_max",fmax)):
                if _v is not None:
                    enr_stats[_f] = enr_stats.get(_f, 0) + 1

            c.execute("""INSERT INTO projects(project_id,city,note,project_name,plan_current,plan_raw,tender_raw,request,
                         developers,description,status_raw,exec_forecast,occupancy_forecast,extra,relpath,project_type,
                         existing_units,new_units,commercial_sqm,office_sqm,public_sqm,industrial_sqm,mixed_use_sqm,floors_max)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (pid,row["city"],row["note"],row["project"],row["plan_current"],row["plan_raw"],row["tender"],row["request"],
                       row["developers"],row["description"],row["status"],row["exec_forecast"],
                       row["occupancy_forecast"],row["extra"],row["relpath"],ptype,
                       eu,nu,com,off,pub,ind,mix,fmax))

    con.commit()
    # indexes
    c.executescript("""
      CREATE INDEX ix_ev_pid ON status_events(project_id);
      CREATE INDEX ix_te_pid ON tenders(project_id);
      CREATE INDEX ix_te_no  ON tenders(tender_no);
      CREATE INDEX ix_pr_plan ON projects(plan_current);
    """)
    con.commit()
    c.execute("SELECT stage_label,COUNT(*) FROM status_events WHERE stage_code IS NOT NULL GROUP BY stage_label ORDER BY 2 DESC")
    stage_dist = c.fetchall()
    c.execute("SELECT COUNT(*) FROM status_events WHERE is_current=1 AND stage_code IS NOT NULL")
    current_mapped = c.fetchone()[0]
    c.execute("SELECT SUM(existing_units),SUM(new_units),SUM(commercial_sqm),SUM(office_sqm),SUM(industrial_sqm),SUM(mixed_use_sqm) FROM projects")
    sums = c.fetchone()
    con.close()

    cov = stats["mapped"]/(stats["mapped"]+stats["unmapped"]) if (stats["mapped"]+stats["unmapped"]) else 0
    print("DB:", DB_PATH)
    print("STATS:", stats)
    print(f"stage mapping coverage: {cov:.1%}")
    print("project_type:", type_dist)
    print(f"projects with a mapped current stage: {current_mapped}")
    print("enrichment (projects with a value):", enr_stats)
    print(f"totals -> existing_units:{sums[0]} new_units:{sums[1]} commercial_sqm:{sums[2]} office_sqm:{sums[3]} industrial_sqm:{sums[4]} mixed_use_sqm:{sums[5]}")
    print("stage distribution (current-name : count):")
    for label, n in stage_dist:
        print(f"   {label}: {n}")
    print("sample UNMAPPED stage segments:")
    for s in list(unmapped_samples)[:40]:
        print("   -", s)


if __name__ == "__main__":
    main()
