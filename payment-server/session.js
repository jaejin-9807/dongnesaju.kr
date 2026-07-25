/**
 * ===================================================================
 * session.js
 * ===================================================================
 * 아주 단순한 서명 토큰 기반 세션. 외부 패키지(jsonwebtoken 등) 없이
 * Node 내장 crypto의 HMAC-SHA256으로 직접 서명/검증한다.
 *
 * 토큰 형식: base64url(payloadJSON) + "." + base64url(HMAC서명)
 * 쿠키 이름: saju_session (고객), saju_admin_session (관리자)
 * ===================================================================
 */
const crypto = require("crypto");

const SECRET = process.env.SESSION_SECRET || "dev-secret-change-me-in-production";
const MAX_AGE_MS = 1000 * 60 * 60 * 24 * 14; // 14일

function b64url(input) {
  return Buffer.from(input).toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
function b64urlDecode(input) {
  input = input.replace(/-/g, "+").replace(/_/g, "/");
  while (input.length % 4) input += "=";
  return Buffer.from(input, "base64").toString("utf-8");
}

function sign(payload) {
  const body = b64url(JSON.stringify({ ...payload, exp: Date.now() + MAX_AGE_MS }));
  const sig = crypto.createHmac("sha256", SECRET).update(body).digest("hex");
  return `${body}.${sig}`;
}

function verify(token) {
  if (!token || typeof token !== "string" || !token.includes(".")) return null;
  const [body, sig] = token.split(".");
  const expected = crypto.createHmac("sha256", SECRET).update(body).digest("hex");
  if (sig !== expected) return null;
  try {
    const payload = JSON.parse(b64urlDecode(body));
    if (payload.exp && Date.now() > payload.exp) return null;
    return payload;
  } catch (e) {
    return null;
  }
}

function setCookie(res, name, token) {
  res.cookie(name, token, {
    httpOnly: true,
    maxAge: MAX_AGE_MS,
    sameSite: "lax",
  });
}

function clearCookie(res, name) {
  res.clearCookie(name);
}

module.exports = { sign, verify, setCookie, clearCookie };
