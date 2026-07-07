import csv
import html
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests


DOC_URL = "https://docs.qq.com/smartsheet/DVUxMWFNiSmtkb3Bx?tab=th1cKO"
DOC_ID = "DVUxMWFNiSmtkb3Bx"
GLOBAL_PAD_ID = "300000000$ULLXSbJkdopq"
GET_SHEET_URL = "https://docs.qq.com/dop-api/get/sheet"
OPENDOC_URL = "https://docs.qq.com/dop-api/opendoc"
OUTPUT_DIR = Path(__file__).resolve().parent

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": DOC_URL,
}

TARGET_SHEET_NAMES = {
    "2027届内推暑期实习信息",
    "27届非内推暑期实习信息",
    "27届秋招提前批",
    "27届日常实习",
    "2026届春招内推",
}


def get_json(url, params):
    response = requests.get(url, params=params, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.json()


def read_opendoc_title():
    params = {
        "id": DOC_ID,
        "normal": "1",
        "outformat": "1",
        "startrow": "0",
        "endrow": "60",
        "wb": "1",
        "nowb": "0",
        "callback": "clientVarsCallback",
        "xsrf": "",
        "t": str(int(time.time() * 1000)),
    }
    response = requests.get(OPENDOC_URL, params=params, headers=HEADERS, timeout=30)
    response.raise_for_status()
    match = re.search(r'clientVarsCallback\("(.+)"\)', response.text)
    if not match:
        return "腾讯文档岗位合集"
    payload = json.loads(html.unescape(match.group(1)))
    return payload.get("clientVars", {}).get("padTitle") or "腾讯文档岗位合集"


def get_sheet_page(tab_id, start=0, end=200):
    params = {
        "padId": GLOBAL_PAD_ID,
        "tab": tab_id,
        "subId": tab_id,
        "outformat": "1",
        "startrow": str(start),
        "endrow": str(end),
        "normal": "1",
        "preview_token": "",
        "nowb": "1",
    }
    data = get_json(GET_SHEET_URL, params)
    if data.get("retcode") != 0:
        raise RuntimeError(f"get/sheet failed for {tab_id}: {data}")
    text = data["data"]["initialAttributedText"]["text"][0]
    return text


def get_workbook():
    text = get_sheet_page("sc_nvPJ02", 0, 100)
    return json.loads(text["workbook"])


def extract_options(field_meta):
    options = {}

    def walk(node):
        if isinstance(node, dict):
            maybe = node.get("3")
            if isinstance(maybe, list):
                for item in maybe:
                    if isinstance(item, dict) and "1" in item and "2" in item:
                        options[str(item["1"])] = str(item["2"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(field_meta)
    return options


def parse_segments(segments):
    texts = []
    urls = []
    if not isinstance(segments, list):
        return "", urls
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        seg_type = segment.get("1")
        label = segment.get("2") or ""
        url = segment.get("3") or ""
        if label:
            texts.append(str(label))
        if seg_type == "url" or url.startswith(("http://", "https://", "mailto:")):
            final_url = url or label
            if final_url:
                urls.append({"label": str(label or final_url), "url": str(final_url)})
    return "".join(texts).strip(), urls


def is_plausible_url(url):
    url = (url or "").strip()
    if url.startswith("mailto:"):
        return True
    if not url.startswith(("http://", "https://")):
        return False
    reject_words = ["招满为止", "已截止", "暂无", "无", "待定", "见公告"]
    if any(word in url for word in reject_words):
        return False
    if re.search(r"https?://20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}$", url):
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = parsed.netloc
    if not host:
        return False
    return "." in host or host.lower() == "localhost"


def normalize_cell(cell, options):
    if not isinstance(cell, dict):
        return "", []
    parts = []
    urls = []

    if isinstance(cell.get("1"), list):
        text, found = parse_segments(cell["1"])
        if text:
            parts.append(text)
        urls.extend(found)

    if isinstance(cell.get("8"), list):
        text, found = parse_segments(cell["8"])
        if text:
            parts.append(text)
        urls.extend(found)

    if "9" in cell:
        raw = cell["9"]
        values = raw if isinstance(raw, list) else [raw]
        labels = [options.get(str(value), str(value)) for value in values if str(value)]
        if labels:
            parts.append("、".join(labels))

    if "4" in cell:
        value = cell["4"]
        if isinstance(value, dict):
            value = value.get("1") or value.get("2") or value.get("v") or ""
        if value:
            parts.append(str(value))

    text = "\n".join(part for part in parts if part).strip()
    deduped_urls = []
    seen = set()
    for item in urls:
        url = item.get("url", "").strip()
        if not url or url in seen or not is_plausible_url(url):
            continue
        seen.add(url)
        deduped_urls.append(item)
    return text, deduped_urls


def first_matching(fields, patterns):
    for pattern in patterns:
        regex = re.compile(pattern)
        for name, info in fields.items():
            if regex.search(name) and info["value"]:
                return info["value"]
    return ""


def urls_matching(fields, patterns):
    regexes = [re.compile(pattern) for pattern in patterns]
    result = []
    seen = set()
    for name, info in fields.items():
        if not any(regex.search(name) for regex in regexes):
            continue
        for item in info["urls"]:
            url = item["url"].strip()
            if url and url not in seen:
                seen.add(url)
                result.append(item)
    return result


def all_urls(fields):
    result = []
    seen = set()
    for info in fields.values():
        for item in info["urls"]:
            url = item["url"].strip()
            if url and url not in seen:
                seen.add(url)
                result.append(item)
    return result


def infer_referral_code(fields, all_text):
    code = first_matching(fields, [r"内推码", r"推荐码"])
    if code and not is_plausible_url(code) and len(code) <= 80:
        return code
    match = re.search(r"(?:内推码|推荐码)\s*[:：]\s*([A-Za-z0-9_\-]{3,})", all_text)
    return match.group(1) if match else ""


def ms_to_date(value):
    try:
        ts = int(value)
    except (TypeError, ValueError):
        return ""
    if ts <= 0:
        return ""
    if ts > 10_000_000_000:
        ts = ts / 1000
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def normalize_job(sheet, row_id, row, field_defs, field_options):
    cells = row.get("1", {}) if isinstance(row, dict) else {}
    fields = {}
    updated_ms = 0
    for field_id, cell in cells.items():
        meta = field_defs.get(field_id, {})
        name = meta.get("30") or field_id
        value, urls = normalize_cell(cell, field_options.get(field_id, {}))
        if not value and not urls:
            continue
        while name in fields:
            name = f"{name} {field_id}"
        fields[name] = {"value": value, "urls": urls}
        try:
            updated_ms = max(updated_ms, int(cell.get("32", 0)))
        except (TypeError, ValueError, AttributeError):
            pass

    all_text = "\n".join(info["value"] for info in fields.values() if info["value"])
    referral_code = infer_referral_code(fields, all_text)
    referral_links = urls_matching(fields, [r"内推链接", r"推荐链接", r"内推"])
    direct_urls = urls_matching(fields, [r"投递", r"内推链接", r"招聘公告", r"链接", r"邮箱"])
    if not direct_urls:
        direct_urls = all_urls(fields)

    sheet_name = sheet["name"]
    has_referral = bool(referral_code or referral_links)
    if "非内推" in sheet_name:
        has_referral = False
    elif "内推" in sheet_name:
        has_referral = True
    elif "内推链接" in "".join(fields.keys()) and direct_urls:
        has_referral = True

    company = first_matching(fields, [r"公司名称", r"公司名", r"企业", r"官方平台"])
    role = first_matching(fields, [r"招聘岗位", r"岗位名称", r"岗位", r"招聘公告"])
    deadline = first_matching(fields, [r"截止时间", r"投递截止", r"截止", r"日期", r"时间"])
    location = first_matching(fields, [r"工作地点", r"地点", r"城市"])
    industry = first_matching(fields, [r"所属行业", r"行业"])
    job_type = first_matching(fields, [r"招聘类型", r"招聘对象", r"类型"])
    exam = first_matching(fields, [r"笔试"])
    progress = first_matching(fields, [r"投递进度"])
    degree = first_matching(fields, [r"硕士", r"学历", r"招聘对象"])
    note = first_matching(fields, [r"其他信息", r"备注", r"投递邮箱", r"细节", r"文本"])

    if not company and not role and not direct_urls and len(all_text) < 2:
        return None

    return {
        "id": f"{sheet['id']}:{row_id}",
        "rowId": row_id,
        "sourceSheetId": sheet["id"],
        "sourceSheet": sheet_name,
        "sourceUrl": f"https://docs.qq.com/smartsheet/{DOC_ID}?tab={sheet['id']}",
        "category": "has_referral" if has_referral else "no_referral",
        "company": company or "未标注公司",
        "role": role or "未标注岗位",
        "deadline": deadline,
        "location": location,
        "industry": industry,
        "jobType": job_type,
        "degree": degree,
        "exam": exam,
        "progress": progress,
        "referralCode": referral_code,
        "referralLinks": referral_links,
        "primaryUrl": direct_urls[0]["url"] if direct_urls else "",
        "primaryUrlLabel": direct_urls[0]["label"] if direct_urls else "",
        "urls": direct_urls,
        "note": note,
        "updatedAt": ms_to_date(updated_ms),
        "fields": fields,
        "searchText": "\n".join([sheet_name, company, role, deadline, location, industry, job_type, referral_code, all_text]).lower(),
    }


def parse_sheet(sheet):
    first = get_sheet_page(sheet["id"], 0, 200)
    max_row = int(first.get("max_row") or 0)
    pages = [(0, 200)]
    for start in range(200, max_row + 1, 200):
        pages.append((start, start + 200))

    jobs = {}
    field_defs = {}
    field_options = {}

    for start, end in pages:
        text = first if start == 0 else get_sheet_page(sheet["id"], start, end)
        smartsheet = json.loads(text["smartsheet"])
        for batch in smartsheet:
            for op in batch:
                if op.get("t") == 3005:
                    field_defs = op.get("c", {}).get("3", {}).get("3", {}) or field_defs
                    field_options = {field_id: extract_options(meta) for field_id, meta in field_defs.items()}
                if op.get("t") == 3028:
                    records = op.get("c", {}).get("2", {}).get("1", {}) or {}
                    for row_id, row in records.items():
                        job = normalize_job(sheet, row_id, row, field_defs, field_options)
                        if job:
                            jobs[job["id"]] = job
    return list(jobs.values())


def write_outputs(title, jobs):
    jobs.sort(key=lambda item: (item.get("updatedAt") or "", item.get("company") or ""), reverse=True)
    fetched_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "title": title,
        "sourceUrl": DOC_URL,
        "fetchedAt": fetched_at,
        "total": len(jobs),
        "hasReferral": sum(1 for job in jobs if job["category"] == "has_referral"),
        "noReferral": sum(1 for job in jobs if job["category"] == "no_referral"),
        "jobs": jobs,
    }

    data_js = "window.JOBS_DATA = " + json.dumps(payload, ensure_ascii=False, indent=2) + ";\n"
    (OUTPUT_DIR / "jobs-data.js").write_text(data_js, encoding="utf-8")

    with (OUTPUT_DIR / "jobs.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "category",
                "sourceSheet",
                "company",
                "role",
                "deadline",
                "location",
                "industry",
                "jobType",
                "degree",
                "exam",
                "progress",
                "referralCode",
                "primaryUrl",
                "updatedAt",
                "sourceUrl",
                "note",
            ],
        )
        writer.writeheader()
        for job in jobs:
            writer.writerow({key: job.get(key, "") for key in writer.fieldnames})

    print(json.dumps({key: payload[key] for key in ["title", "fetchedAt", "total", "hasReferral", "noReferral"]}, ensure_ascii=False, indent=2))


def main():
    title = read_opendoc_title()
    workbook = get_workbook()
    sheets = [sheet for sheet in workbook if sheet.get("name") in TARGET_SHEET_NAMES and not sheet.get("hidden")]
    all_jobs = []
    for sheet in sheets:
        print(f"fetching {sheet['name']} ({sheet['id']})")
        all_jobs.extend(parse_sheet(sheet))
    write_outputs(title, all_jobs)


if __name__ == "__main__":
    main()
