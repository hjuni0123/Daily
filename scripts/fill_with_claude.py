#!/usr/bin/env python3
"""
fetch_toss.py(또는 fetch_pykrx.py)가 만든 데이터 JSON을 읽어서, Claude(웹서치
툴)로 "왜 이렇게 움직였는지"·이번 주 캘린더처럼 조사·판단이 필요한 필드만
뉴스 기반으로 채운다.

**숫자(지수 종가/등락률/환율/수급 금액)는 절대 건드리지 않는다** — 이미
거래소/토스 API에서 가져온 실제 값을 그대로 신뢰하고, Claude에게는 "왜"에
해당하는 서술형 필드만 맡긴다. sectors(업종 수치)도 Toss API가 지원하지 않아
채워져 있지 않으면 그대로 비워둔다 — Claude가 업종 등락률/비중 수치를 지어내지
않는다. 오늘자 캘린더 첫 칸(마감 요약)도 코드가 실제 등락률로 직접 조립하고,
Claude에게는 그 옆에 붙는 한 줄 요약만 맡긴다.

.env에 ANTHROPIC_API_KEY 필요 (https://console.anthropic.com 에서 발급).

사용법:
    python3 scripts/fill_with_claude.py data/2026-08-24.json
"""
import datetime
import json
import sys
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import toss_client  # noqa: E402 (재사용: .env 로더)

MODEL = "claude-opus-5"

DOW_EN = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]

SYSTEM_PROMPT = """당신은 한양증권 인천프리미어지점의 데일리 마켓 브리핑을 작성하는
애널리스트입니다. 사용자가 준 실제 시황 숫자(토스증권 Open API/거래소에서 가져온
값, 절대 사실이며 변경 대상이 아님)를 바탕으로, 오늘 "왜" 이렇게 움직였는지와
이번 주 남은 캘린더를 웹서치로 조사해서 채웁니다.

원칙:
- 절대 숫자를 지어내지 않습니다. 이미 주어진 숫자는 서술에 인용만 하고,
  "왜" 그런지 근거는 반드시 웹서치로 찾은 뉴스 기사·거래소 공식 자료를 근거로
  씁니다.
- 나무위키 등 사용자 편집 위키, 개인 블로그, 주가예측 사이트는 근거로 쓰지
  않습니다. 언론사 뉴스 기사·거래소 공식 자료만 사용하세요.
- 뉴스에서 확인 안 되면 구체적인 이유를 지어내지 말고, 알려진 사실 범위
  안에서만(예: "특별한 재료 없이 프로그램 매매 영향" 같은 일반적 설명) 짧게
  서술하세요.
- 짧고 단정한 문체. "~것으로 보인다", "~라고 판단된다" 같은 헤지 표현을 문장마다
  반복하지 않습니다. 사실을 먼저 던지고 근거를 붙이는 순서로 씁니다. 뻔한
  전환어("이는 ~를 시사한다", "한편") 남발 금지. 실제 데스크 노트처럼 씁니다.
- 각 필드는 1~2문장으로 압축합니다 (3문장 넘기지 않습니다).
"""


def build_user_prompt(data: dict) -> str:
    indicators_str = "\n".join(
        f"- {i['label']}: {i['close']} ({i['change_pct']})" for i in data["indicators"]
    )
    issue_stocks_str = "\n".join(
        f"- {s['name']}({s['ticker']}): {s['change_pct']}%" for s in data["issue_stocks"]
    )
    labels_str = ", ".join(f'"{i["label"]}"' for i in data["indicators"])
    return f"""오늘은 {data['date']} ({data['weekday']}) 입니다.

[오늘 지수/지표 — 실제 값, 서술에 인용만 하고 절대 변경하지 마세요]
{indicators_str}

[오늘 등락률 상위/하위 종목 — 실제 값, ticker로 매칭해서 이유만 채우세요]
{issue_stocks_str}

이 정보를 바탕으로 웹서치로 오늘자 한국 증시 마감 시황 뉴스, 위 종목들이 왜
움직였는지, 이번 주 남은 평일(내일부터 이번 주 금요일까지)의 주요 일정(경제지표
발표·실적 발표·연준 이벤트·한국은행 회의 등)을 조사해서 스키마에 맞게 채워주세요.

- issue_stocks의 ticker는 위에 준 종목코드와 정확히 일치해야 합니다.
- indicator_notes의 label은 다음과 정확히 일치해야 합니다: {labels_str}
- remaining_days는 내일부터 이번 주 금요일까지만(토요일·일요일 제외, 오늘은
  포함하지 마세요 — 오늘은 이미 코드가 채웁니다). date는 "25"처럼 일(day)만,
  dow는 MON/TUE/WED/THU/FRI 중 하나."""


OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "리포트 메인 제목, 한 문장, 임팩트 있게"},
        "subtitle": {"type": "string", "description": "제목을 보충하는 한 줄"},
        "today_note": {"type": "string", "description": "오늘 캘린더 칸에 들어갈 한 줄 요약 (예: 삼성그룹주 급락, 외국인 대량 순매도)"},
        "indicator_notes": {
            "type": "array",
            "description": "입력으로 준 지표 각각에 대해 왜 이렇게 움직였는지 한 줄",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "description": "입력으로 준 지표 label과 정확히 일치"},
                    "note": {"type": "string", "description": "왜 이렇게 움직였는지 한 줄"},
                },
                "required": ["label", "note"],
                "additionalProperties": False,
            },
        },
        "issue_stocks": {
            "type": "array",
            "description": "입력으로 준 이슈 종목 각각에 대해 하나씩",
            "items": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "입력으로 준 종목코드와 정확히 일치"},
                    "reason": {"type": "string", "description": "왜 움직였는지, 뉴스 근거 포함, 1~2문장"},
                    "persistence": {"type": "string", "enum": ["높음", "중립", "약세 지속"]},
                    "checkpoint": {"type": "string", "description": "다음에 뭘 언제 확인해야 하는지"},
                },
                "required": ["ticker", "reason", "persistence", "checkpoint"],
                "additionalProperties": False,
            },
        },
        "remaining_days": {
            "type": "array",
            "description": "내일부터 이번 주 금요일까지 (오늘 제외, 토·일 제외)",
            "items": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "일(day)만, 예: 25"},
                    "dow": {"type": "string", "enum": ["MON", "TUE", "WED", "THU", "FRI"]},
                    "events": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "time": {"type": "string", "description": "예: 09:00, 21:30, 새벽, 오전, 종일"},
                                "title": {"type": "string", "description": "이벤트명"},
                                "note": {"type": "string", "description": "왜 중요한지, 무엇을 확인해야 하는지 짧게"},
                                "importance": {"type": "integer", "enum": [0, 1, 2, 3], "description": "지수 방향을 바꿀 수 있는 정도. 0=보통, 3=매우 중요(★★★)"},
                            },
                            "required": ["time", "title", "note", "importance"],
                            "additionalProperties": False,
                        },
                    },
                    "footer": {"type": "string", "description": "그 날짜 칸 맨 아래 한 줄 요약 (없으면 빈 문자열)"},
                },
                "required": ["date", "dow", "events", "footer"],
                "additionalProperties": False,
            },
        },
        "next_week": {"type": "string", "description": "다음 주 예고 한 줄 (예: 9/1(화) 09:00 8월 수출입 잠정치 — ...)"},
    },
    "required": ["title", "subtitle", "today_note", "indicator_notes", "issue_stocks", "remaining_days", "next_week"],
    "additionalProperties": False,
}


def _request(client: anthropic.Anthropic, messages: list):
    return client.messages.create(
        model=MODEL,
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        thinking={"type": "adaptive"},
        output_config={
            "effort": "high",
            "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
        },
        tools=[{
            "type": "web_search_20260209",
            "name": "web_search",
            "max_uses": 12,
        }],
        messages=messages,
    )


