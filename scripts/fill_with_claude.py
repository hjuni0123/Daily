#!/usr/bin/env python3
"""
fetch_toss.py(또는 fetch_pykrx.py)가 만든 데이터 JSON을 읽어서, Claude(웹서치
툴)로 "왜 이렇게 움직였는지"·업종 동향·이번 주 일정·금일 체크포인트처럼 조사와
판단이 필요한 필드를 뉴스/공식 자료 기반으로 채운다.

**이미 실제 값이 있는 숫자(KOSPI/KOSDAQ/원달러 환율의 시가·장중고점·종가 등,
토스 API에서 가져온 값)는 절대 건드리지 않는다** — merge()가 원본 close가
"-"인 지표만 Claude 응답으로 덮어써서 코드 차원에서 보장한다. "-"로 남아있던
값(WTI 원유·필라델피아 반도체가 EXPERIMENTAL 조회에 실패한 경우)과
sectors(업종 방향성·비중)는 Claude가 웹서치로 찾은 실제 공개 정보로 채우되,
못 찾으면 지어내지 않고 "-"/빈 배열로 남긴다.

.env에 ANTHROPIC_API_KEY 필요 (https://console.anthropic.com 에서 발급).

사용법:
    python3 scripts/fill_with_claude.py data/2026-08-26.json
"""
import json
import sys
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import toss_client  # noqa: E402 (재사용: .env 로더)

MODEL = "claude-opus-5"

SYSTEM_PROMPT = """당신은 한양증권 인천프리미어지점의 데일리 마켓 브리핑(Daily
Market Close)을 작성하는 애널리스트입니다. 사용자가 준 실제 시황 숫자(토스증권
Open API/거래소에서 가져온 값, 절대 사실이며 변경 대상이 아님)를 바탕으로, 오늘
"왜" 이렇게 움직였는지, 업종 동향, 이번 주 일정, 금일 체크포인트(섹터별 관심
종목·오늘의 관점·근거)를 웹서치로 조사해서 채웁니다.

원칙:
- 절대 숫자를 지어내지 않습니다(hallucination 금지). 이미 실제 값이 채워진
  지표(예: KOSPI/KOSDAQ/원달러 환율)는 서술에 인용만 하고 절대 변경하지
  않습니다 — indicator_updates에도 입력값 그대로 반복해서 돌려주면 됩니다.
- "-"로 비어있는 지표(WTI 원유·필라델피아 반도체 등)는 웹서치로 실제 종가/
  등락 수치를 찾아 채웁니다. 신뢰할 수 있는 출처(언론사 시황 기사, 거래소/
  공식 지표 제공처)에서 확인된 값만 씁니다. 확인이 안 되면 추정치를 지어내지
  말고 "-"를 그대로 둡니다.
- sectors(업종 동향)도 마찬가지입니다 — 언론 마감 시황 기사의 업종별 등락
  보도, 거래소 업종지수 자료 등 실제 공개된 정보만 씁니다. 정확한 등락률을
  못 구하면 "강보합"/"+1%대"/"약보합"처럼 방향성 버킷으로 표현해도 됩니다
  (지어낸 정밀 수치보다 방향성만 정확한 버킷이 낫습니다). 확인 안 되는 업종은
  통째로 빼세요.
- checkpoints(금일 체크포인트)와 calendar(이번 주 일정)에 인용하는 개별
  종목명·등락률·이벤트 일시도 전부 웹서치로 확인한 실제 정보만 씁니다.
- 나무위키 등 사용자 편집 위키, 개인 블로그, 주가예측 사이트는 근거로 쓰지
  않습니다. 언론사 뉴스 기사·거래소 공식 자료만 사용하세요.
- 뉴스에서 확인 안 되면 구체적인 이유를 지어내지 말고, 알려진 사실 범위
  안에서만(예: "특별한 재료 없이 프로그램 매매 영향" 같은 일반적 설명) 짧게
  서술하세요.
- 짧고 단정한 문체. "~것으로 보인다", "~라고 판단된다" 같은 헤지 표현을 문장마다
  반복하지 않습니다. 사실을 먼저 던지고 근거를 붙이는 순서로 씁니다. 뻔한
  전환어("이는 ~를 시사한다", "한편") 남발 금지. 실제 데스크 노트처럼 씁니다.
- 각 필드는 1~3문장으로 압축합니다.
"""


