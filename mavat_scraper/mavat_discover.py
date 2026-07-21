r"""
mavat_discover.py — discover new plans on Mavat for the projects pipeline.

Strategy (the status dropdown can't be driven headless, so filtering is client-side):
  1. Search nationwide with כל התכניות + תאריך הסטטוס האחרון >= --since.
  2. Page through ALL results via the 'הצג עוד' (load more) button, harvesting every
     sv3/Search response (page 1: 20 rows, subsequent pages: 50 rows).
  3. Store every row in mavat_discovery.db; flag rows whose status is one of the
     TARGET_STATUSES (early planning stages = "new plan" signal) and whether the plan
     is already tracked in projects.db.
  4. Candidates = target status + not in vault + not excluded. Reviewed via the
     companion review page (see export_review_json / mavat_review.html).

Usage (mavat_scraper venv):
  venv\Scripts\python.exe mavat_discover.py --since 01/01/2022            # backfill
  venv\Scripts\python.exe mavat_discover.py --since 01/01/2024 --count-only
  venv\Scripts\python.exe mavat_discover.py                                # since last sweep
  venv\Scripts\python.exe mavat_discover.py --export-json out.json        # no scrape; dump
"""
import argparse
import json
import re
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
PROJECTS_DB = HERE.parent / "projects.db"
DISCOVERY_DB = HERE / "mavat_discovery.db"
SEARCH_URL = "https://mavat.iplan.gov.il/SV3?searchEntity=1&entityType=1&searchMethod=2"

# Statuses worth surfacing for review (chosen by the user 2026-07-09; revised 2026-07-12:
# added Pre-Ruling, dropped two labels that do not exist as Mavat UNIFIED_STATUS_DESC
# values; revised 2026-07-15: unified with mavat_diff.py's status-change whitelist — same
# 9 statuses now govern new-candidate discovery here AND change-reporting there. Anything
# else (עריכת תכנית תמ"א, הפצה למוזמנים, במילוי תנאים להפקדה, הגשת/מילוי הערות והשגות,
# הכרעה בהתנגדויות/אישור, בהליך אישור, העברה לממשלה לאישור) is intentionally excluded —
# the user does not want review or vault updates for those. Matching is exact. KEEP IN
# SYNC with MAVAT_TRACKED_STATUSES in mavat_diff.py.
TARGET_STATUSES = {
    "הכנת הודעה 77/78",
    "הכנת תכנית",
    "Pre-Ruling",
    "תסקיר סביבתי",
    "בבדיקת תנאי סף",
    "בבדיקה תכנונית",
    "הפקדה להתנגדויות/השגות",
    "אישור",
    "נדחתה",
}

CLICK_DELAY_S = 0.8       # politeness between load-more clicks
PAGE_TIMEOUT_S = 25       # wait for each page's search response


def open_db():
    con = sqlite3.connect(DISCOVERY_DB)
    con.execute("""CREATE TABLE IF NOT EXISTS discovered(
        plan TEXT PRIMARY KEY,
        name TEXT, location TEXT, authority TEXT,
        status TEXT, status_date TEXT, mid INTEGER, url TEXT,
        target_status INTEGER, in_vault INTEGER,
        first_seen TEXT, last_seen TEXT,
        excluded INTEGER DEFAULT 0, exclude_reason TEXT, comment TEXT,
        raw JSON)""")
    con.execute("""CREATE TABLE IF NOT EXISTS sweeps(
        id INTEGER PRIMARY KEY AUTOINCREMENT, started TEXT, since_date TEXT,
        records_total INTEGER, rows_harvested INTEGER, finished TEXT, note TEXT)""")
    con.commit()
    return con


def vault_plans():
    con = sqlite3.connect(PROJECTS_DB)
    plans = {str(r[0]).strip().replace(" ", "")
             for r in con.execute("SELECT plan_current FROM projects WHERE plan_current != ''")}
    con.close()
    return plans


def norm_plan(s):
    return str(s or "").strip().replace(" ", "")


DISPLAY_CAP = 1400   # the site stops serving 'הצג עוד' around 1,470 rows; stay under it


