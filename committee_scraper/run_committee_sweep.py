r"""
run_committee_sweep.py — daily rotation over local-planning-committee scrapers
(C:\R_PROJECTS\local_committee_scrapers), spread across many days instead of one
weekly burst against a shared backend (root cause of the 2026-06-24 Complot outage:
all 70 Complot municipalities proxy through one host, handasi.complot.co.il, which
rate-limited/reset connections under a full-133 weekly blast).

This project's own code is NOT duplicated here — we invoke the other project's venv
+ its `run_subset.py` entry point (added 2026-07-13, additive, does not touch its
existing scripts) for N least-recently-scraped municipalities, then import the
resulting per-municipality master-table CSVs into committee_state.db.

Dedup with Mavat (user decision 2026-07-13): the committee CSVs carry a קישור למבאת
(Mavat link) column. A committee-discovered plan whose link is populated has already
entered the Mavat pipeline and does not need separate committee-level tracking —
workflow is local-committee preapproval -> Mavat process -> Mavat approval. Such rows
are auto-"graduated" (excluded, reason recorded, link kept for reference) rather than
surfaced as open candidates. A secondary check cross-references the plan number
against the vault (`projects.db`) for the same reason.

Bartech plans (2026-07-13): rewritten upstream to use Playwright instead of Selenium.
The old failure wasn't Bartech blocking bots — it was chromedriver.exe falling out of
sync with an auto-updating system Chrome. Playwright bundles its own Chromium, so
there's no external driver to version-pin, and its plain headless browser already
passes Bartech's invisible reCAPTCHA on plans search (verified against Holon). Both
systems now run in the default rotation.

Usage (run with projects_monitor's own interpreter — no extra deps needed):
  python run_committee_sweep.py --count 20                 # 20 least-recently-scraped
  python run_committee_sweep.py --munis haifa ashdod        # explicit subset
  python run_committee_sweep.py --count 20 --systems complot
"""
import argparse
import csv
import json
import re
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
STATE_DB = HERE / "committee_state.db"
PROJECTS_DB = HERE.parent / "projects.db"
MAVAT_DISCOVERY_DB = HERE.parent / "mavat_scraper" / "mavat_discovery.db"

SCRAPER_ROOT = Path(r"C:\R_PROJECTS\local_committee_scrapers\unified_scraper\municipal_scraper")
SCRAPER_PY = SCRAPER_ROOT / ".venv" / "Scripts" / "python.exe"

MAVAT_LINK_PLAN_RX = re.compile(r"[?&]text=([0-9]{3}-[0-9]{6,8})")

# Complot's own CSV plan_link points at its backend/low-graphics viewer
# (handasi.complot.co.il/magicscripts/mgrqispi.dll?...&siteid=<sid>&n=<id>&...), not the
# public, nicely-rendered municipal front-end site each municipality actually has. BUT
# (found 2026-07-20, bnei brak 404ing): there is NO single universal front-end route across
# Complot-hosted sites — each municipality's own webmaster embeds the plans-search widget at
# their own page path/theme. `iron` uses /binyan/#taba/<internal-n-id>; `bnei brak` uses a
# totally different path AND keys by the plan NUMBER, not the internal id:
# /תושבים/vadad-tichnun-bnya/tochnit_binyan/#search/GetTabaByNumber&siteid=<sid>&n=<plan_number>
# &l=true&arguments=siteid,n,l. Guessing a formula for an unconfirmed municipality risks a
# broken link, which is worse than the ugly-but-working backend link — so only municipalities
# with a confirmed entry below get rewritten; everyone else keeps the original backend link.
COMPLOT_SITEID_RX = re.compile(r"[?&]siteid=(\d+)")
COMPLOT_BACKEND_N_RX = re.compile(r"[?&]n=(\d+)")

