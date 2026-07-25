/**
 * ===================================================================
 * sajuEngine.js
 * ===================================================================
 * saju_engine/run_saju.py(파이썬 사주 계산 엔진)를 child_process로 호출하는
 * Node.js 브릿지. 의뢰인 생년월일시를 넘기면 계산된 사주 결과(JSON)를 받는다.
 * ===================================================================
 */
const { spawn } = require("child_process");
const path = require("path");

const PYTHON_BIN = process.env.PYTHON_BIN || (process.platform === "win32" ? "python" : "python3");
const ENGINE_DIR = path.join(__dirname, "saju_engine");
const ENGINE_SCRIPT = path.join(ENGINE_DIR, "run_saju.py");
const PDF_SCRIPT = path.join(ENGINE_DIR, "make_pdf.py");

function calculateSaju(sajuInfo) {
  return new Promise((resolve, reject) => {
    const proc = spawn(PYTHON_BIN, [ENGINE_SCRIPT], {
      cwd: ENGINE_DIR,
      env: { ...process.env, PYTHONIOENCODING: "utf-8" },
    });

    let stdoutChunks = [];
    let stderrChunks = [];

    proc.stdout.on("data", (chunk) => stdoutChunks.push(chunk));
    proc.stderr.on("data", (chunk) => stderrChunks.push(chunk));

    proc.on("close", (code) => {
      const stdout = Buffer.concat(stdoutChunks).toString("utf-8");
      const stderr = Buffer.concat(stderrChunks).toString("utf-8");

      if (!stdout.trim()) {
        return reject(new Error("사주 계산 엔진이 아무 결과도 반환하지 않았습니다: " + stderr));
      }
      try {
        const parsed = JSON.parse(stdout.trim().split("\n").pop());
        if (!parsed.success) {
          return reject(new Error(parsed.message || "사주 계산 실패"));
        }
        resolve(parsed);
      } catch (e) {
        reject(new Error("사주 계산 결과 파싱 실패: " + e.message + " / stdout: " + stdout));
      }
    });

    proc.on("error", (err) => {
      reject(new Error("사주 계산 엔진 실행 실패 (python이 설치되어 있는지 확인해 주세요): " + err.message));
    });

    proc.stdin.write(JSON.stringify(sajuInfo));
    proc.stdin.end();
  });
}

function generatePdf(sajuResult, outputPath, meta = {}) {
  return new Promise((resolve, reject) => {
    // PYTHONIOENCODING을 지정해 Windows 콘솔 기본 코드페이지(CP949 등)와 무관하게
    // 파이썬 stdout/stderr가 항상 UTF-8로 나오도록 강제한다.
    // meta: 표지/기준연도 등 make_pdf.py가 사용하는 부가정보(고객명/리포트종류/기준연도/주문번호 등)
    const payload = { ...sajuResult, meta: { ...(sajuResult.meta || {}), ...meta } };
    const proc = spawn(PYTHON_BIN, [PDF_SCRIPT, outputPath], {
      cwd: ENGINE_DIR,
      env: { ...process.env, PYTHONIOENCODING: "utf-8" },
    });

    let stdoutChunks = [];
    let stderrChunks = [];

    proc.stdout.on("data", (chunk) => stdoutChunks.push(chunk));
    proc.stderr.on("data", (chunk) => stderrChunks.push(chunk));

    proc.on("close", (code) => {
      const stdout = Buffer.concat(stdoutChunks).toString("utf-8");
      const stderr = Buffer.concat(stderrChunks).toString("utf-8");

      // AI 해석 생성 성공/실패(폴백) 여부는 정보성 로그이므로, 에러가 아니어도
      // 관리자가 서버 콘솔에서 확인할 수 있도록 그대로 출력한다.
      if (stderr.includes("[AI 해석 생성 실패")) {
        console.log(stderr.trim());
      } else if (stderr.trim()) {
        console.log("[make_pdf.py stderr] " + stderr.trim());
      }

      if (!stdout.trim()) {
        return reject(new Error(friendlyPdfError(stderr, code)));
      }
      try {
        const parsed = JSON.parse(stdout.trim().split("\n").pop());
        if (!parsed.success) {
          return reject(new Error(friendlyPdfError(parsed.message || "", code)));
        }
        resolve(parsed);
      } catch (e) {
        reject(new Error(friendlyPdfError(stderr, code) + " (파싱 오류: " + e.message + ")"));
      }
    });

    proc.on("error", (err) => {
      reject(new Error("PDF 생성 스크립트 실행 실패: " + err.message));
    });

    proc.stdin.write(JSON.stringify(payload));
    proc.stdin.end();
  });
}

/**
 * 설치된 PDF 렌더 엔진(Playwright/WeasyPrint/LibreOffice) 가용성을 조사한다.
 * 서버 시작 시 헬스체크에 사용(섹션 4: 브라우저 실행 가능 여부 검사).
 */
function probeRenderEngines() {
  return new Promise((resolve) => {
    const proc = spawn(PYTHON_BIN, [path.join(ENGINE_DIR, "pdf_render.py")], {
      cwd: ENGINE_DIR,
      env: { ...process.env, PYTHONIOENCODING: "utf-8" },
    });
    let out = [];
    proc.stdout.on("data", (c) => out.push(c));
    proc.on("close", () => {
      const raw = Buffer.concat(out).toString("utf-8");
      try {
        // 파이썬 라이브러리 경고문이 앞에 섞여도 JSON 블록만 뽑아 파싱한다.
        const a = raw.indexOf("{");
        const b = raw.lastIndexOf("}");
        resolve(JSON.parse(a >= 0 && b > a ? raw.slice(a, b + 1) : raw));
      } catch (e) {
        resolve({ playwright: false, weasyprint: false, libreoffice: false, error: e.message });
      }
    });
    proc.on("error", (err) => resolve({ playwright: false, weasyprint: false, libreoffice: false, error: err.message }));
  });
}

/**
 * LibreOffice 미설치/경로 문제 등 자주 발생하는 케이스를 사람이 읽기 쉬운
 * 한국어 안내 메시지로 바꿔준다. 원본 에러 문구도 함께 남겨 디버깅에 활용한다.
 */
function friendlyPdfError(rawMessage, code) {
  const msg = (rawMessage || "").trim();
  const lower = msg.toLowerCase();

  if (lower.includes("soffice") && (lower.includes("not found") || lower.includes("찾을 수 없") || lower.includes("no such file") || code === null)) {
    return (
      "PDF 생성 실패: LibreOffice(soffice) 프로그램을 찾지 못했습니다. " +
      "LibreOffice가 설치되어 있는지 확인하고, 설치 후에는 서버(명령프롬프트)를 완전히 종료했다가 다시 실행해 주세요. " +
      (msg ? `(상세: ${msg})` : "")
    );
  }
  if (!msg) {
    return `PDF 생성 실패: 알 수 없는 오류가 발생했습니다. (종료 코드: ${code})`;
  }
  return "PDF 생성 실패: " + msg;
}

module.exports = { calculateSaju, generatePdf, probeRenderEngines };
