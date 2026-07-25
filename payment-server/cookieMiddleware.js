/**
 * ===================================================================
 * cookieMiddleware.js
 * ===================================================================
 * cookie-parser 패키지 없이, req.cookies 읽기와 res.cookie() 쓰기를
 * 직접 구현한 아주 단순한 쿠키 미들웨어. (외부 설치 없이 바로 동작)
 * ===================================================================
 */
function parseCookieHeader(header) {
  const out = {};
  if (!header) return out;
  header.split(";").forEach((part) => {
    const idx = part.indexOf("=");
    if (idx === -1) return;
    const key = part.slice(0, idx).trim();
    const val = part.slice(idx + 1).trim();
    if (key) out[key] = decodeURIComponent(val);
  });
  return out;
}

function cookieMiddleware(req, res, next) {
  req.cookies = parseCookieHeader(req.headers.cookie);

  res.cookie = function (name, value, options = {}) {
    let str = `${name}=${encodeURIComponent(value)}`;
    if (options.maxAge) str += `; Max-Age=${Math.floor(options.maxAge / 1000)}`;
    str += `; Path=/`;
    if (options.httpOnly) str += `; HttpOnly`;
    if (options.sameSite) str += `; SameSite=${options.sameSite === "lax" ? "Lax" : options.sameSite}`;
    const prev = res.getHeader("Set-Cookie");
    const arr = prev ? (Array.isArray(prev) ? prev : [prev]) : [];
    arr.push(str);
    res.setHeader("Set-Cookie", arr);
    return res;
  };

  res.clearCookie = function (name) {
    res.cookie(name, "", { maxAge: 0 });
    return res;
  };

  next();
}

module.exports = cookieMiddleware;
