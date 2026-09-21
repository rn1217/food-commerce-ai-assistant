import os
from pathlib import Path

import pymysql
from dotenv import load_dotenv


# 이 파일(app/database.py)의 위치를 기준으로 프로젝트 최상위 폴더를 찾는다.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


# 호출할 때마다 새 DB 연결을 만든다. 호출한 쪽에서 with로 연결을 정리한다.
def get_connection():
    return pymysql.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ["DB_PORT"]),  # 환경변수의 문자열을 정수로 변환
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],  # 비밀번호는 코드에 직접 적지 않는다.
        database=os.environ["DB_NAME"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,  # 각 행을 컬럼명: 값 딕셔너리로 반환
        # 단위는 초. 연결/읽기/쓰기 대기를 제한하며 전체 요청 시간 제한은 아니다.
        connect_timeout=5,
        read_timeout=10,
        write_timeout=10,
    )