import datetime as dt
import html
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "echotik_latest.json"
FASTMOSS_PATH = ROOT / "data" / "fastmoss_latest.json"
REPORT_DIR = ROOT / "reports"
PUSH_LOG_PATH = REPORT_DIR / "push-log.json"


def bangkok_now():
    return dt.datetime.now(dt.timezone.utc).astimezone(dt.timezone(dt.timedelta(hours=7)))


def load_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def xml(value):
    return html.escape(str(value or ""), quote=True)


def number(value):
    try:
        return float(str(value or "").replace("฿", "").replace(",", ""))
    except Exception:
        return 0.0


def short(value, length):
    value = str(value or "")
    return value if len(value) <= length else value[: length - 1] + "…"


def split_lines(value, size, max_lines):
    value = str(value or "")
    lines = []
    while value and len(lines) < max_lines:
        lines.append(value[:size])
        value = value[size:]
    if value and lines:
        lines[-1] = lines[-1][: max(1, size - 1)] + "…"
    return lines or [""]


def money_total(value):
    return f"฿{value:,.0f}"


def match_by_id(rows):
    return {str(row.get("product_id")): row for row in rows}


def compact_metric(value):
    value = str(value or "-")
    return short(value.replace("฿", "฿"), 14)


def already_pushed_today(date_name):
    if os.getenv("FORCE_SEND", "").strip().lower() in ("1", "true", "yes"):
        return False
    push_log = load_json(PUSH_LOG_PATH, {})
    return push_log.get("last_success_date") == date_name


