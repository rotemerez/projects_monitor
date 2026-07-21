r"""
make_review_page.py — generate mavat_review.html: an interactive local page for reviewing
new-plan candidates from BOTH discovery sources:
  - Mavat nationwide status sweep (mavat_discovery.db, this folder)
  - Local-committee scraper rotation (committee_scraper/committee_state.db) — plans that
    have not yet reached Mavat (committee candidates whose קישור למבאת/vault match already
    appeared are auto-"graduated"/excluded upstream by run_committee_sweep.py and do not
    show up here as open, per user decision 2026-07-13: once in Mavat, no need to track
    at the committee level too).

The page embeds combined candidate data, keeps flag/comment decisions in localStorage
(keyed by a per-source-unique id: bare plan number for Mavat, "muni::plan_number" for
committee — the "::" makes collisions between the two impossible), and exports them as
JSON. Feed that file back with:
  venv\Scripts\python.exe apply_review.py decisions.json

Regenerate after every discovery/committee sweep:
  venv\Scripts\python.exe make_review_page.py
"""
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
MAVAT_DB = HERE / "mavat_discovery.db"
COMMITTEE_DB = HERE.parent / "committee_scraper" / "committee_state.db"
STATE_DB = HERE / "mavat_state.db"
PROJECTS_DB = HERE.parent / "projects.db"
OUT = HERE / "mavat_review.html"

# KEEP IN SYNC with mavat_discover.py:TARGET_STATUSES and mavat_diff.py:
# MAVAT_TRACKED_STATUSES — same 9-status whitelist gates what shows up here too.
MAVAT_TRACKED_STATUSES = {
    "הכנת הודעה 77/78", "הכנת תכנית", "Pre-Ruling", "תסקיר סביבתי",
    "בבדיקת תנאי סף", "בבדיקה תכנונית", "הפקדה להתנגדויות/השגות", "אישור", "נדחתה",
}


def load_mavat():
    con = sqlite3.connect(MAVAT_DB)
    for ddl in ("ALTER TABLE discovered ADD COLUMN kept INTEGER DEFAULT 0",
                "ALTER TABLE discovered ADD COLUMN decided_at TEXT",
                "ALTER TABLE discovered ADD COLUMN vault_notice_seen INTEGER DEFAULT 0",
                "ALTER TABLE discovered ADD COLUMN vault_notice_seen_at TEXT"):
        try:
            con.execute(ddl)
        except sqlite3.OperationalError:
            pass
    has_units = any(r[1] == "units_ge10"
                    for r in con.execute("PRAGMA table_info(discovered)"))
    units_col = ", COALESCE(units_ge10,0)" if has_units else ", 0"
    # Excludes the one-time 2026-07-15 backlog cutover (~14.5k historical אישור/נדחתה rows
    # that newly qualified when TARGET_STATUSES was widened to the 9-status whitelist) —
    # pure migration noise, not a real decision worth keeping in the page's history tab.
    # Bloated the payload to 12MB before this filter; see migrate_target_status.py.
    # BUG (found 2026-07-16): `exclude_reason NOT LIKE '...'` evaluates to NULL — not
    # true — for every never-excluded row (exclude_reason IS NULL), so SQLite silently
    # dropped ALL genuinely open candidates, not just the backlog noise. The `IS NULL OR`
    # is required; do not remove it.
    cur = con.execute(f"""SELECT plan, name, location, authority, status, status_date, url,
                                 excluded, exclude_reason, comment, first_seen,
                                 COALESCE(kept,0), decided_at{units_col}
                          FROM discovered WHERE target_status=1 AND in_vault=0
                            AND (exclude_reason IS NULL
                                 OR exclude_reason NOT LIKE 'אוטומטי: סטטוס נכלל לראשונה%')
                          ORDER BY status, location, plan""")
    rows = []
    for (plan, name, location, authority, status, status_date, url, excluded,
         exclude_reason, comment, first_seen, kept, decided_at, units10) in cur.fetchall():
        rows.append({"plan": plan, "display_plan": plan, "name": name, "location": location,
                     "authority": authority, "status": status, "status_date": status_date,
                     "url": url, "excluded": excluded, "exclude_reason": exclude_reason,
                     "comment": comment, "first_seen": first_seen, "kept": kept,
                     "decided_at": decided_at, "units10": units10, "source": "mavat",
                     "kind": "candidate"})

    # Vault-notice rows: plans already tracked in the vault (in_vault=1) that just showed
    # up in the Mavat sweep — worth a look at the Mavat page itself (goals/quantities/PDFs
    # are often richer than the committee source they were originally entered from), but
    # not a keep/exclude decision since they're already tracked. One-time nudge: dismissed
    # via vault_notice_seen instead of the kept/excluded flags (2026-07-15, user decision).
    cur = con.execute("""SELECT plan, name, location, authority, status, status_date, url,
                                first_seen
                         FROM discovered
                         WHERE target_status=1 AND in_vault=1
                           AND COALESCE(vault_notice_seen,0)=0
                         ORDER BY first_seen DESC""")
    for plan, name, location, authority, status, status_date, url, first_seen in cur.fetchall():
        rows.append({"plan": plan, "display_plan": plan, "name": name, "location": location,
                     "authority": authority, "status": status, "status_date": status_date,
                     "url": url, "excluded": 0, "exclude_reason": None, "comment": None,
                     "first_seen": first_seen, "kept": 0, "decided_at": None, "units10": 0,
                     "source": "mavat", "kind": "vault_notice"})
    con.close()
    return rows


