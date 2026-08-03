// Trạng thái dùng chung của app khách hàng, kèm cơ chế thông báo thay đổi.

import { api, query } from '../api.js';

const CART_KEY = 'uav.cart';

export const state = {
  user: null,
  config: { home_lat: 21.0278, home_lon: 105.8342, max_payload_kg: 2.5 },
  products: [],
  categories: [],
  category: '',
  search: '',
  cart: loadCart(),
  addresses: [],
  destination: null,      // { label, address, lat, lon }
  orders: [],
  orderScope: 'active',
  uavs: [],
  trackedOrderId: null,
};

const listeners = new Set();

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function emit(topic) {
  for (const fn of listeners) fn(topic);
}

function loadCart() {
  try {
    return JSON.parse(sessionStorage.getItem(CART_KEY)) || {};
  } catch {
    return {};
  }
}

function persistCart() {
  sessionStorage.setItem(CART_KEY, JSON.stringify(state.cart));
}

// ---------- Giỏ hàng ----------

export function setQuantity(productId, quantity) {
  const next = Math.max(0, Math.min(20, quantity));
  if (next === 0) delete state.cart[productId];
  else state.cart[productId] = next;
  persistCart();
  emit('cart');
}

export function clearCart() {
  state.cart = {};
  persistCart();
  emit('cart');
}

export function productById(id) {
  return state.products.find((product) => product.id === id) || null;
}

/** Tổng hợp giỏ hàng; bỏ qua sản phẩm không còn trong danh mục. */
export function cartTotals() {
  let count = 0, price = 0, weight = 0;
  const lines = [];
  for (const [productId, quantity] of Object.entries(state.cart)) {
    const product = productById(productId);
    if (!product) continue;
    count += quantity;
    price += product.price * quantity;
    weight += product.weight_kg * quantity;
    lines.push({ product, quantity });
  }
  return { count, price, weight, lines };
}

export function isOverweight() {
  return cartTotals().weight > state.config.max_payload_kg;
}

// ---------- Nạp dữ liệu ----------

export async function loadCatalog() {
  const [products, categories] = await Promise.all([
    api.get(`/api/products${query({ q: state.search, category: state.category })}`),
    api.get('/api/categories'),
  ]);
  state.products = products;
  state.categories = categories;
  emit('catalog');
}

export async function loadConfig() {
  state.config = await api.get('/api/config');
  emit('config');
}

export async function loadOrders() {
  state.orders = await api.get(`/api/orders/mine${query({ scope: state.orderScope })}`);
  emit('orders');
}

export async function loadUavs() {
  state.uavs = await api.get('/api/uavs');
  emit('uavs');
}

export async function loadAddresses() {
  state.addresses = await api.get('/api/addresses');
  emit('addresses');
}

const OPEN_STATUSES = new Set(['PENDING', 'CONFIRMED', 'ASSIGNED', 'DISPATCHED', 'IN_FLIGHT', 'ARRIVED', 'DELIVERED', 'RETURNING']);

/** Đơn đang chạy gần nhất — dùng cho thẻ nổi và màn theo dõi mặc định. */
export async function fetchLiveOrder() {
  const active = await api.get('/api/orders/mine?scope=active');
  return active.find((order) => OPEN_STATUSES.has(order.status)) || null;
}

export function uavById(id) {
  return state.uavs.find((uav) => uav.id === id) || null;
}

export function homePoint() {
  return [state.config.home_lat, state.config.home_lon];
}
