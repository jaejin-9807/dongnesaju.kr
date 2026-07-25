# -*- coding: utf-8 -*-
"""
pdf_render.py
=============
HTML(문자열/파일) -> A4 세로형 PDF 렌더링 엔진.

우선순위 체인 (섹션 4 요구사항):
    1) Playwright (Headless Chromium)  ← 주 엔진. 사용자 배포(Windows)에서 사용.
    2) WeasyPrint                       ← 리눅스/CI/폴백. 브라우저 다운로드 불필요.
    3) LibreOffice(soffice)             ← 최후의 비상 폴백(기존 코드 유지).

- LibreOffice HTML 변환은 더 이상 "주 방식"이 아니며 마지막 폴백으로만 쓴다.
- 각 엔진은 독립적으로 실패할 수 있고, 실패하면 다음 엔진으로 넘어간다.
- 어떤 엔진으로 렌더했는지, 실패 원인은 무엇인지 호출부가 알 수 있도록 반환한다.
- 머리글/꼬리글/페이지번호:
    * Chromium: header_template / footer_template (HTML) 로 주입
    * WeasyPrint: HTML/CSS 의 @page margin-box + counter(page) 로 처리
  두 방식이 하나의 HTML에서 함께 동작하도록 report_html.py 가 CSS 를 구성한다.
"""
import os
import sys
import shutil
import subprocess
import tempfile
from pathlib import Path


A4 = {"width_mm": 210, "height_mm": 297}


def file_uri(path: str) -> str:
    return Path(path).resolve().as_uri()