def load_committee():
    if not COMMITTEE_DB.exists():
        return []
    con = sqlite3.connect(COMMITTEE_DB)
    cur = con.execute("""SELECT id, muni, plan_number, plan_name, status, status_date,
                                plan_link, excluded, exclude_reason, comment, first_seen,
                                COALESCE(kept,0), decided_at
                         FROM committee_candidates
                         WHERE COALESCE(graduated,0)=0
                         ORDER BY status, muni, plan_number""")
    rows = []
    for (cid, muni, plan_number, plan_name, status, status_date, plan_link, excluded,
         exclude_reason, comment, first_seen, kept, decided_at) in cur.fetchall():
        rows.append({"plan": cid, "display_plan": plan_number, "name": plan_name,
                     "location": muni, "authority": "ועדה מקומית", "status": status,
                     "status_date": status_date, "url": plan_link, "excluded": excluded,
                     "exclude_reason": exclude_reason, "comment": comment,
                     "first_seen": first_seen, "kept": kept, "decided_at": decided_at,
                     "units10": 0, "source": "committee", "kind": "candidate"})
    con.close()
    return rows


def load_changes():
    """Pending Mavat status/unit changes for vault-tracked plans (mavat_state.db), merged
    into the same review page (2026-07-15, replaces mavat_changes.html). Only surfaced
    when the plan's current/new status is in MAVAT_TRACKED_STATUSES — a units-only change
    (status unchanged) is judged by the plan's current status_desc since it has no
    new_status of its own. Keyed as 'chg::<id>' so it can never collide with a bare plan
    number (mavat candidate/vault-notice) or a 'muni::plan' committee id."""
    if not STATE_DB.exists():
        return []
    state = sqlite3.connect(STATE_DB)
    cur = state.execute("""SELECT c.id, c.plan, c.changed_at, c.old_status, c.old_date,
                                  c.new_status, c.new_date, c.old_units, c.new_units,
                                  c.note, s.status_desc, c.status_detail
                           FROM mavat_changes c LEFT JOIN mavat_status s ON s.plan = c.plan
                           WHERE c.approved IS NULL
                           ORDER BY c.changed_at DESC, c.plan""")
    raw = cur.fetchall()
    state.close()

    proj = sqlite3.connect(PROJECTS_DB)
    ctx = {}
    for plan, city, name in proj.execute(
            "SELECT plan_current, city, project_name FROM projects WHERE plan_current != ''"):
        ctx.setdefault(str(plan).strip().replace(" ", ""), (city, name))
    proj.close()

    rows = []
    for (cid, plan, changed_at, old_status, old_date, new_status, new_date,
         old_units, new_units, note, cur_status_desc, status_detail) in raw:
        effective_status = new_status or cur_status_desc
        if effective_status not in MAVAT_TRACKED_STATUSES:
            continue
        city, name = ctx.get(plan, ("", ""))
        # status_detail (2026-07-19): the plan's own stage-history label for this date, when
        # it names a section-106(ב) re-deposit-after-corrections — distinguishes that from an
        # original deposit, which Mavat's own status bucket doesn't (both show the same
        # generic "הפקדה להתנגדויות/השגות"). None for the vast majority of changes that never
        # go through a 106(ב) cycle.
        rows.append({"plan": f"chg::{cid}", "display_plan": plan,
                     "name": f"{city} / {name}".strip(" /") if (city or name) else plan,
                     "location": city, "authority": "שינוי סטטוס", "status": new_status,
                     "status_date": new_date, "old_status": old_status,
                     "old_date": old_date, "old_units": old_units, "new_units": new_units,
                     "note": note, "status_detail": status_detail,
                     "url": "https://mavat.iplan.gov.il/SV3?searchEntity=1&entityType=1"
                            "&searchMethod=2",
                     "excluded": 0, "exclude_reason": None, "comment": None,
                     "first_seen": changed_at, "kept": 0, "decided_at": None,
                     "units10": 0, "source": "mavat", "kind": "status_change"})
    return rows


