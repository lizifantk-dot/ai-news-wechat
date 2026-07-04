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

PRODUCTS = [
    {"product_id": "1731209475345779408", "name_cn": "豆浆机 / 多功能破壁机"},
    {"product_id": "1730508436883278544", "name_cn": "煮蛋器"},
    {"product_id": "1730942410885335760", "name_cn": "手持挂烫机"},
    {"product_id": "1730585612576197328", "name_cn": "电煮锅 / 多功能电锅"},
]


def bangkok_now():
    return dt.datetime.now(dt.timezone.utc).astimezone(dt.timezone(dt.timedelta(hours=7)))


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
            "Referer": "https://www.fastmoss.com/zh/e-commerce/search?region=TH",
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


def fetch_product(product_id, cookie):
    params = {
        "page": "1",
        "pagesize": "10",
        "order": "2,2",
        "region": "TH",
        "words": product_id,
        "_time": str(int(dt.datetime.now(dt.timezone.utc).timestamp())),
        "cnonce": str(random.randint(10000000, 99999999)),
    }
    url = "https://www.fastmoss.com/api/goods/V2/search?" + urllib.parse.urlencode(params)
    data = request_json(url, cookie)
    if data.get("code") != 200:
        raise RuntimeError(f"FastMoss API error for {product_id}: {data}")
    products = ((data.get("data") or {}).get("product_list")) or []
    for item in products:
        if str(item.get("product_id")) == str(product_id):
            return item
    return products[0] if products else {}


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


def main():
    cookie = os.getenv("FASTMOSS_COOKIE", "").strip()
    if not cookie:
        print("FASTMOSS_COOKIE is not configured; skip FastMoss fetch.")
        return 0

    now = bangkok_now()
    rows = []
    for product in PRODUCTS:
        item = fetch_product(product["product_id"], cookie)
        rows.append(normalize(item, product, now))

    DATA_DIR.mkdir(exist_ok=True)
    OUT_JSON.write_text(json.dumps({"products": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(json.dumps({"ok": True, "source": "FastMoss", "products": len(rows)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
