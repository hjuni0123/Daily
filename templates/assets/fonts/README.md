# KoPub World Dotum

한양증권 실제 리서치 자료(PDF)에 임베드된 폰트를 확인해보니 본문/제목 서체가
**KoPub World 돋움체**(Bold/Medium)였다. 이 폰트는 한국출판인회의(KOPUS)가
무료 배포하는 서체로 상업적 이용이 허용된다 (출처:
https://www.kopus.org/biz-electronic-kopubworld/).

여기 있는 두 파일은 완성형 한글 전체 음절(U+AC00–D7A3) + 자모 + 라틴/숫자/기호만
남기고 `fonttools`로 서브셋한 WOFF2다 (원본 웹폰트는 개당 ~2MB, 서브셋 후 개당
~300KB). PDF에 실제 임베드된 폰트는 그 문서에 쓰인 글자만 들어있는 훨씬 작은
서브셋이라 매일 바뀌는 리포트 본문에는 못 쓰므로, 배포처(KOPUS)가 공개한 전체
웹폰트를 받아 다시 서브셋했다.

`render_report.py`가 이 두 파일을 base64로 인코딩해 HTML 리포트에 `@font-face`로
직접 삽입한다 (파일 하나만 있어도 어디서 열든 동일하게 보이도록).
