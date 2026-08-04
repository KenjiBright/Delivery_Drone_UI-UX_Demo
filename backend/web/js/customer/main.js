// Khởi động app khách hàng: đăng nhập, điều hướng, đồng bộ thời gian thực.

import { ApiError, api, clearSession, connectSocket, getToken, login } from '../api.js';
import { injectSprite } from '../icons.js';
import { confirmDialog, customerStatusLabel, escapeHtml, toast } from '../ui.js';
import { addressIcon, openSaveAddress } from './address.js';
import {
  currentProfile, initProfileForms, loadProfile, renderAddressOptions, renderSessions,
} from './profile.js';
import { initCart, renderCart, renderDestination } from './cart.js';
import { initHome, renderCartBadge, renderCategories, renderProducts, syncProductQuantities } from './home.js';
import { initOrders, paintTracking, renderOrderList, renderTracking, resizeMap } from './orders.js';
import {
  fetchLiveOrder, loadAddresses, loadCatalog, loadConfig, loadOrders, loadUavs, state, subscribe,
} from './store.js';
import { icon } from '../icons.js';
import { getMode, onThemeChange, setMode } from '../theme.js';

injectSprite();

const SCREENS = ['home', 'cart', 'orders', 'profile', 'track'];
let currentScreen = 'home';
let disconnect = null;

// ---------- Điều hướng ----------

function showScreen(name) {
  currentScreen = name;
  for (const screen of SCREENS) {
    document.getElementById(`screen-${screen}`).classList.toggle('hidden', screen !== name);
  }
  document.querySelectorAll('.tabbar__item').forEach((item) => {
    item.classList.toggle('is-active', item.dataset.screen === name);
    item.setAttribute('aria-current', item.dataset.screen === name ? 'page' : 'false');
  });
  // Màn theo dõi chiếm toàn bộ, ẩn thanh tab và thẻ đơn nổi.
  document.getElementById('tabbar').classList.toggle('hidden', name === 'track');
  refreshLiveOrder();
  window.scrollTo({ top: 0 });
  if (name === 'track') resizeMap();
}

async function openTracking(orderId) {
  showScreen('track');
  location.hash = `#/order/${orderId}`;
  await renderTracking(orderId);
  resizeMap();
}

function initNav() {
  document.querySelectorAll('.tabbar__item').forEach((item) => {
    item.onclick = () => {
      location.hash = `#/${item.dataset.screen}`;
      showScreen(item.dataset.screen);
    };
  });

  document.getElementById('btn-track-back').onclick = () => {
    location.hash = '#/orders';
    showScreen('orders');
  };

  document.getElementById('live-order').onclick = () => {
    if (state.trackedOrderId) openTracking(state.trackedOrderId);
  };

  // Cho phép chia sẻ link và bấm nút back của trình duyệt.
  window.addEventListener('hashchange', applyRoute);
}

