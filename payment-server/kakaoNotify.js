/**
 * ===================================================================
 * kakaoNotify.js — 카카오톡 "나에게 보내기"로 사장님에게 알림 전송
 * ===================================================================
 * 손님이 회원가입 / 주문 / 결제(입금확인)를 하면, 사장님 본인 카카오톡으로
 * 알림 메시지를 보냅니다. (카카오 기본 템플릿 memo/default/send)
 *
 * 준비물(무료 · 사업자 불필요):
 *   1) https://developers.kakao.com 에서 앱 생성 → REST API 키
 *   2) 카카오 로그인 활성화 + 동의항목 "카카오톡 메시지 전송(talk_message)" ON
 *   3) Redirect URI 등록: {BASE_URL}/api/admin/kakao/callback
 *   4) 서버 환경변수(.env / Railway Variables)
 *        KAKAO_REST_KEY = 앱의 REST API 키
 *        BASE_URL       = https://www.dongnesaju.kr
 *   5) 사장님이 브라우저에서 1회 인증:
 *        {BASE_URL}/api/admin/kakao/connect  → 카카오 로그인/동의
 *      → refresh_token 이 서버(DATA_DIR/kakao_token.json)에 저장됨.
 *
 * access_token 은 만료되면 refresh_token 으로 자동 갱신합니다.
 * refresh_token 자체가 만료(약 2개월)되면 /connect 를 한 번 더 하면 됩니다.
 * ===================================================================
 */
const fs = require("fs");
const path = require("path");

const DATA_DIR = process.env.DATA_DIR || __dirname;
try { fs.mkdirSync(DATA_DIR, { recursive: true }); } catch (e) {}
const TOKEN_PATH = path.join(DATA_DIR, "kakao_token.json");

const REST_KEY = process.env.KAKAO_REST_KEY || "";
const BASE_URL = process.env.BASE_URL || "https://www.dongnesaju.kr";
const REDIRECT_URI = BASE_URL.replace(/\/+$/, "") + "/api/admin/kakao/callback";

function readToken() {
  try { return JSON.parse(fs.readFileSync(TOKEN_PATH, "utf-8")); } catch (e) { return null; }
}
function writeToken(t) {
  try { fs.writeFileSync(TOKEN_PATH, JSON.stringify(t, null, 2), "utf-8"); } catch (e) {}
}

function hasRestKey() { return !!REST_KEY; }
function isConnected() { const t = readToken(); return !!(t && t.refresh_token); }
function isConfigured() { return hasRestKey() && isConnected(); }

// 사장님이 처음 인증할 때 이동할 카카오 로그인 URL
function authorizeUrl() {
  const p = new URLSearchParams({
    client_id: REST_KEY,
    redirect_uri: REDIRECT_URI,
    response_type: "code",
    scope: "talk_message",
  });
  return "https://kauth.kakao.com/oauth/authorize?" + p.toString();
}

// 콜백에서 받은 code 를 토큰으로 교환하고 refresh_token 저장
async function exchangeCode(code) {
  const body = new URLSearchParams({
    grant_type: "authorization_code",
    client_id: REST_KEY,
    redirect_uri: REDIRECT_URI,
    code,
  });
  const r = await fetch("https://kauth.kakao.com/oauth/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded;charset=utf-8" },
    body,
  });
  const j = await r.json();
  if (j.access_token || j.refresh_token) {
    writeToken({ ...(readToken() || {}), ...j, savedAt: Date.now() });
    return { ok: true };
  }
  return { ok: false, error: j };
}

// 저장된 refresh_token 으로 새 access_token 발급
async function getAccessToken() {
  const t = readToken();
  if (!t || !t.refresh_token) throw new Error("카카오 연결이 아직 안 되어 있습니다. /api/admin/kakao/connect 로 1회 인증하세요.");
  const body = new URLSearchParams({
    grant_type: "refresh_token",
    client_id: REST_KEY,
    refresh_token: t.refresh_token,
  });
  const r = await fetch("https://kauth.kakao.com/oauth/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded;charset=utf-8" },
    body,
  });
  const j = await r.json();
  if (!j.access_token) throw new Error("access token 갱신 실패: " + JSON.stringify(j));
  const nt = { ...t, access_token: j.access_token, savedAt: Date.now() };
  if (j.refresh_token) nt.refresh_token = j.refresh_token; // 카카오가 갱신해주면 교체
  writeToken(nt);
  return j.access_token;
}

// 내 카카오톡으로 텍스트 메시지 전송
async function sendToMe(text, link) {
  if (!isConfigured()) {
    console.log("[카카오알림] 미설정 상태라 건너뜀:", (text || "").slice(0, 40));
    return { skipped: true };
  }
  const url = link || BASE_URL.replace(/\/+$/, "") + "/admin.html";
  const template = {
    object_type: "text",
    text: String(text || "").slice(0, 990),
    link: { web_url: url, mobile_web_url: url },
    button_title: "관리자 페이지 열기",
  };
  const at = await getAccessToken();
  const body = new URLSearchParams({ template_object: JSON.stringify(template) });
  const r = await fetch("https://kapi.kakao.com/v2/api/talk/memo/default/send", {
    method: "POST",
    headers: { Authorization: "Bearer " + at, "Content-Type": "application/x-www-form-urlencoded;charset=utf-8" },
    body,
  });
  const j = await r.json().catch(() => ({}));
  if (r.status !== 200) throw new Error("카카오 전송 실패(" + r.status + "): " + JSON.stringify(j));
  return j;
}

// 실패해도 서비스 흐름을 막지 않도록 감싼 안전 호출
async function notify(text, link) {
  try { return await sendToMe(text, link); }
  catch (e) { console.error("[카카오알림] 전송 오류:", e.message); return { error: e.message }; }
}

module.exports = {
  hasRestKey, isConnected, isConfigured,
  authorizeUrl, exchangeCode, getAccessToken, sendToMe, notify,
  REDIRECT_URI,
};
