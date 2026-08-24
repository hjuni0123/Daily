# KoPub World 서체

한양증권 실제 리서치 자료(PDF)에 임베드된 폰트를 확인해보니 본문/제목 서체가
**KoPub World 돋움체**(Dotum, Bold/Light)였다. 이 폰트는 한국출판인회의(KOPUS)가
무료 배포하는 서체로 상업적 이용이 허용된다 (출처:
https://www.kopus.org/biz-electronic-kopubworld/).

`KoPubWorld-Dotum-Pro-*.woff2` 는 사용자가 직접 제공한 **KoPub World Dotum Pro**
데스크톱용 OTF(Bold/Light)를 `fonttools`로 서브셋한 것이다 — 완성형 한글 전체
음절(U+AC00–D7A3) + 자모 + 라틴/숫자/기호만 남기고, 원본(개당 3~4MB)을 개당
~280~290KB로 줄였다. 매일 바뀌는 리포트 본문 어떤 글자가 와도 다 그려진다.

`render_report.py`가 이 두 파일을 base64로 인코딩해 HTML 리포트에 `@font-face`로
직접 삽입한다 (Bold=700, Light=300 — 본문 기본 두께는 Light).

## batang/ — 아직 미사용

사용자가 함께 제공한 **KoPub World 바탕체 Pro**(Bold/Medium/Light, 세리프체)도
같은 방식으로 서브셋해 `batang/`에 넣어뒀다. 현재 HTML/워드 리포트 어디에도 적용돼
있지 않다 — 어디에 쓸지(예: 제목만 세리프로, 표지용 등) 정해지면 반영할 수 있다.

## 워드(.docx) 버전은 별도

`scripts/docx/render_docx.js`는 Word 문서 포맷 특성상 커스텀 폰트를 파일에
내장하지 못해(임베딩 자체는 OOXML 스펙에 있지만 도구 지원이 불안정) 대신 Word
표준 한글 서체(맑은 고딕)를 쓴다. 실제 KoPub 서체가 설치된 PC에서 열면 그걸로
바꿔서 볼 수 있다.
