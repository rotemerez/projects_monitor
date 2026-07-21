"""
mavat_status.py — look up planning-plan status from Mavat (mavat.iplan.gov.il)
for a daily 'did the status change, and when' check.

Approach (validated against the live site):
  - A plain HTTP client is blocked by the gov.il WAF (F5-style JS challenge), and even
    an in-page fetch() to /rest/api/SV4/1 is blocked. But driving the real search UI
    works: submitting a plan number triggers POST /rest/api/sv3/Search, whose result
    row already contains the current status + status code + status date.
  - So we drive one browser context, warm it once, and reuse it for many lookups.

Returns per plan:
  plan, matched(bool), mid, name, location, authority,
  status_desc, status_short, status_code, status_date, decision_date, update_date

Usage:
  python mavat_status.py 457-1253954 457-1260348 ...          # warm session, headed
  python mavat_status.py --headless 457-1253954 ...           # headless
  python mavat_status.py --cold 457-1253954 ...               # fresh context per plan (benchmark)
  python mavat_status.py --file plans.txt --headless --json out.json
"""
import sys, json, time, argparse
from pathlib import Path
from playwright.sync_api import sync_playwright

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

SEARCH_URL = "https://mavat.iplan.gov.il/SV3?searchEntity=1&entityType=1&searchMethod=2"
PLAN_FIELD = "input[aria-label='מספר תכנית']"
BLOCK_TYPES = {"image", "media", "font"}

FIELDS = ["ENTITY_NUMBER", "ENTITY_NAME", "MP_ID", "MMI_ENTITY_ID", "ENTITY_LOCATION",
          "AUTH_NAME", "UNIFIED_STATUS_DESC", "INTERNET_SHORT_STATUS",
          "INTERNET_STATUS_CODE", "INTERNET_STATUS_DATE", "BI_STATUS_DATE",
          "APP_DATE_DATE", "UPDATE_DATE"]


def _norm_plan(s):
    return str(s).strip().replace(" ", "")


def _extract(rows, plan):
    want = _norm_plan(plan)
    match = next((r for r in rows if _norm_plan(r.get("ENTITY_NUMBER")) == want), None)
    if match is None:
        uniq = {_norm_plan(r.get("ENTITY_NUMBER")) for r in rows}
        if len(uniq) == 1 and rows:
            match = rows[0]
    if not match:
        return None
    mid = match.get("MP_ID") or match.get("MMI_ENTITY_ID")
    return {
        "plan": str(match.get("ENTITY_NUMBER")),
        "matched": True,
        "mid": int(mid) if mid else None,
        "name": match.get("ENTITY_NAME"),
        "location": match.get("ENTITY_LOCATION"),
        "authority": match.get("AUTH_NAME"),
        "status_desc": match.get("UNIFIED_STATUS_DESC"),
        "status_short": match.get("INTERNET_SHORT_STATUS"),
        "status_code": int(match["INTERNET_STATUS_CODE"]) if match.get("INTERNET_STATUS_CODE") else None,
        # Swapped 2026-07-15: BI_STATUS_DATE is the date shown next to the current status
        # on the plan's own Mavat page (confirmed against a live screenshot — plan
        # 215-1288927's top box showed 16/11/2025, matching BI_STATUS_DATE exactly).
        # INTERNET_STATUS_DATE instead tracks the latest entry across the FULL "שלבי טיפול
        # בתכנית" stage-history table, which can advance (e.g. an unrelated Treasury
        # sub-approval step) without the plan's real displayed status or its date moving
        # at all — using it as "status_date" caused false-positive "changes" in
        # mavat_diff.py whenever that happened.
        "status_date": match.get("BI_STATUS_DATE"),
        "decision_date": match.get("INTERNET_STATUS_DATE"),
        "update_date": match.get("UPDATE_DATE"),
        "url": f"https://mavat.iplan.gov.il/SV4/1/{int(mid)}/310" if mid else None,
    }