data = load_mavat() + load_committee() + load_changes()

generated = datetime.now().strftime("%d/%m/%Y %H:%M")
payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")

html = """<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<title>סקירת תכניות חדשות</title>
<style>
  :root { --bg:#f7f8fa; --card:#fff; --line:#e3e6ea; --txt:#1c2733; --dim:#6b7683;
          --blue:#1560a8; --red:#c0392b; --green:#1e8449; --purple:#7c4dab; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:"Segoe UI",Arial,sans-serif; background:var(--bg);
         color:var(--txt); }
  header { position:sticky; top:0; z-index:5; background:var(--card);
           border-bottom:1px solid var(--line); padding:10px 18px; }
  h1 { font-size:18px; margin:0 0 8px; }
  .bar { display:flex; flex-wrap:wrap; gap:8px; align-items:center; }
  .bar input[type=text] { padding:6px 10px; border:1px solid var(--line); border-radius:6px;
        min-width:220px; font-size:14px; }
  .chip { border:1px solid var(--line); background:#fff; border-radius:14px; padding:4px 12px;
          font-size:13px; cursor:pointer; user-select:none; }
  .chip.on { background:var(--blue); color:#fff; border-color:var(--blue); }
  .counts { font-size:13px; color:var(--dim); margin-inline-start:auto; }
  main { padding:14px 18px; max-width:1250px; margin:0 auto; }
  table { width:100%; border-collapse:collapse; background:var(--card);
          border:1px solid var(--line); }
  th { text-align:right; font-size:12.5px; color:var(--dim); font-weight:600;
       padding:8px 10px; border-bottom:1px solid var(--line); background:#fbfcfd;
       position:sticky; top:var(--hdrH, 64px); z-index:4; }
  td { padding:8px 10px; border-bottom:1px solid var(--line); font-size:13.5px;
       vertical-align:top; }
  tr.excluded td { background:#fdf0ee; color:#8d6e68; }
  tr.kept td { background:#eefaf1; }
  tr.vaultnotice td { background:#eaf3fc; }
  tr.statuschange td { background:#f6f0fb; }
  a { color:var(--blue); text-decoration:none; }
  .u10 { display:inline-block; background:#e8f1fa; color:var(--blue); border-radius:10px;
         font-size:11px; padding:1px 7px; margin-inline-start:6px; }
  .vn { display:inline-block; background:#dbeafc; color:var(--blue); border-radius:10px;
        font-size:11px; padding:1px 7px; margin-inline-start:6px; font-weight:600; }
  .chg { display:inline-block; background:#ecdffa; color:var(--purple); border-radius:10px;
         font-size:11px; padding:1px 7px; margin-inline-start:6px; font-weight:600; }
  .units { background:#e8f1fa; color:var(--blue); border-radius:10px; font-size:12px;
       padding:1px 8px; display:inline-block; margin-top:3px; }
  .arrow { color:var(--dim); }
  .src { display:inline-block; border-radius:10px; font-size:11px; padding:1px 7px;
         margin-inline-start:6px; background:#f1e9f7; color:var(--purple); }
  .btn { border:1px solid var(--line); background:#fff; border-radius:6px; padding:3px 10px;
         font-size:12.5px; cursor:pointer; margin-inline-end:4px; }
  .btn.ex { color:var(--red); border-color:#e7c4bf; }
  .btn.keep { color:var(--green); border-color:#bfe3c9; }
  .btn.active-ex { background:var(--red); color:#fff; }
  .btn.active-keep { background:var(--green); color:#fff; }
  .reason { margin-top:5px; }
  .reason select { font-size:12.5px; padding:3px 6px; border:1px solid var(--line);
       border-radius:5px; width:100%; margin-top:3px; }
  .comment { width:100%; font-size:12.5px; padding:3px 6px; border:1px solid var(--line);
       border-radius:5px; margin-top:4px; }
  .export { background:var(--blue); color:#fff; border:none; border-radius:6px;
       padding:7px 16px; font-size:14px; cursor:pointer; }
  .muted { color:var(--dim); font-size:12px; }
</style>
</head>
<body>
<header>
  <h1>סקירת מועמדים — תכניות חדשות <span class="muted">(נוצר __GENERATED__)</span></h1>
  <div class="bar">
    <input type="text" id="q" placeholder="חיפוש חופשי: שם / מספר / ישוב">
    <span id="statusChips"></span>
    <span class="chip" data-state="open">פתוחות</span>
    <span class="chip" data-state="kept">נשמרו</span>
    <span class="chip" data-state="excluded">הוחרגו</span>
    <span class="chip" id="u10chip">10+ יח"ד</span>
    <span class="chip" id="newChip">חדשות מהסריקה האחרונה</span>
    <span class="chip" id="vnChip">כבר בכספת — חדש במבא"ת</span>
    <span class="chip" id="chgChip">שינויי סטטוס לאישור</span>
    <span class="chip" data-src="mavat">מבא"ת</span>
    <span class="chip" data-src="committee">ועדה מקומית</span>
    <button class="export" id="exportBtn">יצוא החלטות (JSON)</button>
    <button class="btn" id="markSeenBtn" title="כל התכניות הנוכחיות יסומנו כנצפו; רק תכניות שיתגלו מכאן והלאה יקבלו תג 'חדש'">סמן הכל כנצפה</button>
    <span class="muted" id="wmLabel"></span>
    <span class="counts" id="counts"></span>
  </div>
</header>
<main>
  <table>
    <thead><tr>
      <th style="width:130px">מס' תכנית</th><th>שם</th><th style="width:120px">מיקום</th>
      <th style="width:90px">סמכות</th><th style="width:140px">סטטוס</th>
      <th style="width:85px">תאריך</th><th style="width:260px">החלטה</th>
    </tr></thead>
    <tbody id="rows"></tbody>
  </table>
</main>
<script id="data" type="application/json">__DATA__</script>
<script>
const DATA = JSON.parse(document.getElementById('data').textContent);
const LSKEY = 'mavat_review_decisions_v1';
const REASONS = ['תכנית נקודתית / בניין בודד','תשתיות / ניקוז / דרכים','שטח פתוח / חקלאי',
                 'מוסדות ציבור בלבד','לא רלוונטי גיאוגרפית','תכנית קטנה מדי','אחר'];
let decisions = JSON.parse(localStorage.getItem(LSKEY) || '{}');
// seed from DB state (decisions applied on previous rounds, incl. automatic rules).
// An AUTO-rule decision (reason starts "אוטומטי:") must never get stuck in the browser once
// the underlying rule/data changes — found 2026-07-21 (502-1406529: auto-excluded, then
// un-excluded server-side by a same-day rule fix + backlog reopen, but a browser that had
// already loaded the page kept showing the stale cached "excluded" state indefinitely, since
// seeding only ever ran once per plan). A genuine HUMAN decision (any other reason, or a
// kept/rejected/approved state) is never touched here — only auto-tagged entries are
// refreshed to match the current DB on every load.
for (const r of DATA) {
  const cached = decisions[r.plan];
  const cachedIsAuto = cached && cached.state === 'excluded'
                      && (cached.reason || '').startsWith('אוטומטי:');
  if (r.excluded && (!cached || cachedIsAuto)) {
    decisions[r.plan] = {state:'excluded', reason:r.exclude_reason||'', comment:r.comment||'',
                         ts:r.decided_at||''};
  } else if (!r.excluded && cachedIsAuto) {
    delete decisions[r.plan];
  }
  if (r.kept && !decisions[r.plan])
    decisions[r.plan] = {state:'kept', reason:'', comment:r.comment||'', ts:r.decided_at||''};
}
// "new" = first seen AFTER the user's caught-up watermark (set via the 'סמן כנצפה'
// button). Survives any number of missed sweeps: plans stay badged until the user
// explicitly marks themselves caught up. Without a watermark yet, fall back to
// "the most recent sweep batch" (per source, since Mavat/committee sweep on different
// schedules).
const WMKEY = 'mavat_review_seen_until';
let watermark = localStorage.getItem(WMKEY) || '';
const latestSeenBySource = {};
for (const r of DATA) {
  const fs = (r.first_seen||'').slice(0,10);
  if (!latestSeenBySource[r.source] || fs > latestSeenBySource[r.source])
    latestSeenBySource[r.source] = fs;
}
function isNew(r) {
  const fs = (r.first_seen||'').slice(0,10);
  if (watermark) return fs > watermark.slice(0,10) || (r.first_seen||'') > watermark;
  return fs === latestSeenBySource[r.source];
}
let stateFilter = 'open', statusFilter = null, q = '', u10only = false,
    newOnly = false, sourceFilter = null, vnOnly = false, chgOnly = false;   // default view: open only

function esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
                        .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
function save() { localStorage.setItem(LSKEY, JSON.stringify(decisions)); }
function dec(p) { return decisions[p] || {state:'open', reason:'', comment:''}; }

function reasonUi(d) {
  if (d.state !== 'excluded') return '';
  const opts = ['<option value="">— סיבת החרגה —</option>'];
  const inList = REASONS.includes(d.reason);
  for (const x of REASONS)
    opts.push(`<option value="${esc(x)}"${d.reason===x?' selected':''}>${esc(x)}</option>`);
  if (d.reason && !inList)
    opts.push(`<option value="${esc(d.reason)}" selected>${esc(d.reason)}</option>`);
  return `<div class="reason"><select data-act="reason">${opts.join('')}</select></div>`;
}

function fmtDate(ts) {
  if (!ts) return '';
  const d = new Date(ts);
  if (isNaN(d)) return ts.slice(0,10);
  return d.toLocaleDateString('he-IL');
}

function render() {
  const tbody = document.getElementById('rows');
  const ql = q.trim();
  let kept = 0, excluded = 0, open = 0, newCount = 0, vnPending = 0, chgPending = 0;
  const visible = [];
  for (const r of DATA) {
    const d = dec(r.plan);
    const isVn = r.kind === 'vault_notice';
    const isChg = r.kind === 'status_change';
    const isSpecial = isVn || isChg;
    if (isVn) { if (d.state !== 'seen') vnPending++; }
    else if (isChg) { if (d.state !== 'approved' && d.state !== 'rejected') chgPending++; }
    else if (d.state==='kept') kept++; else if (d.state==='excluded') excluded++; else open++;
    if (isNew(r) && d.state==='open' && !isSpecial) newCount++;
    if (vnOnly && !isVn) continue;
    if (chgOnly && !isChg) continue;
    if (!vnOnly && isVn && d.state === 'seen') continue;
    if (!chgOnly && isChg && (d.state === 'approved' || d.state === 'rejected')) continue;
    if ((stateFilter === 'kept' || stateFilter === 'excluded') && isSpecial) continue;
    if (stateFilter && !isSpecial && d.state !== stateFilter) continue;
    if (statusFilter && r.status !== statusFilter) continue;
    if (sourceFilter && r.source !== sourceFilter) continue;
    if (u10only && !r.units10) continue;
    if (newOnly && !isNew(r)) continue;
    if (ql && !((r.name||'')+(r.display_plan||'')+(r.location||'')).includes(ql)) continue;
    visible.push([r, d]);
  }
  // kept view = the vault-entry queue: most recent decision first
  if (stateFilter === 'kept')
    visible.sort((a, b) => (b[1].ts||'').localeCompare(a[1].ts||''));
  const rowsHtml = [];
  for (const [r, d] of visible) {
    const isVn = r.kind === 'vault_notice';
    const isChg = r.kind === 'status_change';
    const cls = isVn ? 'vaultnotice' : isChg ? 'statuschange'
              : d.state==='excluded' ? 'excluded' : d.state==='kept' ? 'kept' : '';
    const badges = (r.units10 ? '<span class="u10">10+</span>' : '')
                 + (isVn ? '<span class="vn">כבר בכספת — חדש במבא"ת</span>'
                    : isChg ? '<span class="chg">שינוי סטטוס</span>'
                    : isNew(r) ? '<span class="u10" style="background:#e6f6ec;color:var(--green)">חדש</span>' : '')
                 + (r.source==='committee' ? '<span class="src">ועדה מקומית</span>' : '');
    const decidedTag = (d.state!=='open' && d.ts)
      ? `<div class="muted">הוחלט: ${fmtDate(d.ts)}</div>` : '';
    let actionCell;
    if (isVn) {
      actionCell = `<button class="btn keep ${d.state==='seen'?'active-keep':''}" data-act="seen">כבר נבדק, הבנתי</button>
         ${decidedTag}`;
    } else if (isChg) {
      const isUnitsOnly = r.note === 'units-only';
      const changeTxt = isUnitsOnly
        ? '<span class="muted">שינוי יח"ד בלבד (ללא שינוי סטטוס)</span>'
        : `${esc(r.old_status||'?')} <span class="muted">(${esc(r.old_date||'')})</span>
           <span class="arrow">←</span> <b>${esc(r.status||'')}</b>
           <span class="muted">(${esc(r.status_date||'')})</span>`
          + (r.status_detail ? `<div class="muted">(${esc(r.status_detail)})</div>` : '');
      const unitsTxt = (r.old_units!=null && r.new_units!=null && r.old_units!==r.new_units)
        ? `<span class="units">${r.old_units} ← <b>${r.new_units}</b></span>`
        : (r.new_units!=null ? `<span class="units">${r.new_units}</span>` : '');
      actionCell = `<div>${changeTxt}</div>${unitsTxt}<div style="margin-top:5px">
         <button class="btn keep ${d.state==='approved'?'active-keep':''}" data-act="approve">אשר לכספת</button>
         <button class="btn ex ${d.state==='rejected'?'active-ex':''}" data-act="reject">דחה</button>
         ${decidedTag}
         <input class="comment" data-act="comment" placeholder="הערה..." value="${esc(d.comment)}"></div>`;
    } else {
      actionCell = `<button class="btn keep ${d.state==='kept'?'active-keep':''}" data-act="keep">להזנה</button>
         <button class="btn ex ${d.state==='excluded'?'active-ex':''}" data-act="exclude">להחריג</button>
         ${decidedTag}
         ${reasonUi(d)}
         <input class="comment" data-act="comment" placeholder="הערה..." value="${esc(d.comment)}">`;
    }
    // no real link for this row (2026-07-21: an empty href fell back to '#', which browsers
    // resolve to the CURRENT page — misleadingly looked like a broken/self-referencing link
    // rather than "no link available"). Render plain text instead of a dead anchor.
    const planCell = r.url
      ? `<a href="${esc(r.url)}" target="_blank" title="נצפתה: ${esc((r.first_seen||'').slice(0,10))}">${esc(r.display_plan)}</a>`
      : `<span title="אין קישור זמין">${esc(r.display_plan)}</span>`;
    rowsHtml.push(`<tr class="${cls}" data-plan="${esc(r.plan)}">
      <td>${planCell}${badges}</td>
      <td>${esc(r.name)}</td><td>${esc(r.location)}</td><td>${esc(r.authority)}</td>
      <td>${esc(r.status)}</td><td>${esc(r.status_date)}</td>
      <td>${actionCell}</td></tr>`);
  }
  tbody.innerHTML = rowsHtml.join('');
  const newChip = document.getElementById('newChip');
  if (newChip) newChip.textContent = `חדשות מהסריקה האחרונה (${newCount})`;
  const vnChip = document.getElementById('vnChip');
  if (vnChip) vnChip.textContent = `כבר בכספת — חדש במבא"ת (${vnPending})`;
  const chgChip = document.getElementById('chgChip');
  if (chgChip) chgChip.textContent = `שינויי סטטוס לאישור (${chgPending})`;
  document.getElementById('counts').textContent =
    `מציג ${visible.length} · פתוחות ${open} · נשמרו ${kept} · הוחרגו ${excluded}`
    + ` · התראות כספת ${vnPending} · שינויי סטטוס ${chgPending} · סה"כ ${DATA.length}`;
}

const tbody = document.getElementById('rows');
tbody.addEventListener('click', e => {
  const btn = e.target.closest('button[data-act]');
  if (!btn) return;
  const plan = btn.closest('tr').dataset.plan;
  const act = btn.dataset.act;
  const target = act === 'keep' ? 'kept' : act === 'seen' ? 'seen'
               : act === 'approve' ? 'approved' : act === 'reject' ? 'rejected' : 'excluded';
  const d = dec(plan);
  d.state = (d.state === target) ? 'open' : target;
  d.ts = new Date().toISOString();
  decisions[plan] = d; save(); render();
});
tbody.addEventListener('change', e => {
  const el = e.target;
  const tr = el.closest('tr');
  if (!tr) return;
  const plan = tr.dataset.plan;
  const d = dec(plan);
  if (el.matches('select[data-act="reason"]')) d.reason = el.value;
  if (el.matches('input[data-act="comment"]')) d.comment = el.value;
  decisions[plan] = d; save();
});

document.getElementById('q').addEventListener('input', e => { q=e.target.value; render(); });
document.querySelectorAll('.chip[data-state]').forEach(ch => ch.onclick = () => {
  const s = ch.dataset.state;
  stateFilter = (stateFilter===s) ? null : s;
  document.querySelectorAll('.chip[data-state]').forEach(c =>
    c.classList.toggle('on', c.dataset.state===stateFilter));
  render();
});
document.getElementById('u10chip').onclick = () => {
  u10only = !u10only;
  document.getElementById('u10chip').classList.toggle('on', u10only);
  render();
};
document.getElementById('newChip').onclick = () => {
  newOnly = !newOnly;
  document.getElementById('newChip').classList.toggle('on', newOnly);
  render();
};
document.getElementById('vnChip').onclick = () => {
  vnOnly = !vnOnly;
  document.getElementById('vnChip').classList.toggle('on', vnOnly);
  render();
};
document.getElementById('chgChip').onclick = () => {
  chgOnly = !chgOnly;
  document.getElementById('chgChip').classList.toggle('on', chgOnly);
  render();
};
document.querySelectorAll('.chip[data-src]').forEach(ch => ch.onclick = () => {
  const s = ch.dataset.src;
  sourceFilter = (sourceFilter===s) ? null : s;
  document.querySelectorAll('.chip[data-src]').forEach(c =>
    c.classList.toggle('on', c.dataset.src===sourceFilter));
  render();
});
function wmRender() {
  document.getElementById('wmLabel').textContent =
    watermark ? `נצפה עד: ${fmtDate(watermark)}` : '';
}
document.getElementById('markSeenBtn').onclick = () => {
  watermark = new Date().toISOString();
  localStorage.setItem(WMKEY, watermark);
  wmRender(); render();
};
wmRender();
// status chips
const statuses = [...new Set(DATA.map(r=>r.status))];
const chipsBox = document.getElementById('statusChips');
for (const s of statuses) {
  const el = document.createElement('span');
  el.className = 'chip';
  el.textContent = s + ` (${DATA.filter(r=>r.status===s).length})`;
  el.onclick = () => {
    statusFilter = (statusFilter===s) ? null : s;
    chipsBox.querySelectorAll('.chip').forEach(c=>c.classList.remove('on'));
    if (statusFilter) el.classList.add('on');
    render();
  };
  chipsBox.appendChild(el);
}
// reflect the default open-only view in the chip bar
document.querySelector('.chip[data-state="open"]').classList.add('on');
// pin the column-titles row exactly below the real header height (it varies with
// window width as the chip bar wraps) — a hardcoded offset leaves a see-through gap
function setStickyTop() {
  document.documentElement.style.setProperty('--hdrH',
    document.querySelector('header').offsetHeight + 'px');
}
window.addEventListener('resize', setStickyTop);
setStickyTop();
document.getElementById('exportBtn').onclick = () => {
  const out = [];
  for (const [plan, d] of Object.entries(decisions))
    if (d.state !== 'open' || d.comment)
      out.push({plan, state:d.state, reason:d.reason||'', comment:d.comment||'',
                ts:d.ts||''});
  // UTF-8 BOM prefix: without it, some Windows text tools (Notepad, some chat/upload
  // pipelines) auto-detect the system codepage (cp1252/1255) instead of UTF-8 and mangle
  // every Hebrew character into '×'-led mojibake on open. The BOM makes UTF-8 explicit.
  const blob = new Blob(['﻿' + JSON.stringify(out, null, 1)],
                        {type:'application/json;charset=utf-8'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'mavat_review_decisions.json';
  a.click();
};
render();
</script>
</body>
</html>
"""

html = html.replace("__DATA__", payload).replace("__GENERATED__", generated)
OUT.write_text(html, encoding="utf-8")
n_mavat = sum(1 for r in data if r["source"] == "mavat")
n_committee = sum(1 for r in data if r["source"] == "committee")
print(f"[OK] {len(data)} candidates ({n_mavat} mavat, {n_committee} committee) -> {OUT}")
