import datetime as dt
import email.utils
import html
import json
import os
import re
import sys
import textwrap
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


FEEDS = [
    ("OpenAI News", "https://openai.com/news/rss.xml"),
    ("Anthropic News", "https://www.anthropic.com/news/rss.xml"),
    ("Google AI Blog", "https://blog.google/technology/ai/rss/"),
    ("Google DeepMind", "https://deepmind.google/discover/blog/rss.xml"),
    ("Microsoft AI Blog", "https://blogs.microsoft.com/ai/feed/"),
    ("NVIDIA AI Blog", "https://blogs.nvidia.com/blog/category/deep-learning/feed/"),
    ("Meta AI", "https://ai.meta.com/blog/rss/"),
    ("MIT News AI", "https://news.mit.edu/topic/artificial-intelligence2-rss.xml"),
    ("VentureBeat AI", "https://venturebeat.com/category/ai/feed/"),
    ("The Decoder", "https://the-decoder.com/feed/"),
]

KEYWORDS = (
    "ai",
    "artificial intelligence",
    "agent",
    "agents",
    "llm",
    "model",
    "openai",
    "anthropic",
    "claude",
    "gemini",
    "deepmind",
    "meta ai",
    "microsoft copilot",
    "generative",
    "automation",
    "search",
    "ads",
    "commerce",
    "ecommerce",
)


def utc_now():
    return dt.datetime.now(dt.timezone.utc)


def bangkok_now():
    return utc_now().astimezone(dt.timezone(dt.timedelta(hours=7)))


def fetch_url(url, timeout=20):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "ai-news-wechat/1.0 (+https://github.com/)",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def translate_to_chinese(text):
    text = clean_text(text)
    if not text:
        return ""
    if re.search(r"[\u4e00-\u9fff]", text):
        return text

    params = urllib.parse.urlencode(
        {
            "client": "gtx",
            "sl": "auto",
            "tl": "zh-CN",
            "dt": "t",
            "q": text[:4500],
        }
    )
    url = f"https://translate.googleapis.com/translate_a/single?{params}"
    try:
        data = json.loads(fetch_url(url, timeout=15).decode("utf-8"))
        translated = "".join(part[0] for part in data[0] if part and part[0])
        return clean_text(translated) or text
    except Exception:
        return text


def text_of(node, names):
    for name in names:
        found = node.find(name)
        if found is not None and found.text:
            return clean_text(found.text)
    return ""


def clean_text(value):
    value = re.sub(r"<[^>]+>", " ", html.unescape(value or ""))
    value = re.sub(r"\s+", " ", value).strip()
    return value


def parse_date(value):
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed and parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed
    except Exception:
        pass
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = dt.datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed
    except Exception:
        return None


def parse_feed(source, xml_bytes):
    root = ET.fromstring(xml_bytes)
    items = []

    for item in root.findall(".//channel/item"):
        title = text_of(item, ["title"])
        link = text_of(item, ["link"])
        summary = text_of(item, ["description", "summary"])
        published = parse_date(text_of(item, ["pubDate", "published", "updated"]))
        items.append(make_item(source, title, link, summary, published))

    atom_ns = "{http://www.w3.org/2005/Atom}"
    for entry in root.findall(f".//{atom_ns}entry"):
        title = text_of(entry, [f"{atom_ns}title"])
        summary = text_of(entry, [f"{atom_ns}summary", f"{atom_ns}content"])
        published = parse_date(text_of(entry, [f"{atom_ns}published", f"{atom_ns}updated"]))
        link = ""
        link_node = entry.find(f"{atom_ns}link")
        if link_node is not None:
            link = link_node.attrib.get("href", "")
        items.append(make_item(source, title, link, summary, published))

    return [item for item in items if item["title"] and item["url"]]


def make_item(source, title, url, summary, published):
    return {
        "source": source,
        "title": title,
        "url": url,
        "summary": summary[:500],
        "published": published.isoformat() if published else "",
    }


def collect_items():
    lookback_hours = int(os.getenv("LOOKBACK_HOURS", "72"))
    cutoff = utc_now() - dt.timedelta(hours=lookback_hours)
    collected = []
    errors = []

    for source, feed_url in FEEDS:
        try:
            feed = fetch_url(feed_url)
            for item in parse_feed(source, feed):
                published = parse_date(item["published"])
                text = f"{item['title']} {item['summary']}".lower()
                if published and published < cutoff:
                    continue
                if any(keyword in text for keyword in KEYWORDS):
                    collected.append(item)
        except Exception as exc:
            errors.append(f"{source}: {exc}")

    unique = {}
    for item in collected:
        key = item["url"].split("?")[0].rstrip("/")
        if key not in unique:
            unique[key] = item

    items = list(unique.values())
    items.sort(key=lambda value: value.get("published") or "", reverse=True)
    return items[:25], errors


