import csv
import json
import time
import urllib.request

API = "https://pv.snec.org.cn/api/getInviteCompanyList"
HEADERS = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}
OUT = r"g:/SNEC-RESEARCH/exhibitors_list.csv"
LIMIT = 200


def fetch_page(page):
    body = {
        "page": page,
        "limit": LIMIT,
        "search": {"Year": "2026", "ExamineStateCode": "audited"},
    }
    req = urllib.request.Request(
        API,
        data=json.dumps(body).encode("utf-8"),
        headers=HEADERS,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_name(raw):
    try:
        obj = json.loads(raw)
        return obj.get("CN", ""), obj.get("EN", "")
    except (json.JSONDecodeError, TypeError):
        return str(raw or ""), ""


def main():
    first = fetch_page(1)
    total = first.get("total", 0)
    rows = []
    seen = set()

    def add_items(data):
        for item in data.get("listdata") or []:
            key = item.get("InviteCompanyInfoID") or item.get("InviteCompanyID")
            if key in seen:
                continue
            seen.add(key)
            cn, en = parse_name(item.get("CompanyName", ""))
            hall = item.get("PavilionCode", "") or ""
            booth = item.get("BoothNo", "") or ""
            booth_display = f"{hall} {booth}".strip() if hall or booth else ""
            rows.append(
                {
                    "company_name_cn": cn,
                    "company_name_en": en,
                    "hall": hall,
                    "booth": booth,
                    "booth_display": booth_display,
                    "invite_company_id": item.get("InviteCompanyID", ""),
                    "invite_company_info_id": item.get("InviteCompanyInfoID", ""),
                    "exb_contract_id": item.get("ExbContractID", ""),
                    "company_logo_url": item.get("CompanyLogo", ""),
                    "source": "pv.snec.org.cn/api/getInviteCompanyList",
                    "year": "2026",
                }
            )

    add_items(first)
    pages = (total + LIMIT - 1) // LIMIT
    print(f"Total exhibitors: {total}, pages: {pages}")

    for page in range(2, pages + 1):
        data = fetch_page(page)
        add_items(data)
        print(f"Page {page}/{pages} -> collected {len(rows)}")
        time.sleep(0.15)

    fieldnames = [
        "company_name_cn",
        "company_name_en",
        "hall",
        "booth",
        "booth_display",
        "invite_company_id",
        "invite_company_info_id",
        "exb_contract_id",
        "company_logo_url",
        "source",
        "year",
    ]
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    with_booth = sum(1 for r in rows if r["booth"] or r["hall"])
    print(f"Wrote {len(rows)} rows to {OUT}")
    print(f"Rows with hall/booth assigned: {with_booth}")


if __name__ == "__main__":
    main()
