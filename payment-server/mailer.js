/**
 * ===================================================================
 * mailer.js (v2)
 * ===================================================================
 * 결제 완료 시 사장님(운영자)에게 "의뢰인 성명 + 결제완료" 알림을 보내는 모듈.
 * SMTP 설정은 .env의 MAIL_* 값을 사용한다. (예: 네이버 메일, Gmail 등)
 *
 * 고객에게 결과 PDF를 자동 발송하지 않는다. 사장님이 /api/orders 목록에서
 * 계산 결과를 확인하고, 결과지를 직접 만들어 의뢰인에게 전달하는 방식이다.
 *
 * ★ 카카오톡(비즈메시지/알림톡) 발송은 아직 연동되어 있지 않습니다.
 *   카카오 비즈메시지 발신프로필/템플릿 승인이 완료되면
 *   sendOwnerKakaoAlert() 자리에 실제 호출을 추가하면 됩니다.
 *   (지금은 로그만 남기고 아무 동작도 하지 않습니다.)
 * ===================================================================
 */
const nodemailer = require("nodemailer");

function getTransporter() {
  const host = process.env.MAIL_HOST;
  const port = Number(process.env.MAIL_PORT || 465);
  const user = process.env.MAIL_USER;
  const pass = process.env.MAIL_PASS;

  if (!host || !user || !pass) {
    throw new Error("메일 발송 설정(MAIL_HOST, MAIL_USER, MAIL_PASS)이 .env에 없습니다.");
  }

  return nodemailer.createTransport({
    host,
    port,
    secure: port === 465,
    auth: { user, pass },
  });
}

function summarizePerson(label, person) {
  if (!person) return "";
  const b = person.sajuInfo || person;
  return (
    `${label}: ${person.name || "-"}` +
    (person.nameHanja ? `(${person.nameHanja})` : "") +
    ` / ${person.gender || "-"} / ${b.year || "-"}년 ${b.month || "-"}월 ${b.day || "-"}일` +
    (b.hour ? ` ${b.hour}시${b.minute ? b.minute + "분" : ""}` : "") +
    ` (${b.calendarType || person.calendarType || "-"})` +
    (person.zodiac ? ` / ${person.zodiac}` : "")
  );
}

/**
 * 사장님(운영자)에게 "의뢰인 성명 + 결제완료" 알림 메일을 보낸다.
 * order: orderStore의 주문 객체 (person1, person2, sajuResult 등 포함)
 */
async function sendOwnerNotification(order) {
  const notifyEmail = process.env.NOTIFY_EMAIL;
  if (!notifyEmail) {
    console.log("[운영자 알림 미발송] .env에 NOTIFY_EMAIL이 설정되어 있지 않습니다.");
    return null;
  }

  const transporter = getTransporter();
  const fromName = process.env.MAIL_FROM_NAME || "동네사주카페";
  const fromAddress = process.env.MAIL_USER;

  const personLines = [summarizePerson("의뢰인", order.person1)];
  if (order.person2) personLines.push(summarizePerson("상대방", order.person2));

  return transporter.sendMail({
    from: `"${fromName}" <${fromAddress}>`,
    to: notifyEmail,
    subject: `[결제완료] ${order.customerName}님 - ${order.orderName} (${order.amount.toLocaleString()}원)`,
    text:
      `새 결제가 완료되었습니다.\n\n` +
      `주문번호: ${order.orderId}\n` +
      `상품명: ${order.orderName}\n` +
      `금액: ${order.amount.toLocaleString()}원\n` +
      `결제수단: ${order.pg || "-"}\n\n` +
      `의뢰인 연락처: ${order.customerName} (${order.customerEmail}, ${order.customerPhone || "-"})\n\n` +
      personLines.join("\n") +
      `\n\n관리자 페이지(/api/orders)에서 계산된 사주 결과를 확인하고,\n` +
      `결과지를 직접 만들어 의뢰인에게 전달해 주세요.`,
    html:
      `<div style="font-family:sans-serif;line-height:1.8;">` +
      `<p><b>새 결제가 완료되었습니다.</b></p>` +
      `<p>주문번호: ${order.orderId}<br>` +
      `상품명: <b>${order.orderName}</b><br>` +
      `금액: <b>${order.amount.toLocaleString()}원</b><br>` +
      `결제수단: ${order.pg || "-"}</p>` +
      `<p>의뢰인 연락처: ${order.customerName} (${order.customerEmail}, ${order.customerPhone || "-"})</p>` +
      `<p>${personLines.join("<br>")}</p>` +
      `<p style="color:#8B4513;">관리자 페이지(/api/orders)에서 계산된 사주 결과를 확인하고,<br>` +
      `결과지를 직접 만들어 의뢰인에게 전달해 주세요.</p>` +
      `</div>`,
  });
}