# found 2026-07-20 by user — different theme, keyed by plan NUMBER not internal id
_BNEI_BRAK_LINK = lambda base, site_id, n, plan_number: (
    f"{base}/תושבים/vadad-tichnun-bnya/tochnit_binyan/"
    f"#search/GetTabaByNumber&siteid={site_id}&n={plan_number}&l=true&arguments=siteid,n,l"
)
# `iron`'s pattern (confirmed 2026-07-20: n=2102 matched Mavat.iplan's own internal id on
# both pages). Extended 2026-07-20 to every other Complot municipality whose own site's base
# /binyan/ path returned HTTP 200 (an HTTP-level check, run against all 36 municipalities
# scraped so far) — NOT a per-plan confirmation, since this is a client-side hash route and
# the server can't distinguish "resolves to the right plan" from "app loads, shows not-found"
# for a specific id. Accepted per user 2026-07-20 ("current links are useless to me anyway")
# in preference to the always-useless raw backend link. ariel/ashdod/ashkelon/hod hasharon/
# kfar saba (=ksaba)/ma'ale naftali confirmed 404 on this path and must NOT be added here;
# givatayim's whole domain currently redirects to an unrelated abuse page (inconclusive,
# likely domain-down, not a pattern mismatch) and is also left out for now.
_IRON_LINK = lambda base, site_id, n, plan_number: f"{base}/binyan/#taba/{n}"
# found 2026-07-20 by user — a THIRD distinct template: givatayim's own registry url
# (www.givatayim.muni.il) is currently broken (redirects to an unrelated abuse page), so it
# has no working front-end of its own; the real link instead lives on the shared Complot
# backend domain itself, under a municipality-specific slug ("gtm"), keyed by plan NUMBER
# like bnei brak. `base` (muni_url) is ignored here — the domain is hardcoded, not derived.
_GIVATAYIM_LINK = lambda base, site_id, n, plan_number: (
    "https://handasi.complot.co.il/gtm/taba-search.min.htm"
    f"#search/GetTabaByNumber&siteid={site_id}&n={plan_number}&l=true&arguments=siteid,n,l"
)
# found 2026-07-20 by user — a FOURTH distinct template: own site, but a different search
# page/path than bnei brak's, still keyed by plan NUMBER. Confirms hod hasharon's earlier
# 404 on the iron-style /binyan/ path was a genuine template mismatch, not a fluke.
_HOD_HASHARON_LINK = lambda base, site_id, n, plan_number: (
    f"{base}/newengine/Pages/taba2.aspx"
    f"#search/GetTabaByNumber&siteid={site_id}&n={plan_number}&l=true&arguments=siteid,n,l"
)
# found 2026-07-20 by user — a FIFTH distinct template: same page path as hod hasharon
# (/newengine/Pages/taba2.aspx) but a different, simpler hash route — direct #taba/<n>,
# keyed by the INTERNAL id again (not the plan number, unlike hod hasharon/bnei brak/
# givatayim despite sharing that page). Two registry keys ("kfar saba" and "ksaba") point at
# the same domain/site_id — both get this override.
_KFAR_SABA_LINK = lambda base, site_id, n, plan_number: f"{base}/newengine/Pages/taba2.aspx#taba/{n}"

COMPLOT_MUNI_LINK_OVERRIDES = {
    "iron": _IRON_LINK,
    "bnei brak": _BNEI_BRAK_LINK,
    "givatayim": _GIVATAYIM_LINK,
    "hod hasharon": _HOD_HASHARON_LINK,
    "kfar saba": _KFAR_SABA_LINK,
    "ksaba": _KFAR_SABA_LINK,
}
for _muni in ("bat yam", "be'er sheva", "beit shean", "beit shemesh", "betar illit",
              "biq'at beit hakerem", "dimona", "efrat", "eilat", "emeq hayarden",
              "galil east", "ganei tikva", "giv'ot alonim", "hagalil center",
              "hagalil lower", "hagilboa", "haifa", "herzliya", "hevel eilot",
              "karnei shomron", "kfar yona", "kiryat ata", "lev hasharon",
              "ma'ale hagalil", "ma'ale hermon", "ma'alot-tarshiha"):
    COMPLOT_MUNI_LINK_OVERRIDES[_muni] = _IRON_LINK


