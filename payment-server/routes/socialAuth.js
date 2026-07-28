/**
 * ===================================================================
 * routes/socialAuth.js
 * ===================================================================
 * 네이버 / 카카오 / 구글 소셜 로그인(OAuth 2.0 Authorization Code 방식).
 *
 * 흐름 (3사 공통):
 *   1) 고객이 "OO로 로그인" 버튼 클릭 -> GET /api/auth/:provider
 *      -> 각 사 로그인 페이지로 리다이렉트
 *   2) 고객이 동의 -> 각 사가 콜백 주소(GET /api/auth/:provider/callback)로
 *      code(인가코드)를 담아 되돌려보냄
 *   3) 서버가 code로 access_token 발급받고, 그 토큰으로 프로필(이메일/이름) 조회
 *   4) userStore.findOrCreateBySocial()로 회원 조회/자동가입 후 세션 쿠키 발급
 *   5) 마이페이지(/my.html)로 이동
 *
 * 필요한 .env 값 (없으면 해당 버튼 클릭 시 안내 메시지와 함께 준비중 처리):
 *   NAVER_CLIENT_ID, NAVER_CLIENT_SECRET
 *   KAKAO_CLIENT_ID   (카카오는 REST API 키 하나만 있으면 기본 동작, 시크릿은 선택)
 *   KAKAO_CLIENT_SECRET (선택, 카카오 개발자센터에서 "Client Secret 사용"을 켠 경우만)
 *   GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
 *   BASE_URL (콜백 주소 조립에 사용, 예: http://localhost:3000)
 *
 * 각 사 개발자 콘솔에 등록해야 하는 "Redirect URI(콜백 URL)":
 *   네이버: {BASE_URL}/api/auth/naver/callback
 *   카카오: {BASE_URL}/api/auth/kakao/callback
 *   구글  : {BASE_URL}/api/auth/google/callback
 * ===================================================================
 */
const express = require("express");
const crypto = require("crypto");
// Node 18+ 내장 fetch 우선 사용(없으면 node-fetch 폴백)
const fetch = globalThis.fetch ? globalThis.fetch.bind(globalThis) : require("node-fetch");
const userStore = require("../userStore");
const session = require("../session");
const { COOKIE_NAME } = require("./auth");
const kakaoNotify = require("../kakaoNotify");

const router = express.Router();

// 카카오 REST 키: 소셜 로그인 전용 KAKAO_CLIENT_ID 가 없으면 알림용 KAKAO_REST_KEY 재사용
function kakaoRestKey() {
  return process.env.KAKAO_CLIENT_ID || process.env.KAKAO_REST_KEY || "";
}

function baseUrl() {
  return process.env.BASE_URL || "http://localhost:3000";
}

function redirectUri(provider) {
  return `${baseUrl()}/api/auth/${provider}/callback`;
}

function notConfigured(provider) {
  const map = {
    naver: !process.env.NAVER_CLIENT_ID || !process.env.NAVER_CLIENT_SECRET,
    kakao: !kakaoRestKey(),
    google: !process.env.GOOGLE_CLIENT_ID || !process.env.GOOGLE_CLIENT_SECRET,
  };
  return map[provider];
}

function friendlyName(provider) {
  return { naver: "네이버", kakao: "카카오", google: "구글" }[provider] || provider;
}

/**
 * 로그인 완료 후 세션 쿠키를 발급하고 마이페이지로 보낸다.
 */
function issueSessionAndRedirect(res, user) {
  const token = session.sign({ userId: user.userId, role: user.role || "customer" });
  session.setCookie(res, COOKIE_NAME, token);
  res.redirect("/my.html");
}

function redirectWithError(res, message) {
  res.redirect(`/login.html?socialError=${encodeURIComponent(message)}`);
}

// ---------------------------------------------------------------
// 1) 로그인 시작 -> 각 사 인가(authorize) 페이지로 리다이렉트
// ---------------------------------------------------------------
router.get("/:provider", (req, res, next) => {
  const { provider } = req.params;
  if (!["naver", "kakao", "google"].includes(provider)) return next();

  if (notConfigured(provider)) {
    return redirectWithError(res, `${friendlyName(provider)} 로그인은 아직 키 등록 전이라 준비 중입니다.`);
  }

  const state = crypto.randomBytes(16).toString("hex");
  res.cookie("saju_oauth_state", state, { httpOnly: true, maxAge: 5 * 60 * 1000, sameSite: "lax" });

  let authUrl;
  if (provider === "naver") {
    authUrl = `https://nid.naver.com/oauth2.0/authorize?response_type=code`
      + `&client_id=${encodeURIComponent(process.env.NAVER_CLIENT_ID)}`
      + `&redirect_uri=${encodeURIComponent(redirectUri("naver"))}`
      + `&state=${state}`;
  } else if (provider === "kakao") {
    authUrl = `https://kauth.kakao.com/oauth/authorize?response_type=code`
      + `&client_id=${encodeURIComponent(kakaoRestKey())}`
      + `&redirect_uri=${encodeURIComponent(redirectUri("kakao"))}`
      + `&state=${state}`;
  } else if (provider === "google") {
    authUrl = `https://accounts.google.com/o/oauth2/v2/auth?response_type=code`
      + `&client_id=${encodeURIComponent(process.env.GOOGLE_CLIENT_ID)}`
      + `&redirect_uri=${encodeURIComponent(redirectUri("google"))}`
      + `&scope=${encodeURIComponent("openid email profile")}`
      + `&state=${state}`;
  }
  res.redirect(authUrl);
});

