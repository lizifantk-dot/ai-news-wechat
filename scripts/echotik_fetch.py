import csv
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUT_CSV = DATA_DIR / "echotik_latest.csv"
OUT_JSON = DATA_DIR / "echotik_latest.json"

PRODUCTS = [
    {"product_id": "1731209475345779408", "name_cn": "豆浆机 / 多功能破壁机"},
    {"product_id": "1730508436883278544", "name_cn": "煮蛋器"},
    {"product_id": "1730942410885335760", "name_cn": "手持挂烫机"},
    {"product_id": "1730585612576197328", "name_cn": "电煮锅 / 多功能电锅"},
]


def bangkok_now():
    return dt.datetime.now(dt.timezone.utc).astimezone(dt.timezone(dt.timedelta(hours=7)))


def request_product_detail(auth_token):
    product_ids = ",".join(item["product_id"] for item in PRODUCTS)
    url = "https://open.echotik.live/api/v3/echotik/product/detail?" + urllib.parse.urlencode(
        {"product_ids": product_ids}
    )
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": auth_token,
            "Accept": "application/json",
            "User-Agent": "ai-news-wechat/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8"))


def money(value):
    if value in (None, ""):
        return ""
    try:
        return f"฿{float(value):,.2f}"
    except Exception:
        return str(value)


def pick_price(item):
    min_price = item.get("min_price")
    max_price = item.get("max_price")
    if min_price in (None, "") and max_price in (None, ""):
        return ""
    if min_price == max_price or max_price in (None, ""):
        return money(min_price)
    return f"{money(min_price)}-{money(max_price)}"


def normalize_rows(api_items):
    by_id = {str(item.get("product_id")): item for item in api_items}
    rows = []
    now = bangkok_now()
    for product in PRODUCTS:
        item = by_id.get(product["product_id"], {})
        rows.append(
            {
                "snapshot_time": now.strftime("%Y-%m-%d %H:%M:%S"),
                "product_id": product["product_id"],
                "name_cn": product["name_cn"],
                "product_name": item.get("product_name", ""),
                "region": item.get("region", ""),
                "price": pick_price(item),
                "day1_sold": item.get("total_sale_1d_cnt", ""),
                "day7_sold": item.get("total_sale_7d_cnt", ""),
                "day30_sold": item.get("total_sale_30d_cnt", ""),
                "sold": item.get("total_sale_cnt", ""),
                "gmv": money(item.get("total_sale_gmv_amt", "")),
                "day7_gmv": money(item.get("total_sale_gmv_7d_amt", "")),
                "review_count": item.get("review_count", ""),
                "rating": item.get("product_rating", ""),
                "video_7d": item.get("total_video_7d_cnt", ""),
                "live_7d": item.get("total_live_7d_cnt", ""),
                "source": "EchoTik API",
            }
        )
    return rows


def main():
    auth_token = os.getenv("ECHOTIK_AUTH_TOKEN", "").strip()
    if not auth_token:
        print("ECHOTIK_AUTH_TOKEN is not configured; skip EchoTik fetch.")
        return 0

    data = request_product_detail(auth_token)
    if data.get("code") != 0:
        raise RuntimeError(f"EchoTik API error: {data}")

    rows = normalize_rows(data.get("data") or [])
    DATA_DIR.mkdir(exist_ok=True)
    OUT_JSON.write_text(json.dumps({"products": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(json.dumps({"ok": True, "source": "EchoTik", "products": len(rows)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
