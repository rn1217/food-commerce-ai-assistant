from pathlib import Path

from app.database import get_connection


def main():
    root = Path(__file__).resolve().parent.parent
    sql = (root / "sql" / "create_ai_logs.sql").read_text(encoding="utf-8")
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql)
    print("ai_logs table is ready (existing rows preserved).")


if __name__ == "__main__":
    main()
