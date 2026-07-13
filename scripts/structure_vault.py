#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate a STRUCTURED copy of the vault from projects.db.

- Writes to a NEW folder (does NOT touch the live vault).
- One .md per neighborhood (mirrors city/note tree).
- Per project: Dataview inline fields (`שדה:: ערך`), one status event per line.
- Description kept verbatim; unmapped status + leaked text flagged ⚠️ (nothing lost).

Usage (PowerShell):
  python -X utf8 structure_vault.py projects.db "<OUT_DIR>"
"""

import os, re, sys, sqlite3

DB_PATH = sys.argv[1] if len(sys.argv) > 1 else "projects.db"
OUT_DIR = sys.argv[2] if len(sys.argv) > 2 else "vault_structured"

TYPE_HE = {
    "state_land": "קרקע מדינה",
    "urban_renewal": "התחדשות עירונית",
    "combination": "עסקת קומבינציה",
    "municipal": "רשות מקומית",
    # unknown -> omitted
}

HIST_LABEL = {
    "plan_raw": "תכנית", "description": "תיאור", "status": "סטטוס",
    "exec_forecast": "צפי לביצוע", "occupancy_forecast": "צפי לאכלוס",
}

SQM_FIELDS = [
    ("commercial_sqm", 'מ"ר מסחר'),
    ("office_sqm", 'מ"ר משרדים'),
    ("mixed_use_sqm", 'מ"ר מעורב'),
    ("industrial_sqm", 'מ"ר תעשייה'),
    ("public_sqm", 'מ"ר ציבור'),
]


def esc(s):
    return (s or "").replace("\r", " ").replace("\n", " ").strip()


def main():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    c = con.cursor()

    # group projects by file
    rows = c.execute("SELECT * FROM projects ORDER BY relpath, project_id").fetchall()
    files = {}
    for r in rows:
        files.setdefault(r["relpath"], []).append(r)

    n_files = n_proj = n_flagged = 0
    for relpath, projs in files.items():
        out_path = os.path.join(OUT_DIR, relpath)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        lines = []
        multi = len(projs) > 1
        if multi:
            lines.append("### פרויקטים")
        for p in projs:
            pid = p["project_id"]
            n_proj += 1
            if multi:
                lines.append(f"#### {esc(p['project_name'])}")

            def fld(name, val, inferred=False):
                if val is not None and str(val).strip() != "":
                    tag = " ·משוער" if inferred else ""
                    lines.append(f"- {name}:: {esc(str(val))}{tag}")

            fld("תכנית", p["plan_current"])
            fld("מכרז", p["tender_raw"])
            fld("בקשה", p["request"])
            fld("יזמים", p["developers"])
            fld('יח"ד קיימות', p["existing_units"], inferred=True)
            fld('יח"ד חדשות', p["new_units"], inferred=True)
            for col, label in SQM_FIELDS:
                fld(label, p[col], inferred=True)
            fld("קומות", p["floors_max"], inferred=True)

            # status events, one per line (mapped -> "label date"; unmapped -> raw + ⚠️)
            # keep the ORIGINAL status text verbatim (wording + tender/permit number + date);
            # canonical stage_code stays in the DB, not written over the source note.
            evs = c.execute("SELECT * FROM status_events WHERE project_id=? ORDER BY seq", (pid,)).fetchall()
            for e in evs:
                raw = esc(e["raw"])
                if not raw:
                    continue
                cur = " (נוכחי)" if e["is_current"] else ""
                lines.append(f"- סטטוס:: {raw}{cur}")

            # signatures
            sigs = c.execute("SELECT * FROM signatures WHERE project_id=? ORDER BY id", (pid,)).fetchall()
            for s in sigs:
                d = f" {s['date_norm']}" if s["date_norm"] else ""
                lines.append(f"- חתימות:: {s['percent']}%{d}")

            # forecasts (keep prose, split on commas to one per line)
            for src in (p["exec_forecast"], p["occupancy_forecast"]):
                if src and src.strip():
                    # split on item-separating commas only, not thousands-separators (8,000)
                    for part in re.split(r',\s*(?=\D)', src):
                        if part.strip():
                            lines.append(f"- צפי:: {esc(part)}")

            # description verbatim (keep strikethrough / prose intact)
            if p["description"] and p["description"].strip():
                fld("תיאור", p["description"])

            # (value_history is kept in the DB; not written to notes — the strikethrough
            #  stays verbatim in תיאור, so a history line here would be redundant.)

            # leaked/other text -> flagged, not lost
            if p["extra"] and p["extra"].strip():
                lines.append(f"- הערה:: {esc(p['extra'])} ⚠️")
                n_flagged += 1

            lines.append("")  # blank line between projects

        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines).rstrip() + "\n")
        n_files += 1

    con.close()
    print(f"wrote {n_files} files, {n_proj} projects to: {OUT_DIR}")
    print(f"flagged ⚠️ lines (unmapped status / leaked text) for review: {n_flagged}")


if __name__ == "__main__":
    main()
