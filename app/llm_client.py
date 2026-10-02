"""Gemini HTTP 호출만 담당한다. API 키나 원본 오류는 로그에 남기지 않는다."""
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / '.env')


class LLMError(Exception):
    """외부로 전달해도 안전한 오류 코드만 보관한다."""


def generate_text(prompt: str) -> dict:
    key = os.getenv('GEMINI_API_KEY', '').strip()
    model = os.getenv('LLM_MODEL', '').strip() or 'gemini-3.8-flash'
    if not key:
        raise LLMError('missing_key')
    request = Request(
        'https://generativelanguage.googleapis.com/v1beta/interactions',
        data=json.dumps({'model': model, 'input': prompt}).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'x-goog-api-key': key},
        method='POST',
    )
    try:
        # 자동 재시도 없음. 20초는 소켓 대기 제한이며 전체 요청의 절대 제한은 아니다.
        with urlopen(request, timeout=20) as response:
            raw = response.read(262145)
        if len(raw) > 262144:
            raise LLMError('response_too_large')
        data = json.loads(raw)
        if data.get('status') != 'completed':
            raise LLMError('incomplete_response')
        text = '\n'.join(
            part['text']
            for step in data.get('steps', []) if step.get('type') == 'model_output'
            for part in step.get('content', [])
            if part.get('type') == 'text' and isinstance(part.get('text'), str)
        ).strip()
        if not text:
            raise LLMError('empty_response')
        # 토큰 수가 제공되지 않으면 0으로 꾸미지 않고 null로 둔다.
        usage = data.get('usage') or {}
        return {'text': text, 'model': model, 'usage': {
            name: usage.get(name) for name in
            ('total_input_tokens', 'total_output_tokens', 'total_tokens')
        }}
    except HTTPError as exc:
        raise LLMError(f'http_{exc.code}') from None
    except (TimeoutError, URLError, OSError):
        raise LLMError('network_or_timeout') from None
    except (ValueError, TypeError, AttributeError, KeyError):
        raise LLMError('invalid_response') from None
