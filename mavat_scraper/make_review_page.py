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
OUT = HERE / "mavat_review.html"


def load_mavat():
    con = sqlite3.connect(MAVAT_DB)
    for ddl in ("ALTER TABLE discovered ADD COLUMN kept INTEGER DEFAULT 0",
                "ALTER TABLE discovered ADD COLUMN decided_at TEXT"):
        try:
            con.execute(ddl)
        except sqlite3.OperationalError:
            pass
    has_units = any(r[1] == "units_ge10"
                    for r in con.execute("PRAGMA table_info(discovered)"))
    units_col = ", COALESCE(units_ge10,0)" if has_units else ", 0"
    cur = con.execute(f"""SELECT plan, name, location, authority, status, status_date, url,
                                 excluded, exclude_reason, comment, first_seen,
                                 COALESCE(kept,0), decided_at{units_col}
                          FROM discovered WHERE target_status=1 AND in_vault=0
                          ORDER BY status, location, plan""")
    rows = []
    for (plan, name, location, authority, status, status_date, url, excluded,
         exclude_reason, comment, first_seen, kept, decided_at, units10) in cur.fetchall():
        rows.append({"plan": plan, "display_plan": plan, "name": name, "location": location,
                     "authority": authority, "status": status, "status_date": status_date,
                     "url": url, "excluded": excluded, "exclude_reason": exclude_reason,
                     "comment": comment, "first_seen": first_seen, "kept": kept,
                     "decided_at": decided_at, "units10": units10, "source": "mavat"})
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
                     "units10": 0, "source": "committee"})
    con.close()
    return rows


data = load_mavat() + load_committee()

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
  a { color:var(--blue); text-decoration:none; }
  .u10 { display:inline-block; background:#e8f1fa; color:var(--blue); border-radius:10px;
         font-size:11px; padding:1px 7px; margin-inline-start:6px; }
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
// seed from DB state (decisions applied on previous rounds, incl. automatic rules)
for (const r of DATA) {
  if (r.excluded && !decisions[r.plan])
    decisions[r.plan] = {state:'excluded', reason:r.exclude_reason||'', comment:r.comment||'',
                         ts:r.decided_at||''};
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
    newOnly = false, sourceFilter = null;   // default view: open only

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
  let kept = 0, excluded = 0, open = 0, newCount = 0;
  const visible = [];
  for (const r of DATA) {
    const d = dec(r.plan);
    if (d.state==='kept') kept++; else if (d.state==='excluded') excluded++; else open++;
    if (isNew(r) && d.state==='open') newCount++;
    if (stateFilter && d.state !== stateFilter) continue;
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
    const cls = d.state==='excluded' ? 'excluded' : d.state==='kept' ? 'kept' : '';
    const badges = (r.units10 ? '<span class="u10">10+</span>' : '')
                 + (isNew(r) ? '<span class="u10" style="background:#e6f6ec;color:var(--green)">חדש</span>' : '')
                 + (r.source==='committee' ? '<span class="src">ועדה מקומית</span>' : '');
    const decidedTag = (d.state!=='open' && d.ts)
      ? `<div class="muted">הוחלט: ${fmtDate(d.ts)}</div>` : '';
    rowsHtml.push(`<tr class="${cls}" data-plan="${esc(r.plan)}">
      <td><a href="${esc(r.url||'#')}" target="_blank" title="נצפתה: ${esc((r.first_seen||'').slice(0,10))}">${esc(r.display_plan)}</a>${badges}</td>
      <td>${esc(r.name)}</td><td>${esc(r.location)}</td><td>${esc(r.authority)}</td>
      <td>${esc(r.status)}</td><td>${esc(r.status_date)}</td>
      <td>
        <button class="btn keep ${d.state==='kept'?'active-keep':''}" data-act="keep">להזנה</button>
        <button class="btn ex ${d.state==='excluded'?'active-ex':''}" data-act="exclude">להחריג</button>
        ${decidedTag}
        ${reasonUi(d)}
        <input class="comment" data-act="comment" placeholder="הערה..." value="${esc(d.comment)}">
      </td></tr>`);
  }
  tbody.innerHTML = rowsHtml.join('');
  const newChip = document.getElementById('newChip');
  if (newChip) newChip.textContent = `חדשות מהסריקה האחרונה (${newCount})`;
  document.getElementById('counts').textContent =
    `מציג ${visible.length} · פתוחות ${open} · נשמרו ${kept} · הוחרגו ${excluded} · סה"כ ${DATA.length}`;
}

const tbody = document.getElementById('rows');
tbody.addEventListener('click', e => {
  const btn = e.target.closest('button[data-act]');
  if (!btn) return;
  const plan = btn.closest('tr').dataset.plan;
  const target = btn.dataset.act === 'keep' ? 'kept' : 'excluded';
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
  const blob = new Blob([JSON.stringify(out, null, 1)], {type:'application/json'});
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
