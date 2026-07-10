import csv
import datetime as dt
import json
import os
import random
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUT_CSV = DATA_DIR / "fastmoss_latest.csv"
OUT_JSON = DATA_DIR / "fastmoss_latest.json"
STATUS_JSON = DATA_DIR / "fastmoss_status.json"

PRODUCTS = [
    {"product_id": "1731209475345779408", "name_cn": "豆浆机 / 多功能破壁机"},
    {"product_id": "1730508436883278544", "name_cn": "煮蛋器"},
    {"product_id": "1730942410885335760", "name_cn": "手持挂烫机"},
    {"product_id": "1730585612576197328", "name_cn": "电煮锅 / 多功能电锅"},
]

BASE_URL = "https://www.fastmoss.com"
SEARCH_URL = f"{BASE_URL}/zh/e-commerce/search?region=TH"


def bangkok_now():
    return dt.datetime.now(dt.timezone.utc).astimezone(dt.timezone(dt.timedelta(hours=7)))


def write_status(ok, message, *, cookie_source="", products=0):
    DATA_DIR.mkdir(exist_ok=True)
    now = bangkok_now()
    STATUS_JSON.write_text(
        json.dumps(
            {
                "ok": ok,
                "message": message,
                "cookie_source": cookie_source,
                "products": products,
                "checked_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                "date": now.strftime("%Y-%m-%d"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def request_json(url, cookie):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,th;q=0.7",
            "Referer": SEARCH_URL,
            "Cookie": cookie,
        },
    )
    last_error = None
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=75) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(3 * attempt)
    raise last_error


def product_url(product_id):
    params = {
        "page": "1",
        "pagesize": "10",
        "order": "2,2",
        "region": "TH",
        "words": product_id,
        "_time": str(int(dt.datetime.now(dt.timezone.utc).timestamp())),
        "cnonce": str(random.randint(10000000, 99999999)),
    }
    return f"{BASE_URL}/api/goods/V2/search?" + urllib.parse.urlencode(params)


def auth_error(data):
    text = json.dumps(data, ensure_ascii=False)
    return (
        data.get("code") in (401, 403)
        or "MAG_AUTH" in text
        or '"is_login": 0' in text
        or "'is_login': 0" in text
    )


def short_error(exc):
    text = str(exc)
    if "MAG_AUTH" in text or "is_login" in text:
        return "FastMoss Cookie 已失效，需要重新登录。"
    if "Timeout" in text and "locator" in text:
        return "FastMoss 自动登录未找到账号输入框，可能页面结构变化或触发验证。"
    return text[:500]


def fetch_product(product_id, cookie):
    data = request_json(product_url(product_id), cookie)
    if auth_error(data):
        raise PermissionError("FastMoss login expired (MAG_AUTH_3019 / is_login=0).")
    if data.get("code") != 200:
        raise RuntimeError(f"FastMoss API error for {product_id}: {data}")
    products = ((data.get("data") or {}).get("product_list")) or []
    for item in products:
        if str(item.get("product_id")) == str(product_id):
            return item
    if not products:
        raise RuntimeError(f"FastMoss returned no product for {product_id}")
    return products[0]


def value(item, *keys):
    for key in keys:
        current = item.get(key)
        if current not in (None, ""):
            return current
    return ""


def normalize(item, product, now):
    return {
        "snapshot_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "product_id": product["product_id"],
        "name_cn": product["name_cn"],
        "product_name": value(item, "title", "product_name"),
        "price": value(item, "price", "price_show", "sale_price"),
        "day1_sold": value(item, "yday_sold_count", "yday_sold_count_show"),
        "day7_sold": value(item, "day7_sold_count", "day7_sold_count_show"),
        "sold": value(item, "sold_count", "sold_count_show"),
        "day7_gmv": value(item, "day7_sale_amount_show", "day7_sale_amount"),
        "gmv": value(item, "sale_amount_show", "sale_amount"),
        "rating": value(item, "product_rating"),
        "commission": value(item, "crate_show", "crate"),
        "author_order_rate": value(item, "author_order_rate_show", "author_order_rate"),
        "shop_name": (item.get("shop_info") or {}).get("name") or item.get("shop_name") or "CAMEL Mall",
        "source": "FastMoss",
    }


def cookies_to_header(cookies):
    return "; ".join(f"{item['name']}={item['value']}" for item in cookies if item.get("name") and item.get("value"))


