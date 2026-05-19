import os
import sys

import psycopg2

DB_URL = os.environ.get("DATABASE_URL")
if not DB_URL:
    raise SystemExit("DATABASE_URL is required")
TABLE_NAME = "snec26_exhibitors"

BASE_COLUMNS = """
    id SERIAL PRIMARY KEY,
    company_name_cn VARCHAR(500) NOT NULL,
    company_name_en VARCHAR(500),
    hall VARCHAR(50),
    booth VARCHAR(100),
    booth_display VARCHAR(150),
    invite_company_id UUID,
    invite_company_info_id UUID,
    exb_contract_id UUID,
    company_logo_url TEXT,
    source VARCHAR(255),
    year VARCHAR(10) DEFAULT '2026',
    products_services TEXT,
    website_url VARCHAR(500),
    contact_name VARCHAR(255),
    contact_email VARCHAR(255),
    contact_phone VARCHAR(255),
    contact_info TEXT,
    country VARCHAR(100),
    state_province VARCHAR(100),
    address TEXT,
    company_profile TEXT,
    enriched_at TIMESTAMP,
    enrichment_status VARCHAR(100) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
"""

EXHIBITOR_INDEXES = """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_snec26_exhibitors_invite_info_id
        ON snec26_exhibitors (invite_company_info_id)
        WHERE invite_company_info_id IS NOT NULL;
    CREATE INDEX IF NOT EXISTS idx_snec26_exhibitors_company_cn
        ON snec26_exhibitors (company_name_cn);
    CREATE INDEX IF NOT EXISTS idx_snec26_exhibitors_hall_booth
        ON snec26_exhibitors (hall, booth);
    CREATE INDEX IF NOT EXISTS idx_snec26_exhibitors_country_state
        ON snec26_exhibitors (country, state_province);
    CREATE INDEX IF NOT EXISTS idx_snec26_exhibitors_enrichment_status
        ON snec26_exhibitors (enrichment_status);
"""

# Anonymous browser users (cookie = UUID)
WEB_USERS_TABLE = "snec26_web_users"
WEB_USERS_DDL = f"""
    CREATE TABLE IF NOT EXISTS {WEB_USERS_TABLE} (
        id UUID PRIMARY KEY,
        display_name VARCHAR(100) NOT NULL DEFAULT '',
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_snec26_web_users_updated
        ON {WEB_USERS_TABLE} (updated_at DESC);
"""

# Per-exhibitor photo gallery (list of images)
IMAGES_TABLE = "snec26_exhibitor_images"
IMAGES_DDL = f"""
    CREATE TABLE IF NOT EXISTS {IMAGES_TABLE} (
        id SERIAL PRIMARY KEY,
        exhibitor_id INTEGER NOT NULL
            REFERENCES snec26_exhibitors(id) ON DELETE CASCADE,
        image_path TEXT NOT NULL,
        image_url TEXT,
        caption TEXT,
        sort_order INTEGER NOT NULL DEFAULT 0,
        captured_at TIMESTAMP,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_snec26_images_exhibitor
        ON {IMAGES_TABLE} (exhibitor_id, sort_order, created_at);
"""

# Per-exhibitor notes (list of notes; each row = one note entry)
NOTES_TABLE = "snec26_notes"
NOTES_DDL = f"""
    CREATE TABLE IF NOT EXISTS {NOTES_TABLE} (
        id SERIAL PRIMARY KEY,
        exhibitor_id INTEGER NOT NULL
            REFERENCES snec26_exhibitors(id) ON DELETE CASCADE,
        author_name VARCHAR(255) NOT NULL,
        note_detail TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_snec26_notes_exhibitor
        ON {NOTES_TABLE} (exhibitor_id, created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_snec26_notes_author
        ON {NOTES_TABLE} (author_name);
"""


def setup_database():
    print("[*] Connecting to PostgreSQL...")
    try:
        conn = psycopg2.connect(DB_URL)
        cursor = conn.cursor()

        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                {BASE_COLUMNS}
            );
            """
        )

        cursor.execute(
            f"""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = %s;
            """,
            (TABLE_NAME,),
        )
        existing = {row[0] for row in cursor.fetchall()}
        migrations = {
            "products_services": "TEXT",
            "website_url": "VARCHAR(500)",
            "contact_name": "VARCHAR(255)",
            "contact_email": "VARCHAR(255)",
            "contact_phone": "VARCHAR(255)",
            "contact_info": "TEXT",
            "country": "VARCHAR(100)",
            "state_province": "VARCHAR(100)",
            "address": "TEXT",
            "company_profile": "TEXT",
            "enriched_at": "TIMESTAMP",
            "enrichment_status": "VARCHAR(100) NOT NULL DEFAULT 'pending'",
        }
        for col, col_type in migrations.items():
            if col not in existing:
                cursor.execute(
                    f"ALTER TABLE {TABLE_NAME} ADD COLUMN {col} {col_type};"
                )
                print(f"[+] Added column {col}")

        if "enrichment_status" in existing or "enrichment_status" in migrations:
            cursor.execute(
                f"""
                UPDATE {TABLE_NAME}
                SET enrichment_status = 'pending'
                WHERE enrichment_status IS NULL OR TRIM(enrichment_status) = '';
                """
            )

        cursor.execute(EXHIBITOR_INDEXES)
        cursor.execute(WEB_USERS_DDL)
        cursor.execute(IMAGES_DDL)
        cursor.execute(NOTES_DDL)

        for tbl, col, ddl in (
            (IMAGES_TABLE, "web_user_id", "UUID REFERENCES snec26_web_users(id) ON DELETE SET NULL"),
            (NOTES_TABLE, "web_user_id", "UUID REFERENCES snec26_web_users(id) ON DELETE SET NULL"),
        ):
            cursor.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_name = %s AND column_name = %s
                """,
                (tbl, col),
            )
            if not cursor.fetchone():
                cursor.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {ddl};")
                print(f"[+] Added {tbl}.{col}")

        conn.commit()
        print(f"[+] Table '{TABLE_NAME}' ready.")
        print(f"[+] Table '{WEB_USERS_TABLE}' ready (cookie-based visitors).")
        print(f"[+] Table '{IMAGES_TABLE}' ready (gallery list per exhibitor).")
        print(f"[+] Table '{NOTES_TABLE}' ready (notes list per exhibitor).")
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"[-] Error: {e}")
        return False


if __name__ == "__main__":
    if not setup_database():
        sys.exit(1)
