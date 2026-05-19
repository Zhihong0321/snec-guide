"""
Enrich snec26_exhibitors from SNEC public APIs:
- products/services, website, contact, country, China province (state)
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

import psycopg2

DB_URL = os.environ.get("DATABASE_URL")
if not DB_URL:
    raise SystemExit("DATABASE_URL is required")
TABLE_NAME = "snec26_exhibitors"
API_BASE = "https://pv.snec.org.cn/api"
YEAR = "2026"
DELAY_SEC = 0.12
BATCH_COMMIT = 50

HEADERS = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}

CHINA_NAMES = {"中国", "china", "中国大陆", "中國"}

PROVINCE_FROM_PREFIX = {
    "北京": "北京市",
    "上海": "上海市",
    "天津": "天津市",
    "重庆": "重庆市",
    "河北": "河北省",
    "山西": "山西省",
    "辽宁": "辽宁省",
    "吉林": "吉林省",
    "黑龙江": "黑龙江省",
    "江苏": "江苏省",
    "浙江": "浙江省",
    "安徽": "安徽省",
    "福建": "福建省",
    "江西": "江西省",
    "山东": "山东省",
    "河南": "河南省",
    "湖北": "湖北省",
    "湖南": "湖南省",
    "广东": "广东省",
    "海南": "海南省",
    "四川": "四川省",
    "贵州": "贵州省",
    "云南": "云南省",
    "陕西": "陕西省",
    "甘肃": "甘肃省",
    "青海": "青海省",
    "台湾": "台湾省",
    "内蒙古": "内蒙古自治区",
    "广西": "广西壮族自治区",
    "西藏": "西藏自治区",
    "宁夏": "宁夏回族自治区",
    "新疆": "新疆维吾尔自治区",
    "香港": "香港特别行政区",
    "澳门": "澳门特别行政区",
}

CITY_TO_PROVINCE = {
    "北京": "北京市",
    "上海": "上海市",
    "天津": "天津市",
    "重庆": "重庆市",
    "广州": "广东省",
    "深圳": "广东省",
    "珠海": "广东省",
    "东莞": "广东省",
    "佛山": "广东省",
    "杭州": "浙江省",
    "宁波": "浙江省",
    "温州": "浙江省",
    "嘉兴": "浙江省",
    "绍兴": "浙江省",
    "苏州": "江苏省",
    "南京": "江苏省",
    "无锡": "江苏省",
    "常州": "江苏省",
    "南通": "江苏省",
    "合肥": "安徽省",
    "芜湖": "安徽省",
    "西安": "陕西省",
    "成都": "四川省",
    "武汉": "湖北省",
    "长沙": "湖南省",
    "郑州": "河南省",
    "济南": "山东省",
    "青岛": "山东省",
    "厦门": "福建省",
    "福州": "福建省",
    "昆明": "云南省",
    "沈阳": "辽宁省",
    "大连": "辽宁省",
    "哈尔滨": "黑龙江省",
    "长春": "吉林省",
    "石家庄": "河北省",
    "太原": "山西省",
    "南昌": "江西省",
    "南宁": "广西壮族自治区",
    "海口": "海南省",
    "兰州": "甘肃省",
    "银川": "宁夏回族自治区",
    "乌鲁木齐": "新疆维吾尔自治区",
    "拉萨": "西藏自治区",
    "呼和浩特": "内蒙古自治区",
}


def post_api(path, body):
    req = urllib.request.Request(
        f"{API_BASE}/{path}",
        data=json.dumps(body).encode("utf-8"),
        headers=HEADERS,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if isinstance(payload, dict) and payload.get("error"):
        raise ValueError(payload["error"])
    return payload


def parse_json_field(raw, lang="CN"):
    if not raw:
        return ""
    if isinstance(raw, dict):
        return (raw.get(lang) or raw.get("EN") or "").strip()
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return (obj.get(lang) or obj.get("EN") or "").strip()
    except (json.JSONDecodeError, TypeError):
        pass
    return str(raw).strip()


def extract_province_from_address(address):
    if not address:
        return ""
    address = address.strip()
    m = re.match(
        r"^(.+?(?:省|自治区|特别行政区))",
        address,
    )
    if m:
        return m.group(1)
    for municipality in ("北京市", "上海市", "天津市", "重庆市"):
        if address.startswith(municipality) or address.startswith(municipality[:2]):
            return municipality
    m2 = re.match(r"^(北京|上海|天津|重庆)", address)
    if m2:
        return m2.group(1) + "市"
    return ""


def extract_province_from_name(name):
    if not name:
        return ""
    for prefix, full in PROVINCE_FROM_PREFIX.items():
        if name.startswith(prefix):
            return full
    return ""


def extract_province_from_text(text):
    if not text:
        return ""
    for city, prov in CITY_TO_PROVINCE.items():
        if city in text:
            return prov
    return ""


def is_china(country):
    if not country:
        return False
    c = country.strip().lower()
    return c in CHINA_NAMES or "china" in c or country.strip() == "中国"


def normalize_country(raw_country, address, company_name, profile):
    country = parse_json_field(raw_country) or (raw_country or "").strip()
    if not country and address:
        if extract_province_from_address(address) or extract_province_from_name(
            company_name
        ):
            country = "China"
    if not country and company_name:
        if extract_province_from_name(company_name):
            country = "China"
    if not country and profile and re.search(r"[\u4e00-\u9fff]", profile):
        if extract_province_from_text(profile) or any(
            k in profile for k in ("中国", "国内", "我国")
        ):
            country = "China"
    return country


def resolve_state_province(country, address, company_name, profile):
    if not is_china(country):
        return ""
    for fn in (
        lambda: extract_province_from_address(address),
        lambda: extract_province_from_name(company_name),
        lambda: extract_province_from_text(address or ""),
        lambda: extract_province_from_text(profile or ""),
        lambda: extract_province_from_text(company_name or ""),
    ):
        prov = fn()
        if prov:
            return prov
    return ""


def products_from_contract(data):
    seen = set()
    items = []
    for row in data.get("ProductTypeRecordList") or []:
        name = parse_json_field(row.get("productTypeName"))
        if name and name not in seen:
            seen.add(name)
            items.append(name)
    return "; ".join(items)


def products_from_highlight(data):
    first = parse_json_field(data.get("FirstProductTypeName"))
    prod = parse_json_field(data.get("ProductTypeName"))
    parts = []
    if first and prod:
        parts.append(f"{first}: {prod}")
    elif prod:
        parts.append(prod)
    elif first:
        parts.append(first)

    hot = []
    for p in data.get("HotProdList") or []:
        title = parse_json_field(p.get("ProductName") or p.get("Title"))
        if title:
            hot.append(title)
    if hot:
        parts.append("Featured products: " + "; ".join(hot[:10]))
    return " | ".join(parts)


def build_contact(data, prefix=""):
    def g(key):
        return (data.get(prefix + key) or data.get(key) or "").strip()

    name = g("Contacts") or g("Contact")
    email = g("ComEmail") or g("Email")
    tel = g("Tel") or g("Mobile") or g("Phone")
    fax = g("Fax")
    mobile = g("Mobile")

    bits = []
    if name:
        bits.append(f"Name: {name}")
    if email:
        bits.append(f"Email: {email}")
    if tel:
        bits.append(f"Tel: {tel}")
    if mobile and mobile != tel:
        bits.append(f"Mobile: {mobile}")
    if fax:
        bits.append(f"Fax: {fax}")

    phone = tel or mobile
    return name, email, phone, " | ".join(bits)


def fetch_contract(exb_contract_id):
    return post_api("getExbContractByID", {"ExbContractID": exb_contract_id})


def fetch_highlight(invite_company_info_id):
    return post_api(
        "getComProdTechHlightsByExbContractID",
        {
            "InviteCompanyInfoID": invite_company_info_id,
            "MemberPK": "",
            "Year": YEAR,
        },
    )


def enrich_row(row):
    info_id = str(row["invite_company_info_id"])
    exb_id = row["exb_contract_id"]
    company_name = row["company_name_cn"] or ""

    contract = {}
    highlight = {}

    if exb_id:
        try:
            contract = fetch_contract(str(exb_id))
            time.sleep(DELAY_SEC)
        except Exception:
            contract = {}

    try:
        highlight = fetch_highlight(info_id)
        time.sleep(DELAY_SEC)
    except Exception:
        highlight = {}

    products = products_from_contract(contract) or products_from_highlight(highlight)
    website = (contract.get("WebSite") or highlight.get("Url") or "").strip()
    address = (contract.get("Address") or "").strip()
    profile = parse_json_field(highlight.get("ComProfile"))

    c_name, c_email, c_phone, c_info = build_contact(contract)
    country = normalize_country(
        contract.get("Country") or highlight.get("Country"),
        address,
        company_name,
        profile,
    )
    state = resolve_state_province(country, address, company_name, profile)

    hall = (contract.get("PavilionCode") or highlight.get("PavilionCode") or "").strip()
    booth = (contract.get("BoothNo") or highlight.get("BoothNo") or "").strip()
    booth_display = f"{hall} {booth}".strip() if hall or booth else ""

    return {
        "products_services": products or None,
        "website_url": website or None,
        "contact_name": c_name or None,
        "contact_email": c_email or None,
        "contact_phone": c_phone or None,
        "contact_info": c_info or None,
        "country": country or None,
        "state_province": state or None,
        "address": address or None,
        "company_profile": profile or None,
        "hall": hall or None,
        "booth": booth or None,
        "booth_display": booth_display or None,
    }


def main(limit=None, skip_enriched=False):
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    query = f"""
        SELECT id, company_name_cn, invite_company_info_id, exb_contract_id, enriched_at
        FROM {TABLE_NAME}
    """
    if skip_enriched:
        query += " WHERE enriched_at IS NULL"
    query += " ORDER BY id"
    if limit:
        query += f" LIMIT {int(limit)}"

    cur.execute(query)
    rows = cur.fetchall()
    total = len(rows)
    print(f"[*] Enriching {total} exhibitors...")

    update_sql = f"""
        UPDATE {TABLE_NAME} SET
            products_services = %(products_services)s,
            website_url = %(website_url)s,
            contact_name = %(contact_name)s,
            contact_email = %(contact_email)s,
            contact_phone = %(contact_phone)s,
            contact_info = %(contact_info)s,
            country = %(country)s,
            state_province = %(state_province)s,
            address = %(address)s,
            company_profile = %(company_profile)s,
            hall = %(hall)s,
            booth = %(booth)s,
            booth_display = %(booth_display)s,
            enriched_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %(id)s
    """

    ok = 0
    for i, (rid, name_cn, info_id, exb_id, _) in enumerate(rows, 1):
        try:
            data = enrich_row(
                {
                    "invite_company_info_id": info_id,
                    "exb_contract_id": exb_id,
                    "company_name_cn": name_cn,
                }
            )
            data["id"] = rid
            cur.execute(update_sql, data)
            ok += 1
        except Exception as e:
            print(f"[-] id={rid} {name_cn[:30]}... -> {e}")

        if i % BATCH_COMMIT == 0:
            conn.commit()
            print(f"    ... {i}/{total} processed ({ok} ok)")

    conn.commit()

    cur.execute(
        f"""
        SELECT
            COUNT(*) AS total,
            COUNT(products_services) AS with_products,
            COUNT(website_url) FILTER (WHERE website_url IS NOT NULL AND website_url <> '') AS with_website,
            COUNT(contact_email) FILTER (WHERE contact_email IS NOT NULL AND contact_email <> '') AS with_email,
            COUNT(country) AS with_country,
            COUNT(state_province) FILTER (WHERE state_province IS NOT NULL AND state_province <> '') AS with_state,
            COUNT(hall) FILTER (WHERE hall IS NOT NULL AND hall <> '') AS with_hall
        FROM {TABLE_NAME}
        """
    )
    stats = cur.fetchone()
    print("[+] Done. Stats:", stats)
    cur.close()
    conn.close()


if __name__ == "__main__":
    limit = None
    skip = "--skip-enriched" in sys.argv
    for arg in sys.argv[1:]:
        if arg.isdigit():
            limit = int(arg)
    main(limit=limit, skip_enriched=skip)
