# Daily — 지점 배포용 데일리 마켓 브리핑

증권사 PB 지점에 매일 장마감 후 뿌리는 1~2페이지짜리 데일리 리포트의 **양식**과
**자동 생성 파이프라인**.

## 구성

```
templates/
  daily_report_template.md.j2    # 리포트 양식 (마크다운)
  daily_report_template.html.j2  # 리포트 양식 (인쇄/이메일용 스타일 HTML, 한양증권 CI 적용)
  assets/                        # 한양증권 CI 로고 + 실제 사용 서체(KoPub World Dotum)
scripts/
  render_report.py    # 데이터 JSON -> 양식에 채워 .md/.html 생성
  fetch_pykrx.py       # (선택) pykrx로 코스피/코스닥 지수·등락률 상위종목 자동 수집
  toss_client.py       # (선택, 미검증) 토스증권 Open API 클라이언트 초안
  requirements.txt
  docx/
    render_docx.js      # 데이터 JSON -> 동일 양식의 .docx(워드) 생성
    package.json
docs/
  AUTOMATION_GUIDE.md  # 매일 자동 실행되는 세션이 따르는 절차서
reports/
  sample/               # 포맷 시연용 예시 리포트 (실제 시황 데이터 아님)
data/                   # 생성된 리포트의 원본 데이터 JSON (자동 생성 시 쌓임)
```

## 리포트 양식 구성 (2페이지, 실제 증권사 데일리 스트래티지 노트 형식)

제목/부제 + **SIGNAL·KEY·STEP** 3줄 요약을 맨 위에 두고, 이어서:

1. **Ⅰ. 지수 · 대외 지표** — KOSPI/KOSDAQ/환율/미 10년물/S&P선물·유가를 표로, 각 행마다
   "왜 중요한지" 해석을 붙인다. 아래에 투자자별 순매수(외국인/기관/개인)와 시장 폭
   (상승·하락 종목수, 거래대금, 신용잔고) 박스.
2. **Ⅱ. 업종 동향 맵** — 시가총액 비중에 정확히 비례하는 실제 면적의 업종 히트맵(트리맵).
3. **Ⅲ. 이슈 종목** — 종목명, 등락률, 움직인 이유, **지속성**(높음/중립/약세 지속),
   **언제·무엇을 확인**해야 하는지까지 종목별로 짚어준다.
4. **Ⅳ. 캘린더** — 날짜·시간순 일정에 **중요도(★~★★★)**를 매겨 무엇을 우선 봐야 하는지
   명확히 한다.
5. **지점 대응 요약** — 유지/축소/현금·안내 3분류로 이번 주 실전 대응을 정리.

컴플라이언스는 짧은 불릿 3줄 + 맨 아래 한 줄 고지로 최소화해 가독성을 우선했다.

`templates/*.j2` 파일 자체가 실제 사용하는 양식이자 렌더링 템플릿이다. 문구나 섹션을
바꾸고 싶으면 이 파일을 직접 수정하면 된다.

### CI (한양증권 브랜드) & 서체

HTML 리포트 상단/하단의 로고는 실제 한양증권 공식 리서치 자료(PDF)에서 추출한 CI 원본
이미지다(`templates/assets/hy_logo_*.png`). CI 컬러(딥퍼플 그라데이션: `#2D2864` →
`#754BE4` → `#AB7CFB`)도 해당 로고 이미지에서 실측한 값을 `daily_report_template.html.j2`의
CSS 변수(`--hy-deep`, `--hy-mid`, `--hy-light`)로 사용한다.

본문 서체도 실제 리포트 PDF에 임베드된 폰트를 확인해 그대로 맞췄다 — **KoPub World
돋움체**(Bold/Medium, 한국출판인회의 무료 배포 서체)다. `templates/assets/fonts/`에
완성형 한글 전체(가능한 모든 음절) 서브셋 WOFF2로 들어있고, `render_report.py`가
base64로 인코딩해 HTML에 `@font-face`로 직접 삽입한다 — 파일 하나만 있어도 폰트가
안 깨진다. 자세한 출처/라이선스는 `templates/assets/fonts/README.md` 참고.

로고나 컬러, 서체가 바뀌면 `templates/assets/`의 파일만 교체하면 `render_report.py`가
자동으로 다시 인코딩해 반영한다.

업종 히트맵은 `squarify`(트리맵 알고리즘)로 각 업종의 `weight`(시가총액 비중)에
정확히 비례하는 실제 면적을 계산한다 — 박스 크기가 대충 비슷하게 나오지 않고,
반도체처럼 비중이 큰 업종은 확실히 크게, 작은 업종은 확실히 작게 나온다.

## 수동으로 한 번 생성해보기

