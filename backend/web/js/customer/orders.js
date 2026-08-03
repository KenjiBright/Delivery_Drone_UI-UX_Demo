// Danh sách đơn và màn theo dõi chi tiết.

import { api } from '../api.js';
import { icon } from '../icons.js';
import {
  TRACK_STEPS, createMap, distanceMeters, escapeHtml, formatDateTime, formatDuration,
  formatMoney, formatTime, formatWeight, markerIcon, ratingStars, statusBadge, statusLabel,
  stepIndex, toast, uavStatusBadge,
} from '../ui.js';
import { homePoint, loadOrders, loadUavs, state, uavById } from './store.js';

let map = null;
let layers = null;
let ratingValue = 0;
let openTracking = () => {};

export function initOrders({ onOpenTracking }) {
  openTracking = onOpenTracking;

  document.querySelectorAll('.segmented__item').forEach((tab) => {
    tab.onclick = () => {
      document.querySelectorAll('.segmented__item').forEach((item) => {
        item.classList.toggle('is-active', item === tab);
        item.setAttribute('aria-selected', String(item === tab));
      });
      state.orderScope = tab.dataset.scope;
      loadOrders();
    };
  });

  document.getElementById('btn-verify').addEventListener('click', verifyPin);
  document.getElementById('btn-rate').addEventListener('click', submitRating);
  renderStars();
}

// ---------- Danh sách ----------

export function renderOrderList() {
  const container = document.getElementById('order-list');
  if (!state.orders.length) {
    container.innerHTML = `
      <div class="empty">
        ${icon('inbox', { size: 34 })}
        <strong>${state.orderScope === 'active' ? 'Chưa có đơn nào đang giao' : 'Chưa có đơn nào trong lịch sử'}</strong>
        <p>Đặt hàng ở trang chủ để thấy tiến trình giao bằng drone tại đây.</p>
      </div>`;
    return;
  }

  container.innerHTML = state.orders.map((order) => `
    <button class="card order-card" data-order="${escapeHtml(order.id)}">
      <div class="order-card__top">
        <span class="order-card__id">${escapeHtml(order.id)}</span>
        ${statusBadge(order.status)}
      </div>
      <p class="order-card__addr">${escapeHtml(order.delivery_address)}</p>
      <div class="order-card__foot">
        ${icon('clock', { size: 14 })}<span>${formatDateTime(order.created_at)}</span>
        ${order.rating ? `${icon('star', { size: 14, className: 'icon--filled' })}<span>${order.rating}</span>` : ''}
        <span class="order-card__total">${formatMoney(order.total_price)}</span>
      </div>
    </button>`).join('');

  container.querySelectorAll('[data-order]').forEach((button) => {
    button.onclick = () => openTracking(button.dataset.order);
  });
}

// ---------- Theo dõi ----------

export async function renderTracking(orderId) {
  let order;
  try {
    order = await api.get(`/api/orders/${orderId}`);
  } catch (error) {
    toast(error.message, 'error');
    return;
  }
  await loadUavs();
  paintTracking(order);
}

/** Vẽ lại màn theo dõi từ dữ liệu đơn; bản đồ được giữ nguyên giữa các lần cập nhật. */
export function paintTracking(order) {
  state.trackedOrderId = order.id;
  const uav = order.assigned_uav ? uavById(order.assigned_uav) : null;

  document.getElementById('track-title').textContent = order.id;
  document.getElementById('track-status-badge').innerHTML = statusBadge(order.status);
  renderSteps(order.status);
  updateMap(order, uav);
  renderEta(order, uav);
  renderUav(uav);

  document.getElementById('pin-card').classList.toggle('hidden', order.status !== 'ARRIVED');
  const canRate = order.status === 'COMPLETED' && !order.rating;
  document.getElementById('rate-card').classList.toggle('hidden', !canRate);

  renderDetail(order);
}

function renderSteps(status) {
  const current = stepIndex(status);
  const cancelled = status === 'CANCELLED';
  document.getElementById('track-steps').innerHTML = TRACK_STEPS.map((step, index) => {
    const cls = cancelled ? '' : index < current ? 'is-done' : index === current ? 'is-current' : '';
    return `
      <div class="track-step ${cls}">
        <span class="track-step__dot">${icon(index < current && !cancelled ? 'check' : step.icon, { size: 16 })}</span>
        <span class="track-step__label">${escapeHtml(step.label)}</span>
      </div>`;
  }).join('');
}

function updateMap(order, uav) {
  const target = [order.delivery_lat, order.delivery_lon];
  const uavPoint = uav ? [uav.lat, uav.lon] : homePoint();

  if (!map) {
    map = createMap(document.getElementById('track-map'), uavPoint, { zoom: 14.5 });
    layers = {
      home: L.marker(homePoint(), { icon: markerIcon('home') }).addTo(map),
      target: L.marker(target, { icon: markerIcon('target') }).addTo(map),
      uav: L.marker(uavPoint, { icon: markerIcon('uav', { heading: uav?.heading || 0 }) }).addTo(map),
      route: L.polyline([homePoint(), uavPoint, target], { color: '#2563eb', weight: 4, opacity: .85 }).addTo(map),
    };
    map.fitBounds(L.latLngBounds([homePoint(), target]), { padding: [40, 40] });
    return;
  }

  layers.home.setLatLng(homePoint());
  layers.target.setLatLng(target);
  layers.uav.setLatLng(uavPoint).setIcon(markerIcon('uav', { heading: uav?.heading || 0 }));
  layers.route.setLatLngs([homePoint(), uavPoint, target]);
}

export function resizeMap() {
  map?.invalidateSize();
}

