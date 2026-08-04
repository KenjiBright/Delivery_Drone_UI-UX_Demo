// Quản lý đơn hàng: lọc, tìm kiếm, sắp xếp, phân trang, điều phối và nhật ký.

import { api } from '../../api.js';
import { icon } from '../../icons.js';
import {
  createMap, escapeHtml, formatDateTime, formatMoney, formatTime, formatWeight,
  markerIcon, openModal, ratingStars, statusBadge, statusLabel, toast, uavStatusBadge,
} from '../../ui.js';
import { homePoint, loadOrders, loadUavs, selectedOrder, setFilter, state, uavById } from '../store.js';

const STATUS_OPTIONS = [
  ['', 'Tất cả trạng thái'], ['PENDING', 'Chờ xác nhận'], ['CONFIRMED', 'Đã xác nhận'],
  ['ASSIGNED', 'Đã gán UAV'], ['DISPATCHED', 'Chuẩn bị bay'], ['IN_FLIGHT', 'Đang giao'],
  ['ARRIVED', 'Đã đến nơi'], ['UNLOCKED', 'Đang lấy hàng'], ['DELIVERED', 'Đã giao'], ['RETURNING', 'UAV quay về'],
  ['COMPLETED', 'Hoàn thành'], ['CANCELLED', 'Đã huỷ'],
];

// Mỗi trạng thái mở ra đúng một hành động kế tiếp.
const NEXT_ACTION = {
  PENDING: { path: 'confirm', label: 'Xác nhận đơn', glyph: 'check' },
  CONFIRMED: { path: 'assign', label: 'Gán UAV tự động', glyph: 'drone' },
  ASSIGNED: { path: 'dispatch', label: 'Cho phép xuất phát', glyph: 'navigation' },
  // Khách đã đóng thùng, UAV đậu tại điểm giao chờ đúng lệnh này.
  DELIVERED: { path: 'recall', label: 'Cho UAV quay về', glyph: 'refresh' },
};

const CANCELLABLE = new Set(['PENDING', 'CONFIRMED', 'ASSIGNED']);
const COLUMNS = [
  ['id', 'Mã đơn', false], ['customer_username', 'Khách hàng', false], ['status', 'Trạng thái', true],
  ['delivery_address', 'Điểm giao', false], ['total_weight_kg', 'Tải', false],
  ['total_price', 'Tiền', true], ['created_at', 'Tạo lúc', true],
];

let map = null;
let layers = null;
let mounted = false;

export function renderOrders(container) {
  if (!mounted) {
    container.innerHTML = shell();
    bindToolbar(container);
    mounted = true;
  }
  renderTable(container);
  renderDetail(container);
}

export function invalidateOrdersView() {
  mounted = false;
  map = null;
}

function shell() {
  return `
    <div class="panel">
      <div class="panel__head">
        <div class="toolbar" style="flex:1">
          <div class="input-group">
            ${icon('search', { size: 17 })}
            <input class="input" id="order-q" placeholder="Tìm mã đơn, khách hàng hoặc địa chỉ" aria-label="Tìm đơn hàng">
          </div>
          <select class="input" id="order-status" aria-label="Lọc theo trạng thái">
            ${STATUS_OPTIONS.map(([value, text]) => `<option value="${value}">${text}</option>`).join('')}
          </select>
          <select class="input" id="order-scope" aria-label="Nhóm đơn">
            <option value="">Mọi đơn</option>
            <option value="open">Đang xử lý</option>
            <option value="closed">Đã kết thúc</option>
          </select>
          <a class="btn btn--secondary btn--sm" href="/api/admin/orders.csv" download>
            ${icon('download', { size: 16 })}Xuất CSV
          </a>
        </div>
      </div>
      <div class="table-wrap"><table id="order-table"></table></div>
      <div class="pager">
        <span class="pager__info" id="pager-info"></span>
        <button class="btn btn--secondary btn--sm" id="page-prev">${icon('chevron-left', { size: 16 })}Trước</button>
        <button class="btn btn--secondary btn--sm" id="page-next">Sau${icon('chevron-right', { size: 16 })}</button>
      </div>
    </div>

    <div class="dispatch">
      <div class="panel">
        <div class="panel__head"><h2 id="map-caption">Bản đồ nhiệm vụ</h2></div>
        <div class="map" id="dispatch-map"></div>
      </div>
      <div class="stack" id="order-detail"></div>
    </div>`;
}

