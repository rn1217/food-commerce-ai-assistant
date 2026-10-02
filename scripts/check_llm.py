"""Run one Gemini connection check. Never print the API key or raw errors."""
import json
import logging
import os
from pathlib import Path
import socket
from time import perf_counter
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main():
    # 실행 위치에 관계없이 프로젝트 최상위 .env를 읽는다.
    load_dotenv(PROJECT_ROOT / '.env')
    key = os.getenv('GEMINI_API_KEY', '').strip()
    model = os.getenv('LLM_MODEL', '').strip() or 'gemini-3.8-flash'
    if not key:
        logger.error('GEMINI_API_KEY가 없습니다. 프로젝트 .env를 저장했는지 확인하세요.')
        return 1

    # 질문을 JSON으로 변환한다. DB 데이터나 사용자 정보는 전송하지 않는다.
    payload = {'model': model, 'input': '한국어로 연결 테스트 성공이라고 짧게 답해줘.'}
    request = Request(
        'https://generativelanguage.googleapis.com/v1beta/interactions',
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'x-goog-api-key': key},
        method='POST',
    )
    started = perf_counter()
    try:
        # 자동 재시도 없이 한 번만 호출하며, 네트워크 대기 제한을 둔다.
        with urlopen(request, timeout=30) as response:
            data = json.load(response)
        # REST 응답의 model_output 단계에서 실제 답변 텍스트만 추출한다.
        answer = '\n'.join(
            part['text']
            for step in data.get('steps', []) if step.get('type') == 'model_output'
            for part in step.get('content', [])
            if part.get('type') == 'text' and isinstance(part.get('text'), str)
        ).strip()
        if data.get('status') != 'completed' or not answer:
            logger.error('API 응답은 받았지만 완료된 텍스트 답변이 없습니다.')
            return 1
        print('연결 성공')
        print('모델:', model)
        print('답변:', answer)
        print(f'응답 시간: {perf_counter() - started:.2f}초')
        return 0
    except HTTPError as exc:
        hints = {
            400: '요청 형식, 모델 설정 또는 키가 유효한지 확인하세요.',
            401: '키 인증을 확인하세요.',
            403: '키의 권한 및 API 이용 가능 여부를 확인하세요.',
            404: '모델 이름과 API 지원 여부를 확인하세요.',
            429: '무료 할당량 또는 호출 제한을 확인하세요. 유료 전환은 필요하지 않습니다.',
        }
        logger.error('Gemini HTTP %s: %s', exc.code, hints.get(exc.code, '서비스 상태를 확인하고 나중에 다시 실행하세요.'))
        return 1
    except (URLError, TimeoutError, socket.timeout):
        logger.error('네트워크 연결 또는 대기 시간 오류입니다. 인터넷 연결을 확인하세요.')
        return 1
    except (ValueError, TypeError, AttributeError, KeyError):
        logger.error('예상한 JSON 응답 구조가 아닙니다. API 응답 형식을 확인해야 합니다.')
        return 1


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    raise SystemExit(main())
