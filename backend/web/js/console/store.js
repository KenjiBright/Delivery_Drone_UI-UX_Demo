// Trạng thái dùng chung của console điều phối.

import { api, query } from '../api.js';

export const state = {
  user: null,
  settings: {},
  stats: null,
  orders: { items: [], total: 0, page: 1, pages: 1, page_size: 25 },
  filters: { status: '', q: '', scope: '', sort: 'created_at', direction: 'desc', page: 1 },
  selectedOrderId: null,
  selectedEvents: [],
  uavs: [],
  products: [],
  customers: [],
};

const listeners = new Set();

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function emit(topic) {
  for (const fn of listeners) fn(topic);
}

export async function loadOrders() {
  state.orders = await api.get(`/api/admin/orders${query({ ...state.filters, page_size: state.orders.page_size })}`);
  // Giữ lựa chọn hiện tại nếu vẫn còn trong danh sách, nếu không thì chọn dòng đầu.
  if (!state.orders.items.some((order) => order.id === state.selectedOrderId)) {
    state.selectedOrderId = state.orders.items[0]?.id || null;
    state.selectedEvents = [];
  }
  emit('orders');
  if (state.selectedOrderId) loadEvents(state.selectedOrderId);
}

export async function loadEvents(orderId) {
  state.selectedEvents = await api.get(`/api/admin/orders/${orderId}/events`);
  emit('events');
}

export async function loadUavs() {
  state.uavs = await api.get('/api/uavs');
  emit('uavs');
}

export async function loadStats() {
  state.stats = await api.get('/api/admin/stats');
  emit('stats');
}

export async function loadProducts() {
  state.products = await api.get('/api/admin/products');
  emit('products');
}

export async function loadCustomers() {
  state.customers = await api.get('/api/admin/customers');
  emit('customers');
}

export async function loadSettings() {
  state.settings = await api.get('/api/admin/settings');
  emit('settings');
}

export function selectedOrder() {
  return state.orders.items.find((order) => order.id === state.selectedOrderId) || null;
}

export function uavById(id) {
  return state.uavs.find((uav) => uav.id === id) || null;
}

export function homePoint() {
  return [Number(state.settings.home_lat ?? 21.0278), Number(state.settings.home_lon ?? 105.8342)];
}

export function setFilter(patch) {
  Object.assign(state.filters, patch);
  if (!('page' in patch)) state.filters.page = 1;
  return loadOrders();
}
