// Khởi động console: đăng nhập, điều hướng, cảnh báo và đồng bộ thời gian thực.

import { ApiError, api, clearSession, connectSocket, getToken, login } from '../api.js';
import { icon, injectSprite } from '../icons.js';
import { escapeHtml, toast } from '../ui.js';
import {
  loadCustomers, loadOrders, loadProducts, loadSettings, loadStats, loadUavs, state, subscribe,
} from './store.js';
import { initDashboard, invalidateDashboard, renderDashboard, resizeDashboardMap } from './views/dashboard.js';
import { invalidateOrdersView, renderOrders, resizeOrdersMap } from './views/orders.js';
import { renderFleet } from './views/fleet.js';
import { renderAnalytics } from './views/analytics.js';
import { renderCatalog } from './views/catalog.js';
import { renderCustomers } from './views/customers.js';
import { renderSettings } from './views/settings.js';

injectSprite();

const VIEWS = {
  dashboard: { title: 'Tổng quan', render: renderDashboard },
  orders: { title: 'Đơn hàng', render: renderOrders },
  fleet: { title: 'Đội UAV', render: renderFleet },
  analytics: { title: 'Thống kê', render: renderAnalytics },
  catalog: { title: 'Sản phẩm', render: renderCatalog },
  customers: { title: 'Khách hàng', render: renderCustomers },
  settings: { title: 'Cấu hình', render: renderSettings },
};

let currentView = 'dashboard';
let disconnect = null;

// ---------- Điều hướng ----------

function showView(name) {
  if (!VIEWS[name]) name = 'dashboard';
  currentView = name;

  for (const key of Object.keys(VIEWS)) {
    document.getElementById(`view-${key}`).classList.toggle('hidden', key !== name);
  }
  document.querySelectorAll('.navitem[data-view]').forEach((item) => {
    item.classList.toggle('is-active', item.dataset.view === name);
    item.setAttribute('aria-current', item.dataset.view === name ? 'page' : 'false');
  });
  document.getElementById('view-title').textContent = VIEWS[name].title;
  document.querySelector('.sidebar').classList.remove('is-open');

  paint(name);
  // Leaflet tính sai kích thước nếu container bị ẩn lúc khởi tạo.
  if (name === 'orders') resizeOrdersMap();
  if (name === 'dashboard') resizeDashboardMap();
}

function paint(name = currentView) {
  VIEWS[name].render(document.getElementById(`view-${name}`));
}

