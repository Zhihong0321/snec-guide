"""Export snec26_exhibitors to enriched CSV."""
import csv
import os
import psycopg2

DB_URL = os.environ.get("DATABASE_URL")
if not DB_URL:
    raise SystemExit("DATABASE_URL is required")
OUT = os.path.join(os.path.dirname(__file__), "exhibitors_enriched.csv")

FIELDS = [
    "company_name_cn",
    "company_name_en",
    "hall",
    "booth",
    "booth_display",
    "products_services",
    "website_url",
    "contact_name",
    "contact_email",
    "contact_phone",
    "contact_info",
    "country",
    "state_province",
    "address",
    "invite_company_info_id",
    "company_logo_url",
]

conn = psycopg2.connect(DB_URL)
cur = conn.cursor()
cur.execute(
    f"SELECT {', '.join(FIELDS)} FROM snec26_exhibitors ORDER BY company_name_cn"
)
with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(FIELDS)
    w.writerows(cur.fetchall())
cur.close()
conn.close()
print(f"[+] Exported {OUT}")
