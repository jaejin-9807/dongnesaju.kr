/**
 * ===================================================================
 * routes/auth.js
 * ===================================================================
 * 고객 회원가입/로그인/로그아웃/내정보 API.
 *
 * 소셜 로그인(네이버/카카오/구글)은 각사 개발자 콘솔에서 클라이언트ID와
 * 시크릿을 발급받은 뒤 이 파일에 OAuth 콜백 라우트를 추가하고
 * userStore.findOrCreateBySocial()을 호출하면 된다. 지금은 이메일+비밀번호
 * 방식만 실제로 동작하며, 소셜 버튼은 프론트에서 안내 문구만 표시한다.
 * ===================================================================
 */
const express = require("express");
const userStore = require("../userStore");
const session = require("../session");
const kakaoNotify = require("../kakaoNotify");

const router = express.Router();
const COOKIE_NAME = "saju_session";

router.post("/signup", (req, res) => {
  const { email, password, name, phone } = req.body;
  if (!email || !password || !name) {
    return res.status(400).json({ success: false, message: "이메일, 비밀번호, 이름은 필수입니다." });
  }
  if (String(password).length < 4) {
    return res.status(400).json({ success: false, message: "비밀번호는 4자 이상이어야 합니다." });
  }
  try {
    const user = userStore.createUser({ email, password, name, phone, role: "customer" });
    const token = session.sign({ userId: user.userId, role: user.role });
    session.setCookie(res, COOKIE_NAME, token);
    // 사장님에게 카카오톡 알림(새 회원가입) — 설정돼 있을 때만 전송
    kakaoNotify.notify(
      `🙋 [동네사주카페] 새 회원가입\n· 이름: ${name}\n· 이메일: ${email}\n· 연락처: ${phone || "-"}`
    );
    res.json({ success: true, user });
  } catch (e) {
    res.status(400).json({ success: false, message: e.message });
  }
});

router.post("/login", (req, res) => {
  const { email, password } = req.body;
  if (!email || !password) {
    return res.status(400).json({ success: false, message: "이메일과 비밀번호를 입력해 주세요." });
  }
  const user = userStore.verifyLogin(email, password);
  if (!user) {
    return res.status(401).json({ success: false, message: "이메일 또는 비밀번호가 올바르지 않습니다." });
  }
  const token = session.sign({ userId: user.userId, role: user.role });
  session.setCookie(res, COOKIE_NAME, token);
  res.json({ success: true, user });
});

router.post("/logout", (req, res) => {
  session.clearCookie(res, COOKIE_NAME);
  res.json({ success: true });
});

router.get("/me", (req, res) => {
  const payload = session.verify(req.cookies && req.cookies[COOKIE_NAME]);
  if (!payload) return res.status(401).json({ success: false, message: "로그인이 필요합니다." });
  const user = userStore.findById(payload.userId);
  if (!user) return res.status(401).json({ success: false, message: "로그인이 필요합니다." });
  res.json({ success: true, user: userStore.sanitize(user) });
});

/**
 * 로그인한 고객만 통과시키는 미들웨어 (다른 라우트에서 재사용)
 */
function requireCustomer(req, res, next) {
  const payload = session.verify(req.cookies && req.cookies[COOKIE_NAME]);
  if (!payload) return res.status(401).json({ success: false, message: "로그인이 필요합니다." });
  const user = userStore.findById(payload.userId);
  if (!user) return res.status(401).json({ success: false, message: "로그인이 필요합니다." });
  req.currentUser = user;
  next();
}

module.exports = router;
module.exports.requireCustomer = requireCustomer;
module.exports.COOKIE_NAME = COOKIE_NAME;