function initNav() {
  document.querySelectorAll('.navitem[data-view]').forEach((item) => {
    item.onclick = () => {
      location.hash = `#/${item.dataset.view}`;
      showView(item.dataset.view);
    };
  });

  document.getElementById('btn-menu').onclick = () => {
    document.querySelector('.sidebar').classList.toggle('is-open');
  };

  document.getElementById('btn-refresh').onclick = async () => {
    await refreshAll();
    toast('Đã làm mới dữ liệu', 'success');
  };

  document.getElementById('btn-logout').onclick = () => {
    disconnect?.();
    clearSession();
    location.hash = '';
    location.reload();
  };

  window.addEventListener('hashchange', () => showView(location.hash.replace(/^#\//, '')));
}

export function openOrder(orderId) {
  state.selectedOrderId = orderId;
  location.hash = '#/orders';
  showView('orders');
}

// ---------- Cảnh báo ----------

function renderAlerts() {
  const box = document.getElementById('alerts');
  const alerts = [];
  const fleet = state.stats?.fleet;

  if (fleet?.low_battery.length) {
    alerts.push({
      tone: 'warn', glyph: 'battery',
      text: `${fleet.low_battery.join(', ')} có pin dưới ${fleet.low_battery_threshold}%.`,
      action: { label: 'Xem đội UAV', view: 'fleet' },
    });
  }
  if (fleet && fleet.total > 0 && fleet.available === 0) {
    alerts.push({ tone: 'danger', glyph: 'alert-triangle', text: 'Không còn UAV rảnh. Đơn mới sẽ phải chờ.' });
  }
  const pending = state.stats?.totals.pending ?? 0;
  if (pending >= 3) {
    alerts.push({
      tone: 'warn', glyph: 'clock',
      text: `${pending} đơn đang chờ xác nhận.`,
      action: { label: 'Xử lý ngay', view: 'orders' },
    });
  }

  box.innerHTML = alerts.map((alert, index) => `
    <div class="alert alert--${alert.tone}" role="status">
      ${icon(alert.glyph, { size: 18 })}<span>${escapeHtml(alert.text)}</span>
      ${alert.action ? `<button class="btn btn--secondary btn--sm alert__action" data-alert="${index}">${escapeHtml(alert.action.label)}</button>` : ''}
    </div>`).join('');

  box.querySelectorAll('[data-alert]').forEach((button) => {
    button.onclick = () => {
      location.hash = `#/${alerts[Number(button.dataset.alert)].action.view}`;
      showView(alerts[Number(button.dataset.alert)].action.view);
    };
  });

  const badge = document.getElementById('nav-pending-badge');
  badge.textContent = pending;
  badge.classList.toggle('hidden', pending === 0);
}

// ---------- Dữ liệu ----------

async function refreshAll() {
  await Promise.all([loadOrders(), loadUavs(), loadStats(), loadProducts(), loadCustomers(), loadSettings()]);
}

function bindStore() {
  subscribe((topic) => {
    if (topic === 'stats') renderAlerts();
    // Chỉ vẽ lại màn đang hiển thị để tránh dựng DOM thừa.
    const affects = {
      orders: ['orders', 'events', 'uavs'],
      dashboard: ['stats', 'uavs', 'orders'],
      fleet: ['uavs', 'settings'],
      analytics: ['stats'],
      catalog: ['products'],
      customers: ['customers'],
      settings: ['settings', 'uavs', 'products', 'stats'],
    };
    if (affects[currentView]?.includes(topic)) paint();
  });
}

function setConnection(online) {
  const element = document.getElementById('conn-status');
  element.classList.toggle('is-online', online);
  document.getElementById('conn-text').textContent = online ? 'Thời gian thực' : 'Mất kết nối';
}

function initRealtime() {
  disconnect = connectSocket('/ws/operator', {
    onStatus: setConnection,
    onMessage: async (event) => {
      await Promise.all([loadOrders(), loadUavs(), loadStats()]);
      if (event?.type === 'order_created') {
        toast(`Đơn mới ${event.order.id} từ ${event.order.customer_username}`, 'success');
      } else if (event?.type === 'order_rated') {
        toast(`${event.order.id} được đánh giá ${event.order.rating}/5 sao`);
      }
    },
  });

  // Dự phòng khi WebSocket bị chặn trong mạng LAN.
  setInterval(() => Promise.all([loadOrders(), loadUavs(), loadStats()]), 15000);
}

// ---------- Vòng đời ----------

async function start(user) {
  state.user = user;
  document.getElementById('view-login').classList.add('hidden');
  document.getElementById('app').classList.remove('hidden');
  document.getElementById('topbar-user').textContent = user.display_name;

  invalidateDashboard();
  invalidateOrdersView();
  initDashboard({ openOrder });
  initNav();
  bindStore();

  await refreshAll();
  renderAlerts();
  initRealtime();
  showView(location.hash.replace(/^#\//, '') || 'dashboard');
}

function initLogin() {
  const form = document.getElementById('login-form');
  const errorBox = document.getElementById('login-error');
  const submit = document.getElementById('login-submit');

  form.onsubmit = async (event) => {
    event.preventDefault();
    errorBox.classList.add('hidden');
    submit.disabled = true;
    submit.innerHTML = `<span class="spinner"></span>Đang đăng nhập…`;
    try {
      const user = await login(
        document.getElementById('login-username').value.trim(),
        document.getElementById('login-password').value,
        'operator',
      );
      await start(user);
    } catch (error) {
      errorBox.textContent = error.message;
      errorBox.classList.remove('hidden');
    } finally {
      submit.disabled = false;
      submit.textContent = 'Đăng nhập điều phối';
    }
  };
}

/** Còn token trong sessionStorage thì vào thẳng console. */
async function restoreSession() {
  if (!getToken()) return;
  try {
    const user = await api.get('/api/auth/me');
    if (user.role === 'operator') await start(user);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) clearSession();
  }
}

initLogin();
restoreSession();
