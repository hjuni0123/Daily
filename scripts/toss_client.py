#!/usr/bin/env python3
"""
토스증권 Open API 클라이언트 (베스트에포트 초안 — 미검증).

주의:
- 이 스크립트는 공개 검색 결과만으로 작성됐다. 이 환경(조직 방화벽)에서는
  developers.tossinvest.com, openapi.tossinvest.com 모두 접속이 막혀 있어
  1차 문서를 직접 열람하거나 실제 호출을 테스트하지 못했다. 엔드포인트 경로,
  요청/응답 형식은 실제 문서 대비 다를 수 있다.
- 공식/비공식 여부도 확인 못했다. 사용 전 https://developers.tossinvest.com
  문서와 대조해서 검증할 것.
- API 키/시크릿은 절대 코드나 커밋에 하드코딩하지 않는다. .env 파일(gitignore
  대상)에 TOSS_API_KEY / TOSS_API_SECRET 로 저장하고 여기서는 환경변수로만 읽는다.

사용법 (검증 후):
    python3 scripts/toss_client.py --stock 005930
"""
import argparse
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
TOKEN_URL = "https://openapi.tossinvest.com/oauth2/token"  # 확인 필요
QUOTE_URL = "https://openapi.tossinvest.com/v1/market/price"  # 확인 필요

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
        auth=(client_id, client_secret),
        data={"grant_type": "client_credentials"},
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
        params={"stockCode": stock_code},
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
    except Exception as e:
        print(f"실패: {e}", file=sys.stderr)
        print(
            "이 환경에서 openapi.tossinvest.com 접속이 막혀 있을 수 있습니다. "
            "로컬 PC/사내 서버에서 실행해보세요.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(data)


if __name__ == "__main__":
    main()
