"""
Visit log helpers: per-exhibitor image gallery + notes lists.

Usage:
  python db_visit.py add-image --exhibitor-id 123 --path "photos/booth.jpg" --caption "Main booth"
  python db_visit.py add-note --exhibitor-id 123 --author "Alex" --detail "Strong TOPCon line"
  python db_visit.py show --exhibitor-id 123
  python db_visit.py find --name "隆基"
"""
import argparse
import os
import sys
from datetime import datetime

import psycopg2
from psycopg2.extras import RealDictCursor

DB_URL = os.environ.get("DATABASE_URL")
if not DB_URL:
    raise SystemExit("DATABASE_URL is required")


def connect():
    return psycopg2.connect(DB_URL)


def find_exhibitor_by_name(name_part):
    with connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, company_name_cn, hall, booth, booth_display
                FROM snec26_exhibitors
                WHERE company_name_cn ILIKE %s OR company_name_en ILIKE %s
                ORDER BY company_name_cn
                LIMIT 20
                """,
                (f"%{name_part}%", f"%{name_part}%"),
            )
            return cur.fetchall()


def get_visit_bundle(exhibitor_id):
    with connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, company_name_cn, company_name_en, hall, booth, booth_display,
                       products_services, country, state_province
                FROM snec26_exhibitors WHERE id = %s
                """,
                (exhibitor_id,),
            )
            exhibitor = cur.fetchone()
            if not exhibitor:
                return None

            cur.execute(
                """
                SELECT id, image_path, image_url, caption, sort_order, captured_at, created_at
                FROM snec26_exhibitor_images
                WHERE exhibitor_id = %s
                ORDER BY sort_order, captured_at NULLS LAST, created_at
                """,
                (exhibitor_id,),
            )
            images = cur.fetchall()

            cur.execute(
                """
                SELECT id, author_name, note_detail, created_at, updated_at
                FROM snec26_notes
                WHERE exhibitor_id = %s
                ORDER BY created_at DESC
                """,
                (exhibitor_id,),
            )
            notes = cur.fetchall()

    return {"exhibitor": exhibitor, "images": images, "notes": notes}


def add_image(exhibitor_id, image_path, caption=None, image_url=None, captured_at=None, sort_order=0):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO snec26_exhibitor_images (
                    exhibitor_id, image_path, image_url, caption, sort_order, captured_at
                ) VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (exhibitor_id, image_path, image_url, caption, sort_order, captured_at),
            )
            image_id = cur.fetchone()[0]
        conn.commit()
    return image_id


def add_note(exhibitor_id, author_name, note_detail):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO snec26_notes (exhibitor_id, author_name, note_detail)
                VALUES (%s, %s, %s)
                RETURNING id, created_at
                """,
                (exhibitor_id, author_name, note_detail),
            )
            row = cur.fetchone()
        conn.commit()
    return row


def print_bundle(bundle):
    ex = bundle["exhibitor"]
    print(f"\n=== {ex['company_name_cn']} (id={ex['id']}) ===")
    if ex.get("booth_display") or ex.get("hall"):
        print(f"Booth: {ex.get('booth_display') or ex.get('hall')}")
    if ex.get("products_services"):
        print(f"Products: {ex['products_services'][:200]}...")

    print(f"\n--- Image gallery ({len(bundle['images'])}) ---")
    if not bundle["images"]:
        print("  (empty)")
    for img in bundle["images"]:
        when = img["captured_at"] or img["created_at"]
        cap = f" | {img['caption']}" if img["caption"] else ""
        print(f"  [{img['id']}] {img['image_path']}{cap}  ({when})")

    print(f"\n--- Notes ({len(bundle['notes'])}) ---")
    if not bundle["notes"]:
        print("  (empty)")
    for note in bundle["notes"]:
        print(f"  [{note['id']}] {note['created_at']} | {note['author_name']}")
        print(f"       {note['note_detail']}")


def main():
    parser = argparse.ArgumentParser(description="SNEC visit log: images + notes per exhibitor")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_find = sub.add_parser("find", help="Search exhibitor by name")
    p_find.add_argument("--name", required=True)

    p_show = sub.add_parser("show", help="Show gallery + notes for one exhibitor")
    p_show.add_argument("--exhibitor-id", type=int, required=True)

    p_img = sub.add_parser("add-image", help="Add photo to exhibitor gallery")
    p_img.add_argument("--exhibitor-id", type=int, required=True)
    p_img.add_argument("--path", required=True, help="Local file path of the photo")
    p_img.add_argument("--url", help="Optional public URL if uploaded")
    p_img.add_argument("--caption")
    p_img.add_argument("--sort-order", type=int, default=0)

    p_note = sub.add_parser("add-note", help="Add a note for an exhibitor")
    p_note.add_argument("--exhibitor-id", type=int, required=True)
    p_note.add_argument("--author", required=True, help="Who wrote this note")
    p_note.add_argument("--detail", required=True, help="Note content")

    args = parser.parse_args()

    if args.cmd == "find":
        rows = find_exhibitor_by_name(args.name)
        for r in rows:
            booth = r["booth_display"] or r["hall"] or "-"
            print(f"id={r['id']:4}  {booth:12}  {r['company_name_cn']}")
        return

    if args.cmd == "show":
        bundle = get_visit_bundle(args.exhibitor_id)
        if not bundle:
            print("Exhibitor not found.")
            sys.exit(1)
        print_bundle(bundle)
        return

    if args.cmd == "add-image":
        captured = datetime.now()
        image_id = add_image(
            args.exhibitor_id,
            args.path,
            caption=args.caption,
            image_url=args.url,
            captured_at=captured,
            sort_order=args.sort_order,
        )
        print(f"[+] Image #{image_id} added (captured {captured})")
        return

    if args.cmd == "add-note":
        note_id, created_at = add_note(args.exhibitor_id, args.author, args.detail)
        print(f"[+] Note #{note_id} added at {created_at}")


if __name__ == "__main__":
    main()