// ---------------------------------------------------------------
// 2) 콜백 -> code로 토큰 교환 -> 프로필 조회 -> 회원 조회/생성 -> 세션 발급
// ---------------------------------------------------------------
router.get("/:provider/callback", async (req, res, next) => {
  const { provider } = req.params;
  if (!["naver", "kakao", "google"].includes(provider)) return next();

  const { code, state, error, error_description } = req.query;
  const savedState = req.cookies && req.cookies["saju_oauth_state"];
  res.clearCookie("saju_oauth_state");

  if (error) {
    return redirectWithError(res, `${friendlyName(provider)} 로그인이 취소되었습니다: ${error_description || error}`);
  }
  if (!code) {
    return redirectWithError(res, `${friendlyName(provider)} 로그인 인가 코드가 없습니다.`);
  }
  if (provider !== "kakao" && (!state || state !== savedState)) {
    // 카카오는 state 미전달 환경이 종종 있어 완화 적용, 네이버/구글은 엄격 검증
    return redirectWithError(res, "로그인 요청 검증에 실패했습니다. 다시 시도해 주세요.");
  }

  try {
    let profile; // { socialId, email, name }

    if (provider === "naver") {
      const tokenRes = await fetch(
        `https://nid.naver.com/oauth2.0/token?grant_type=authorization_code`
        + `&client_id=${encodeURIComponent(process.env.NAVER_CLIENT_ID)}`
        + `&client_secret=${encodeURIComponent(process.env.NAVER_CLIENT_SECRET)}`
        + `&code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}`
      );
      const tokenJson = await tokenRes.json();
      if (!tokenJson.access_token) throw new Error("네이버 토큰 발급 실패: " + JSON.stringify(tokenJson));

      const profRes = await fetch("https://openapi.naver.com/v1/nid/me", {
        headers: { Authorization: `Bearer ${tokenJson.access_token}` },
      });
      const profJson = await profRes.json();
      const info = profJson.response || {};
      profile = { socialId: info.id, email: info.email, name: info.name || info.nickname };
    }

    if (provider === "kakao") {
      const params = new URLSearchParams({
        grant_type: "authorization_code",
        client_id: kakaoRestKey(),
        redirect_uri: redirectUri("kakao"),
        code: String(code),
      });
      if (process.env.KAKAO_CLIENT_SECRET) params.set("client_secret", process.env.KAKAO_CLIENT_SECRET);

      const tokenRes = await fetch("https://kauth.kakao.com/oauth/token", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: params,
      });
      const tokenJson = await tokenRes.json();
      if (!tokenJson.access_token) throw new Error("카카오 토큰 발급 실패: " + JSON.stringify(tokenJson));

      const profRes = await fetch("https://kapi.kakao.com/v2/user/me", {
        headers: { Authorization: `Bearer ${tokenJson.access_token}` },
      });
      const profJson = await profRes.json();
      const account = profJson.kakao_account || {};
      profile = {
        socialId: String(profJson.id),
        email: account.email,
        name: (account.profile && account.profile.nickname) || "",
      };
    }

    if (provider === "google") {
      const params = new URLSearchParams({
        grant_type: "authorization_code",
        client_id: process.env.GOOGLE_CLIENT_ID,
        client_secret: process.env.GOOGLE_CLIENT_SECRET,
        redirect_uri: redirectUri("google"),
        code: String(code),
      });
      const tokenRes = await fetch("https://oauth2.googleapis.com/token", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: params,
      });
      const tokenJson = await tokenRes.json();
      if (!tokenJson.access_token) throw new Error("구글 토큰 발급 실패: " + JSON.stringify(tokenJson));

      const profRes = await fetch("https://www.googleapis.com/oauth2/v2/userinfo", {
        headers: { Authorization: `Bearer ${tokenJson.access_token}` },
      });
      const profJson = await profRes.json();
      profile = { socialId: profJson.id, email: profJson.email, name: profJson.name || "" };
    }

    if (!profile || !profile.socialId) {
      throw new Error("프로필 정보를 가져오지 못했습니다.");
    }

    const user = userStore.findOrCreateBySocial({
      provider,
      socialId: profile.socialId,
      email: profile.email,
      name: profile.name,
    });

    // 처음 가입한 소셜 회원이면 사장님에게 카카오톡 알림 전송
    if (user && user._isNew) {
      kakaoNotify.notify(
        `🙋 [동네사주카페] 새 회원가입 (${friendlyName(provider)})\n` +
        `· 이름: ${user.name || "-"}\n` +
        `· 이메일: ${user.email || "-"}`
      );
    }

    issueSessionAndRedirect(res, user);
  } catch (e) {
    console.error(`${friendlyName(provider)} 로그인 오류:`, e.message);
    redirectWithError(res, `${friendlyName(provider)} 로그인 처리 중 오류가 발생했습니다: ${e.message}`);
  }
});

module.exports = router;
