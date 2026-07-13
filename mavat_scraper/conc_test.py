"""Concurrency test: N parallel browser contexts (one browser), each looking up the
same plan set. Reports per-lookup status + any non-200 API responses (WAF blocks).
"""
import sys, json, time, asyncio
from playwright.async_api import async_playwright
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SEARCH_URL = "https://mavat.iplan.gov.il/SV3?searchEntity=1&entityType=1&searchMethod=2"
PLAN_FIELD = "input[aria-label='מספר תכנית']"
PLANS = ["457-1253954", "457-1260348", "457-1162601", "601-0806554", "601-0629725"]
N = int(sys.argv[1]) if len(sys.argv) > 1 else 3
BLOCK_TYPES = {"image", "media", "font"}


def norm(s):
    return str(s).strip().replace(" ", "")


async def _route(route):
    if route.request.resource_type in BLOCK_TYPES:
        await route.abort()
    else:
        await route.continue_()


async def worker(browser, wid, plans, blocks, block_assets=True):
    ctx = await browser.new_context(locale="he-IL", viewport={"width": 1300, "height": 850})
    if block_assets:
        await ctx.route("**/*", _route)
    page = await ctx.new_page()
    rows = {"list": [], "n": 0, "plan": None, "plan_n": 0}

    def on_resp(resp):
        if "/rest/api/" in resp.url and resp.status != 200:
            blocks.append((wid, resp.status, resp.url))
        if "/rest/api/sv3/Search" in resp.url and resp.status == 200:
            async def grab():
                try:
                    for blk in await resp.json():
                        for row in ((blk.get("result") or {}).get("dtResults") or []):
                            rows["list"].append(row)
                    rows["n"] += 1
                    # only a response whose request payload names our plan counts as OUR query
                    if rows["plan"] and rows["plan"] in (resp.request.post_data or ""):
                        rows["plan_n"] += 1
                except Exception:
                    pass
            asyncio.create_task(grab())

    page.on("response", on_resp)
    out = []
    for plan in plans:
        t0 = time.time()
        try:
            await page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=60000)
            fld = page.locator(PLAN_FIELD)
            await fld.wait_for(state="visible", timeout=30000)
            # select 'כל התכניות' and VERIFY it took (first radio of the group); a silently
            # failed click leaves the 3-month default filter on -> false miss
            radios = page.get_by_role("radio")   # custom ARIA radios, not <input>

            filter_deadline = time.time() + 15
            filter_ok = False
            while time.time() < filter_deadline:
                try:
                    if await radios.count() >= 1 and await radios.first.is_checked():
                        filter_ok = True
                        break
                except Exception:
                    pass
                try:
                    await page.get_by_text("כל התכניות", exact=True).click(timeout=2000)
                except Exception:
                    try:
                        await radios.first.check(force=True, timeout=2000)
                    except Exception:
                        pass
                await page.wait_for_timeout(250)
            if not filter_ok:
                out.append((plan, False, "ERR filter_not_set", round(time.time() - t0, 2)))
                continue
            # wait for OUR plan's search response (matched by request payload) — the page
            # fires generic searches on load and on the filter toggle
            rows["list"] = []
            rows["plan"] = norm(plan)
            rows["plan_n"] = 0
            await fld.click()
            await fld.fill(norm(plan))
            await page.wait_for_timeout(250)
            await fld.press("Enter")
            deadline = time.time() + 25
            match = None
            while time.time() < deadline:
                await page.wait_for_timeout(300)
                match = next((r for r in rows["list"] if norm(r.get("ENTITY_NUMBER")) == norm(plan)), None)
                if match is not None:
                    break
                if rows["plan_n"] > 0:
                    await page.wait_for_timeout(700)
                    match = next((r for r in rows["list"] if norm(r.get("ENTITY_NUMBER")) == norm(plan)), None)
                    break
            dt = round(time.time() - t0, 2)
            out.append((plan, match is not None, match.get("UNIFIED_STATUS_DESC") if match else None, dt))
        except Exception as e:
            out.append((plan, False, f"ERR {e}", round(time.time() - t0, 2)))
    await ctx.close()
    return wid, out


async def main():
    block_assets = "--no-block" not in sys.argv
    blocks = []
    t0 = time.time()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        results = await asyncio.gather(*[worker(browser, i, PLANS, blocks, block_assets) for i in range(N)])
        await browser.close()
    total = round(time.time() - t0, 2)
    ok = 0
    for wid, out in results:
        for plan, matched, status, dt in out:
            ok += 1 if matched else 0
            print(f"  w{wid} {plan:<16} {'OK' if matched else 'MISS':<5} {str(status or ''):<22} {dt}s")
    print(f"\nCONCURRENCY={N} total_lookups={N*len(PLANS)} matched={ok} wall={total}s "
          f"blocks(non-200)={len(blocks)}")
    if blocks:
        print("BLOCKS:", blocks[:10])


asyncio.run(main())
