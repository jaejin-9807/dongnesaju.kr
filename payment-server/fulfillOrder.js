/**
 * ===================================================================
 * fulfillOrder.js (v3)
 * ===================================================================
 * 결제가 승인 완료된 직후 호출되는 "이행(fulfillment)" 공통 로직.
 *
 * v3 변경사항:
 *   - 결제완료 시 상태를 PAID_WAITING_DELIVERY로 두고, deliverableAt에
 *     "결제시각 + 2시간"을 저장한다. 사장님이 확인하기 전까지 고객
 *     마이페이지에는 "확인 중입니다" 안내가 뜬다 (프론트에서 deliverableAt
 *     기준으로 카운트다운 표시).
 *   - 고객에게 PDF를 자동 생성/발송하지 않는다. 사장님(운영자)에게
 *     "의뢰인 성명 + 결제완료" 알림만 이메일(+카카오톡 자리)로 보낸다.
 *   - 사장님은 /admin.html 에서 계산된 사주 결과를 확인하고,
 *     "운세풀이 시작하기" 버튼으로 PDF를 직접 생성해 전달한다.
 * ===================================================================
 */
const path = require("path");
const fs = require("fs");
const { sendOwnerNotification, sendOwnerKakaoAlert } = require("./mailer");
const orderStore = require("./orderStore");

const PDF_OUTPUT_DIR = path.join(__dirname, "generated_pdfs");
if (!fs.existsSync(PDF_OUTPUT_DIR)) fs.mkdirSync(PDF_OUTPUT_DIR, { recursive: true });

const WAIT_MS = 1000 * 60 * 60 * 2; // 2시간

async function fulfillOrder(orderId) {
  const order = orderStore.getOrder(orderId);
  if (!order) throw new Error("주문을 찾을 수 없습니다: " + orderId);

  const paidAt = new Date().toISOString();
  const deliverableAt = new Date(Date.now() + WAIT_MS).toISOString();

  orderStore.updateOrder(order.orderId, {
    status: "PAID_WAITING_DELIVERY",
    paidAt,
    deliverableAt,
  });
  const updatedOrder = orderStore.getOrder(order.orderId);

  try {
    await sendOwnerNotification(updatedOrder);
    orderStore.updateOrder(order.orderId, { ownerNotified: true });
  } catch (e) {
    console.error("운영자 알림 이메일 발송 실패:", e.message);
    orderStore.updateOrder(order.orderId, { ownerNotified: false, ownerNotifyError: e.message });
  }

  try {
    await sendOwnerKakaoAlert(updatedOrder);
  } catch (e) {
    console.error("카카오톡 알림 시도 중 오류:", e.message);
  }

  return orderStore.getOrder(order.orderId);
}

module.exports = { fulfillOrder, WAIT_MS, PDF_OUTPUT_DIR };