/**
 * 카카오톡(비즈메시지) 알림 자리 (미구현 - 발신프로필/템플릿 승인 후 연동)
 */
async function sendOwnerKakaoAlert(order) {
  console.log(
    `[카카오톡 미연동] "${order.customerName}님 결제완료" 알림을 카카오톡으로 보내려고 했으나, ` +
    `카카오 비즈메시지 연동이 아직 설정되지 않아 건너뜁니다. ` +
    `(.env에 KAKAO_BIZ_* 값 추가 후 이 함수에 실제 발송 API 호출을 구현하세요)`
  );
  return null;
}

/**
 * 의뢰인(고객)에게 완성된 PDF 결과지를 메일로 직접 발송한다.
 * 관리자 페이지에서 "메일로 보내기" 버튼을 누르면 호출된다.
 * order.customerEmail에 이미 저장된 주소로 보내므로, 관리자가 메일 주소를
 * 따로 입력할 필요 없이 원클릭으로 발송할 수 있다.
 */
async function sendResultToCustomer(order, pdfPath) {
  if (!order.customerEmail) {
    throw new Error("주문에 저장된 고객 이메일이 없습니다.");
  }

  const transporter = getTransporter();
  const fromName = process.env.MAIL_FROM_NAME || "동네사주카페";
  const fromAddress = process.env.MAIL_USER;
  const attachmentName = `${order.customerName}_사주풀이_결과지.pdf`;

  return transporter.sendMail({
    from: `"${fromName}" <${fromAddress}>`,
    to: order.customerEmail,
    subject: `[동네사주카페] ${order.customerName}님의 ${order.orderName} 결과지가 도착했습니다`,
    text:
      `${order.customerName}님, 안녕하세요.\n\n` +
      `요청하신 "${order.orderName}" 결과지를 첨부파일로 보내드립니다.\n` +
      `첨부된 PDF 파일을 열어 확인해 주세요.\n\n` +
      `이용해 주셔서 감사합니다.\n동네사주카페 드림`,
    html:
      `<div style="font-family:sans-serif;line-height:1.8;">` +
      `<p>${order.customerName}님, 안녕하세요.</p>` +
      `<p>요청하신 <b>${order.orderName}</b> 결과지를 첨부파일로 보내드립니다.<br>` +
      `첨부된 PDF 파일을 열어 확인해 주세요.</p>` +
      `<p>이용해 주셔서 감사합니다.<br>동네사주카페 드림</p>` +
      `</div>`,
    attachments: [
      {
        filename: attachmentName,
        path: pdfPath,
      },
    ],
  });
}

/**
 * 의뢰인(고객)에게 완성된 PDF 결과지를 문자(SMS/알림톡)로 안내한다.
 * ★ 아직 실제 문자 발송사(SENS, 알리고 등) 연동이 되어 있지 않은 스텁입니다.
 *   .env에 SMS_API_KEY 등 관련 값이 채워지면, 이 함수 내부에서 실제 문자
 *   발송 API를 호출하도록 구현을 채워 넣으면 됩니다. 지금은 관리자 페이지의
 *   "문자로 보내기" 버튼을 눌러도 로그만 남고 실제 문자는 발송되지 않습니다.
 */
async function sendResultSmsToCustomer(order, downloadUrl) {
  if (!order.customerPhone) {
    throw new Error("주문에 저장된 고객 연락처가 없습니다.");
  }
  console.log(
    `[문자 미연동] ${order.customerPhone}로 "${order.customerName}님의 ${order.orderName} 결과지가 준비되었습니다" ` +
    `문자를 보내려고 했으나, SMS 발송 연동이 아직 설정되지 않아 건너뜁니다. ` +
    `(.env에 SMS 발송사 API 키 추가 후 mailer.js의 sendResultSmsToCustomer() 안에 실제 호출을 구현하세요)`
  );
  return { simulated: true, phone: order.customerPhone };
}

module.exports = {
  sendOwnerNotification,
  sendOwnerKakaoAlert,
  sendResultToCustomer,
  sendResultSmsToCustomer,
};
