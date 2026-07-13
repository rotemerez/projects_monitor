r"""
make_changes_page.py — generate mavat_changes.html: approval page for detected Mavat
status/unit changes (pending rows in mavat_state.db:mavat_changes).

Approve = the change will be written into the vault (new `- סטטוס::` line in the project
block) by apply_changes.py; Reject = recorded, never shown again. Decisions persist in
localStorage and are exported as JSON:
  venv\Scripts\python.exe apply_changes.py changes_decisions.json

Regenerated automatically by the nightly run (run_status_diff.bat).
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
STATE_DB = HERE / "mavat_state.db"
PROJECTS_DB = HERE.parent / "projects.db"
OUT = HERE / "mavat_changes.html"

state = sqlite3.connect(STATE_DB)
cur = state.execute("""SELECT id, plan, changed_at, old_status, old_date, new_status,
                              new_date, old_units, new_units, note
                       FROM mavat_changes WHERE approved IS NULL
                       ORDER BY changed_at DESC, plan""")
cols = ["id", "plan", "changed_at", "old_status", "old_date", "new_status", "new_date",
        "old_units", "new_units", "note"]
changes = [dict(zip(cols, r)) for r in cur.fetchall()]
state.close()

proj = sqlite3.connect(PROJECTS_DB)
ctx = {}
for plan, city, name in proj.execute(
        "SELECT plan_current, city, project_name FROM projects WHERE plan_current != ''"):
    ctx.setdefault(str(plan).strip().replace(" ", ""), (city, name))
proj.close()
for ch in changes:
    city, name = ctx.get(ch["plan"], ("", ""))
    ch["city"], ch["project"] = city, name
    ch["url"] = f"https://mavat.iplan.gov.il/SV3?searchEntity=1&entityType=1&searchMethod=2"

generated = datetime.now().strftime("%d/%m/%Y %H:%M")
payload = json.dumps(changes, ensure_ascii=False).replace("</", "<\\/")

html = """<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<title>אישור עדכוני סטטוס — Mavat</title>
<style>
  :root { --bg:#f7f8fa; --card:#fff; --line:#e3e6ea; --txt:#1c2733; --dim:#6b7683;
          --blue:#1560a8; --red:#c0392b; --green:#1e8449; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:"Segoe UI",Arial,sans-serif; background:var(--bg);
         color:var(--txt); }
  header { position:sticky; top:0; z-index:5; background:var(--card);
           border-bottom:1px solid var(--line); padding:10px 18px; }
  h1 { font-size:18px; margin:0 0 8px; }
  .bar { display:flex; flex-wrap:wrap; gap:8px; align-items:center; }
  .export { background:var(--blue); color:#fff; border:none; border-radius:6px;
       padding:7px 16px; font-size:14px; cursor:pointer; }
  .counts { font-size:13px; color:var(--dim); margin-inline-start:auto; }
  main { padding:14px 18px; max-width:1200px; margin:0 auto; }
  table { width:100%; border-collapse:collapse; background:var(--card);
          border:1px solid var(--line); }
  th { text-align:right; font-size:12.5px; color:var(--dim); font-weight:600;
       padding:8px 10px; border-bottom:1px solid var(--line); background:#fbfcfd;
       position:sticky; top:var(--hdrH, 60px); z-index:4; }
  td { padding:8px 10px; border-bottom:1px solid var(--line); font-size:13.5px;
       vertical-align:top; }
  tr.approved td { background:#eefaf1; }
  tr.rejected td { background:#fdf0ee; color:#8d6e68; }
  a { color:var(--blue); text-decoration:none; }
  .btn { border:1px solid var(--line); background:#fff; border-radius:6px; padding:3px 10px;
         font-size:12.5px; cursor:pointer; margin-inline-end:4px; }
  .btn.ok { color:var(--green); border-color:#bfe3c9; }
  .btn.no { color:var(--red); border-color:#e7c4bf; }
  .btn.on-ok { background:var(--green); color:#fff; }
  .btn.on-no { background:var(--red); color:#fff; }
  .comment { width:100%; font-size:12.5px; padding:3px 6px; border:1px solid var(--line);
       border-radius:5px; margin-top:4px; }
  .arrow { color:var(--dim); }
  .units { background:#e8f1fa; color:var(--blue); border-radius:10px; font-size:12px;
       padding:1px 8px; }
  .muted { color:var(--dim); font-size:12px; }
</style>
</head>
<body>
<header>
  <h1>אישור עדכוני סטטוס ממבא"ת <span class="muted">(נוצר __GENERATED__)</span></h1>
  <div class="bar">
    <button class="export" id="exportBtn">יצוא החלטות (JSON)</button>
    <span class="muted">מאושר = יתווסף כשורת סטטוס לכספת (vault) ע"י apply_changes.py</span>
    <span class="counts" id="counts"></span>
  </div>
</header>
<main>
  <table>
    <thead><tr>
      <th style="width:110px">מס' תכנית</th><th>פרויקט</th>
      <th>שינוי</th><th style="width:110px">יח"ד</th>
      <th style="width:95px">זוהה בתאריך</th><th style="width:220px">החלטה</th>
    </tr></thead>
    <tbody id="rows"></tbody>
  </table>
</main>
<script id="data" type="application/json">__DATA__</script>
<script>
const DATA = JSON.parse(document.getElementById('data').textContent);
const LSKEY = 'mavat_changes_decisions_v1';
let decisions = JSON.parse(localStorage.getItem(LSKEY) || '{}');

function esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
                        .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
function save() { localStorage.setItem(LSKEY, JSON.stringify(decisions)); }
function dec(id) { return decisions[id] || {action:'', comment:''}; }

function render() {
  const tbody = document.getElementById('rows');
  let approved = 0, rejected = 0, open = 0;
  const rowsHtml = [];
  for (const ch of DATA) {
    const d = dec(ch.id);
    if (d.action==='approve') approved++; else if (d.action==='reject') rejected++; else open++;
    const cls = d.action==='approve' ? 'approved' : d.action==='reject' ? 'rejected' : '';
    const isUnitsOnly = ch.note === 'units-only';
    const changeTxt = isUnitsOnly
      ? '<span class="muted">שינוי יח"ד בלבד (ללא שינוי סטטוס)</span>'
      : `${esc(ch.old_status||'?')} <span class="muted">(${esc(ch.old_date||'')})</span>
         <span class="arrow">←</span> <b>${esc(ch.new_status||'')}</b>
         <span class="muted">(${esc(ch.new_date||'')})</span>`;
    const unitsTxt = (ch.old_units!=null && ch.new_units!=null && ch.old_units!==ch.new_units)
      ? `<span class="units">${ch.old_units} ← <b>${ch.new_units}</b></span>`
      : (ch.new_units!=null ? `<span class="muted">${ch.new_units}</span>` : '');
    rowsHtml.push(`<tr class="${cls}" data-id="${ch.id}">
      <td>${esc(ch.plan)}</td>
      <td>${esc(ch.city)}${ch.project ? ' / ' + esc(ch.project) : ''}</td>
      <td>${changeTxt}</td>
      <td>${unitsTxt}</td>
      <td>${esc((ch.changed_at||'').slice(0,10))}</td>
      <td>
        <button class="btn ok ${d.action==='approve'?'on-ok':''}" data-act="approve">אשר</button>
        <button class="btn no ${d.action==='reject'?'on-no':''}" data-act="reject">דחה</button>
        <input class="comment" data-act="comment" placeholder="הערה..." value="${esc(d.comment)}">
      </td></tr>`);
  }
  tbody.innerHTML = rowsHtml.join('');
  document.getElementById('counts').textContent =
    `ממתינים ${open} · לאישור ${approved} · נדחו ${rejected} · סה"כ ${DATA.length}`;
}

const tbody = document.getElementById('rows');
tbody.addEventListener('click', e => {
  const btn = e.target.closest('button[data-act]');
  if (!btn) return;
  const id = btn.closest('tr').dataset.id;
  const d = dec(id);
  d.action = (d.action === btn.dataset.act) ? '' : btn.dataset.act;
  d.ts = new Date().toISOString();
  decisions[id] = d; save(); render();
});
tbody.addEventListener('change', e => {
  if (!e.target.matches('input[data-act="comment"]')) return;
  const id = e.target.closest('tr').dataset.id;
  const d = dec(id);
  d.comment = e.target.value;
  decisions[id] = d; save();
});
document.getElementById('exportBtn').onclick = () => {
  const out = [];
  for (const [id, d] of Object.entries(decisions))
    if (d.action)
      out.push({id: Number(id), action: d.action, comment: d.comment||'', ts: d.ts||''});
  const blob = new Blob([JSON.stringify(out, null, 1)], {type:'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'mavat_changes_decisions.json';
  a.click();
};
function setStickyTop() {
  document.documentElement.style.setProperty('--hdrH',
    document.querySelector('header').offsetHeight + 'px');
}
window.addEventListener('resize', setStickyTop);
setStickyTop();
render();
</script>
</body>
</html>
"""

html = html.replace("__DATA__", payload).replace("__GENERATED__", generated)
OUT.write_text(html, encoding="utf-8")
print(f"[OK] {len(changes)} pending changes -> {OUT}")