def complot_frontend_link(muni, backend_link, muni_url, plan_number):
    override = COMPLOT_MUNI_LINK_OVERRIDES.get(muni)
    if not backend_link or not muni_url or not override:
        return backend_link
    n_m = COMPLOT_BACKEND_N_RX.search(backend_link)
    site_m = COMPLOT_SITEID_RX.search(backend_link)
    if not n_m or not site_m:
        return backend_link
    return override(muni_url.rstrip("/"), site_m.group(1), n_m.group(1), plan_number)


def open_state():
    con = sqlite3.connect(STATE_DB)
    con.execute("""CREATE TABLE IF NOT EXISTS committee_muni_state(
        muni TEXT PRIMARY KEY, system TEXT, last_scraped_at TEXT, last_result TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS committee_candidates(
        id TEXT PRIMARY KEY, muni TEXT, plan_number TEXT, plan_name TEXT,
        status TEXT, status_date TEXT, plan_type TEXT, authority TEXT, developer TEXT,
        mavat_link TEXT, mavat_plan_number TEXT, plan_link TEXT,
        first_seen TEXT, last_seen TEXT,
        graduated INTEGER DEFAULT 0, graduated_at TEXT,
        excluded INTEGER DEFAULT 0, exclude_reason TEXT, comment TEXT,
        kept INTEGER DEFAULT 0, decided_at TEXT)""")
    for ddl in ("ALTER TABLE committee_candidates ADD COLUMN objectives TEXT",):
        try:
            con.execute(ddl)
        except sqlite3.OperationalError:
            pass  # column already exists
    con.commit()
    return con