def _query(page, responses, since_ddmmyyyy, plan_prefix=None, count_only=False,
           max_pages=None, min_units=None):
    """Fresh form -> set filters -> search -> harvest all pages. Returns (rows, records)."""
    rows = []
    meta = {"records": None}
    page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=60000)
    page.locator("input[aria-label='מספר תכנית']").wait_for(state="visible", timeout=30000)
    page.wait_for_timeout(1200)

    # verified all-plans radio (same pattern as mavat_status.py)
    radios = page.get_by_role("radio")
    deadline = time.time() + 30
    ok = False
    while time.time() < deadline:
        try:
            if radios.count() >= 1 and radios.first.is_checked():
                ok = True
                break
        except Exception:
            pass
        try:
            page.get_by_text("כל התכניות", exact=True).click(timeout=2000)
        except Exception:
            pass
        page.wait_for_timeout(250)
    if not ok:
        raise RuntimeError("could not verify the all-plans filter")

    # masked date input: must be typed, not fill()ed
    fld = page.locator("input[aria-label='תאריך הסטטוס האחרון']").first
    fld.click()
    page.wait_for_timeout(300)
    page.keyboard.type(since_ddmmyyyy, delay=100)
    page.wait_for_timeout(300)
    page.keyboard.press("Tab")
    page.wait_for_timeout(500)
    if fld.input_value() != since_ddmmyyyy:
        raise RuntimeError(f"date not accepted: {fld.input_value()!r}")

    if plan_prefix:
        pf = page.locator("input[aria-label='מספר תכנית']")
        pf.click()
        pf.fill(plan_prefix)
        page.wait_for_timeout(300)

    if min_units:
        uf = page.locator("input[aria-label='מספר יחידות דיור החל מ']").first
        uf.click()
        page.keyboard.type(str(min_units), delay=80)
        page.wait_for_timeout(300)

    def is_ours(post_data):
        """The page also fires generic searches (on load / on the radio toggle); only a
        response whose REQUEST payload carries our exact filters is ours."""
        pd = post_data or ""
        if '"dateLastStatusDate"' not in pd or '"dateLastStatusDate":null' in pd:
            return False
        if min_units and f'"residentialUnit":{min_units},' not in pd:
            return False   # numeric in the payload, comma-terminated (avoid 10 vs 100)
        return f'"plNumber":"{plan_prefix or ""}"' in pd

    def harvest(new_pairs):
        got = 0
        for post_data, body in new_pairs:
            if not is_ours(post_data):
                continue
            for blk in body:
                r = blk.get("result") or {}
                if not isinstance(r, dict):
                    continue
                if r.get("intRecordsCount") is not None and meta["records"] is None:
                    meta["records"] = r["intRecordsCount"]
                for row in (r.get("dtResults") or []):
                    rows.append(row)
                    got += 1
        return got

    def wait_ours(start_idx, timeout_s=PAGE_TIMEOUT_S):
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if any(is_ours(pd) for pd, _ in responses[start_idx:]):
                return True
            page.wait_for_timeout(250)
        return False

    n = len(responses)
    btn = page.get_by_role("button", name="חיפוש", exact=True)
    deadline = time.time() + 10
    while time.time() < deadline and not btn.is_enabled():
        page.wait_for_timeout(300)
    btn.click(timeout=8000)
    wait_ours(n)
    page.wait_for_timeout(600)
    harvest(responses[n:])
    if count_only:
        return rows, meta["records"] or 0

    expected = meta["records"] or 0
    clicks = stalls = 0
    while len(rows) < expected:
        if max_pages and clicks >= max_pages:
            print(f"[!] stopping at --max-pages={max_pages}; "
                  f"harvested {len(rows)}/{expected}", flush=True)
            break
        n = len(responses)
        try:
            page.get_by_role("button", name="הצג עוד").click(timeout=8000)
        except Exception:
            if len(rows) < expected:
                print(f"[!] load-more gone at {len(rows)}/{expected} "
                      f"(prefix={plan_prefix})", flush=True)
            break
        got_resp = wait_ours(n)
        got = harvest(responses[n:]) if got_resp else 0
        clicks += 1
        if got == 0:
            stalls += 1
            if stalls >= 3:
                print(f"[!] 3 empty responses; stopping at {len(rows)}/{expected}",
                      flush=True)
                break
        else:
            stalls = 0
        if clicks % 20 == 0:
            print(f"  ... {len(rows)}/{expected} rows", flush=True)
        time.sleep(CLICK_DELAY_S)
    return rows, meta["records"] or 0