def fill(data: dict) -> dict:
    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": build_user_prompt(data)}]
    response = _request(client, messages)

    # 서버 툴(웹서치) 라운드가 길어지면 pause_turn으로 끊길 수 있어 이어서 진행한다.
    attempts = 0
    while response.stop_reason == "pause_turn" and attempts < 5:
        messages.append({"role": "assistant", "content": response.content})
        response = _request(client, messages)
        attempts += 1

    if response.stop_reason == "refusal":
        raise RuntimeError(f"Claude가 응답을 거부했습니다: {response.stop_details}")

    text = next((b.text for b in response.content if b.type == "text"), None)
    if not text:
        raise RuntimeError(f"텍스트 응답을 찾지 못했습니다. stop_reason={response.stop_reason}")
    return json.loads(text)


def _today_calendar_day(data: dict, today_note: str) -> dict:
    """오늘 캘린더 칸은 코드가 실제 등락률로 직접 조립한다 (숫자 재타이핑에 의한
    오차/환각 위험을 없앤다)."""
    by_label = {i["label"]: i for i in data["indicators"]}
    kospi = by_label.get("KOSPI", {})
    kosdaq = by_label.get("KOSDAQ", {})
    d = datetime.date.fromisoformat(data["date"])
    return {
        "date": str(d.day),
        "dow": DOW_EN[d.weekday()],
        "events": [{
            "time": "마감",
            "title": f"코스피 {kospi.get('change_pct', '-')} / 코스닥 {kosdaq.get('change_pct', '-')}",
            "note": today_note,
            "importance": 0,
        }],
        "footer": "오늘 자료 기준일",
    }


def merge(data: dict, filled: dict) -> dict:
    data["title"] = filled["title"]
    data["subtitle"] = filled["subtitle"]

    notes_by_label = {n["label"]: n["note"] for n in filled["indicator_notes"]}
    for ind in data["indicators"]:
        if ind["label"] in notes_by_label:
            ind["note"] = notes_by_label[ind["label"]]

    filled_by_ticker = {s["ticker"]: s for s in filled["issue_stocks"]}
    for stock in data["issue_stocks"]:
        f = filled_by_ticker.get(stock["ticker"])
        if f:
            stock["reason"] = f["reason"]
            stock["persistence"] = f["persistence"]
            stock["checkpoint"] = f["checkpoint"]
        else:
            print(f"경고: {stock['ticker']}({stock['name']}) 에 대한 응답을 못 찾음 — TODO로 남김", file=sys.stderr)

    today_day = _today_calendar_day(data, filled["today_note"])
    days = [today_day]
    for d in filled["remaining_days"]:
        events = [dict(e, stars="") for e in d.get("events", [])]
        days.append({"date": d["date"], "dow": d["dow"], "events": events, "footer": d.get("footer", "")})
    data["calendar"] = {"days": days, "next_week": filled["next_week"]}

    return data


def main():
    if len(sys.argv) != 2:
        print("사용법: python3 scripts/fill_with_claude.py data/2026-08-24.json", file=sys.stderr)
        sys.exit(1)

    path = Path(sys.argv[1])
    toss_client._load_env_file(ROOT / ".env")

    if not __import__("os").environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY가 .env에 없습니다. https://console.anthropic.com 에서 발급해 "
              ".env에 ANTHROPIC_API_KEY=... 로 추가하세요.", file=sys.stderr)
        sys.exit(1)

    data = json.loads(path.read_text(encoding="utf-8"))
    print("Claude로 뉴스 조사 및 정성적 필드 작성 중... (웹서치 여러 번 돌 수 있어 1~2분 걸릴 수 있음)", file=sys.stderr)
    filled = fill(data)
    data = merge(data, filled)

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"채움 완료: {path}")


if __name__ == "__main__":
    main()
