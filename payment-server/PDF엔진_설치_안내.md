# PDF 생성 엔진 설치 안내 (v5 — Playwright/Chromium)

기존 LibreOffice HTML 변환 방식을 **Playwright(Headless Chromium)** 기반으로 교체했습니다.
LibreOffice는 삭제하지 않고 **최후의 비상 폴백**으로만 남겨 두었습니다.

렌더 우선순위: **Playwright(Chromium) → WeasyPrint → LibreOffice**

## 1) 파이썬 의존성 설치

```bash
cd payment-server/saju_engine
pip install -r requirements.txt
python -m playwright install chromium
```

- Windows에서 `python`이 인식되지 않으면 `py -m pip ...`, `py -m playwright install chromium` 로 실행하세요.
- 서버가 파이썬을 못 찾으면 `.env`에 `PYTHON_BIN=python` (또는 전체 경로)을 지정하세요.

## 2) 서버 실행

```bash
cd payment-server
npm install
node server.js
```

서버가 시작되면 콘솔에 사용 가능한 렌더 엔진이 출력됩니다.

```
[PDF엔진] 사용 가능: Playwright(Chromium), WeasyPrint, LibreOffice(폴백) (주 엔진: Playwright)
```

엔진이 하나도 없으면 경고가 뜨며, `python -m playwright install chromium` 안내가 출력됩니다.
관리자 로그인 후 `GET /api/admin/render-health` 로도 상태를 확인할 수 있습니다.

## 3) 폰트

`saju_engine/fonts/` 에 한글 본문/제목용 번들 폰트(OFL, Noto Serif/Sans KR 서브셋)가 포함되어
`@font-face`로 고정 사용됩니다. **OS 기본 글꼴에 의존하지 않으며**, 중국어(CJK SC) 글리프가
한글 본문에 섞이지 않습니다. matplotlib 그래프도 동일 번들 폰트를 사용해 어떤 환경에서도
한글이 깨지지 않습니다.

## 4) 표지 이미지

`saju_engine/assets/cover_source.jpg` 를 배경으로 사용하고, 고객명·리포트종류·생년월일·
양/음력·출생시간(또는 "출생시간 미상")·기준연도는 **HTML 텍스트 레이어로 동적 출력**됩니다.
표지 이미지를 교체하려면 같은 파일명으로 A4 세로 비율(약 3:4) 이미지를 넣으면 됩니다.

## 5) 산출물

- A4 세로, 배경 인쇄, 머리글/꼬리글/페이지번호, 실제 페이지번호가 있는 목차
- 실제 콘텐츠 분량에 따라 약 42~48페이지가 자연스럽게 생성(빈 페이지·강제 늘리기 없음)
- 파일명: `고객명_리포트종류_기준연도.pdf` (사용 불가 문자 제거)
