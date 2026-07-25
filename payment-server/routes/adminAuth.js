/**
 * ===================================================================
 * routes/adminAuth.js
 * ===================================================================
 * 사장님(운영자) 전용 로그인. 일반 회원가입과는 완전히 분리된 별도
 * 인증이다. 아이디/비밀번호는 .env의 ADMIN_ID / ADMIN_PASSWORD 값을
 * 사용한다 (회원가입 절차 없음 - 서버 소유자만 아는 값).
 * ===================================================================
 */
const express = require("express");
const session = require("../session");

const router = express.Router();
const COOKIE_NAME = "saju_admin_session";

router.post("/login", (req, res) => {
  const { adminId, password } = req.body;
  const validId = process.env.ADMIN_ID || "admin";
  const validPw = process.env.ADMIN_PASSWORD || "changeme";

  if (adminId !== validId || password !== validPw) {
    return res.status(401).json({ success: false, message: "관리자 아이디 또는 비밀번호가 올바르지 않습니다." });
  }

  const token = session.sign({ role: "admin", adminId });
  session.setCookie(res, COOKIE_NAME, token);
  res.json({ success: true });
});

router.post("/logout", (req, res) => {
  session.clearCookie(res, COOKIE_NAME);
  res.json({ success: true });
});

router.get("/me", (req, res) => {
  const payload = session.verify(req.cookies && req.cookies[COOKIE_NAME]);
  if (!payload || payload.role !== "admin") {
    return res.status(401).json({ success: false, message: "관리자 로그인이 필요합니다." });
  }
  res.json({ success: true, adminId: payload.adminId });
});

function requireAdmin(req, res, next) {
  const payload = session.verify(req.cookies && req.cookies[COOKIE_NAME]);
  if (!payload || payload.role !== "admin") {
    return res.status(401).json({ success: false, message: "관리자 로그인이 필요합니다." });
  }
  next();
}

module.exports = router;
module.exports.requireAdmin = requireAdmin;
module.exports.COOKIE_NAME = COOKIE_NAME;