# ------------------------------------------------------------------
# 엔진별 가용성 검사 (서버 시작 시 헬스체크에 사용)
# ------------------------------------------------------------------
def probe_engines() -> dict:
    """설치/실행 가능한 렌더 엔진을 조사한다. server.js 헬스체크가 호출."""
    status = {"playwright": False, "weasyprint": False, "libreoffice": False,
              "chromium_path": None, "errors": {}}

    # Playwright: 다운로드된 Chromium 이 없으면 설치된 Edge/Chrome 를 빌려 쓴다.
    try:
        from playwright.sync_api import sync_playwright  # noqa
        with sync_playwright() as p:
            launched = False
            detail = []
            exe = p.chromium.executable_path
            if exe and os.path.exists(exe):
                try:
                    b = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
                    b.close(); launched = True; status["chromium_path"] = exe
                except Exception as e:  # noqa
                    detail.append(f"bundled:{e}")
            if not launched:
                for ch in ("msedge", "chrome"):
                    try:
                        b = p.chromium.launch(channel=ch, args=["--no-sandbox", "--disable-dev-shm-usage"])
                        b.close(); launched = True; status["chromium_path"] = f"channel:{ch}"; break
                    except Exception as e:  # noqa
                        detail.append(f"{ch}:{e}")
            status["playwright"] = launched
            if not launched:
                status["errors"]["playwright"] = (
                    "Chromium 다운로드본도 없고 Edge/Chrome 실행도 실패했습니다. "
                    "'python -m playwright install chromium' 를 실행하거나 Edge/Chrome 설치를 확인하세요. "
                    "(" + "; ".join(detail) + ")"
                )
    except Exception as e:  # noqa
        status["errors"]["playwright"] = str(e)

    # WeasyPrint? (import 시 뿜는 경고가 stdout 을 오염시키지 않도록 억제)
    try:
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            import weasyprint  # noqa
        status["weasyprint"] = True
    except Exception as e:  # noqa
        status["errors"]["weasyprint"] = str(e)

    # LibreOffice?
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice and os.name == "nt":
        for c in (r"C:\Program Files\LibreOffice\program\soffice.exe",
                  r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"):
            if os.path.exists(c):
                soffice = c
                break
    status["libreoffice"] = bool(soffice)
    status["soffice_path"] = soffice
    return status


# ------------------------------------------------------------------
# 개별 엔진 렌더 함수 — 성공 시 output_pdf 생성, 실패 시 예외
# ------------------------------------------------------------------
def _render_playwright(html_path: str, output_pdf: str, header_html: str,
                       footer_html: str, margins: dict, timeout_ms: int = 120000):
    from playwright.sync_api import sync_playwright

    def _launch(p):
        args = ["--no-sandbox", "--disable-dev-shm-usage"]
        errs = []
        exe = p.chromium.executable_path
        if exe and os.path.exists(exe):
            try:
                return p.chromium.launch(args=args)
            except Exception as e:  # noqa
                errs.append(f"bundled:{e}")
        # 다운로드된 Chromium 이 없으면 설치된 Edge -> Chrome 순서로 시도
        for ch in ("msedge", "chrome"):
            try:
                return p.chromium.launch(channel=ch, args=args)
            except Exception as e:  # noqa
                errs.append(f"{ch}:{e}")
        raise RuntimeError("Playwright 브라우저 실행 실패(Chromium/Edge/Chrome): " + "; ".join(errs))

    with sync_playwright() as p:
        browser = _launch(p)
        try:
            page = browser.new_page()
            page.goto(file_uri(html_path), wait_until="networkidle", timeout=timeout_ms)
            # 웹폰트/이미지 로딩 안정화
            try:
                page.evaluate("document.fonts && document.fonts.ready")
                page.wait_for_timeout(300)
            except Exception:
                pass
            has_hf = bool(header_html or footer_html)
            page.pdf(
                path=output_pdf,
                format="A4",
                print_background=True,
                display_header_footer=has_hf,
                header_template=header_html or "<span></span>",
                footer_template=footer_html or "<span></span>",
                margin={
                    "top": margins.get("top", "16mm"),
                    "bottom": margins.get("bottom", "16mm"),
                    "left": margins.get("left", "0mm"),
                    "right": margins.get("right", "0mm"),
                },
                prefer_css_page_size=True,
            )
        finally:
            browser.close()
    if not os.path.exists(output_pdf) or os.path.getsize(output_pdf) == 0:
        raise RuntimeError("Playwright 가 PDF 를 생성하지 못했습니다.")


def _render_weasyprint(html_path: str, output_pdf: str, **_):
    from weasyprint import HTML
    HTML(filename=html_path).write_pdf(output_pdf)
    if not os.path.exists(output_pdf) or os.path.getsize(output_pdf) == 0:
        raise RuntimeError("WeasyPrint 가 PDF 를 생성하지 못했습니다.")


def _render_libreoffice(html_path: str, output_pdf: str, **_):
    """최후 폴백. 기존 office/soffice 헬퍼 재사용."""
    sys.path.insert(0, os.path.dirname(__file__))
    from office.soffice import run_soffice
    outdir = tempfile.mkdtemp(prefix="saju_lo_")
    try:
        res = run_soffice(
            ["--headless", "--convert-to", "pdf", "--outdir", outdir, html_path],
            capture_output=True, text=True, timeout=180,
        )
        produced = os.path.join(outdir, Path(html_path).stem + ".pdf")
        if res.returncode != 0 or not os.path.exists(produced):
            raise RuntimeError(f"LibreOffice 변환 실패: {res.stderr or res.stdout}")
        shutil.move(produced, output_pdf)
    finally:
        shutil.rmtree(outdir, ignore_errors=True)


_ENGINES = [
    ("playwright", _render_playwright),
    ("weasyprint", _render_weasyprint),
    ("libreoffice", _render_libreoffice),
]


def render_pdf(html_path: str, output_pdf: str,
               header_html: str = "", footer_html: str = "",
               margins: dict = None, prefer: str = None,
               debug_dir: str = None) -> dict:
    """
    HTML 파일을 PDF 로 렌더한다. 우선순위 체인을 순서대로 시도한다.

    Args:
        html_path: 렌더할 HTML 파일 경로
        output_pdf: 저장할 PDF 경로
        header_html/footer_html: Chromium 용 머리글/꼬리글 템플릿(HTML)
        margins: {"top","bottom","left","right"} (Chromium 용)
        prefer: 특정 엔진을 우선 시도("playwright"|"weasyprint"|"libreoffice")
        debug_dir: 실패 시 임시 HTML/로그를 남길 디렉터리(관리자 확인용)

    Returns:
        {"engine": "playwright"|..., "attempts": [{"engine","ok","error"}...]}
    """
    margins = margins or {"top": "16mm", "bottom": "16mm", "left": "0mm", "right": "0mm"}
    order = list(_ENGINES)
    if prefer:
        order.sort(key=lambda e: 0 if e[0] == prefer else 1)

    attempts = []
    for name, fn in order:
        try:
            fn(html_path, output_pdf, header_html=header_html,
               footer_html=footer_html, margins=margins)
            attempts.append({"engine": name, "ok": True, "error": None})
            return {"engine": name, "attempts": attempts}
        except Exception as e:  # noqa
            attempts.append({"engine": name, "ok": False, "error": str(e)})
            continue

    # 전부 실패 — 디버그 자료 남기기
    if debug_dir:
        try:
            os.makedirs(debug_dir, exist_ok=True)
            shutil.copy(html_path, os.path.join(debug_dir, "failed_report.html"))
            with open(os.path.join(debug_dir, "render_errors.txt"), "w", encoding="utf-8") as f:
                for a in attempts:
                    f.write(f"[{a['engine']}] {a['error']}\n")
        except Exception:
            pass
    raise RuntimeError("모든 PDF 렌더 엔진이 실패했습니다: " +
                       " | ".join(f"{a['engine']}={a['error']}" for a in attempts))


if __name__ == "__main__":
    import json
    print(json.dumps(probe_engines(), ensure_ascii=False, indent=2))
