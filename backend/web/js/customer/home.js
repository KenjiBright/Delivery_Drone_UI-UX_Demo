// Trang chủ: tìm kiếm, danh mục và danh sách sản phẩm.

import { icon } from '../icons.js';
import { escapeHtml, formatMoney } from '../ui.js';
import { cartTotals, loadCatalog, setQuantity, state } from './store.js';

const PRODUCT_ICONS = new Set(['medkit', 'pill', 'document', 'food', 'coffee', 'chip', 'battery', 'package']);

let searchTimer = null;

export function initHome() {
  document.getElementById('product-search').addEventListener('input', (event) => {
    state.search = event.target.value.trim();
    // Tìm kiếm bỏ luôn bộ lọc danh mục, tránh việc gõ đúng tên mà vẫn ra rỗng.
    if (state.search) state.category = '';
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => loadCatalog(), 300);
  });

  document.getElementById('btn-notifications').addEventListener('click', () => {
    import('../ui.js').then(({ toast }) => toast('Chưa có thông báo mới'));
  });
}

export function renderCategories() {
  const container = document.getElementById('category-chips');
  const chips = [{ label: 'Tất cả', value: '' }, ...state.categories.map((name) => ({ label: name, value: name }))];
  container.innerHTML = chips.map((chip) =>
    `<button class="chip ${state.category === chip.value ? 'is-active' : ''}"
             data-category="${escapeHtml(chip.value)}"
             aria-pressed="${state.category === chip.value}">${escapeHtml(chip.label)}</button>`
  ).join('');

  container.querySelectorAll('.chip').forEach((chip) => {
    chip.onclick = () => {
      state.category = chip.dataset.category;
      loadCatalog();
    };
  });
}

export function renderProducts() {
  const container = document.getElementById('product-list');
  document.getElementById('product-count').textContent =
    state.products.length ? `${state.products.length} sản phẩm` : '';

  if (!state.products.length) {
    container.innerHTML = `
      <div class="empty">
        ${icon('search', { size: 34 })}
        <strong>Không tìm thấy sản phẩm</strong>
        <p>Thử từ khoá khác hoặc chọn danh mục "Tất cả".</p>
      </div>`;
    return;
  }

  container.innerHTML = state.products.map((product) => {
    const glyph = PRODUCT_ICONS.has(product.icon) ? product.icon : 'package';
    const quantity = state.cart[product.id] || 0;
    return `
      <article class="product">
        <div class="product__icon">${icon(glyph, { size: 24 })}</div>
        <div class="product__body">
          <p class="product__name">${escapeHtml(product.name)}</p>
          <p class="product__desc">${escapeHtml(product.description)}</p>
          <div class="product__meta">
            <span class="product__price">${formatMoney(product.price)}</span>
            <span class="product__weight">${product.weight_kg} kg</span>
          </div>
        </div>
        <div class="stepper">
          <button class="stepper__btn" data-dec="${escapeHtml(product.id)}"
                  aria-label="Bớt ${escapeHtml(product.name)}" ${quantity === 0 ? 'disabled' : ''}>
            ${icon('minus', { size: 16 })}
          </button>
          <span class="stepper__value" data-qty="${escapeHtml(product.id)}">${quantity}</span>
          <button class="stepper__btn stepper__btn--add" data-inc="${escapeHtml(product.id)}"
                  aria-label="Thêm ${escapeHtml(product.name)}">
            ${icon('plus', { size: 16 })}
          </button>
        </div>
      </article>`;
  }).join('');

  container.querySelectorAll('[data-inc]').forEach((button) => {
    button.onclick = () => setQuantity(button.dataset.inc, (state.cart[button.dataset.inc] || 0) + 1);
  });
  container.querySelectorAll('[data-dec]').forEach((button) => {
    button.onclick = () => setQuantity(button.dataset.dec, (state.cart[button.dataset.dec] || 0) - 1);
  });
}

/** Cập nhật số lượng tại chỗ để bấm +/- không phải dựng lại cả danh sách. */
export function syncProductQuantities() {
  for (const product of state.products) {
    const quantity = state.cart[product.id] || 0;
    const value = document.querySelector(`[data-qty="${CSS.escape(product.id)}"]`);
    if (value) value.textContent = quantity;
    const decrement = document.querySelector(`[data-dec="${CSS.escape(product.id)}"]`);
    if (decrement) decrement.disabled = quantity === 0;
  }
}

export function renderCartBadge() {
  const { count } = cartTotals();
  const badge = document.getElementById('cart-badge');
  badge.textContent = count;
  badge.classList.toggle('hidden', count === 0);
}
