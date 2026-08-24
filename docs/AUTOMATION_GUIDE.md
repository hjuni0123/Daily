# 자동화 실행 가이드 (매일 4시 리포트 생성)

이 문서는 **매일 장마감 후 자동으로 실행되는 세션**(Claude Code Remote Routine)이 따라야 할
절차다. 사람이 참고해도 되고, 스케줄된 세션이 이 문서를 읽고 그대로 수행해도 된다.

리포트 양식은 `reports/sample/2026-08-24_sample.json`을 렌더링한 결과를 기준으로 한다.
그 파일을 열어 필드 구조를 먼저 파악한 뒤 아래 절차를 따르면 이해가 빠르다.

이 리포지토리는 KRX/증권사 API 서버에 직접 접근이 막힌 네트워크에서도 동작하도록,
`WebSearch`/`WebFetch`로 시황을 조사해 JSON을 채우고 `scripts/render_report.py`로
포맷을 렌더링하는 방식을 기본 경로로 한다.

## 절차

1. **오늘 날짜/거래일 확인.** 오늘이 한국 증시 휴장일(주말/공휴일)이면 리포트를 생성하지 말고
   종료한다.

2. **헤드라인 잡기.** 오늘 시장을 관통하는 한 문장을 `title`(굵은 제목, 예: "지수는 올랐지만
   오른 건 둘뿐 — 압축 장세의 재확인")과 `subtitle`(그 이유를 보충하는 한 줄)로 정리한다.
   `eyebrow`는 문서 종류 태그로 보통 "시장 마감 브리프" 고정.

3. **SIGNAL / KEY / STEP 세 줄 요약.**
   - `signal`: 오늘 수급/가격에서 관찰된 사실 한 문장 (예: 외국인 순매수 지속 여부, 상승/하락
     종목수 등 "체감"을 보여주는 지표)
   - `key_point`: 그 사실의 배경/원인이 되는 구조적 요인 한 문장 (예: 금리 레벨, 정책 이슈)
   - `step`: 이번 주 신경 써야 할 핵심 분기점과, 그때까지 어떻게 대응할지 한 문장

4. **Ⅰ. 지수·대외 지표 조사 (WebSearch).**
   `indicators` 배열에 아래 행을 채운다. 각 행은 `label`/`close`/`change_pt`/`change_pct`/
   `note`(그 수치가 왜 중요한지 한 줄 해석)로 구성:
   - KOSPI, KOSDAQ 종가·전일비·등락률
   - 원/달러 환율
   - 미국 10년물 국채금리 (전일 대비 bp 변화)
   - S&P500 선물 / WTI 유가 (간밤 변동)
   - `flows`: KOSPI/KOSDAQ 투자자별(외국인/기관/개인) 순매수 대금(억원), 선물 수급 한 줄.
     정확한 억원 단위 수치를 못 찾으면 "-" 로 두거나 방향성만 서술한다 (없는 숫자를
     지어내지 않는다).
   - `breadth`: 상승/하락 종목수, 거래대금(20일 평균 대비), 신용잔고. 못 찾으면 해당
     필드는 생략 가능.
   - 검색 쿼리 예시: `"코스피 코스닥 마감 시황 YYYY년 M월 D일"`,
     `"YYYY년 M월 D일 외국인 기관 개인 순매수"`, `"YYYY년 M월 D일 상승 하락 종목수"`

5. **Ⅱ. 업종 동향 맵 조사.**
   `sectors` 배열: 10~15개 업종의 `change_pct`와 **실제 시가총액 비중을 반영한 `weight`**
   (반도체가 특히 크다는 걸 잊지 말 것 — 대충 비슷한 숫자를 나열하지 않는다). `sector_prose`에
   2~3문장으로 업종 간 명암을 서술한다.

6. **Ⅲ. 이슈 종목 조사 — 왜 움직였고, 이어질 것인가.**
   `issue_stocks` 배열, 각 항목은:
   - `name`/`ticker`/`change_pct`
   - `reason`: 뉴스·수급·실적 등 왜 움직였는지 (한 줄, 근거 포함)
   - `persistence`: "높음"(추세 지속 가능성 높음) / "중립" / "약세 지속"(추가 하락 우려) 중 하나
   - `checkpoint`: **다음에 뭘, 언제 확인해야 하는지** 한 줄 (예: "8/27(목) 06:00 엔비디아
     실적의 DC 매출·가이던스")
   시총 큰 종목, 등락률 큰 종목, 관심도 높은 종목(뉴스에 많이 언급된 종목) 위주로 4~6개.

7. **Ⅳ. 캘린더 조사 — 언제, 무엇을, 왜 봐야 하나.**
   `calendar` 배열, 오늘부터 5~7일 내 일정을 시간순으로. 각 항목:
   - `datetime`: "8/28(금) 21:30" 처럼 날짜·요일·시간
   - `event`: 이벤트명
   - `importance`: 1~3 (3 = 엔비디아 실적, CPI/PCE 같은 확실한 변곡점 / 2 = 일반 지표 / 1 = 참고용)
   - `checkpoint`: 컨센서스·서프라이즈 시 영향·관련 종목을 한 줄로

8. **지점 대응 요약.** `stance.maintain`(유지) / `stance.reduce`(축소) / `stance.cash`
   (현금·고객 안내) 각각 한두 문장. 이번 주 실전 대응 관점에서 작성.

9. **데이터 JSON 작성.** 위 내용을 `data/{YYYY-MM-DD}.json`에 정리한다 (`data/` 없으면 생성).
   `reports/sample/2026-08-24_sample.json`을 스키마 예시로 그대로 참고할 것.

10. **렌더링 실행.**
    ```
    python3 scripts/render_report.py data/{YYYY-MM-DD}.json
    ```
    `reports/{YYYY-MM-DD}_market_report.md` 와 `.html` 이 생성된다.

11. **검증.** `.md`를 열어 표가 깨지지 않았는지, TODO/빈 값이 남아있지 않은지 확인.
    수치가 소스마다 다르면 가장 신뢰도 높은 소스를 우선하고, 확신이 없으면 리포트에
    "(추정치)"라고 표기하거나 그 필드를 비워둔다(지어내지 않는다). 나무위키 등
    사용자 편집 위키는 사실 확인 보조용으로만 쓴다.

12. **결과 전달.** `SendUserFile`로 `.html`(및 원하면 `.md`)을 사용자에게 보낸다. 메시지에는
    오늘 KOSPI/KOSDAQ 등락률과 SIGNAL 한 줄을 요약해 포함한다.

13. **저장소에 커밋.** `data/{YYYY-MM-DD}.json`과 `reports/{YYYY-MM-DD}_market_report.md/.html`을
    커밋하고 지정된 브랜치에 푸시해 이력을 남긴다.

## 참고: 로컬 PC/사내 서버에서 완전 자동화하려면

이 원격 세션 환경은 조직 보안 정책상 KRX/증권사 API 서버에 직접 접근이 막혀 있다
(`data.krx.co.kr`, `openapi.tossinvest.com` 모두 확인됨). 방화벽 제약이 없는 자체
서버/PC에서 크론으로 돌린다면:

- `scripts/fetch_pykrx.py`로 코스피/코스닥 지수와 등락률 상위 종목을 자동 수집할 수 있다.
- `scripts/toss_client.py`(미검증 초안, `.env`에 `TOSS_API_KEY`/`TOSS_API_SECRET` 필요)로
  토스증권 Open API 시세를 가져올 수 있다 — 단, 사용 전 반드시
  https://developers.tossinvest.com 문서와 엔드포인트를 대조해서 검증할 것.
- 두 경우 모두 `issue_stocks`의 `reason`/`persistence`/`checkpoint`, `calendar`,
  `stance` 같은 정성적 판단 항목은 여전히 Claude(WebSearch)나 사람이 채워야 한다.

크론 예시 (평일 16:00 KST 실행, 데이터 소스는 상황에 맞게 스크립트로 채운 뒤):
```
0 16 * * 1-5 cd /path/to/Daily && python3 scripts/render_report.py data/$(date +\%F).json
```
