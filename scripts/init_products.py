"""CSV 전체를 검증한 후 새 상품만 저장한다. python -m scripts.init_products"""
import argparse
from pathlib import Path

import pandas as pd

from app.database import get_connection

ROOT = Path(__file__).resolve().parent.parent
COLUMNS = ['product_id', 'name', 'category', 'price', 'description', 'sweetness',
           'packaging', 'storage_method', 'gift_available', 'is_active']


def load_products(path):
    # 문자열로 읽어 빈 값, 소수, 잘못된 숫자를 변환 전에 검사한다.
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding='utf-8-sig')
    if list(frame.columns) != COLUMNS or frame.empty:
        raise ValueError('CSV 열 이름/순서가 다르거나 상품이 없습니다.')
    for column in COLUMNS:
        frame[column] = frame[column].str.strip()
        if frame[column].eq('').any():
            raise ValueError(f'{column}: 빈 값이 있습니다.')
    limits = {'product_id': (1, 2147483647), 'price': (1, 100000000),
              'sweetness': (1, 5), 'gift_available': (0, 1), 'is_active': (0, 1)}
    for column, (low, high) in limits.items():
        if not frame[column].str.fullmatch(r'[0-9]{1,10}').all():
            raise ValueError(f'{column}: 정수만 입력하세요.')
        frame[column] = pd.to_numeric(frame[column])
        if not frame[column].between(low, high).all():
            raise ValueError(f'{column}: 허용 범위는 {low}~{high}입니다.')
    if frame['product_id'].duplicated().any():
        raise ValueError('중복 product_id가 있습니다.')
    for column, allowed in {'packaging': {'individual', 'bulk'},
                            'storage_method': {'room', 'refrigerated', 'frozen'}}.items():
        if not frame[column].isin(allowed).all():
            raise ValueError(f'{column}: 지원하지 않는 값입니다.')
    for column, limit in {'name': 150, 'category': 50, 'description': 1000}.items():
        if frame[column].str.len().gt(limit).any():
            raise ValueError(f'{column}: 최대 {limit}자입니다.')
    return frame


def insert_products(frame):
    records = frame.to_dict(orient='records')
    # 열 이름은 개발자가 고정하고, CSV 값은 모두 %s로 바인딩한다.
    with get_connection() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT ' + ', '.join(COLUMNS) + ' FROM products')
                existing = {row['product_id']: row for row in cursor.fetchall()}
                pending = []
                for row in records:
                    previous = existing.get(row['product_id'])
                    if previous is not None:
                        if any(previous[k] != row[k] for k in COLUMNS):
                            raise ValueError(f"기존 상품 ID {row['product_id']}의 내용이 다릅니다. 저장을 취소합니다.")
                    else:
                        pending.append(tuple(row[k] for k in COLUMNS))
                if pending:
                    cursor.executemany(
                        'INSERT INTO products (' + ', '.join(COLUMNS) + ') VALUES ('
                        + ', '.join(['%s'] * len(COLUMNS)) + ')', pending)
            connection.commit()
        except Exception:
            # 일부만 저장되는 상황을 피하기 위해 전체 추가 작업을 취소한다.
            connection.rollback()
            raise
    return {'added': len(pending), 'skipped': len(records) - len(pending)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv', type=Path, default=ROOT / 'data' / 'products.csv')
    parser.add_argument('--check-only', action='store_true', help='CSV만 검사하고 DB에 저장하지 않음')
    args = parser.parse_args()
    frame = load_products(args.csv)
    print(f"CSV valid: rows={len(frame)}, price={frame.price.min()}~{frame.price.max()}")
    print('Packaging:', frame.packaging.value_counts().to_dict())
    if not args.check_only:
        print('Product initialization:', insert_products(frame))


if __name__ == '__main__':
    main()