class MavatSession:
    """One warm browser context; call lookup() many times."""

    def __init__(self, playwright, headless=True, block_assets=True):
        self.browser = playwright.chromium.launch(headless=headless)
        self.ctx = self.browser.new_context(locale="he-IL", viewport={"width": 1400, "height": 900})
        if block_assets:
            self.ctx.route("**/*", self._router)
        self.page = self.ctx.new_page()
        self._rows = []
        self._search_responses = 0
        self._plan_responses = 0   # responses whose request body names the current plan
        self._current_plan = None
        self.page.on("response", self._on_response)
        self._warm = False

    def _router(self, route):
        if route.request.resource_type in BLOCK_TYPES:
            return route.abort()
        return route.continue_()

    def _on_response(self, resp):
        if "/rest/api/sv3/Search" in resp.url and resp.status == 200:
            try:
                body = resp.json()
                for blk in body:
                    r = blk.get("result") or {}
                    for row in (r.get("dtResults") or []):
                        self._rows.append(row)
                self._search_responses += 1
                # The page also fires generic searches (on load, on filter toggle); only a
                # response whose request payload names our plan proves OUR query returned.
                if self._current_plan and self._current_plan in (resp.request.post_data or ""):
                    self._plan_responses += 1
            except Exception:
                pass

    def _select_all_plans(self, timeout_s=15):
        """Ensure the 'כל התכניות' radio is actually selected before searching. The default
        'last 3 months' filter hides plans without recent activity, and a silently-failed
        click here was the root cause of false MISSes — so verify the checked state."""
        # the radios are custom ARIA components, not <input> — locate by role
        radios = self.page.get_by_role("radio")
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            try:
                if radios.count() >= 1 and radios.first.is_checked():
                    return True   # first radio of the group == כל התכניות
            except Exception:
                pass
            try:
                self.page.get_by_text("כל התכניות", exact=True).click(timeout=2000)
            except Exception:
                try:
                    radios.first.check(force=True, timeout=2000)
                except Exception:
                    pass
            self.page.wait_for_timeout(250)
        return False

    def lookup(self, plan, timeout_s=25):
        t0 = time.time()
        self.page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=60000)
        fld = self.page.locator(PLAN_FIELD)
        fld.wait_for(state="visible", timeout=30000)
        if not self._warm:
            self.page.wait_for_timeout(500)
            self._warm = True
        if not self._select_all_plans():
            # searching with the wrong filter would yield a FALSE miss — report an error instead
            return {"plan": _norm_plan(plan), "matched": False, "error": "filter_not_set",
                    "elapsed_s": round(time.time() - t0, 2)}
        self._rows = []
        self._plan_responses = 0
        self._current_plan = _norm_plan(plan)
        fld.click()
        fld.fill(_norm_plan(plan))
        self.page.wait_for_timeout(250)
        fld.press("Enter")

        # Wait for OUR plan's search response (identified by its request payload); generic
        # page-load / filter-toggle searches must not end the wait.
        deadline = time.time() + timeout_s
        result = None
        while time.time() < deadline:
            self.page.wait_for_timeout(300)
            result = _extract(self._rows, plan)
            if result is not None:
                break
            if self._plan_responses > 0:
                # our query returned; brief grace for a possible 2nd batch, then decide
                self.page.wait_for_timeout(700)
                result = _extract(self._rows, plan)
                break
        self._current_plan = None
        elapsed = round(time.time() - t0, 2)
        if result is None:
            return {"plan": _norm_plan(plan), "matched": False, "elapsed_s": elapsed,
                    "rows_seen": len(self._rows)}
        result["elapsed_s"] = elapsed
        return result

    def fetch_detail(self, mid, timeout_s=25):
        """Load the plan's SV4 detail page and capture the SPA's own detail XHR
        (direct REST calls are WAF-blocked; interception of the page's request works).
        Returns the raw detail JSON dict, or None."""
        captured = []

        def on_resp(resp):
            if "/rest/api/SV4/" in resp.url and resp.status == 200:
                try:
                    captured.append(resp.json())
                except Exception:
                    pass

        self.page.on("response", on_resp)
        try:
            self.page.goto(f"https://mavat.iplan.gov.il/SV4/1/{mid}/310",
                           wait_until="domcontentloaded", timeout=60000)
            deadline = time.time() + timeout_s
            while time.time() < deadline and not captured:
                self.page.wait_for_timeout(300)
        finally:
            self.page.remove_listener("response", on_resp)
        return captured[0] if captured else None

    def close(self):
        try:
            self.browser.close()
        except Exception:
            pass


