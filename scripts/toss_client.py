#!/usr/bin/env python3
"""
토스증권 Open API 클라이언트.

공식 문서(WTS 설정 > Open API > 가이드, /llms.txt)로 검증 완료:
- 토큰 발급은 HTTP Basic Auth가 아니라 client_id/client_secret을
  application/x-www-form-urlencoded 바디 파라미터로 보낸다.
- 시세 조회는 GET /api/v1/prices?symbols={code}.
- 계좌·자산/주문/조건주문 카테고리는 X-Tossinvest-Account 헤더가 추가로 필요하다
  (이 스크립트는 시세 조회만 다룬다 — 계좌 연동은 범위 밖).
- 허용 IP 목록에 없는 IP에서 호출하면 403 (WTS 설정 > Open API > 허용 IP 관리
  에서 등록).

API 키/시크릿은 절대 코드나 커밋에 하드코딩하지 않는다. .env 파일(gitignore
대상)에 TOSS_API_KEY / TOSS_API_SECRET 로 저장하고 여기서는 환경변수로만 읽는다.

사용법:
    python3 scripts/toss_client.py --stock 005930
"""
import argparse
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
TOKEN_URL = "https://openapi.tossinvest.com/oauth2/token"
QUOTE_URL = "https://openapi.tossinvest.com/api/v1/prices"

_token_cache = {"access_token": None, "expires_at": 0}


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def get_access_token() -> str:
    if _token_cache["access_token"] and time.time() < _token_cache["expires_at"]:
        return _token_cache["access_token"]

    client_id = os.environ.get("TOSS_API_KEY")
    client_secret = os.environ.get("TOSS_API_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError(
            "TOSS_API_KEY / TOSS_API_SECRET 환경변수가 없습니다. "
            ".env 파일을 만들거나 (.env.example 참고) 셸에서 export 하세요."
        )

    resp = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=10,
    )
    resp.raise_for_status()
    payload = resp.json()

    _token_cache["access_token"] = payload["access_token"]
    _token_cache["expires_at"] = time.time() + payload.get("expires_in", 3000) - 60
    return _token_cache["access_token"]


def get_price(stock_code: str) -> dict:
    token = get_access_token()
    resp = requests.get(
        QUOTE_URL,
        params={"symbols": stock_code},
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def main():
    _load_env_file(ROOT / ".env")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock", required=True, help="종목코드 (예: 005930)")
    args = parser.parse_args()

    try:
        data = get_price(args.stock)
    except requests.exceptions.HTTPError as e:
        body = e.response.text if e.response is not None else ""
        print(f"실패: {e}\n응답 본문: {body}", file=sys.stderr)
        print(
            "403이면 WTS 설정 > Open API > 허용 IP 관리에 현재 공인 IP가 "
            "등록되어 있는지 확인하세요 (curl -s https://api.ipify.org).",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as e:
        print(f"실패: {e}", file=sys.stderr)
        sys.exit(1)

    print(data)


if __name__ == "__main__":
    main()
