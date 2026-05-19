import csv
import os
import sys
import psycopg2
from psycopg2.extras import execute_batch

DB_URL = os.environ.get("DATABASE_URL")
if not DB_URL:
    raise SystemExit("DATABASE_URL is required")
TABLE_NAME = "snec26_exhibitors"
CSV_PATH = os.path.join(os.path.dirname(__file__), "exhibitors_list.csv")


def empty_to_none(value):
    if value is None:
        return None
    value = str(value).strip()
    return value if value else None


def load_csv_rows():
    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(f"{CSV_PATH} not found")

    rows = []
    with open(CSV_PATH, mode="r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            info_id = empty_to_none(row.get("invite_company_info_id"))
            if not info_id:
                continue
            rows.append(
                (
                    empty_to_none(row.get("company_name_cn")) or "Unknown",
                    empty_to_none(row.get("company_name_en")),
                    empty_to_none(row.get("hall")),
                    empty_to_none(row.get("booth")),
                    empty_to_none(row.get("booth_display")),
                    empty_to_none(row.get("invite_company_id")),
                    info_id,
                    empty_to_none(row.get("exb_contract_id")),
                    empty_to_none(row.get("company_logo_url")),
                    empty_to_none(row.get("source")),
                    empty_to_none(row.get("year")) or "2026",
                )
            )
    return rows


def sync_data():
    rows = load_csv_rows()
    print(f"[+] Loaded {len(rows)} rows from {CSV_PATH}")

    conn = psycopg2.connect(DB_URL)
    cursor = conn.cursor()

    cursor.execute(f"TRUNCATE TABLE {TABLE_NAME} RESTART IDENTITY;")
    print(f"[+] Truncated '{TABLE_NAME}'.")

    insert_query = f"""
        INSERT INTO {TABLE_NAME} (
            company_name_cn,
            company_name_en,
            hall,
            booth,
            booth_display,
            invite_company_id,
            invite_company_info_id,
            exb_contract_id,
            company_logo_url,
            source,
            year
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
    """

    execute_batch(cursor, insert_query, rows, page_size=500)
    conn.commit()

    cursor.execute(f"SELECT COUNT(*) FROM {TABLE_NAME};")
    count = cursor.fetchone()[0]
    print(f"[+] Inserted {count} rows into '{TABLE_NAME}'.")

    cursor.execute(
        f"""
        SELECT COUNT(*) FROM {TABLE_NAME}
        WHERE hall IS NOT NULL AND hall <> '';
        """
    )
    with_hall = cursor.fetchone()[0]
    print(f"[+] Rows with hall assigned: {with_hall}")

    cursor.close()
    conn.close()
    return count


if __name__ == "__main__":
    try:
        sync_data()
    except Exception as e:
        print(f"[-] Sync failed: {e}")
        sys.exit(1)