function bindToolbar(container) {
  let timer = null;
  container.querySelector('#order-q').addEventListener('input', (event) => {
    clearTimeout(timer);
    timer = setTimeout(() => setFilter({ q: event.target.value.trim() }), 300);
  });
  container.querySelector('#order-status').addEventListener('change', (event) => setFilter({ status: event.target.value }));
  container.querySelector('#order-scope').addEventListener('change', (event) => setFilter({ scope: event.target.value }));
  container.querySelector('#page-prev').onclick = () => {
    if (state.filters.page > 1) setFilter({ page: state.filters.page - 1 });
  };
  container.querySelector('#page-next').onclick = () => {
    if (state.filters.page < state.orders.pages) setFilter({ page: state.filters.page + 1 });
  };
}

function renderTable(container) {
  const { items, total, page, pages } = state.orders;
  const table = container.querySelector('#order-table');

  const head = COLUMNS.map(([key, title, sortable]) => {
    if (!sortable) return `<th>${title}</th>`;
    const active = state.filters.sort === key;
    const sort = active ? (state.filters.direction === 'asc' ? 'ascending' : 'descending') : 'none';
    return `<th aria-sort="${sort}" data-sort="${key}" tabindex="0" role="button">
      ${title}<span class="sort-mark">${active && state.filters.direction === 'asc' ? '↑' : '↓'}</span>
    </th>`;
  }).join('');

  const body = items.length
    ? items.map((order) => `
        <tr data-order="${escapeHtml(order.id)}" class="${order.id === state.selectedOrderId ? 'is-selected' : ''}" tabindex="0">
          <td class="tnum">${escapeHtml(order.id)}</td>
          <td>${escapeHtml(order.customer_username)}</td>
          <td>${statusBadge(order.status)}</td>
          <td class="td-wrap">${escapeHtml(order.delivery_address)}</td>
          <td class="tnum">${order.total_weight_kg} kg</td>
          <td class="tnum">${formatMoney(order.total_price)}</td>
          <td class="tnum">${formatDateTime(order.created_at)}</td>
        </tr>`).join('')
    : `<tr><td colspan="${COLUMNS.length}">
         <div class="empty">${icon('inbox', { size: 30 })}<strong>Không có đơn nào khớp bộ lọc</strong>
         <p>Thử xoá từ khoá hoặc chọn "Mọi đơn".</p></div></td></tr>`;

  table.innerHTML = `<thead><tr>${head}</tr></thead><tbody>${body}</tbody>`;

  table.querySelectorAll('[data-sort]').forEach((th) => {
    const apply = () => {
      const key = th.dataset.sort;
      const direction = state.filters.sort === key && state.filters.direction === 'desc' ? 'asc' : 'desc';
      setFilter({ sort: key, direction });
    };
    th.onclick = apply;
    th.onkeydown = (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        apply();
      }
    };
  });

  table.querySelectorAll('[data-order]').forEach((row) => {
    const select = () => {
      state.selectedOrderId = row.dataset.order;
      import('../store.js').then(({ loadEvents }) => loadEvents(row.dataset.order));
      renderOrders(container);
    };
    row.onclick = select;
    row.onkeydown = (event) => {
      if (event.key === 'Enter') select();
    };
  });

  const from = total ? (page - 1) * state.orders.page_size + 1 : 0;
  const to = Math.min(page * state.orders.page_size, total);
  container.querySelector('#pager-info').textContent = `${from}–${to} trên ${total} đơn · trang ${page}/${pages}`;
  container.querySelector('#page-prev').disabled = page <= 1;
  container.querySelector('#page-next').disabled = page >= pages;
}