def sweep(since_ddmmyyyy, count_only=False, headless=True, max_pages=None):
    """Single nationwide date-scoped search (weekly mode). Capped at ~1,470 rows by the
    site — fine for routine windows; use --backfill for large ones."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context(locale="he-IL", viewport={"width": 1400, "height": 1400})
        page = ctx.new_page()
        responses = []

        def on_resp(resp):
            if "/rest/api/sv3/Search" in resp.url and resp.status == 200:
                try:
                    responses.append((resp.request.post_data, resp.json()))
                except Exception:
                    pass
        page.on("response", on_resp)
        rows, records = _query(page, responses, since_ddmmyyyy, count_only=count_only,
                               max_pages=max_pages)
        print(f"[..] since {since_ddmmyyyy}: {records} records", flush=True)
        browser.close()
    return rows, {"records": records}


def backfill(since_ddmmyyyy, headless=True, min_units=None):
    """Full harvest of a large window by recursive plan-number-prefix slicing (the site
    caps any single result list at ~1,470 rows). Covers new-format numbers (NNN-...);
    old-format numbers can't be prefix-sliced and are skipped — logged at the end."""
    # seed prefixes: district codes seen in our DBs
    codes = set()
    for db, q in [(PROJECTS_DB, "SELECT plan_current FROM projects"),
                  (DISCOVERY_DB, "SELECT plan FROM discovered")]:
        try:
            con = sqlite3.connect(db)
            for (v,) in con.execute(q):
                m = re.match(r"^(\d{3})-", norm_plan(v))
                if m:
                    codes.add(m.group(1))
            con.close()
        except Exception:
            pass
    # cover unseen district codes too: probe every leading digit series via recursion
    seeds = sorted({c + "-" for c in codes})
    print(f"[..] backfill since {since_ddmmyyyy}: {len(seeds)} seed prefixes", flush=True)

    all_rows = []
    failed_prefixes = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context(locale="he-IL", viewport={"width": 1400, "height": 1400})
        responses = []

        def on_resp(resp):
            if "/rest/api/sv3/Search" in resp.url and resp.status == 200:
                try:
                    responses.append((resp.request.post_data, resp.json()))
                except Exception:
                    pass

        holder = {"page": None}

        def new_page():
            if holder["page"]:
                try:
                    holder["page"].close()
                except Exception:
                    pass
            pg = ctx.new_page()
            pg.on("response", on_resp)
            holder["page"] = pg

        new_page()

        def q(**kw):
            """_query with retries: a slow render / stalled page gets a fresh page,
            not a dead run."""
            last = None
            for attempt in range(3):
                try:
                    return _query(holder["page"], responses, since_ddmmyyyy,
                                  min_units=min_units, **kw)
                except Exception as e:
                    last = e
                    print(f"  [!] query failed ({type(e).__name__}), "
                          f"attempt {attempt + 1}/3", flush=True)
                    time.sleep(10)
                    new_page()
            raise last

        def do_prefix(prefix):
            try:
                _, count = q(plan_prefix=prefix, count_only=True)
            except Exception:
                failed_prefixes.append(prefix)
                return
            if count == 0:
                return
            if count <= DISPLAY_CAP:
                try:
                    rows, records = q(plan_prefix=prefix)
                except Exception:
                    failed_prefixes.append(prefix)
                    return
                all_rows.extend(rows)
                print(f"  [{prefix}] {len(rows)}/{records} rows "
                      f"(total {len(all_rows)})", flush=True)
            else:
                print(f"  [{prefix}] {count} > cap; splitting", flush=True)
                for d in "0123456789":
                    do_prefix(prefix + d)

        for seed in seeds:
            do_prefix(seed)
        # nationwide total for coverage accounting (old-format numbers not sliceable)
        try:
            _, nationwide = q(count_only=True)
        except Exception:
            nationwide = None
        browser.close()

    if failed_prefixes:
        print(f"[!] {len(failed_prefixes)} prefixes failed after retries and were "
              f"SKIPPED: {failed_prefixes}", flush=True)

    print(f"[..] backfill harvested {len(all_rows)} of {nationwide} nationwide rows "
          f"(gap = old-format plan numbers + unseen district codes)", flush=True)
    return all_rows, {"records": nationwide}


def store(con, rows, vault, since):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur = con.cursor()
    new_targets = 0
    for row in rows:
        plan = norm_plan(row.get("ENTITY_NUMBER"))
        if not plan:
            continue
        status = row.get("UNIFIED_STATUS_DESC")
        mid = row.get("MP_ID") or row.get("MMI_ENTITY_ID")
        is_target = 1 if status in TARGET_STATUSES else 0
        in_vault = 1 if plan in vault else 0
        cur.execute("SELECT 1 FROM discovered WHERE plan=?", (plan,))
        existed = cur.fetchone() is not None
        cur.execute("""INSERT INTO discovered(plan, name, location, authority, status,
                           status_date, mid, url, target_status, in_vault,
                           first_seen, last_seen, raw)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(plan) DO UPDATE SET
                           name=excluded.name, location=excluded.location,
                           authority=excluded.authority, status=excluded.status,
                           status_date=excluded.status_date, mid=excluded.mid,
                           url=excluded.url, target_status=excluded.target_status,
                           in_vault=excluded.in_vault, last_seen=excluded.last_seen,
                           raw=excluded.raw""",
                    (plan, row.get("ENTITY_NAME"), row.get("ENTITY_LOCATION"),
                     row.get("AUTH_NAME"), status, row.get("BI_STATUS_DATE"),
                     int(mid) if mid else None,
                     f"https://mavat.iplan.gov.il/SV4/1/{int(mid)}/310" if mid else None,
                     is_target, in_vault, now, now, json.dumps(row, ensure_ascii=False)))
        if is_target and not in_vault and not existed:
            new_targets += 1
    con.commit()
    return new_targets