async def browser_login(username, password):
    try:
        from playwright.async_api import async_playwright
    except Exception as exc:
        raise RuntimeError("Playwright is not installed; cannot auto-login FastMoss.") from exc

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            locale="zh-CN",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()
        login_urls = [
            f"{BASE_URL}/zh/login",
            f"{BASE_URL}/login",
            SEARCH_URL,
        ]
        for login_url in login_urls:
            await page.goto(login_url, wait_until="domcontentloaded", timeout=90000)
            await page.wait_for_timeout(1500)
            if await page.locator("input").count():
                break

        login_selectors = [
            "text=登录",
            "text=登录/注册",
            "text=登入",
            "text=立即登录",
            "text=Sign in",
            "text=Login",
            "button:has-text('登录')",
        ]
        for selector in login_selectors:
            try:
                if await page.locator(selector).first.count():
                    await page.locator(selector).first.click(timeout=5000)
                    break
            except Exception:
                pass

        password_tabs = [
            "text=密码登录",
            "text=账号密码登录",
            "text=手机账号密码登录",
            "text=手机号登录",
            "text=账号登录",
            "text=Password",
        ]
        for selector in password_tabs:
            try:
                if await page.locator(selector).first.count():
                    await page.locator(selector).first.click(timeout=5000)
                    break
            except Exception:
                pass

        phone_input = page.locator(
            "input[type='tel'], input[type='text'], input[type='email'], input:not([type]), "
            "input[name*='phone'], input[name*='mobile'], input[name*='account'], input[name*='user'], "
            "input[autocomplete='username'], input[placeholder*='手机号'], input[placeholder*='手机'], "
            "input[placeholder*='账号'], input[placeholder*='邮箱'], input[placeholder*='Phone'], input[placeholder*='Email']"
        ).first
        password_input = page.locator("input[type='password']").first

        await phone_input.fill(username, timeout=20000)
        await password_input.fill(password, timeout=20000)

        submit = page.locator(
            "button:has-text('登录'), button:has-text('登入'), button:has-text('Sign in'), button:has-text('Login')"
        ).first
        await submit.click(timeout=10000)
        await page.wait_for_timeout(8000)

        page_text = await page.locator("body").inner_text(timeout=10000)
        if any(word in page_text for word in ["验证码", "验证", "captcha", "短信"]):
            raise RuntimeError("FastMoss requires verification code/captcha; manual verification is needed.")

        await page.goto(SEARCH_URL, wait_until="networkidle", timeout=90000)
        cookies = await context.cookies(BASE_URL)
        await browser.close()
        cookie = cookies_to_header(cookies)
        if not cookie:
            raise RuntimeError("FastMoss login produced no cookies.")
        return cookie


def login_with_credentials():
    username = os.getenv("FASTMOSS_USERNAME", "").strip()
    password = os.getenv("FASTMOSS_PASSWORD", "").strip()
    if not username or not password:
        raise RuntimeError("FASTMOSS_USERNAME/FASTMOSS_PASSWORD are not configured.")
    import asyncio

    return asyncio.run(browser_login(username, password))


def collect_rows(cookie):
    now = bangkok_now()
    rows = []
    for product in PRODUCTS:
        item = fetch_product(product["product_id"], cookie)
        rows.append(normalize(item, product, now))
    return rows


def write_outputs(rows, cookie_source):
    DATA_DIR.mkdir(exist_ok=True)
    OUT_JSON.write_text(
        json.dumps({"products": rows, "source": "FastMoss", "cookie_source": cookie_source}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    write_status(True, "FastMoss data fetched successfully.", cookie_source=cookie_source, products=len(rows))


def main():
    cookie = os.getenv("FASTMOSS_COOKIE", "").strip()
    errors = []

    if cookie:
        try:
            rows = collect_rows(cookie)
            write_outputs(rows, "FASTMOSS_COOKIE")
            print(json.dumps({"ok": True, "source": "FastMoss", "products": len(rows), "login": "cookie"}, ensure_ascii=False))
            return 0
        except Exception as exc:
            errors.append(f"cookie failed: {short_error(exc)}")
            print(f"FastMoss cookie failed, trying account login: {short_error(exc)}", file=sys.stderr)

    try:
        login_cookie = login_with_credentials()
        rows = collect_rows(login_cookie)
        write_outputs(rows, "FASTMOSS_USERNAME_PASSWORD")
        print(json.dumps({"ok": True, "source": "FastMoss", "products": len(rows), "login": "username_password"}, ensure_ascii=False))
        return 0
    except Exception as exc:
        errors.append(f"account login failed: {short_error(exc)}")
        message = "；".join(errors)
        write_status(False, message)
        print(f"ERROR: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