def openai_brief(items):
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None

    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
    source_text = json.dumps(items[:20], ensure_ascii=False, indent=2)
    prompt = f"""
你是给一位在曼谷做电商运营的人写 AI 情报简报的研究助理。
请只基于下面 JSON 里的新闻来源写中文简报，不要编造来源之外的事实。

要求：
- 高信号、可执行，不要泛泛而谈。
- 明确哪些新闻对电商运营、广告、内容、客服、数据分析、自动化有影响。
- 每条关键新闻保留 Markdown 链接。
- 如果来源不足以支持 5 条重大新闻，可以少于 5 条，并说明今天没有特别重大的变化。

结构：
1. 今日最重要动态
2. 值得试用的工具/功能
3. 电商运营机会
4. 今天值得学习
5. 风险提醒
6. 今日建议动作

新闻 JSON：
{source_text}
""".strip()

    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": "你擅长把 AI 新闻翻译成电商运营可以执行的中文行动建议。",
            },
            {"role": "user", "content": prompt},
        ],
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        data = json.loads(response.read().decode("utf-8"))
    parts = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                parts.append(content.get("text", ""))
    return "\n".join(parts).strip()


def fallback_brief(items, errors):
    if not items:
        body = """
## 今日 AI 动态

今天没有从已配置来源抓到足够新的 AI 动态。建议稍后手动运行一次，或检查 RSS 来源是否临时不可用。

## 今日建议动作

1. 检查最近 100 条客服咨询，提炼购买顾虑。
2. 为 1 个核心 SKU 补齐 FAQ、规格、对比表和使用场景。
3. 用 AI 生成 10 条广告 Hook，并按痛点/场景/赠礼/价格/信任分类。
""".strip()
    else:
        lines = [
            "## 今日 AI 动态聚合",
            "",
            "说明：当前未配置 OpenAI API Key，所以本简报使用免费新闻源聚合，并自动翻译为中文。质量会比 AI 深度整理版弱一些，但可以保证你先读得懂。",
            "",
        ]
        for index, item in enumerate(items[:10], start=1):
            date_text = item.get("published", "")[:10] or "日期未知"
            title = translate_to_chinese(item["title"])
            summary = translate_to_chinese(item.get("summary") or "暂无摘要。")
            lines.append(f"{index}. [{title}]({item['url']})")
            lines.append(f"   来源：{item['source']}｜日期：{date_text}")
            lines.append(f"   摘要：{summary}")
            if title != item["title"]:
                lines.append(f"   原标题：{item['title']}")
            lines.append("")
        lines.extend(
            [
                "## 电商运营建议",
                "",
                "1. 把与搜索、广告、客服、素材生成有关的新闻优先记录到你的运营 SOP。",
                "2. 每天选 1 条新工具动态，设计一个 30 分钟小测试，不要只收藏不试用。",
                "3. 对涉及政策、版权、广告审核的 AI 功能，先小范围测试再规模化使用。",
            ]
        )
        body = "\n".join(lines)

    if errors:
        body += "\n\n## 抓取提醒\n\n部分来源抓取失败，不影响本次推送：\n"
        body += "\n".join(f"- {error}" for error in errors[:5])
    return body


def push_serverchan(title, body):
    sendkey = os.getenv("SERVERCHAN_SENDKEY", "").strip()
    if not sendkey:
        raise RuntimeError("Missing SERVERCHAN_SENDKEY secret.")

    url = f"https://sctapi.ftqq.com/{sendkey}.send"
    payload = urllib.parse.urlencode({"text": title, "desp": body}).encode("utf-8")
    request = urllib.request.Request(url, data=payload, method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.loads(response.read().decode("utf-8"))
    if result.get("code") != 0:
        raise RuntimeError(f"ServerChan push failed: {result}")
    return result


def main():
    now = bangkok_now()
    title = f"每日 AI 情报简报 - {now:%Y-%m-%d}"
    items, errors = collect_items()

    try:
        brief = openai_brief(items)
    except Exception as exc:
        brief = None
        errors.append(f"OpenAI summary failed: {exc}")

    if not brief:
        brief = fallback_brief(items, errors)

    header = textwrap.dedent(
        f"""
        # {title}

        信息截止：{now:%Y-%m-%d %H:%M}（曼谷时间）
        来源数量：{len(items)} 条候选动态
        """
    ).strip()
    body = f"{header}\n\n{brief}"
    result = push_serverchan(title, body)
    print(json.dumps({"ok": True, "pushid": result.get("data", {}).get("pushid")}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