def build_user_prompt(data: dict) -> str:
    indicators_str = "\n".join(
        f"- {i['label']}: open={i.get('open')!r} day_high={i.get('day_high')!r} close={i.get('close')!r}"
        + ("  <- close가 \"-\" 입니다, 웹서치로 채워주세요" if i.get("close") in ("-", None) else "  <- 이미 실제 값, 절대 변경 금지")
        for i in data["indicators"]
    )
    candidates_str = "\n".join(
        f"- {c['stocks']}" for c in data.get("checkpoints", []) if c.get("stocks")
    ) or "(없음)"
    labels_str = ", ".join(f'"{i["label"]}"' for i in data["indicators"])
    return f"""오늘은 {data['date']} 입니다.

[오늘 지수/지표]
{indicators_str}

[등락률 상위/하위 종목 후보 — 실제 값, 체크포인트 작성 시 참고만 하세요.
반드시 이 안에서만 골라야 하는 건 아니며, 오늘 시황상 더 중요한 종목/섹터가
있으면 웹서치로 확인해 대체해도 됩니다]
{candidates_str}

이 정보를 바탕으로 웹서치로 오늘자 한국 증시 마감 시황 뉴스, "-"로 비어있는
지표의 실제 수치, 업종별 등락 동향(sectors), 이번 주 일정(경제지표 발표·
실적 발표·연준 이벤트·한국은행 회의 등), 금일 체크포인트(오늘 주목할 섹터
3~4개와 관심 종목·관점·근거)를 조사해서 스키마에 맞게 채워주세요.

- indicator_updates의 label은 다음과 정확히 일치해야 합니다: {labels_str}.
  이미 실제 값이 있는 지표는 open/day_high/close를 입력값 그대로 돌려주고
  (코드가 어차피 무시합니다), "-"인 지표만 실제 웹서치 결과로 채우세요.
- sectors는 오늘 코스피/코스닥 업종별 등락 동향을 8~14개 업종, 시가총액
  비중이 큰 순으로 채워주세요.
- calendar는 오늘을 포함해 이번 주 안에서 실제로 의미 있는 날짜/시간대만
  칸으로 나누세요(요일마다 꼭 하나씩 만들 필요 없음 — 예: 같은 날이라도
  중요 이벤트가 새벽·오전으로 나뉘면 별도 칸으로 쪼개도 됩니다). date는
  "26"처럼 일(day)만, dow는 "MON"/"TUE"/.../"밤"처럼 요일 또는 시간대
  라벨. 오늘 칸의 headline/detail은 위에 준 실제 지표값을 인용해서 쓰세요."""


OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "리포트 메인 제목, 한 문장, 임팩트 있게"},
        "lead": {"type": "string", "description": "제목 아래 붙는 오늘 시황 요약, 1~3문장"},
        "indicator_updates": {
            "type": "array",
            "description": "입력으로 준 지표 각각에 대해. 이미 실제 값이 있는 지표는 open/day_high/close를 입력값 그대로 반복(코드가 무시함), close가 \"-\"인 지표만 웹서치로 찾은 실제 값으로 채운다.",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "description": "입력으로 준 지표 label과 정확히 일치"},
                    "open": {"type": "string", "description": "시가. \"-\"였던 지표만 실제 값으로, 못 찾으면 \"-\" 유지"},
                    "day_high": {"type": "string", "description": "장중 고점. 못 찾으면 \"-\""},
                    "close": {"type": "string", "description": "종가(또는 해외지표는 등락률 자체). 못 찾으면 \"-\""},
                    "note": {"type": "string", "description": "왜 이렇게 움직였는지, 비고란에 들어갈 한 줄"},
                },
                "required": ["label", "open", "day_high", "close", "note"],
                "additionalProperties": False,
            },
        },
        "flows_note": {"type": "string", "description": "수급(외국인/기관/개인 순매수) 요약 한 줄"},
        "sectors": {
            "type": "array",
            "description": "오늘 코스피/코스닥 업종별 등락 동향, 시가총액 비중이 큰 순으로 8~14개",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "업종명, 예: 제조(반도체 포함), 건설, 화학"},
                    "bucket": {"type": "string", "description": "방향성 표시. 예: '강보합', '+2%대', '약보합', '−2%대'"},
                    "weight": {"type": "number", "description": "코스피/코스닥 합산 시가총액 비중(%) 근사치"},
                    "detail": {"type": "string", "description": "그 업종 관련 대표 종목/재료 한 줄 (없으면 빈 문자열)"},
                },
                "required": ["name", "bucket", "weight", "detail"],
                "additionalProperties": False,
            },
        },
        "sector_analysis": {"type": "string", "description": "업종 동향 전체를 요약하는 한 문단"},
        "checkpoints": {
            "type": "array",
            "description": "오늘 주목할 섹터 3~4개",
            "items": {
                "type": "object",
                "properties": {
                    "sector": {"type": "string", "description": "섹터명"},
                    "stocks": {"type": "string", "description": "관심 종목명 (콤마로 구분)"},
                    "view": {"type": "string", "description": "오늘의 관점, 짧은 구절"},
                    "rationale": {"type": "string", "description": "근거, 1~3문장"},
                },
                "required": ["sector", "stocks", "view", "rationale"],
                "additionalProperties": False,
            },
        },
        "calendar": {
            "type": "array",
            "description": "이번 주 일정 칸들 (오늘 포함)",
            "items": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "일(day)만, 예: 26"},
                    "dow": {"type": "string", "description": "요일(MON/TUE/WED/THU/FRI) 또는 시간대 라벨(예: 밤)"},
                    "headline": {"type": "string", "description": "그 칸의 헤드라인 한 줄"},
                    "detail": {"type": "string", "description": "부연 설명, 줄바꿈(\\n)으로 여러 줄 가능"},
                    "footer": {"type": "string", "description": "칸 맨 아래 짧은 태그. 예: '전일 마감', '본 자료 기준일', '개장 전 확인 필수'"},
                },
                "required": ["date", "dow", "headline", "detail", "footer"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["title", "lead", "indicator_updates", "flows_note", "sectors", "sector_analysis", "checkpoints", "calendar"],
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
            "max_uses": 16,
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


def merge(data: dict, filled: dict) -> dict:
    data["title"] = filled["title"]
    data["lead"] = filled["lead"]
    data["flows_note"] = filled.get("flows_note", data.get("flows_note", ""))
    data["sector_analysis"] = filled.get("sector_analysis", "")

    updates_by_label = {u["label"]: u for u in filled["indicator_updates"]}
    for ind in data["indicators"]:
        u = updates_by_label.get(ind["label"])
        if not u:
            continue
        # 이미 실제 값(토스 API 등)이 있던 지표는 코드가 절대 덮어쓰지 않는다 —
        # close가 "-"였던 지표(WTI/필라델피아 반도체 등)만 Claude가 찾은 값으로 채운다.
        if ind.get("close") in ("-", None) and u.get("close") and u["close"] != "-":
            ind["open"] = u.get("open", "-")
            ind["day_high"] = u.get("day_high", "-")
            ind["close"] = u["close"]
        ind["note"] = u.get("note", ind.get("note", ""))

    data["sectors"] = filled.get("sectors", [])
    data["checkpoints"] = filled.get("checkpoints", [])
    data["calendar"] = filled.get("calendar", [])

    return data


def main():
    if len(sys.argv) != 2:
        print("사용법: python3 scripts/fill_with_claude.py data/2026-08-26.json", file=sys.stderr)
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
