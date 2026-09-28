import json
from pathlib import Path

from app.database import get_connection


def main():
    root = Path(__file__).resolve().parent.parent
    schema = (root / "sql" / "create_faqs.sql").read_text(encoding="utf-8")
    faqs = json.loads((root / "data" / "faqs.json").read_text(encoding="utf-8"))
    ids = [faq["faq_id"] for faq in faqs]
    if len(ids) != len(set(ids)):
        raise ValueError("FAQ 초기 데이터에 중복 ID가 있습니다.")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(schema)
            # 이미 있는 ID는 보존한다. 반복 실행해도 기존 답변을 덮어쓰지 않는다.
            cursor.execute("SELECT faq_id FROM faqs")
            existing = {row["faq_id"] for row in cursor.fetchall()}
            added = 0
            for faq in faqs:
                if faq["faq_id"] in existing:
                    continue
                cursor.execute(
                    """INSERT INTO faqs
                    (faq_id, category, question, answer, keywords)
                    VALUES (%s, %s, %s, %s, %s)""",
                    tuple(faq[key] for key in (
                        "faq_id", "category", "question", "answer", "keywords"
                    )),
                )
                added += 1
        connection.commit()
    print(f"FAQ initialization complete: added={added}, skipped={len(faqs) - added}")


if __name__ == "__main__":
    main()
