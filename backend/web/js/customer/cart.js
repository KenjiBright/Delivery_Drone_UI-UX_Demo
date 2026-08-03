// Giỏ hàng và đặt đơn.

import { api } from '../api.js';
import { icon } from '../icons.js';
import { escapeHtml, formatMoney, formatWeight, toast } from '../ui.js';
import { addressIcon, openAddressPicker } from './address.js';
import { cartTotals, clearCart, isOverweight, setQuantity, state } from './store.js';

let onOrderPlaced = () => {};

export function initCart({ onPlaced }) {
  onOrderPlaced = onPlaced;

  document.getElementById('btn-pick-address').addEventListener('click', async () => {
    const point = await openAddressPicker();
    if (point) {
      state.destination = { label: 'Điểm giao đã chọn', ...point };
      renderDestination();
    }
  });

  document.getElementById('btn-place-order').addEventListener('click', placeOrder);
}

export function renderCart() {
  const container = document.getElementById('cart-items');
  const checkout = document.getElementById('cart-checkout');
  const { lines, count, price, weight } = cartTotals();

  checkout.classList.toggle('hidden', count === 0);

  if (!count) {
    container.innerHTML = `
      <div class="empty">
        ${icon('bag', { size: 34 })}
        <strong>Giỏ hàng đang trống</strong>
        <p>Chọn sản phẩm ở trang chủ để bắt đầu đặt giao bằng drone.</p>
      </div>`;
    return;
  }

  container.innerHTML = lines.map(({ product, quantity }) => `
    <div class="card cart-item">
      <div class="product__icon">${icon(product.icon || 'package', { size: 22 })}</div>
      <div class="cart-item__body">
        <p class="cart-item__name">${escapeHtml(product.name)}</p>
        <p class="cart-item__line">${formatMoney(product.price)} × ${quantity} · ${formatWeight(product.weight_kg * quantity)}</p>
      </div>
      <div class="stepper">
        <button class="stepper__btn" data-cart-dec="${escapeHtml(product.id)}" aria-label="Bớt ${escapeHtml(product.name)}">
          ${icon(quantity === 1 ? 'trash' : 'minus', { size: 16 })}
        </button>
        <span class="stepper__value">${quantity}</span>
        <button class="stepper__btn stepper__btn--add" data-cart-inc="${escapeHtml(product.id)}" aria-label="Thêm ${escapeHtml(product.name)}">
          ${icon('plus', { size: 16 })}
        </button>
      </div>
    </div>`).join('');

  container.querySelectorAll('[data-cart-inc]').forEach((button) => {
    button.onclick = () => setQuantity(button.dataset.cartInc, (state.cart[button.dataset.cartInc] || 0) + 1);
  });
  container.querySelectorAll('[data-cart-dec]').forEach((button) => {
    button.onclick = () => setQuantity(button.dataset.cartDec, (state.cart[button.dataset.cartDec] || 0) - 1);
  });

  document.getElementById('sum-count').textContent = count;
  document.getElementById('sum-weight').textContent = formatWeight(weight);
  document.getElementById('sum-price').textContent = formatMoney(price);

  const warning = document.getElementById('weight-warning');
  const over = isOverweight();
  warning.classList.toggle('hidden', !over);
  if (over) {
    warning.innerHTML = `${icon('alert-triangle', { size: 16 })}<span>Vượt tải trọng ${state.config.max_payload_kg} kg. Hãy bớt sản phẩm.</span>`;
  }
  document.getElementById('btn-place-order').disabled = over;
}

export function renderDestination() {
  const label = document.getElementById('selected-address-label');
  const detail = document.getElementById('selected-address-detail');
  if (state.destination) {
    label.textContent = state.destination.label || 'Điểm giao đã chọn';
    detail.textContent = state.destination.address;
  } else {
    label.textContent = 'Chọn điểm giao';
    detail.textContent = 'Chạm để chọn trên bản đồ hoặc tìm địa chỉ';
  }
  renderSavedChips();
}

function renderSavedChips() {
  const container = document.getElementById('saved-address-chips');
  container.innerHTML = state.addresses.map((address) => `
    <button class="chip" data-address="${address.id}">
      ${icon(addressIcon(address.label), { size: 14 })} ${escapeHtml(address.label)}
    </button>`).join('');

  container.querySelectorAll('[data-address]').forEach((button) => {
    button.onclick = () => {
      const address = state.addresses.find((item) => item.id === Number(button.dataset.address));
      if (!address) return;
      state.destination = { label: address.label, address: address.address, lat: address.lat, lon: address.lon };
      renderDestination();
    };
  });
}

async function placeOrder() {
  const { count } = cartTotals();
  if (!count) return toast('Giỏ hàng đang trống', 'error');
  if (!state.destination) return toast('Hãy chọn điểm giao trước', 'error');
  if (isOverweight()) return toast(`Vượt tải trọng ${state.config.max_payload_kg} kg`, 'error');

  const button = document.getElementById('btn-place-order');
  button.disabled = true;
  button.innerHTML = `<span class="spinner"></span>Đang gửi đơn…`;

  try {
    const order = await api.post('/api/orders', {
      items: Object.entries(state.cart).map(([product_id, quantity]) => ({ product_id, quantity })),
      delivery_lat: state.destination.lat,
      delivery_lon: state.destination.lon,
      delivery_address: state.destination.address,
      note: document.getElementById('order-note').value.trim(),
    });
    clearCart();
    document.getElementById('order-note').value = '';
    toast(`Đã đặt đơn ${order.id}. PIN nhận hàng: ${order.verification_code}`, 'success');
    onOrderPlaced(order);
  } catch (error) {
    toast(error.message, 'error');
  } finally {
    button.disabled = false;
    button.textContent = 'Đặt giao hàng bằng UAV';
  }
}