function applyRoute() {
  const hash = location.hash.replace(/^#\//, '');
  const [section, param] = hash.split('/');
  if (section === 'order' && param) return void openTracking(param);
  if (SCREENS.includes(section)) return showScreen(section);
  showScreen('home');
}

// ---------- Thẻ đơn đang giao ----------

async function refreshLiveOrder() {
  const card = document.getElementById('live-order');
  if (currentScreen === 'track') return card.classList.add('hidden');
  try {
    const order = await fetchLiveOrder();
    if (!order) return card.classList.add('hidden');
    state.trackedOrderId = order.id;
    document.getElementById('live-order-status').textContent = customerStatusLabel(order.status);
    document.getElementById('live-order-id').textContent = order.id;
    card.classList.remove('hidden');
  } catch {
    card.classList.add('hidden');
  }
}

// ---------- Tài khoản ----------

function renderProfile() {
  const profile = currentProfile();
  document.getElementById('profile-name').textContent =
    profile?.full_name || profile?.display_name || state.user?.display_name || '—';
  document.getElementById('profile-phone').textContent =
    profile?.phone || state.user?.phone || 'Chưa cập nhật số điện thoại';
  renderAddressOptions();

  const container = document.getElementById('address-list');
  if (!state.addresses.length) {
    container.innerHTML = `
      <div class="empty">
        ${icon('map-pin', { size: 30 })}
        <strong>Chưa lưu địa chỉ nào</strong>
        <p>Lưu địa chỉ hay dùng để đặt hàng nhanh hơn ở lần sau.</p>
      </div>`;
    return;
  }

  container.innerHTML = state.addresses.map((address) => `
    <div class="card address-row">
      <div class="address-row__icon">${icon(addressIcon(address.label), { size: 18 })}</div>
      <div class="address-row__body">
        <strong>${escapeHtml(address.label)}</strong>
        <small>${escapeHtml(address.address)}</small>
      </div>
      <button class="btn btn--icon btn--sm" data-del-address="${address.id}" aria-label="Xoá ${escapeHtml(address.label)}">
        ${icon('trash', { size: 16 })}
      </button>
    </div>`).join('');

  container.querySelectorAll('[data-del-address]').forEach((button) => {
    button.onclick = async () => {
      const confirmed = await confirmDialog('Xoá địa chỉ', 'Địa chỉ này sẽ bị xoá khỏi sổ.', 'Xoá');
      if (!confirmed) return;
      await api.del(`/api/addresses/${button.dataset.delAddress}`);
      await loadAddresses();
      toast('Đã xoá địa chỉ', 'success');
    };
  });
}

/** Điền sẵn điểm giao và ghi chú mặc định để khách đặt đơn nhanh hơn. */
function applyDeliveryPreferences() {
  const profile = currentProfile();
  if (!profile) return;

  if (!state.destination && profile.default_address_id) {
    const saved = state.addresses.find((address) => address.id === profile.default_address_id);
    if (saved) {
      state.destination = { label: saved.label, address: saved.address, lat: saved.lat, lon: saved.lon };
      renderDestination();
    }
  }

  const note = document.getElementById('order-note');
  if (note && !note.value && profile.default_note) note.value = profile.default_note;
}

function syncThemeSwitch(mode = getMode()) {
  document.querySelectorAll('[data-theme-mode]').forEach((button) => {
    const active = button.dataset.themeMode === mode;
    button.classList.toggle('is-active', active);
    button.setAttribute('aria-checked', String(active));
  });
}

function initTheme() {
  document.querySelectorAll('[data-theme-mode]').forEach((button) => {
    button.onclick = () => setMode(button.dataset.themeMode);
  });
  onThemeChange(syncThemeSwitch);
  syncThemeSwitch();
}

function initProfile() {
  initTheme();
  initProfileForms({ onChange: renderProfile });
  document.getElementById('btn-add-address').onclick = openSaveAddress;
  document.getElementById('btn-logout').onclick = async () => {
    const confirmed = await confirmDialog('Đăng xuất', 'Bạn sẽ cần đăng nhập lại để đặt hàng.', 'Đăng xuất');
    if (confirmed) signOut();
  };
}

function signOut() {
  disconnect?.();
  clearSession();
  location.hash = '';
  location.reload();
}

// ---------- Thời gian thực ----------

function initRealtime() {
  disconnect = connectSocket('/ws/customer', {
    onMessage: async (event) => {
      // Server đẩy sẵn dữ liệu đơn nên chỉ cần nạp lại phần liên quan.
      await Promise.all([loadUavs(), loadOrders()]);
      if (currentScreen === 'track' && state.trackedOrderId) {
        const changed = event?.order?.id === state.trackedOrderId;
        if (changed || event?.type === 'telemetry') await renderTracking(state.trackedOrderId);
      } else {
        refreshLiveOrder();
      }
      // Chặng UAV bay về không đẩy thông báo cho khách: đơn của họ đã xong rồi.
      const notify = currentProfile()?.notify_orders ?? 1;
      if (notify && event?.type === 'order_updated' && event.order && event.order.status !== 'RETURNING'
          && event.order.status !== 'COMPLETED') {
        toast(`Đơn ${event.order.id}: ${customerStatusLabel(event.order.status)}`);
      }
    },
  });

  // Dự phòng khi WebSocket bị chặn trong mạng LAN.
  setInterval(() => {
    if (currentScreen === 'track' && state.trackedOrderId) renderTracking(state.trackedOrderId);
    else refreshLiveOrder();
  }, 10000);
}

// ---------- Vòng đời ----------

function bindStore() {
  subscribe((topic) => {
    if (topic === 'catalog') {
      renderCategories();
      renderProducts();
      renderCart();
    }
    if (topic === 'cart') {
      renderCartBadge();
      syncProductQuantities();
      renderCart();
    }
    if (topic === 'orders') renderOrderList();
    if (topic === 'addresses') {
      renderProfile();
      renderDestination();
    }
    if (topic === 'config') {
      document.getElementById('promo-payload').textContent = state.config.max_payload_kg;
    }
  });
}

async function start(user) {
  state.user = user;
  document.getElementById('view-login').classList.add('hidden');
  document.getElementById('app').classList.remove('hidden');
  document.getElementById('hero-name').textContent = user.display_name;

  initHome();
  initCart({ onPlaced: (order) => openTracking(order.id) });
  initOrders({ onOpenTracking: openTracking });
  initProfile();
  initNav();
  bindStore();

  await Promise.all([loadConfig(), loadCatalog(), loadOrders(), loadUavs(), loadAddresses()]);
  await loadProfile().catch(() => null);
  applyDeliveryPreferences();
  renderSessions();
  renderCartBadge();
  renderProfile();
  renderDestination();
  initRealtime();
  applyRoute();
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
        'customer',
      );
      await start(user);
    } catch (error) {
      errorBox.textContent = error.message;
      errorBox.classList.remove('hidden');
    } finally {
      submit.disabled = false;
      submit.textContent = 'Đăng nhập';
    }
  };
}

/** Còn token trong sessionStorage thì vào thẳng app, khỏi bắt đăng nhập lại. */
async function restoreSession() {
  if (!getToken()) return false;
  try {
    const user = await api.get('/api/auth/me');
    if (user.role !== 'customer') return false;
    await start(user);
    return true;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) clearSession();
    return false;
  }
}

initLogin();
restoreSession();