def record_push(date_name, now, result):
    PUSH_LOG_PATH.write_text(
        json.dumps(
            {
                "last_success_date": date_name,
                "last_success_time_bangkok": now.strftime("%Y-%m-%d %H:%M:%S"),
                "pushid": (result.get("data") or {}).get("pushid"),
                "style": "tech-radar",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def point(cx, cy, radius, deg):
    import math

    rad = (deg - 90) * math.pi / 180
    return cx + math.cos(rad) * radius, cy + math.sin(rad) * radius


def build_svg(rows, fastmoss_rows, now):
    rows = rows[:4]
    fastmoss_by_id = match_by_id(fastmoss_rows)
    has_fastmoss = bool(fastmoss_rows)
    sorted_rows = sorted(rows, key=lambda item: number(item.get("day7_sold")), reverse=True)
    max_7 = max([number(item.get("day7_sold")) for item in rows] + [1])
    max_gmv = max([number(item.get("day7_gmv")) for item in rows] + [1])
    total_7 = sum(number(item.get("day7_sold")) for item in rows)
    total_gmv = sum(number(item.get("day7_gmv")) for item in rows)
    total_sold = sum(number(item.get("sold")) for item in rows)
    top = sorted_rows[0] if sorted_rows else {}
    colors = ["#2EE6A6", "#55A7FF", "#FFC857", "#FF6B8A"]

    grid = "".join(
        f'<line x1="60" y1="{332 + i * 126}" x2="1140" y2="{332 + i * 126}" stroke="#112833" opacity="0.48"/>'
        for i in range(9)
    ) + "".join(
        f'<line x1="{90 + i * 110}" y1="300" x2="{90 + i * 110}" y2="1500" stroke="#112833" opacity="0.38"/>'
        for i in range(10)
    )

    rings = []
    for radius in [42, 84, 126, 168, 210]:
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in [point(392, 690, radius, deg) for deg in [0, 90, 180, 270]])
        rings.append(f'<polygon points="{pts}" fill="none" stroke="#294756" stroke-width="1" opacity="0.8"/>')

    axes = []
    radar_points = []
    radar_dots = []
    for idx, row in enumerate(rows):
        deg = idx * 90
        x, y = point(392, 690, 230, deg)
        dy = -12 if y < 690 else 26
        axis_name = short(row.get("name_cn"), 10)
        axes.append(
            f'<line x1="392" y1="690" x2="{x:.1f}" y2="{y:.1f}" stroke="#294756" stroke-width="1.2"/>'
            f'<text x="{x:.1f}" y="{y + dy:.1f}" text-anchor="middle" class="axis">{xml(axis_name)}</text>'
        )
        radius = 45 + number(row.get("day7_sold")) / max_7 * 165
        px, py = point(392, 690, radius, deg)
        radar_points.append(f"{px:.1f},{py:.1f}")
        radar_dots.append(
            f'<circle cx="{px:.1f}" cy="{py:.1f}" r="6" fill="{colors[idx % len(colors)]}" stroke="#EAF6FF" stroke-width="2"/>'
        )

    top_lines = "".join(
        f'<text x="780" y="{646 + idx * 36}" class="focusName">{xml(line)}</text>'
        for idx, line in enumerate(split_lines(top.get("name_cn", "-"), 9, 2))
    )

    row_blocks = []
    for rank, row in enumerate(sorted_rows, 1):
        idx = rows.index(row)
        y = 940 + (rank - 1) * 102
        color = colors[idx % len(colors)]
        sales_width = round(number(row.get("day7_sold")) / max_7 * 265)
        gmv_width = round(number(row.get("day7_gmv")) / max_gmv * 230)
        tag = ["重点警戒", "高热跟踪", "稳定观察", "低位监控"][rank - 1]
        row_blocks.append(
            f"""
  <g transform="translate(62 {y})">
    <rect width="1076" height="82" rx="13" fill="#101D25" stroke="#253D49"/>
    <rect x="0" y="0" width="5" height="82" rx="2.5" fill="{color}"/>
    <text x="28" y="34" class="rank">#{rank}</text>
    <text x="88" y="32" class="rowTitle">{xml(short(row.get("name_cn"), 13))}</text>
    <text x="88" y="60" class="rowSub">EchoTik {xml(compact_metric(row.get("day7_sold")))} 单 · FastMoss {xml(compact_metric((fastmoss_by_id.get(str(row.get("product_id"))) or {}).get("day7_sold")))} 单</text>
    <text x="318" y="32" class="rowMetric">7日销量 {xml(row.get("day7_sold"))}</text>
    <rect x="318" y="50" width="265" height="8" rx="4" fill="#21313A"/>
    <rect x="318" y="50" width="{sales_width}" height="8" rx="4" fill="{color}"/>
    <text x="620" y="32" class="rowMetric">7日GMV {xml(row.get("day7_gmv"))}</text>
    <rect x="620" y="50" width="230" height="8" rx="4" fill="#21313A"/>
    <rect x="620" y="50" width="{gmv_width}" height="8" rx="4" fill="#7DD3FC"/>
    <text x="880" y="32" class="rowSub">Echo总量 {int(number(row.get("sold"))):,}</text>
    <text x="880" y="58" class="rowSub">FM GMV {xml(compact_metric((fastmoss_by_id.get(str(row.get("product_id"))) or {}).get("day7_gmv")))}</text>
    <rect x="972" y="22" width="82" height="30" rx="15" fill="#172A33" stroke="{color}"/>
    <text x="1013" y="43" text-anchor="middle" class="tag">{tag}</text>
  </g>"""
        )

    source_line = (
        "数据源：EchoTik API + FastMoss 会员数据 · GitHub Actions 自动生成 · 推送对象：老板微信"
        if has_fastmoss
        else "数据源：EchoTik API · FastMoss 登录态待更新 · GitHub Actions 自动生成 · 推送对象：老板微信"
    )
    subtitle_source = (
        "EchoTik API + FastMoss Member Data"
        if has_fastmoss
        else "EchoTik API · FastMoss Cookie Pending"
    )

    conclusion = (
        f"今日主警戒：{top.get('name_cn', '-')}，近7天销量 {top.get('day7_sold', '-')} 单。"
        "建议重点盯价格、直播节奏和达人带货。"
    )
    conclusion_lines = "".join(
        f'<text x="94" y="{1434 + idx * 34}" class="conclusion">{xml(line)}</text>'
        for idx, line in enumerate(split_lines(conclusion, 40, 2))
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="1560" viewBox="0 0 1200 1560">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#061017"/><stop offset="0.55" stop-color="#091923"/><stop offset="1" stop-color="#0B0F16"/></linearGradient>
    <linearGradient id="bar" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#2EE6A6"/><stop offset="0.48" stop-color="#55A7FF"/><stop offset="1" stop-color="#FFC857"/></linearGradient>
    <filter id="shadow"><feDropShadow dx="0" dy="12" stdDeviation="14" flood-color="#000" flood-opacity="0.34"/></filter>
    <style>
      text{{font-family:'Microsoft YaHei UI','Microsoft YaHei','Segoe UI',Arial,sans-serif;letter-spacing:0}}
      .h1{{font:800 46px 'Microsoft YaHei UI','Microsoft YaHei','Segoe UI',Arial,sans-serif;fill:#F3FAFF}}
      .h2{{font:400 20px 'Microsoft YaHei UI','Microsoft YaHei','Segoe UI',Arial,sans-serif;fill:#9FB5BF}}
      .label{{font:600 17px 'Microsoft YaHei UI','Microsoft YaHei','Segoe UI',Arial,sans-serif;fill:#8BA5B1}}
      .num{{font:700 34px 'Bahnschrift','Segoe UI',Arial,sans-serif;fill:#F7FBFF}}
      .axis{{font:700 16px 'Microsoft YaHei UI','Microsoft YaHei','Segoe UI',Arial,sans-serif;fill:#B8CAD2}}
      .focusName{{font:800 30px 'Microsoft YaHei UI','Microsoft YaHei','Segoe UI',Arial,sans-serif;fill:#F3FAFF}}
      .focusText{{font:500 19px 'Microsoft YaHei UI','Microsoft YaHei','Segoe UI',Arial,sans-serif;fill:#AFC3CC}}
      .rank{{font:700 24px 'Bahnschrift','Segoe UI',Arial,sans-serif;fill:#EAF6FF}}
      .rowTitle{{font:800 23px 'Microsoft YaHei UI','Microsoft YaHei','Segoe UI',Arial,sans-serif;fill:#F2F8FB}}
      .rowMetric{{font:700 19px 'Microsoft YaHei UI','Microsoft YaHei','Segoe UI',Arial,sans-serif;fill:#DDECF2}}
      .rowSub{{font:500 15px 'Microsoft YaHei UI','Microsoft YaHei','Segoe UI',Arial,sans-serif;fill:#8FA4AE}}
      .tag{{font:700 14px 'Microsoft YaHei UI','Microsoft YaHei','Segoe UI',Arial,sans-serif;fill:#DDF7FF}}
      .conclusion{{font:700 22px 'Microsoft YaHei UI','Microsoft YaHei','Segoe UI',Arial,sans-serif;fill:#F4FBFF}}
      .tiny{{font:400 15px 'Microsoft YaHei UI','Microsoft YaHei','Segoe UI',Arial,sans-serif;fill:#78909A}}
    </style>
  </defs>
  <rect width="1200" height="1560" fill="url(#bg)"/>
  {grid}
  <rect x="42" y="36" width="1116" height="232" rx="24" fill="#0F1C24" stroke="#263F4B" filter="url(#shadow)"/>
  <rect x="42" y="36" width="1116" height="5" rx="2.5" fill="url(#bar)"/>
  <text x="76" y="112" class="h1">CAMEL Mall 竞品雷达情报系统</text>
  <text x="78" y="156" class="h2">{subtitle_source} · TikTok Shop Thailand · {now:%Y-%m-%d}</text>
  <text x="78" y="198" class="h2">监控口径：EchoTik 主口径、FastMoss 交叉校验、7日销量、GMV、售价带宽、竞争强度</text>
  <rect x="906" y="86" width="184" height="50" rx="25" fill="#112A33" stroke="#2EE6A6"/>
  <text x="998" y="119" text-anchor="middle" class="tag" style="font-size:18px">LIVE DATA</text>
  <g filter="url(#shadow)">
    <rect x="62" y="304" width="250" height="116" rx="17" fill="#101D25" stroke="#253D49"/><text x="90" y="350" class="label">监控 SKU</text><text x="90" y="398" class="num">{len(rows)}</text>
    <rect x="335" y="304" width="250" height="116" rx="17" fill="#101D25" stroke="#253D49"/><text x="363" y="350" class="label">近7天总销量</text><text x="363" y="398" class="num">{int(total_7):,}</text>
    <rect x="608" y="304" width="250" height="116" rx="17" fill="#101D25" stroke="#253D49"/><text x="636" y="350" class="label">近7天GMV</text><text x="636" y="398" class="num">{money_total(total_gmv)}</text>
    <rect x="881" y="304" width="257" height="116" rx="17" fill="#101D25" stroke="#253D49"/><text x="909" y="350" class="label">累计总销量</text><text x="909" y="398" class="num">{int(total_sold):,}</text>
  </g>
  <rect x="62" y="462" width="1076" height="416" rx="22" fill="#0B171F" stroke="#223B47" filter="url(#shadow)"/>
  <text x="94" y="520" class="rowTitle">竞争强度雷达</text>
  <text x="94" y="552" class="h2" style="font-size:18px">按近7天销量归一化，越靠外代表近期爆发越强</text>
  {''.join(rings)}
  {''.join(axes)}
  <polygon points="{' '.join(radar_points)}" fill="#2EE6A6" opacity="0.18" stroke="#2EE6A6" stroke-width="3"/>
  {''.join(radar_dots)}
  <rect x="720" y="540" width="360" height="240" rx="18" fill="#101F28" stroke="#294756"/>
  <text x="780" y="600" class="label">今日主警戒对象</text>
  {top_lines}
  <text x="780" y="724" class="focusText">近7天销量：{xml(top.get("day7_sold", "-"))} 单</text>
  <text x="780" y="760" class="focusText">近7天GMV：{xml(top.get("day7_gmv", "-"))}</text>
  <text x="780" y="796" class="focusText">建议：盯价格、达人、直播节奏，并对比 FastMoss 差异</text>
  {''.join(row_blocks)}
  <rect x="62" y="1394" width="1076" height="96" rx="18" fill="#101D25" stroke="#2EE6A6"/>
  {conclusion_lines}
  <text x="62" y="1528" class="tiny">{source_line}</text>
</svg>"""


def push_serverchan(title, body):
    sendkey = os.getenv("SERVERCHAN_BOSS_SENDKEY", "").strip()
    if not sendkey:
        raise RuntimeError("Missing SERVERCHAN_BOSS_SENDKEY")
    payload = urllib.parse.urlencode({"text": title, "desp": body}).encode("utf-8")
    req = urllib.request.Request(f"https://sctapi.ftqq.com/{sendkey}.send", data=payload, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    if result.get("code") != 0:
        raise RuntimeError(f"ServerChan failed: {result}")
    return result


def main():
    now = bangkok_now()
    date_name = now.strftime("%Y-%m-%d")
    REPORT_DIR.mkdir(exist_ok=True)
    if already_pushed_today(date_name):
        print(json.dumps({"ok": True, "skipped": True, "reason": "already_pushed_today"}, ensure_ascii=False))
        return

    data = load_json(DATA_PATH, {})
    rows = data.get("products") or data.get("items") or []
    if not rows:
        raise RuntimeError("Missing EchoTik data. Run scripts/echotik_fetch.py first.")
    fastmoss_data = load_json(FASTMOSS_PATH, {})
    fastmoss_rows = fastmoss_data.get("products") or fastmoss_data.get("items") or []

    svg = build_svg(rows, fastmoss_rows, now)
    report_name = f"camel-mall-tech-radar-{date_name}.svg"
    latest_name = "camel-mall-tech-radar-latest.svg"
    (REPORT_DIR / report_name).write_text(svg, encoding="utf-8")
    (REPORT_DIR / latest_name).write_text(svg, encoding="utf-8")

    image_url = f"https://raw.githubusercontent.com/lizifantk-dot/ai-news-wechat/main/reports/{report_name}"
    title = f"CAMEL Mall 竞品雷达情报 - {date_name}"
    body = (
        f"# CAMEL Mall 竞品雷达情报\\n\\n"
        f"![CAMEL Mall 竞品雷达情报]({image_url})\\n\\n"
        f"图片链接：{image_url}\\n\\n"
        f"数据源：EchoTik API + FastMoss 会员数据（FastMoss 成功抓取时自动展示）· GitHub Actions 自动生成"
    )
    result = push_serverchan(title, body)
    record_push(date_name, now, result)
    print(json.dumps({"ok": True, "pushid": (result.get("data") or {}).get("pushid")}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