def get_registry():
    """Fetch MUNI_REGISTRY from the other project's own venv — never duplicated/hardcoded
    here, so it can't drift out of sync with that project's own municipality list."""
    code = ("import json; from registry.dispatcher import MUNI_REGISTRY; "
            "print(json.dumps(MUNI_REGISTRY))")
    r = subprocess.run([str(SCRAPER_PY), "-c", code], cwd=str(SCRAPER_ROOT),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.exit(f"could not read MUNI_REGISTRY: {r.stderr[-500:]}")
    return json.loads(r.stdout)


# found 2026-07-20: the other project's registry lists "kfar saba" and "ksaba" as two
# separate keys pointing at the IDENTICAL url/site_id/district — an alias, not two real
# municipalities. Scraping both doubled every plan in the review page under two different
# muni labels. Skip the alias entirely so it's never picked, regardless of what the external
# registry contains (a scan confirmed this is currently the only such duplicate).
MUNI_ALIASES_SKIP = {"ksaba"}


def pick_rotation(state, registry, count, systems):
    cur = state.execute("SELECT muni, last_scraped_at FROM committee_muni_state")
    last = dict(cur.fetchall())
    candidates = [m for m, cfg in registry.items()
                  if cfg.get("system") in systems and m not in MUNI_ALIASES_SKIP]
    ordered = sorted(candidates, key=lambda m: (last.get(m) or "", m))
    return ordered[:count]


def run_subset(munis):
    """Invoke the scraper project's own venv for this municipality subset."""
    cmd = [str(SCRAPER_PY), "run_subset.py"] + munis
    print(f"[..] invoking scraper for {len(munis)} municipalities: {', '.join(munis)}",
          flush=True)
    r = subprocess.run(cmd, cwd=str(SCRAPER_ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    for line in (r.stdout or "").splitlines():
        if line.startswith(("[", "done:")):
            print("   ", line, flush=True)
    if r.returncode != 0:
        print("   [!] subset run exited non-zero:", (r.stderr or "")[-500:], flush=True)
    return r


def vault_plan_numbers():
    con = sqlite3.connect(PROJECTS_DB)
    nums = {str(r[0]).strip().replace(" ", "")
           for r in con.execute("SELECT plan_current FROM projects WHERE plan_current != ''")}
    con.close()
    return nums


def mavat_discovery_plans():
    """Plan numbers already found by the independent Mavat nationwide sweep
    (mavat_scraper/mavat_discovery.db). A committee candidate matching one of
    these is already in the Mavat pipeline even if the committee scraper's own
    קישור למבאת column came back empty for it (e.g. some Complot detail pages
    don't expose the link for district-authority plans)."""
    if not MAVAT_DISCOVERY_DB.exists():
        return set()
    con = sqlite3.connect(MAVAT_DISCOVERY_DB)
    plans = {str(r[0]).strip().replace(" ", "") for r in con.execute("SELECT plan FROM discovered")}
    con.close()
    return plans


def reconcile_with_mavat_discovery(state, mavat_plans, now):
    """Graduate any currently-open committee candidate whose plan number has since
    turned up in the Mavat discovery sweep. Runs every sweep against ALL open
    candidates (not just the municipalities just scraped) because the two discovery
    sources run on independent schedules — a plan can surface on the Mavat side
    days after a municipality's committee row was already imported as 'open'."""
    cur = state.execute(
        "SELECT id, plan_number FROM committee_candidates WHERE excluded=0 AND COALESCE(graduated,0)=0")
    open_rows = cur.fetchall()

    graduated = 0
    for cid, plan_number in open_rows:
        if (plan_number or "").strip().replace(" ", "") in mavat_plans:
            state.execute("""UPDATE committee_candidates SET graduated=1, graduated_at=?,
                    excluded=1, exclude_reason=? WHERE id=?""",
                (now, 'כבר במבא"ת (אותר בסריקת מבא"ת ארצית)', cid))
            graduated += 1
    state.commit()
    return graduated


def import_master_csv(state, muni, vault_plans, mavat_plans, now, muni_url=None):
    """Read this municipality's master CSV and reconcile against committee_candidates:
    new open candidates, status refresh, and Mavat-graduation detection.

    The source's own קישור למבאת column is NEVER trusted for graduation (found 2026-07-19):
    both Bartech and Complot populate it as a templated search URL (SV3?text=<plan_number>),
    literally echoing the plan number back, regardless of whether that plan actually exists
    on Mavat. Live lookups against Mavat on samples from both systems' "link-only" rows came
    back NOT FOUND in the large majority of cases — the field carries no real signal in
    either source. Graduation now relies solely on the two genuine cross-checks: already in
    the vault, or found by the independent nationwide Mavat discovery sweep. `mavat_link` /
    `mavat_plan_number` are still stored (useful as a search shortcut in the UI), just never
    used to auto-exclude.
    """
    slug = muni.replace(" ", "_")
    path = SCRAPER_ROOT / "output" / "plans" / "data" / slug / f"{slug}-plans-master-table.csv"
    if not path.exists():
        print(f"   [!] no master CSV for {muni} at {path}")
        return {"rows": 0, "new": 0, "graduated": 0}

    stats = {"rows": 0, "new": 0, "graduated": 0}
    cur = state.cursor()
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            plan_number = (row.get("מספר תוכנית") or "").strip()
            if not plan_number:
                continue
            stats["rows"] += 1
            cid = f"{muni}::{plan_number}"
            mavat_link = (row.get("קישור למבאת") or "").strip()
            m = MAVAT_LINK_PLAN_RX.search(mavat_link)
            mavat_plan_number = m.group(1) if m else None
            plan_norm = plan_number.replace(" ", "")
            plan_link = complot_frontend_link(muni, row.get("קישור לתוכנית"), muni_url,
                                               plan_number)
            objectives = (row.get("מטרות התוכנית") or "").strip() or None

            cur.execute("SELECT graduated, excluded FROM committee_candidates WHERE id=?",
                       (cid,))
            prev = cur.fetchone()

            graduate = (plan_norm in vault_plans) or (plan_norm in mavat_plans)
            reason = None
            if plan_norm in vault_plans:
                reason = "כבר במעקב הכספת (vault)"
            elif plan_norm in mavat_plans:
                reason = 'כבר במבא"ת (אותר בסריקת מבא"ת ארצית)'

            if prev is None:
                stats["new"] += 1
                if graduate:
                    stats["graduated"] += 1
                cur.execute("""INSERT INTO committee_candidates(
                        id, muni, plan_number, plan_name, status, status_date,
                        plan_type, authority, developer, mavat_link, mavat_plan_number,
                        plan_link, objectives, first_seen, last_seen, graduated, graduated_at,
                        excluded, exclude_reason)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (cid, muni, plan_number, row.get("שם תוכנית"), row.get("סטטוס"),
                     row.get("תאריך סטטוס"), row.get("סוג התוכנית"), row.get("בסמכות"),
                     row.get("יזם"), mavat_link or None, mavat_plan_number,
                     plan_link, objectives, now, now,
                     1 if graduate else 0, now if graduate else None,
                     1 if graduate else 0, reason))
            else:
                was_graduated = prev[0]
                cur.execute("""UPDATE committee_candidates SET
                        plan_name=?, status=?, status_date=?, plan_type=?, authority=?,
                        developer=?, mavat_link=?, mavat_plan_number=?, plan_link=?,
                        objectives=?, last_seen=?
                    WHERE id=?""",
                    (row.get("שם תוכנית"), row.get("סטטוס"), row.get("תאריך סטטוס"),
                     row.get("סוג התוכנית"), row.get("בסמכות"), row.get("יזם"),
                     mavat_link or None, mavat_plan_number, plan_link,
                     objectives, now, cid))
                if graduate and not was_graduated:
                    stats["graduated"] += 1
                    cur.execute("""UPDATE committee_candidates SET graduated=1,
                            graduated_at=?, excluded=1, exclude_reason=? WHERE id=?""",
                        (now, reason, cid))
    state.commit()
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, help="N least-recently-scraped municipalities")
    ap.add_argument("--munis", nargs="+", help="explicit municipality list")
    ap.add_argument("--systems", default="complot,bartech",
                    help="comma-separated system types to include (default: complot,bartech "
                        "— bartech plans now runs on Playwright, no ChromeDriver dependency)")
    args = ap.parse_args()
    systems = set(args.systems.split(","))

    if not SCRAPER_PY.exists():
        sys.exit(f"scraper venv not found: {SCRAPER_PY}")

    state = open_state()
    registry = get_registry()

    if args.munis:
        targets = args.munis
    elif args.count:
        targets = pick_rotation(state, registry, args.count, systems)
    else:
        sys.exit("choose --count N or --munis ...")

    if not targets:
        print("[OK] nothing to scrape (no municipalities matched)")
        return

    print(f"[..] {len(targets)} municipalities this run: {', '.join(targets)}", flush=True)
    run_subset(targets)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    vault_plans = vault_plan_numbers()
    mavat_plans = mavat_discovery_plans()
    total_new = total_graduated = 0
    for muni in targets:
        stats = import_master_csv(state, muni, vault_plans, mavat_plans, now,
                                   muni_url=registry.get(muni, {}).get("url"))
        state.execute("""INSERT INTO committee_muni_state(muni, system, last_scraped_at,
                             last_result)
                         VALUES(?,?,?,?)
                         ON CONFLICT(muni) DO UPDATE SET last_scraped_at=excluded.last_scraped_at,
                             last_result=excluded.last_result""",
                     (muni, registry.get(muni, {}).get("system"), now, json.dumps(stats)))
        state.commit()
        total_new += stats["new"]
        total_graduated += stats["graduated"]
        print(f"   {muni}: {stats['rows']} rows, {stats['new']} new, "
              f"{stats['graduated']} already-in-mavat", flush=True)

    # Reconcile ALL currently-open candidates against the Mavat discovery sweep, not
    # just the municipalities just scraped — the two discovery sources run on
    # independent schedules, so a plan can surface on the Mavat side after its
    # committee row was already imported as open.
    drift_graduated = reconcile_with_mavat_discovery(state, mavat_plans, now)
    if drift_graduated:
        print(f"   [reconcile] {drift_graduated} previously-open candidates graduated "
              f"(found in Mavat discovery sweep since last import)", flush=True)
    total_graduated += drift_graduated

    cur = state.execute("""SELECT COUNT(*) FROM committee_candidates
                           WHERE excluded=0 AND COALESCE(kept,0)=0""")
    open_total = cur.fetchone()[0]
    print(f"\n[OK] swept {len(targets)} municipalities; {total_new} new candidates, "
          f"{total_graduated} auto-graduated (already in Mavat/vault); "
          f"{open_total} open committee candidates total")
    state.close()


if __name__ == "__main__":
    main()