```bash
pip install -r scripts/requirements.txt
python3 scripts/render_report.py reports/sample/2026-08-24_sample.json --outdir /tmp/out

# 워드(.docx) 버전도 필요하면
cd scripts/docx && npm install && cd ../..
node scripts/docx/render_docx.js reports/sample/2026-08-24_sample.json /tmp/out/2026-08-24_market_report.docx
```

`.docx`는 사용자가 제공한 워드 양식(같은 "시장 마감 브리프" 레이아웃)을 `docx`(npm)로
그대로 재현한다. 로고는 이미지로, 업종 히트맵은 병합 셀 표로 시가총액 비중에 맞춰
자동 배치된다. 서체는 Word 표준 한글 서체(맑은 고딕)를 쓴다 — HTML처럼 커스텀 폰트를
파일에 내장하는 기능은 워드 문서 포맷 특성상 지원하지 않는다.

`reports/sample/2026-08-24_sample.json` 은 **포맷 시연용 예시 데이터**다 (실제 시황 아님).
실제 리포트를 만들 때는 이 파일을 참고해 같은 스키마로 오늘 데이터를 채운
`data/{YYYY-MM-DD}.json`을 만들고 렌더링하면 된다.

## 매일 자동 생성

`docs/AUTOMATION_GUIDE.md`에 정의된 절차대로, **매일 평일 장마감 직후(15:30 KST) 자동
발동**돼 늦어도 15:40 KST까지 완성을 목표로 스케줄(Routine)이 설정되어 있다. 사용자가
따로 뭔가 보내지 않아도 매일 자동으로 실행된다:

1. WebSearch로 당일 코스피/코스닥 시황, 수급, 업종, 이슈 종목과 그 이유, 캘린더를 조사
   (뉴스 기사·공식 거래소 자료만 근거로 사용, 위키/블로그/예측 사이트 등은 배제 —
   확인 안 되는 수치는 지어내지 않고 "-"로 비움)
2. `data/{날짜}.json`으로 데이터 정리
3. `scripts/render_report.py` + `scripts/docx/render_docx.js`로 `.md`/`.html`/`.docx`
   세 포맷 모두 생성
4. 생성된 리포트 파일을 사용자에게 알림/전달
5. 저장소에 커밋해 이력 보관

> KRX 원본 데이터 서버 접근이 막힌 네트워크에서 실행되는 경우를 기본으로 설계했다
> (WebSearch 기반). 만약 KRX 접근이 가능한 자체 서버/PC에서 크론으로 돌린다면
> `scripts/fetch_pykrx.py`로 지수·등락률 데이터를 더 정확하게 자동 수집할 수 있다.
> 자세한 내용은 `docs/AUTOMATION_GUIDE.md` 참고.

### 토스증권 Open API (선택, 미검증)

`scripts/toss_client.py`에 OAuth2 client_credentials 방식의 클라이언트 초안을
넣어뒀다. **아직 실제로 검증되지 않았다** — 이 리포지토리가 개발되는 환경(조직
방화벽)에서 `developers.tossinvest.com` / `openapi.tossinvest.com` 접속이 모두
막혀 있어서 1차 문서를 직접 확인하거나 실제 호출을 테스트하지 못했다(공개 검색
결과만으로 작성). 사용하려면:

1. https://developers.tossinvest.com 문서와 `scripts/toss_client.py`의 엔드포인트를
   대조해서 검증한다 (특히 토큰 발급 경로, 시세 조회 경로, 응답 스키마).
2. API 키는 저장소 루트의 `.env` 파일에 넣는다 (`.env.example` 참고). `.env`는
   `.gitignore`에 등록되어 있어 **절대 커밋되지 않는다** — 코드에도 하드코딩하지 않는다.
3. **이 API 서버도 KRX와 마찬가지로 이 개발 환경에서는 접속이 막혀 있다.** 매일
   자동 실행되는 Routine도 같은 종류의 환경에서 돌기 때문에, 실제로 쓰려면 방화벽
   제약이 없는 사용자의 로컬 PC나 자체 서버에서 크론으로 돌리는 방식이어야 한다.

## 배포 방법

현재는 "파일 생성 + 알림" 까지 자동화되어 있다. 지점 전파는 알림받은 파일을
이메일/메신저로 직접 전달하면 된다. 추후 Gmail 연동을 활성화하면 지정된 수신자
목록으로 자동 이메일 발송까지 확장할 수 있다.

## 주의사항 (컴플라이언스)

- 자동 생성된 데이터는 **뉴스 검색 기반 요약**이다. 배포 전 반드시 본인이 한 번
  검토(특히 수치와 이슈 종목 이유)한 뒤 전파할 것을 권장한다.
- 리포트 하단에는 투자 권유가 아니라는 고지 문구가 기본 포함되어 있다.
