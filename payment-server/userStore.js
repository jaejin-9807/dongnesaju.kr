/**
 * ===================================================================
 * userStore.js
 * ===================================================================
 * 회원(고객/관리자 겸용) 저장소. orderStore.js와 동일하게 JSON 파일
 * 기반으로 동작한다 (users.json). 비밀번호는 Node 내장 crypto의
 * scrypt로 솔트를 붙여 해시해서 저장하며, 평문은 저장하지 않는다.
 *
 * 소셜 로그인(네이버/카카오/구글)은 클라이언트ID/시크릿 발급 후
 * routes/auth.js에서 각 OAuth 콜백을 이 저장소의 findOrCreateBySocial()에
 * 연결하면 된다. 지금은 이메일+비밀번호 방식만 실제로 동작한다.
 * ===================================================================
 */
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { nanoid } = require("nanoid");

const DB_PATH = path.join(__dirname, "users.json");

function readAll() {
  if (!fs.existsSync(DB_PATH)) return {};
  try {
    const raw = fs.readFileSync(DB_PATH, "utf-8");
    return raw ? JSON.parse(raw) : {};
  } catch (e) {
    console.error("회원 데이터 읽기 실패:", e.message);
    return {};
  }
}

function writeAll(data) {
  fs.writeFileSync(DB_PATH, JSON.stringify(data, null, 2), "utf-8");
}

function hashPassword(password, salt) {
  const s = salt || crypto.randomBytes(16).toString("hex");
  const hash = crypto.scryptSync(password, s, 64).toString("hex");
  return { salt: s, hash };
}

function verifyPassword(password, salt, hash) {
  const { hash: computed } = hashPassword(password, salt);
  return crypto.timingSafeEqual(Buffer.from(computed, "hex"), Buffer.from(hash, "hex"));
}

function findByEmail(email) {
  const all = readAll();
  return Object.values(all).find((u) => u.email.toLowerCase() === String(email).toLowerCase()) || null;
}

function findById(userId) {
  const all = readAll();
  return all[userId] || null;
}

/**
 * 이메일+비밀번호로 신규 회원 생성
 */
function createUser({ email, password, name, phone, role }) {
  if (findByEmail(email)) {
    throw new Error("이미 가입된 이메일입니다.");
  }
  const { salt, hash } = hashPassword(password);
  const userId = "user_" + nanoid(12);
  const all = readAll();
  all[userId] = {
    userId,
    email: String(email).toLowerCase(),
    passwordSalt: salt,
    passwordHash: hash,
    name: name || "",
    phone: phone || "",
    role: role || "customer", // 'customer' | 'admin'
    provider: "email",
    createdAt: new Date().toISOString(),
  };
  writeAll(all);
  return sanitize(all[userId]);
}

/**
 * 이메일+비밀번호 로그인 검증
 */
function verifyLogin(email, password) {
  const user = findByEmail(email);
  if (!user) return null;
  if (!verifyPassword(password, user.passwordSalt, user.passwordHash)) return null;
  return sanitize(user);
}

/**
 * 소셜 로그인 자리 (네이버/카카오/구글 키 발급 후 사용)
 * provider: 'naver' | 'kakao' | 'google', socialId: 각 사에서 내려주는 고유ID
 */
function findOrCreateBySocial({ provider, socialId, email, name }) {
  const all = readAll();
  let user = Object.values(all).find((u) => u.provider === provider && u.socialId === socialId);
  if (user) return sanitize(user);

  const userId = "user_" + nanoid(12);
  all[userId] = {
    userId,
    email: email || `${provider}_${socialId}@social.local`,
    name: name || "",
    provider,
    socialId,
    role: "customer",
    createdAt: new Date().toISOString(),
  };
  writeAll(all);
  return sanitize(all[userId]);
}

function sanitize(user) {
  if (!user) return null;
  const { passwordSalt, passwordHash, ...safe } = user;
  return safe;
}

module.exports = { createUser, verifyLogin, findByEmail, findById, findOrCreateBySocial, sanitize };
