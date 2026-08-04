// Tiện ích hiển thị: định dạng, nhãn trạng thái, toast, modal, bản đồ.

import { icon } from './icons.js';

// ---------- Định dạng ----------

export function formatMoney(value) {
  return `${Number(value || 0).toLocaleString('vi-VN')} đ`;
}

export function formatWeight(value) {
  return `${Number(value || 0).toFixed(2)} kg`;
}

export function formatDateTime(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('vi-VN', {
    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
  });
}

export function formatTime(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' });
}

export function formatDuration(seconds) {
  if (seconds === null || seconds === undefined) return '—';
  const total = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  return minutes ? `${minutes} phút ${rest.toString().padStart(2, '0')} giây` : `${rest} giây`;
}

export function relativeTime(iso) {
  if (!iso) return '—';
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return 'vừa xong';
  if (diff < 3600) return `${Math.floor(diff / 60)} phút trước`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} giờ trước`;
  return `${Math.floor(diff / 86400)} ngày trước`;
}

export function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (ch) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]
  ));
}

// ---------- Trạng thái đơn ----------

const STATUS = {
  PENDING:    { label: 'Chờ xác nhận', tone: 'pending',  icon: 'clock' },
  CONFIRMED:  { label: 'Đã xác nhận',  tone: 'progress', icon: 'check' },
  ASSIGNED:   { label: 'Đã gán UAV',   tone: 'progress', icon: 'drone' },
  DISPATCHED: { label: 'Chuẩn bị bay', tone: 'progress', icon: 'navigation' },
  IN_FLIGHT:  { label: 'Đang giao',    tone: 'progress', icon: 'route' },
  ARRIVED:    { label: 'Đã đến nơi',   tone: 'progress', icon: 'map-pin' },
  DELIVERED:  { label: 'Đã giao',      tone: 'success',  icon: 'check-circle' },
  RETURNING:  { label: 'UAV quay về',  tone: 'progress', icon: 'refresh' },
  COMPLETED:  { label: 'Hoàn thành',   tone: 'success',  icon: 'check-circle' },
  CANCELLED:  { label: 'Đã huỷ',       tone: 'danger',   icon: 'close' },
};

export function statusLabel(status) {
  return STATUS[status]?.label ?? status;
}

export function statusBadge(status) {
  const info = STATUS[status] ?? { label: status, tone: '', icon: 'alert-circle' };
  return `<span class="badge badge--${info.tone}">${icon(info.icon, { size: 13 })}${escapeHtml(info.label)}</span>`;
}

const UAV_STATUS = {
  AVAILABLE: { label: 'Sẵn sàng', tone: 'success' },
  RESERVED: { label: 'Đã giữ chỗ', tone: 'pending' },
  DELIVERING: { label: 'Đang giao', tone: 'progress' },
  WAITING_CONFIRMATION: { label: 'Chờ xác nhận', tone: 'pending' },
  RETURNING: { label: 'Đang về', tone: 'progress' },
  MAINTENANCE: { label: 'Bảo trì', tone: 'danger' },
  OFFLINE: { label: 'Ngoại tuyến', tone: '' },
};

export function uavStatusLabel(status) {
  return UAV_STATUS[status]?.label ?? status;
}

export function uavStatusBadge(status) {
  const info = UAV_STATUS[status] ?? { label: status, tone: '' };
  return `<span class="badge badge--${info.tone} badge--dot">${escapeHtml(info.label)}</span>`;
}

/** Hiển thị điểm đánh giá bằng icon SVG thay vì ký tự sao, để đồng bộ với bộ icon. */
export function ratingStars(value, { size = 14 } = {}) {
  const score = Math.round(value || 0);
  const stars = [1, 2, 3, 4, 5].map((index) =>
    icon('star', { size, className: index <= score ? 'icon--filled' : '' })
  ).join('');
  return `<span class="rating" role="img" aria-label="${score} trên 5 sao"
                style="display:inline-flex;gap:2px;color:var(--rate-star, #b45309);vertical-align:middle">${stars}</span>`;
}

// Các mốc hiển thị trên thanh tiến trình giao hàng.
export const TRACK_STEPS = [
  { key: 'PENDING', label: 'Đặt đơn', icon: 'receipt' },
  { key: 'CONFIRMED', label: 'Xác nhận', icon: 'check' },
  { key: 'DISPATCHED', label: 'Cất cánh', icon: 'drone' },
  { key: 'ARRIVED', label: 'Đến nơi', icon: 'map-pin' },
  { key: 'COMPLETED', label: 'Hoàn tất', icon: 'check-circle' },
];

const STEP_INDEX = {
  PENDING: 0, CONFIRMED: 1, ASSIGNED: 1, DISPATCHED: 2, IN_FLIGHT: 2,
  ARRIVED: 3, DELIVERED: 3, RETURNING: 4, COMPLETED: 4,
};

export function stepIndex(status) {
  return STEP_INDEX[status] ?? 0;
}

// ---------- Toast ----------

function toastStack() {
  let stack = document.querySelector('.toast-stack');
  if (!stack) {
    stack = document.createElement('div');
    stack.className = 'toast-stack';
    // aria-live để trình đọc màn hình thông báo mà không cướp focus.
    stack.setAttribute('aria-live', 'polite');
    document.body.appendChild(stack);
  }
  return stack;
}

export function toast(message, variant = '') {
  const element = document.createElement('div');
  element.className = `toast ${variant ? `toast--${variant}` : ''}`;
  const glyph = variant === 'error' ? 'alert-circle' : variant === 'success' ? 'check-circle' : 'bell';
  element.innerHTML = `${icon(glyph, { size: 18 })}<span>${escapeHtml(message)}</span>`;
  toastStack().appendChild(element);
  setTimeout(() => element.remove(), 3600);
}

// ---------- Modal ----------

/**
 * Mở hộp thoại. `render` nhận hàm close và trả về HTML.
 * Trả về một Promise hoàn tất khi hộp thoại đóng.
 */
export function openModal({ title, body, actions = [], onMount }) {
  return new Promise((resolve) => {
    const scrim = document.createElement('div');
    scrim.className = 'modal-scrim';
    scrim.setAttribute('role', 'dialog');
    scrim.setAttribute('aria-modal', 'true');
    scrim.innerHTML = `
      <div class="modal">
        <div class="modal__head">
          <h3>${escapeHtml(title)}</h3>
          <button class="btn btn--icon btn--sm" data-close aria-label="Đóng">${icon('close', { size: 18 })}</button>
        </div>
        <div class="modal__body">${body}</div>
        ${actions.length ? `<div class="modal__actions">${actions.map((action, index) =>
          `<button class="btn ${action.variant ? `btn--${action.variant}` : ''}" data-action="${index}">${escapeHtml(action.label)}</button>`
        ).join('')}</div>` : ''}
      </div>`;

    const previousFocus = document.activeElement;
    function close(result) {
      document.removeEventListener('keydown', onKey);
      scrim.remove();
      previousFocus?.focus?.();
      resolve(result);
    }
    function onKey(event) {
      if (event.key === 'Escape') close(null);
    }

    scrim.querySelector('[data-close]').onclick = () => close(null);
    scrim.onclick = (event) => { if (event.target === scrim) close(null); };
    document.addEventListener('keydown', onKey);

    actions.forEach((action, index) => {
      scrim.querySelector(`[data-action="${index}"]`).onclick = async () => {
        const value = action.onClick ? await action.onClick(scrim) : true;
        if (value !== false) close(value);
      };
    });

    document.body.appendChild(scrim);
    onMount?.(scrim, close);
    scrim.querySelector('input, textarea, select, button')?.focus();
  });
}

export function confirmDialog(title, message, confirmLabel = 'Xác nhận') {
  return openModal({
    title,
    body: `<p style="color:var(--text-muted)">${escapeHtml(message)}</p>`,
    actions: [
      { label: 'Đóng', variant: 'secondary', onClick: () => null },
      { label: confirmLabel, variant: 'danger', onClick: () => true },
    ],
  });
}

// ---------- Bản đồ ----------

export function createMap(element, center, { zoom = 14.5, onClick } = {}) {
  const map = L.map(element, { zoomControl: true, attributionControl: true }).setView(center, zoom);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap',
  }).addTo(map);
  if (onClick) map.on('click', (event) => onClick([event.latlng.lat, event.latlng.lng]));
  setTimeout(() => map.invalidateSize(), 0);
  return map;
}

export function markerIcon(kind, { heading = 0 } = {}) {
  const glyph = kind === 'home' ? 'warehouse' : kind === 'target' ? 'map-pin' : 'navigation';
  const rotate = kind === 'uav' ? `transform:rotate(${heading}deg)` : '';
  return L.divIcon({
    className: 'map-marker',
    html: `<div class="map-marker__dot map-marker__dot--${kind}" style="${rotate}">${icon(glyph, { size: 18 })}</div>`,
    iconSize: [34, 34],
    iconAnchor: [17, 17],
  });
}

/** Khoảng cách Haversine tính bằng mét — dùng để ước lượng ETA. */
export function distanceMeters([lat1, lon1], [lat2, lon2]) {
  const toRad = (value) => (value * Math.PI) / 180;
  const R = 6371000;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}