function renderDetail(container) {
  const order = selectedOrder();
  const panel = container.querySelector('#order-detail');
  const caption = container.querySelector('#map-caption');

  if (!order) {
    panel.innerHTML = `<div class="panel"><div class="panel__body">
      <div class="empty">${icon('receipt', { size: 30 })}<strong>Chọn một đơn để xem chi tiết</strong></div>
    </div></div>`;
    caption.textContent = 'Bản đồ nhiệm vụ';
    updateMap(container, null, null);
    return;
  }

  const uav = order.assigned_uav ? uavById(order.assigned_uav) : null;
  // Đã ra lệnh quay về rồi thì không còn hành động nào, dù đơn vẫn đang ở DELIVERED.
  const next = order.status === 'DELIVERED' && order.return_released_at ? null : NEXT_ACTION[order.status];
  caption.textContent = `${order.id} · ${statusLabel(order.status)}`;

  panel.innerHTML = `
    <div class="panel">
      <div class="panel__head"><h2>Chi tiết đơn</h2><span class="spacer"></span>${statusBadge(order.status)}</div>
      <div class="panel__body">
        <dl class="detail-list">
          <div class="detail-row"><dt>Mã đơn</dt><dd class="tnum">${escapeHtml(order.id)}</dd></div>
          <div class="detail-row"><dt>Khách hàng</dt><dd>${escapeHtml(order.customer_username)}</dd></div>
          <div class="detail-row"><dt>Điểm giao</dt><dd>${escapeHtml(order.delivery_address)}</dd></div>
          ${order.note ? `<div class="detail-row"><dt>Ghi chú</dt><dd>${escapeHtml(order.note)}</dd></div>` : ''}
          <div class="detail-row"><dt>Tải trọng</dt><dd>${formatWeight(order.total_weight_kg)}</dd></div>
          <div class="detail-row"><dt>Tổng tiền</dt><dd>${formatMoney(order.total_price)}</dd></div>
          <div class="detail-row"><dt>PIN</dt><dd class="tnum">${escapeHtml(order.verification_code)}</dd></div>
          <div class="detail-row"><dt>UAV</dt><dd>${escapeHtml(order.assigned_uav || 'Chưa gán')}</dd></div>
          ${order.box_opened_at ? `<div class="detail-row"><dt>Mở thùng</dt><dd class="tnum">${formatTime(order.box_opened_at)}</dd></div>` : ''}
          ${order.box_closed_at ? `<div class="detail-row"><dt>Đóng thùng</dt><dd class="tnum">${formatTime(order.box_closed_at)}</dd></div>` : ''}
          ${order.return_released_at ? `<div class="detail-row"><dt>Lệnh quay về</dt><dd>${formatTime(order.return_released_at)} · ${escapeHtml(order.return_released_by || '')}</dd></div>` : ''}
          ${order.cancel_reason ? `<div class="detail-row"><dt>Lý do huỷ</dt><dd>${escapeHtml(order.cancel_reason)}</dd></div>` : ''}
          ${order.rating ? `<div class="detail-row"><dt>Đánh giá</dt><dd>${ratingStars(order.rating)} ${escapeHtml(order.review || '')}</dd></div>` : ''}
        </dl>
        <ul style="margin:var(--sp-4) 0 0;padding-left:18px;font-size:14px;color:var(--text-muted)">
          ${order.items.map((item) => `<li>${escapeHtml(item.name)} × ${item.quantity}</li>`).join('')}
        </ul>
      </div>
    </div>

    <div class="panel"><div class="panel__body action-stack">
      ${next ? `<button class="btn" id="btn-next">${icon(next.glyph, { size: 17 })}${next.label}</button>` : ''}
      ${order.status === 'CONFIRMED' ? `<button class="btn btn--secondary" id="btn-assign-manual">${icon('more', { size: 17 })}Chọn UAV cụ thể</button>` : ''}
      ${CANCELLABLE.has(order.status) ? `<button class="btn btn--danger" id="btn-cancel">${icon('close', { size: 17 })}Huỷ đơn</button>` : ''}
      ${!next && !CANCELLABLE.has(order.status) ? `<p class="text-muted" style="text-align:center">Đơn đang ở trạng thái <strong>${statusLabel(order.status)}</strong>, không cần thao tác.</p>` : ''}
    </div></div>

    ${uav ? `<div class="panel">
      <div class="panel__head"><h2>${escapeHtml(uav.id)}</h2><span class="spacer"></span>${uavStatusBadge(uav.status)}</div>
      <div class="panel__body">
        <div class="uav-tile__stats">
          <div><small>Pin</small><strong class="tnum">${uav.battery.toFixed(0)}%</strong></div>
          <div><small>Độ cao</small><strong class="tnum">${uav.altitude.toFixed(1)} m</strong></div>
          <div><small>Tốc độ</small><strong class="tnum">${uav.speed.toFixed(1)} m/s</strong></div>
        </div>
      </div>
    </div>` : ''}

    <div class="panel">
      <div class="panel__head"><h2>Nhật ký trạng thái</h2></div>
      <div class="panel__body">
        ${state.selectedEvents.length ? `<div class="timeline">${state.selectedEvents.slice().reverse().map((event) => `
          <div class="timeline__item">
            <span class="timeline__time">${formatTime(event.created_at)}</span>
            <div class="timeline__body">
              <strong>${escapeHtml(statusLabel(event.status))}</strong>
              <small>${escapeHtml(event.note || '')} · ${escapeHtml(event.actor)}</small>
            </div>
          </div>`).join('')}</div>` : '<p class="text-muted">Chưa có sự kiện.</p>'}
      </div>
    </div>`;

  if (next) panel.querySelector('#btn-next').onclick = () => runAction(order, next.path);
  panel.querySelector('#btn-assign-manual')?.addEventListener('click', () => assignManually(order));
  panel.querySelector('#btn-cancel')?.addEventListener('click', () => cancelOrder(order));

  updateMap(container, order, uav);
}

