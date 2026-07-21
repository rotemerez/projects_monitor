#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Refresh projects.db directly from the STRUCTURED vault (key:: value inline fields).

This replaces parse_vault.py once the vault is in structured form. It reads the
explicit fields you wrote (so your edits/corrections are respected) rather than
guessing from free text. Canonical stage mapping + date normalization are reused
from build_db.py so the DB stays identical in shape.

Usage (PowerShell):
  python -X utf8 refresh_db.py "<vault_structured dir>" projects.db
"""

import os, re, sys, sqlite3
import build_db as bd   # reuse STAGE vocab, map_stage, norm_date, sort_key, parse_tender_no, derive_type, STRIKE, DISTRICT, UR_STAGES

VAULT = sys.argv[1] if len(sys.argv) > 1 else "vault_structured"
DB    = sys.argv[2] if len(sys.argv) > 2 else "projects.db"

FIELD_RE = re.compile(r'^\s*-?\s*(.+?)::\s*(.*\S)\s*$')

SQM_MAP = {
    'מ"ר מסחר': "commercial_sqm", 'מ"ר משרדים': "office_sqm",
    'מ"ר מעורב': "mixed_use_sqm", 'מ"ר תעשייה': "industrial_sqm",
    'מ"ר ציבור': "public_sqm",
}


def clean_val(v):
    v = re.sub(r'\s*·משוער\s*$', '', v)           # drop inferred tag
    return v.strip()


def to_int(v):
    m = re.search(r'\d[\d,]*', clean_val(v))
    return int(m.group().replace(",", "")) if m else None


def blocks(text, note_title):
    lines = text.splitlines()
    idxs = [i for i, l in enumerate(lines) if l.lstrip().startswith("#### ")]
    if not idxs:
        yield note_title, lines, False           # single-project (whole file)
        return
    for j, start in enumerate(idxs):
        name = lines[start].lstrip("# ").strip()
        end = idxs[j + 1] if j + 1 < len(idxs) else len(lines)
        yield name, lines[start + 1:end], True    # explicit #### project block


def parse_block(block_lines):
    d = {}
    for l in block_lines:
        m = FIELD_RE.match(l)
        if m:
            k = m.group(1).strip().lstrip("-").strip()
            d.setdefault(k, []).append(m.group(2).strip())
    return d


def first(d, k):
    v = d.get(k)
    return v[0] if v else None


def main():
    # Build into a temp file and atomically replace DB at the end (os.replace), so any
    # concurrent reader (e.g. mavat_diff.py, woken from the same sleep/wake catch-up) always
    # sees either the complete old DB or the complete new one — never a freshly-truncated,
    # not-yet-repopulated one. Found 2026-07-19: a scheduled-task pile-up after the machine
    # woke from sleep let mavat_diff.py connect to projects.db mid-rebuild (old in-place
    # os.remove()+recreate), read 0 rows, and silently skip an entire day's status diff.
    tmp_db = DB + ".tmp"
    if os.path.exists(tmp_db):
        os.remove(tmp_db)
    con = sqlite3.connect(tmp_db); c = con.cursor()
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

    stats = {"projects": 0, "events": 0, "mapped": 0, "tenders": 0, "signatures": 0}
    pid = 0
    for root, _dirs, files in os.walk(VAULT):
        for fn in files:
            if not fn.endswith(".md"):
                continue
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, VAULT)
            parts = rel.split(os.sep)
            city = parts[0] if len(parts) > 1 else ""
            note = os.path.splitext(fn)[0]
            text = open(full, encoding="utf-8").read()
            for pname, blk, from_header in blocks(text, note):
                d = parse_block(blk)
                if not d and not from_header:
                    continue                      # empty single-project file -> skip (matches original)
                pid += 1
                stats["projects"] += 1
                desc = first(d, "תיאור") or ""
                developers = first(d, "יזמים") or ""
                tender_raw = first(d, "מכרז") or ""

                # ---- status events (verbatim lines -> canonical code + date) ----
                status_lines = [re.sub(r'\s*\(נוכחי\)\s*$', '', s) for s in d.get("סטטוס", [])]
                marked = [i for i, s in enumerate(d.get("סטטוס", [])) if "(נוכחי)" in s]
                evs = []
                for s in status_lines:
                    code = bd.map_stage(s)
                    dt, prec = bd.norm_date(s)
                    if code:
                        stats["mapped"] += 1
                    evs.append([s, code, dt, prec])
                    stats["events"] += 1
                if evs:
                    cur = marked[0] if marked else max(range(len(evs)), key=lambda i: bd.sort_key(evs[i][2]))
                    for i, e in enumerate(evs):
                        c.execute("INSERT INTO status_events(project_id,seq,raw,stage_code,stage_label,date_norm,date_precision,is_current) VALUES(?,?,?,?,?,?,?,?)",
                                  (pid, i, e[0], e[1], bd.STAGE_LABEL.get(e[1]), e[2], e[3], 1 if i == cur else 0))

                # ---- signatures (e.g. "80% 2024-Q4") ----
                for s in d.get("חתימות", []):
                    pm = re.search(r'(\d{1,3})\s*%', s)
                    if pm:
                        rest = s.replace(pm.group(0), "").strip()
                        c.execute("INSERT INTO signatures(project_id,percent,date_norm,date_precision,raw) VALUES(?,?,?,?,?)",
                                  (pid, int(pm.group(1)), rest or None, None, s))
                        stats["signatures"] += 1
                has_sig = bool(d.get("חתימות"))

                # ---- tenders (from מכרז field + tender status events) ----
                tender_rows = []
                if tender_raw.strip():
                    tno, dc, ser, yr = bd.parse_tender_no(tender_raw)
                    if tno:
                        tender_rows.append(("tender_published", tender_raw, tno, dc, ser, yr, None))
                for e in evs:
                    if e[1] in ("tender_published", "tender_won"):
                        tno, dc, ser, yr = bd.parse_tender_no(e[0])
                        if tno or e[1] == "tender_won":
                            tender_rows.append((e[1], e[0], tno, dc, ser, yr, e[2]))
                by_no = {}
                for code, raw, tno, dc, ser, yr, dt in tender_rows:
                    t = by_no.setdefault(tno or raw, {"tender_no": tno, "dc": dc, "ser": ser, "yr": yr,
                                                       "pub": None, "awd": None, "raw": raw, "status": "published"})
                    if code == "tender_published" and dt: t["pub"] = dt
                    if code == "tender_won":
                        t["status"] = "won"
                        if dt: t["awd"] = dt
                has_rmi = False
                for t in by_no.values():
                    if t["tender_no"]: has_rmi = True
                    c.execute("""INSERT INTO tenders(project_id,tender_no,district_code,district,serial,year,status,date_published,date_awarded,winner,raw)
                                 VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                              (pid, t["tender_no"], t["dc"], bd.DISTRICT.get(t["dc"]), t["ser"], t["yr"],
                               t["status"], t["pub"], t["awd"], developers, t["raw"]))
                    stats["tenders"] += 1

                # ---- value history from strikethrough in description ----
                for m in bd.STRIKE.finditer(desc):
                    c.execute("INSERT INTO value_history(project_id,field,old_value,raw_context) VALUES(?,?,?,?)",
                              (pid, "description", m.group(1).strip(), desc[:120]))

                # ---- numeric fields: read from notes (respect edits); fallback to re-derive ----
                eu = to_int(first(d, 'יח"ד קיימות') or "")
                nu = to_int(first(d, 'יח"ד חדשות') or "")
                sqm = {v: to_int(first(d, k) or "") for k, v in SQM_MAP.items()}
                fmax = to_int(first(d, "קומות") or "")
                if eu is None and nu is None and not any(sqm.values()) and fmax is None and desc:
                    eu, nu, com, off, pub, ind, mix, fmax = bd.parse_numbers(desc)
                    sqm = {"commercial_sqm": com, "office_sqm": off, "mixed_use_sqm": mix,
                           "industrial_sqm": ind, "public_sqm": pub}

                # ---- project_type (re-derived; DB only) ----
                has_ur = any(e[1] in bd.UR_STAGES for e in evs)
                has_comb = any(e[1] == "combination_deal" for e in evs)
                ptype = bd.derive_type({"status": " ".join(status_lines), "description": desc,
                                        "extra": " ".join(d.get("הערה", [])), "developers": developers},
                                       has_rmi, has_ur, has_sig, has_comb)

                exec_fc = ", ".join(d.get("צפי", []))
                extra = " ".join(x.replace("⚠️", "").strip() for x in d.get("הערה", []))
                plan = first(d, "תכנית") or ""
                c.execute("""INSERT INTO projects(project_id,city,note,project_name,plan_current,plan_raw,tender_raw,request,
                             developers,description,status_raw,exec_forecast,occupancy_forecast,extra,relpath,project_type,
                             existing_units,new_units,commercial_sqm,office_sqm,public_sqm,industrial_sqm,mixed_use_sqm,floors_max)
                             VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                          (pid, city, note, pname, plan, plan, tender_raw, first(d, "בקשה") or "",
                           developers, desc, " | ".join(status_lines), exec_fc, "", extra, rel, ptype,
                           eu, nu, sqm.get("commercial_sqm"), sqm.get("office_sqm"), sqm.get("public_sqm"),
                           sqm.get("industrial_sqm"), sqm.get("mixed_use_sqm"), fmax))

    con.commit()
    c.executescript("""
      CREATE INDEX ix_ev_pid ON status_events(project_id);
      CREATE INDEX ix_te_no  ON tenders(tender_no);
      CREATE INDEX ix_pr_plan ON projects(plan_current);
    """)
    con.commit(); con.close()
    os.replace(tmp_db, DB)
    print("refreshed DB from structured vault:", DB)
    print("STATS:", stats)


if __name__ == "__main__":
    main()