def export_review_json(con, path):
    """Dump review candidates (target status, not in vault) incl. review state."""
    cur = con.cursor()
    cur.execute("""SELECT plan, name, location, authority, status, status_date, url,
                          excluded, exclude_reason, comment, first_seen
                   FROM discovered
                   WHERE target_status=1 AND in_vault=0
                   ORDER BY status, location, plan""")
    cols = ["plan", "name", "location", "authority", "status", "status_date", "url",
            "excluded", "exclude_reason", "comment", "first_seen"]
    data = [dict(zip(cols, r)) for r in cur.fetchall()]
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[OK] exported {len(data)} candidates -> {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", help="DD/MM/YYYY; default = date of last finished sweep")
    ap.add_argument("--count-only", action="store_true", help="print record count and exit")
    ap.add_argument("--max-pages", type=int, help="safety cap on load-more clicks")
    ap.add_argument("--backfill", action="store_true",
                    help="large window: harvest via recursive plan-prefix slicing")
    ap.add_argument("--tag-units", type=int, metavar="N",
                    help="tagging sweep: re-harvest with 'units >= N' set and flag the "
                         "matching plans (units_ge10 column); implies --backfill")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--export-json", help="no scrape; export review candidates to this path")
    args = ap.parse_args()

    con = open_db()
    if args.export_json:
        export_review_json(con, args.export_json)
        return

    since = args.since
    if not since:
        cur = con.execute("SELECT started FROM sweeps WHERE finished IS NOT NULL "
                          "AND (note IS NULL OR note NOT LIKE 'tag-%') "
                          "ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        if not row:
            sys.exit("no previous sweep — pass --since DD/MM/YYYY for the first run")
        since = datetime.strptime(row[0][:10], "%Y-%m-%d").strftime("%d/%m/%Y")
        print(f"[..] using last sweep date: {since}")

    started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if args.tag_units:
        rows, meta = backfill(since, headless=not args.headed, min_units=args.tag_units)
    elif args.backfill:
        rows, meta = backfill(since, headless=not args.headed)
    else:
        rows, meta = sweep(since, count_only=args.count_only, headless=not args.headed,
                           max_pages=args.max_pages)
    if args.count_only:
        return

    if args.tag_units:
        # tagging run: record which plans clear the units threshold; also store the rows
        # (keeps names/statuses fresh, and catches plans that appeared since the backfill)
        try:
            con.execute("ALTER TABLE discovered ADD COLUMN units_ge10 INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        vault = vault_plans()
        store(con, rows, vault, since)
        tagged = 0
        for row in rows:
            plan = norm_plan(row.get("ENTITY_NUMBER"))
            if plan:
                con.execute("UPDATE discovered SET units_ge10=1 WHERE plan=?", (plan,))
                tagged += 1
        con.execute("INSERT INTO sweeps(started, since_date, records_total, rows_harvested,"
                    "finished, note) VALUES(?,?,?,?,?,?)",
                    (started, since, meta.get("records"), len(rows),
                     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                     f"tag-units>={args.tag_units}"))
        con.commit()
        cur = con.execute("""SELECT units_ge10, COUNT(*) FROM discovered
                             WHERE target_status=1 AND in_vault=0 AND excluded=0
                               AND COALESCE(kept,0)=0 GROUP BY units_ge10""")
        dist = dict(cur.fetchall())
        print(f"\n[OK] tagged {tagged} plans with units>={args.tag_units}; "
              f"open candidates: {dist.get(1, 0)} tagged / {dist.get(0, 0)} untagged")
        return

    con.execute("INSERT INTO sweeps(started, since_date, records_total, rows_harvested) "
                "VALUES(?,?,?,?)", (started, since, meta.get("records"), len(rows)))
    con.commit()
    vault = vault_plans()
    new_targets = store(con, rows, vault, since)
    con.execute("UPDATE sweeps SET finished=? WHERE started=?",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), started))
    con.commit()

    cur = con.execute("SELECT COUNT(*) FROM discovered WHERE target_status=1 AND in_vault=0 "
                      "AND excluded=0")
    total_candidates = cur.fetchone()[0]
    print(f"\n[OK] harvested {len(rows)}/{meta.get('records')} rows since {since}; "
          f"{new_targets} new candidates this sweep; "
          f"{total_candidates} open candidates total")
    cur = con.execute("""SELECT status, COUNT(*) FROM discovered
                         WHERE target_status=1 AND in_vault=0 GROUP BY status ORDER BY 2 DESC""")
    for s, n in cur.fetchall():
        print(f"   {n:5d}  {s}")


if __name__ == "__main__":
    main()