def run(plans, headless=True, cold=False, block_assets=True, delay_s=2.0, retry_miss=True,
        retry_backoff_s=5.0):
    """Look up each plan. Politeness: sleep delay_s between lookups. A MISS is re-queried
    once after retry_backoff_s (misses were observed to be transient) before being recorded."""
    results = []

    def _lookup_with_retry(session, plan):
        r = session.lookup(plan)
        if retry_miss and not r.get("matched"):
            time.sleep(retry_backoff_s)
            r2 = session.lookup(plan)
            r2["retried"] = True
            if r2.get("matched"):
                return r2
            r2["elapsed_s"] = round(r.get("elapsed_s", 0) + r2.get("elapsed_s", 0), 2)
            return r2
        return r

    with sync_playwright() as p:
        if cold:
            for i, plan in enumerate(plans):
                if i and delay_s:
                    time.sleep(delay_s)
                s = MavatSession(p, headless=headless, block_assets=block_assets)
                results.append(_lookup_with_retry(s, plan))
                s.close()
        else:
            s = MavatSession(p, headless=headless, block_assets=block_assets)
            try:
                for i, plan in enumerate(plans):
                    if i and delay_s:
                        time.sleep(delay_s)
                    results.append(_lookup_with_retry(s, plan))
            finally:
                s.close()
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plans", nargs="*")
    ap.add_argument("--file")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--cold", action="store_true", help="fresh browser context per plan")
    ap.add_argument("--no-block", action="store_true", help="do not block images/fonts")
    ap.add_argument("--json", help="write results to this JSON file")
    ap.add_argument("--delay", type=float, default=2.0,
                    help="polite delay in seconds between lookups (default 2.0)")
    ap.add_argument("--no-retry", action="store_true",
                    help="do not re-query a MISS once before recording it")
    args = ap.parse_args()

    plans = list(args.plans)
    if args.file:
        plans += [l.strip() for l in Path(args.file).read_text(encoding="utf-8").splitlines() if l.strip()]
    if not plans:
        plans = ["457-1253954"]

    t0 = time.time()
    results = run(plans, headless=args.headless, cold=args.cold, block_assets=not args.no_block,
                  delay_s=args.delay, retry_miss=not args.no_retry)
    total = round(time.time() - t0, 2)

    for r in results:
        ok = "OK " if r.get("matched") else ("ERR " if r.get("error") else "MISS")
        retried = " [retried]" if r.get("retried") else ""
        if r.get("error"):
            retried += f" error={r['error']}"
        print(f"[{ok}] {r.get('plan'):<16} {str(r.get('status_desc') or ''):<12} "
              f"code={r.get('status_code')} date={r.get('status_date')} "
              f"decision={r.get('decision_date')} ({r.get('elapsed_s')}s){retried}")

    times = [r["elapsed_s"] for r in results if "elapsed_s" in r]
    hits = sum(1 for r in results if r.get("matched"))
    mode = ("headless" if args.headless else "headed") + ("/cold" if args.cold else "/warm")
    print(f"\nMODE={mode} plans={len(plans)} matched={hits} total={total}s "
          f"avg={round(sum(times)/len(times),2) if times else 0}s "
          f"min={min(times) if times else 0}s max={max(times) if times else 0}s")

    if args.json:
        Path(args.json).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print("wrote", args.json)


if __name__ == "__main__":
    main()