async function runAction(order, path, body) {
  try {
    await api.post(`/api/admin/orders/${order.id}/${path}`, body);
    await Promise.all([loadOrders(), loadUavs()]);
    toast(`Đã cập nhật đơn ${order.id}`, 'success');
  } catch (error) {
    toast(error.message, 'error');
  }
}

async function assignManually(order) {
  const usable = state.uavs.filter((uav) => uav.status === 'AVAILABLE' && uav.max_payload_kg >= order.total_weight_kg);
  if (!usable.length) return toast('Không còn UAV rảnh đủ tải trọng', 'error');

  const chosen = await openModal({
    title: 'Chọn UAV thực hiện',
    body: `<label class="field" style="margin:0">
        <span class="field__label">UAV rảnh, đủ tải ${formatWeight(order.total_weight_kg)}</span>
        <select class="input" id="uav-choice">
          ${usable.map((uav) => `<option value="${escapeHtml(uav.id)}">${escapeHtml(uav.id)} — pin ${uav.battery.toFixed(0)}% — tải ${uav.max_payload_kg} kg</option>`).join('')}
        </select>
      </label>`,
    actions: [
      { label: 'Huỷ', variant: 'secondary', onClick: () => null },
      { label: 'Gán UAV', onClick: (scrim) => scrim.querySelector('#uav-choice').value },
    ],
  });
  if (chosen) await runAction(order, 'assign', { uav_id: chosen });
}

async function cancelOrder(order) {
  const reason = await openModal({
    title: `Huỷ đơn ${order.id}`,
    body: `<label class="field" style="margin:0">
        <span class="field__label">Lý do huỷ</span>
        <input class="input" id="cancel-reason" maxlength="250" placeholder="Ví dụ: khách yêu cầu huỷ">
        <span class="field__hint">Lý do được lưu vào nhật ký và hiển thị cho khách hàng.</span>
      </label>`,
    actions: [
      { label: 'Không huỷ', variant: 'secondary', onClick: () => null },
      { label: 'Xác nhận huỷ', variant: 'danger', onClick: (scrim) => scrim.querySelector('#cancel-reason').value.trim() || ' ' },
    ],
  });
  if (reason) await runAction(order, 'cancel', { reason: reason.trim() });
}

function updateMap(container, order, uav) {
  const element = container.querySelector('#dispatch-map');
  if (!element) return;

  const home = homePoint();
  const target = order ? [order.delivery_lat, order.delivery_lon] : home;
  const uavPoint = uav ? [uav.lat, uav.lon] : home;

  if (!map) {
    map = createMap(element, home, { zoom: 13 });
    layers = {
      home: L.marker(home, { icon: markerIcon('home') }).addTo(map),
      target: L.marker(target, { icon: markerIcon('target') }).addTo(map),
      uav: L.marker(uavPoint, { icon: markerIcon('uav') }).addTo(map),
      route: L.polyline([home, uavPoint, target], { color: '#2f81f7', weight: 3, opacity: .8 }).addTo(map),
    };
    return;
  }

  layers.home.setLatLng(home);
  layers.target.setLatLng(target);
  layers.uav.setLatLng(uavPoint).setIcon(markerIcon('uav', { heading: uav?.heading || 0 }));
  layers.route.setLatLngs([home, uavPoint, target]);
}

export function resizeOrdersMap() {
  map?.invalidateSize();
}
