import datetime as dt
import html
import json
import os
import random
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "camel_fastmoss_products.json"
REPORT_DIR = ROOT / "reports"


def bangkok_now():
    return dt.datetime.now(dt.timezone.utc).astimezone(dt.timezone(dt.timedelta(hours=7)))


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


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
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fastmoss_product(product_id, cookie):
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
    products = (((data.get("data") or {}).get("product_list")) or [])
    for item in products:
        if str(item.get("product_id")) == str(product_id):
            return item
    if products:
        return products[0]
    raise RuntimeError(f"FastMoss returned no product for {product_id}")


def xml_escape(value):
    return html.escape(str(value or ""), quote=True)


def short_title(value, max_len=44):
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    return value if len(value) <= max_len else value[: max_len - 1] + "..."


def as_int(value):
    try:
        return int(float(value))
    except Exception:
        return 0


def money(value):
    return str(value or "未知")


def build_svg(items, now):
    top = max(items, key=lambda x: as_int(x.get("day7_sold_count")))
    total_day7 = sum(as_int(x.get("day7_sold_count")) for x in items)
    total_yday = sum(as_int(x.get("yday_sold_count")) for x in items)
    cards = []
    colors = ["#0f7b6c", "#20639b", "#7851a9", "#d97904"]
    y = 500
    for idx, item in enumerate(items, 1):
        color = colors[(idx - 1) % len(colors)]
        title = xml_escape(item["name_cn"])
        price = xml_escape(item.get("price") or "未知")
        day7 = xml_escape(item.get("day7_sold_count_show") or item.get("day7_sold_count") or "0")
        yday = xml_escape(item.get("yday_sold_count_show") or item.get("yday_sold_count") or "0")
        total = xml_escape(item.get("sold_count_show") or item.get("sold_count") or "0")
        gmv7 = xml_escape(item.get("day7_sale_amount_show") or "未知")
        rating = xml_escape(item.get("product_rating") or "未知")
        commission = xml_escape(item.get("crate_show") or item.get("crate") or "未知")
        shop = xml_escape((item.get("shop_info") or {}).get("name") or item.get("shop_name") or "CAMEL Mall")
        author_rate = xml_escape(item.get("author_order_rate_show") or item.get("author_order_rate") or "未知")
        product_title = xml_escape(short_title(item.get("title")))
        cards.append(
            f"""
  <g transform="translate(78 {y})">
    <rect width="1044" height="214" rx="24" fill="#ffffff"/>
    <rect x="28" y="30" width="8" height="154" rx="4" fill="{color}"/>
    <text x="58" y="66" class="font card-title">{idx}. {title}</text>
    <text x="58" y="102" class="font tiny">{product_title}</text>
    <text x="58" y="154" class="font price">{price}</text>
    <text x="250" y="142" class="font small">近7天销量：{day7}｜昨日销量：{yday}｜近7天GMV：{gmv7}</text>
    <text x="250" y="178" class="font small">总销量：{total}｜评分：{rating}｜佣金：{commission}｜达人出单率：{author_rate}</text>
    <rect x="810" y="42" width="178" height="38" rx="19" fill="{color}"/>
    <text x="838" y="68" class="font pill">{shop}</text>
  </g>"""
        )
        y += 238

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="1600" viewBox="0 0 1200 1600">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#f7fafc"/>
      <stop offset="1" stop-color="#edf4f2"/>
    </linearGradient>
    <linearGradient id="hero" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#101820"/>
      <stop offset="1" stop-color="#24515c"/>
    </linearGradient>
    <style>
      .font {{ font-family: "Microsoft YaHei", "Noto Sans CJK SC", Arial, sans-serif; }}
      .title {{ font-size: 54px; font-weight: 800; fill: #ffffff; }}
      .sub {{ font-size: 24px; fill: #d8e7ec; }}
      .label {{ font-size: 22px; fill: #647887; }}
      .value {{ font-size: 42px; font-weight: 800; fill: #14232c; }}
      .small {{ font-size: 22px; fill: #5e707b; }}
      .tiny {{ font-size: 19px; fill: #71828c; }}
      .card-title {{ font-size: 30px; font-weight: 800; fill: #152832; }}
      .price {{ font-size: 34px; font-weight: 800; fill: #0f7b6c; }}
      .pill {{ font-size: 20px; font-weight: 700; fill: #ffffff; }}
    </style>
  </defs>
  <rect width="1200" height="1600" fill="url(#bg)"/>
  <rect x="44" y="44" width="1112" height="226" rx="28" fill="url(#hero)"/>
  <text x="82" y="120" class="font title">CAMEL Mall 竞品情报日报</text>
  <text x="84" y="168" class="font sub">FastMoss 数据源 · TikTok Shop Thailand · {now:%Y-%m-%d}</text>
  <text x="84" y="216" class="font sub">口径：售价 / 昨日销量 / 近7天销量GMV / 总销量 / 达人出单率</text>

  <rect x="78" y="300" width="320" height="150" rx="22" fill="#ffffff"/>
  <text x="110" y="352" class="font label">监控商品</text>
  <text x="110" y="410" class="font value">{len(items)}</text>
  <text x="170" y="410" class="font small">个核心 SKU</text>

  <rect x="440" y="300" width="320" height="150" rx="22" fill="#ffffff"/>
  <text x="472" y="352" class="font label">近7天总销量</text>
  <text x="472" y="410" class="font value">{total_day7:,}</text>
  <text x="472" y="438" class="font small">四品合计</text>

  <rect x="802" y="300" width="320" height="150" rx="22" fill="#ffffff"/>
  <text x="834" y="352" class="font label">昨日总销量</text>
  <text x="834" y="410" class="font value">{total_yday:,}</text>
  <text x="834" y="438" class="font small">四品合计</text>

{''.join(cards)}

  <rect x="78" y="1450" width="1044" height="96" rx="22" fill="#17242d"/>
  <text x="112" y="1494" class="font sub">今日判断：近7天销量最高为 {xml_escape(top['name_cn'])}，近7天销量 {xml_escape(top.get('day7_sold_count_show') or top.get('day7_sold_count'))}。</text>
  <text x="112" y="1532" class="font sub">后续重点：价格变化、近7天增量、达人出单率、直播/视频带货规模。</text>
</svg>
"""


def push_serverchan(title, body):
    sendkey = os.getenv("SERVERCHAN_BOSS_SENDKEY", "").strip()
    if not sendkey:
        raise RuntimeError("Missing SERVERCHAN_BOSS_SENDKEY")
    url = f"https://sctapi.ftqq.com/{sendkey}.send"
    payload = urllib.parse.urlencode({"text": title, "desp": body}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    if result.get("code") != 0:
        raise RuntimeError(f"ServerChan failed: {result}")
    return result


def main():
    cookie = os.getenv("FASTMOSS_COOKIE", "").strip()
    if not cookie:
        raise RuntimeError("Missing FASTMOSS_COOKIE")
    now = bangkok_now()
    products = load_json(CONFIG_PATH)
    items = []
    for product in products:
        item = fastmoss_product(product["product_id"], cookie)
        item["name_cn"] = product["name_cn"]
        items.append(item)

    REPORT_DIR.mkdir(exist_ok=True)
    date_name = now.strftime("%Y-%m-%d")
    svg = build_svg(items, now)
    (REPORT_DIR / f"camel-mall-{date_name}.svg").write_text(svg, encoding="utf-8")
    (REPORT_DIR / "camel-mall-latest.svg").write_text(svg, encoding="utf-8")
    (REPORT_DIR / f"camel-mall-{date_name}.json").write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    image_url = f"https://raw.githubusercontent.com/lizifantk-dot/ai-news-wechat/main/reports/camel-mall-{date_name}.svg"
    body = f"# CAMEL Mall 竞品情报日报\\n\\n![CAMEL Mall 竞品情报日报]({image_url})\\n\\n图片链接：{image_url}\\n\\n数据源：FastMoss"
    result = push_serverchan(f"CAMEL Mall 竞品情报图 - {date_name}", body)
    print(json.dumps({"ok": True, "products": len(items), "pushid": result.get("data", {}).get("pushid")}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