function renderEta(order, uav) {
  const value = document.getElementById('eta-value');
  const target = [order.delivery_lat, order.delivery_lon];

  if (order.status === 'COMPLETED') return void (value.textContent = 'Đã hoàn thành');
  if (order.status === 'CANCELLED') return void (value.textContent = 'Đơn đã huỷ');
  if (order.status === 'ARRIVED') return void (value.textContent = 'UAV đang chờ bạn');
  if (order.status === 'DELIVERED' || order.status === 'RETURNING') return void (value.textContent = 'Đã giao xong');

  if (uav && uav.speed > 0.5) {
    const seconds = distanceMeters([uav.lat, uav.lon], target) / uav.speed;
    value.textContent = `khoảng ${formatDuration(seconds)}`;
    return;
  }
  value.textContent = order.status === 'PENDING' ? 'Chờ điều phối xác nhận' : 'Đang chuẩn bị';
}

function renderUav(uav) {
  const card = document.getElementById('uav-card');
  card.classList.toggle('hidden', !uav);
  if (!uav) return;
  document.getElementById('uav-id').textContent = uav.id;
  document.getElementById('uav-model').textContent = uav.model;
  document.getElementById('uav-status-badge').innerHTML = uavStatusBadge(uav.status);
  document.getElementById('uav-battery').textContent = `${uav.battery.toFixed(0)}%`;
  document.getElementById('uav-altitude').textContent = `${uav.altitude.toFixed(1)} m`;
  document.getElementById('uav-speed').textContent = `${uav.speed.toFixed(1)} m/s`;
}

function renderDetail(order) {
  const events = order.events || [];
  document.getElementById('track-detail').innerHTML = `
    <h3 style="font-size:16px;margin-bottom:var(--sp-3)">Chi tiết đơn</h3>
    <dl style="margin:0">
      <div class="detail-row"><dt>Điểm giao</dt><dd>${escapeHtml(order.delivery_address)}</dd></div>
      ${order.note ? `<div class="detail-row"><dt>Ghi chú</dt><dd>${escapeHtml(order.note)}</dd></div>` : ''}
      <div class="detail-row"><dt>Khối lượng</dt><dd>${formatWeight(order.total_weight_kg)}</dd></div>
      <div class="detail-row"><dt>Thanh toán</dt><dd>${formatMoney(order.total_price)}</dd></div>
      <div class="detail-row"><dt>PIN nhận hàng</dt><dd class="tnum" style="color:var(--brand-700);font-weight:700">${escapeHtml(order.verification_code)}</dd></div>
      ${order.cancel_reason ? `<div class="detail-row"><dt>Lý do huỷ</dt><dd>${escapeHtml(order.cancel_reason)}</dd></div>` : ''}
      ${order.rating ? `<div class="detail-row"><dt>Đánh giá</dt><dd>${ratingStars(order.rating)}${order.review ? ` — ${escapeHtml(order.review)}` : ''}</dd></div>` : ''}
    </dl>

    <h3 style="font-size:16px;margin:var(--sp-5) 0 var(--sp-3)">Sản phẩm</h3>
    <div class="stack">
      ${order.items.map((item) => `
        <div class="detail-row" style="padding:0">
          <dd>${escapeHtml(item.name)} × ${item.quantity}</dd>
          <dd style="flex:none;font-weight:600">${formatMoney(item.line_price)}</dd>
        </div>`).join('')}
    </div>

    ${events.length ? `
      <h3 style="font-size:16px;margin:var(--sp-5) 0 var(--sp-3)">Nhật ký</h3>
      <div class="timeline">
        ${events.slice().reverse().map((event) => `
          <div class="timeline__item">
            <span class="timeline__time">${formatTime(event.created_at)}</span>
            <div class="timeline__body">
              <strong>${escapeHtml(statusLabel(event.status))}</strong>
              <small>${escapeHtml(event.note || event.actor)}</small>
            </div>
          </div>`).join('')}
      </div>` : ''}`;
}

// ---------- Xác nhận PIN & đánh giá ----------

async function verifyPin() {
  const input = document.getElementById('pin-input');
  const code = input.value.trim();
  if (code.length !== 4) return toast('Mã PIN gồm 4 chữ số', 'error');

  const button = document.getElementById('btn-verify');
  button.disabled = true;
  try {
    await api.post(`/api/orders/${state.trackedOrderId}/verify`, { code });
    input.value = '';
    toast('Đã xác nhận nhận hàng. UAV đang quay về.', 'success');
    await renderTracking(state.trackedOrderId);
  } catch (error) {
    toast(error.message, 'error');
  } finally {
    button.disabled = false;
  }
}

function renderStars() {
  const container = document.getElementById('rate-stars');
  container.innerHTML = [1, 2, 3, 4, 5].map((value) => `
    <button class="star ${value <= ratingValue ? 'is-on' : ''}" data-star="${value}"
            role="radio" aria-checked="${value === ratingValue}" aria-label="${value} sao">
      ${icon('star', { size: 26, className: value <= ratingValue ? 'icon--filled' : '' })}
    </button>`).join('');

  container.querySelectorAll('[data-star]').forEach((button) => {
    button.onclick = () => {
      ratingValue = Number(button.dataset.star);
      renderStars();
    };
  });
}

async function submitRating() {
  if (!ratingValue) return toast('Hãy chọn số sao', 'error');
  try {
    await api.post(`/api/orders/${state.trackedOrderId}/rate`, {
      rating: ratingValue,
      review: document.getElementById('rate-review').value.trim(),
    });
    ratingValue = 0;
    document.getElementById('rate-review').value = '';
    renderStars();
    toast('Cảm ơn bạn đã đánh giá', 'success');
    await renderTracking(state.trackedOrderId);
  } catch (error) {
    toast(error.message, 'error');
  }
}
