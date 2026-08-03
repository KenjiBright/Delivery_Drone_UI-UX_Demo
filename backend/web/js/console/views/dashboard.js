// Tổng quan: chỉ số chính, bản đồ toàn đội bay, đơn cần xử lý.

import { icon } from '../../icons.js';
import {
  createMap, escapeHtml, formatDateTime, formatDuration, formatMoney,
  markerIcon, statusBadge, uavStatusLabel,
} from '../../ui.js';
import { homePoint, state } from '../store.js';

let map = null;
const uavMarkers = new Map();
let mounted = false;
let onOpenOrder = () => {};

export function initDashboard({ openOrder }) {
  onOpenOrder = openOrder;
}

export function renderDashboard(container) {
  const stats = state.stats;
  if (!stats) {
    container.innerHTML = `<div class="kpis">${'<div class="card skeleton" style="height:80px"></div>'.repeat(4)}</div>`;
    return;
  }

  if (!mounted) {
    container.innerHTML = `
      <div class="kpis" id="dash-kpis"></div>
      <div class="dispatch">
        <div class="panel">
          <div class="panel__head">
            <h2>Vị trí đội bay</h2><span class="spacer"></span>
            <span class="text-muted" id="fleet-caption"></span>
          </div>
          <div class="map" id="fleet-map"></div>
        </div>
        <div class="panel">
          <div class="panel__head"><h2>Đơn cần xử lý</h2></div>
          <div class="panel__body panel__body--flush" id="pending-list"></div>
        </div>
      </div>`;
    mounted = true;
  }

  renderKpis(container, stats);
  renderPending(container);
  updateFleetMap(container);
}

export function invalidateDashboard() {
  mounted = false;
  map = null;
  uavMarkers.clear();
}

function renderKpis(container, stats) {
  const { totals, fleet } = stats;
  const cards = [
    { label: 'Đơn chờ xác nhận', value: totals.pending, glyph: 'clock', tone: 'warn', sub: 'cần thao tác ngay' },
    { label: 'Đang thực hiện', value: totals.active, glyph: 'route', tone: 'brand', sub: `${fleet.busy}/${fleet.total} UAV đang bận` },
    { label: 'Hoàn thành', value: totals.completed, glyph: 'check-circle', tone: 'ok', sub: `doanh thu ${formatMoney(totals.revenue)}` },
    {
      label: 'Thời gian giao TB', value: totals.avg_delivery_seconds ? formatDuration(totals.avg_delivery_seconds) : '—',
      glyph: 'gauge', tone: '', sub: totals.avg_rating ? `${totals.avg_rating}/5 sao từ ${totals.rating_count} đánh giá` : 'chưa có đánh giá',
    },
  ];

  container.querySelector('#dash-kpis').innerHTML = cards.map((card) => `
    <div class="card kpi">
      <span class="kpi__icon ${card.tone ? `kpi__icon--${card.tone}` : ''}">${icon(card.glyph, { size: 20 })}</span>
      <div class="kpi__body">
        <p class="kpi__label">${escapeHtml(card.label)}</p>
        <p class="kpi__value">${escapeHtml(String(card.value))}</p>
        <p class="kpi__sub">${escapeHtml(card.sub)}</p>
      </div>
    </div>`).join('');
}

function renderPending(container) {
  const pending = state.orders.items
    .filter((order) => ['PENDING', 'CONFIRMED', 'ASSIGNED'].includes(order.status))
    .slice(0, 8);
  const list = container.querySelector('#pending-list');

  if (!pending.length) {
    list.innerHTML = `<div class="empty">${icon('check-circle', { size: 30 })}
      <strong>Không còn đơn chờ</strong><p>Mọi đơn đã được điều phối xong.</p></div>`;
    return;
  }

  list.innerHTML = `<div class="table-wrap"><table><tbody>${pending.map((order) => `
    <tr data-open="${escapeHtml(order.id)}" tabindex="0">
      <td class="tnum">${escapeHtml(order.id)}</td>
      <td>${statusBadge(order.status)}</td>
      <td class="tnum">${formatDateTime(order.created_at)}</td>
    </tr>`).join('')}</tbody></table></div>`;

  list.querySelectorAll('[data-open]').forEach((row) => {
    const open = () => onOpenOrder(row.dataset.open);
    row.onclick = open;
    row.onkeydown = (event) => { if (event.key === 'Enter') open(); };
  });
}

/** Hiển thị toàn bộ UAV trên một bản đồ, marker được tái sử dụng giữa các lần cập nhật. */
function updateFleetMap(container) {
  const element = container.querySelector('#fleet-map');
  if (!element) return;

  if (!map) {
    map = createMap(element, homePoint(), { zoom: 13 });
    L.marker(homePoint(), { icon: markerIcon('home') }).addTo(map).bindTooltip('Trạm xuất phát');
  }

  const seen = new Set();
  for (const uav of state.uavs) {
    seen.add(uav.id);
    const point = [uav.lat, uav.lon];
    const tooltip = `${uav.id} — ${uavStatusLabel(uav.status)} — pin ${uav.battery.toFixed(0)}%`;
    const existing = uavMarkers.get(uav.id);
    if (existing) {
      existing.setLatLng(point).setIcon(markerIcon('uav', { heading: uav.heading })).setTooltipContent(tooltip);
    } else {
      uavMarkers.set(uav.id, L.marker(point, { icon: markerIcon('uav', { heading: uav.heading }) })
        .addTo(map).bindTooltip(tooltip));
    }
  }
  // Dọn marker của UAV đã bị xoá khỏi hệ thống.
  for (const [id, marker] of uavMarkers) {
    if (!seen.has(id)) {
      marker.remove();
      uavMarkers.delete(id);
    }
  }

  const caption = container.querySelector('#fleet-caption');
  if (caption) caption.textContent = `${state.uavs.length} UAV`;
}

export function resizeDashboardMap() {
  map?.invalidateSize();
}
