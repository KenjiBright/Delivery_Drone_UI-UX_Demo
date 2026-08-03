// Quản lý sản phẩm: thêm, sửa, bật/tắt bán, xoá.

import { api } from '../../api.js';
import { icon } from '../../icons.js';
import { confirmDialog, escapeHtml, formatMoney, openModal, toast } from '../../ui.js';
import { loadProducts, state } from '../store.js';

const ICON_CHOICES = ['package', 'medkit', 'pill', 'document', 'food', 'coffee', 'chip', 'battery'];

export function renderCatalog(container) {
  container.innerHTML = `
    <div class="panel">
      <div class="panel__head">
        <h2>Sản phẩm</h2><span class="spacer"></span>
        <span class="text-muted">${state.products.filter((item) => item.active).length}/${state.products.length} đang bán</span>
        <button class="btn btn--sm" id="btn-add-product">${icon('plus', { size: 16 })}Thêm sản phẩm</button>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr>
            <th>Mã</th><th>Tên</th><th>Danh mục</th><th>Giá</th><th>Khối lượng</th><th>Trạng thái</th><th></th>
          </tr></thead>
          <tbody>
            ${state.products.length ? state.products.map((product) => `
              <tr>
                <td class="tnum">${escapeHtml(product.id)}</td>
                <td class="td-wrap">
                  <strong>${escapeHtml(product.name)}</strong>
                  <div class="text-muted" style="font-size:13px">${escapeHtml(product.description)}</div>
                </td>
                <td>${escapeHtml(product.category)}</td>
                <td class="tnum">${formatMoney(product.price)}</td>
                <td class="tnum">${product.weight_kg} kg</td>
                <td><span class="badge badge--${product.active ? 'success' : ''} badge--dot">${product.active ? 'Đang bán' : 'Đã ẩn'}</span></td>
                <td><div class="td-actions">
                  <button class="btn btn--icon btn--sm" data-toggle="${escapeHtml(product.id)}"
                          aria-label="${product.active ? 'Ẩn' : 'Bán lại'} ${escapeHtml(product.name)}">
                    ${icon(product.active ? 'close' : 'check', { size: 15 })}
                  </button>
                  <button class="btn btn--icon btn--sm" data-edit="${escapeHtml(product.id)}"
                          aria-label="Sửa ${escapeHtml(product.name)}">${icon('edit', { size: 15 })}</button>
                  <button class="btn btn--icon btn--sm" data-del="${escapeHtml(product.id)}"
                          aria-label="Xoá ${escapeHtml(product.name)}">${icon('trash', { size: 15 })}</button>
                </div></td>
              </tr>`).join('')
            : `<tr><td colspan="7"><div class="empty">${icon('package', { size: 30 })}
                <strong>Chưa có sản phẩm</strong><p>Thêm sản phẩm để khách hàng có thể đặt.</p></div></td></tr>`}
          </tbody>
        </table>
      </div>
    </div>`;

  container.querySelector('#btn-add-product').onclick = () => openProductForm();
  container.querySelectorAll('[data-edit]').forEach((button) => {
    button.onclick = () => openProductForm(state.products.find((item) => item.id === button.dataset.edit));
  });
  container.querySelectorAll('[data-toggle]').forEach((button) => {
    button.onclick = () => toggleActive(button.dataset.toggle);
  });
  container.querySelectorAll('[data-del]').forEach((button) => {
    button.onclick = () => removeProduct(button.dataset.del);
  });
}

async function openProductForm(product) {
  const editing = Boolean(product);
  const categories = [...new Set(state.products.map((item) => item.category))];

  const result = await openModal({
    title: editing ? `Sửa ${product.name}` : 'Thêm sản phẩm',
    body: `
      ${editing ? '' : `<label class="field">
        <span class="field__label">Mã sản phẩm</span>
        <input class="input" id="p-id" placeholder="FOOD003" maxlength="32">
      </label>`}
      <label class="field">
        <span class="field__label">Tên sản phẩm</span>
        <input class="input" id="p-name" value="${escapeHtml(product?.name || '')}" maxlength="120">
      </label>
      <label class="field">
        <span class="field__label">Mô tả</span>
        <input class="input" id="p-desc" value="${escapeHtml(product?.description || '')}" maxlength="250">
      </label>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--sp-3)">
        <label class="field">
          <span class="field__label">Giá (đ)</span>
          <input class="input" id="p-price" type="number" min="0" step="1000" value="${product?.price ?? 100000}">
        </label>
        <label class="field">
          <span class="field__label">Khối lượng (kg)</span>
          <input class="input" id="p-weight" type="number" min="0.01" step="0.05" value="${product?.weight_kg ?? 0.5}">
        </label>
      </div>
      <label class="field">
        <span class="field__label">Danh mục</span>
        <input class="input" id="p-category" list="category-list" value="${escapeHtml(product?.category || 'Khác')}" maxlength="60">
        <datalist id="category-list">${categories.map((name) => `<option value="${escapeHtml(name)}">`).join('')}</datalist>
      </label>
      <label class="field" style="margin:0">
        <span class="field__label">Biểu tượng</span>
        <select class="input" id="p-icon">
          ${ICON_CHOICES.map((name) => `<option value="${name}" ${product?.icon === name ? 'selected' : ''}>${name}</option>`).join('')}
        </select>
      </label>`,
    actions: [
      { label: 'Huỷ', variant: 'secondary', onClick: () => null },
      {
        label: editing ? 'Lưu thay đổi' : 'Thêm sản phẩm',
        onClick: (scrim) => {
          const payload = {
            name: scrim.querySelector('#p-name').value.trim(),
            description: scrim.querySelector('#p-desc').value.trim(),
            price: Number(scrim.querySelector('#p-price').value),
            weight_kg: Number(scrim.querySelector('#p-weight').value),
            category: scrim.querySelector('#p-category').value.trim() || 'Khác',
            icon: scrim.querySelector('#p-icon').value,
          };
          if (!editing) payload.id = scrim.querySelector('#p-id').value.trim().toUpperCase();
          if (!payload.name) {
            toast('Hãy nhập tên sản phẩm', 'error');
            return false;
          }
          if (!editing && payload.id.length < 2) {
            toast('Hãy nhập mã sản phẩm', 'error');
            return false;
          }
          if (!(payload.weight_kg > 0)) {
            toast('Khối lượng phải lớn hơn 0', 'error');
            return false;
          }
          return payload;
        },
      },
    ],
  });
  if (!result) return;

  try {
    if (editing) await api.patch(`/api/admin/products/${product.id}`, result);
    else await api.post('/api/admin/products', result);
    await loadProducts();
    toast(editing ? 'Đã cập nhật sản phẩm' : 'Đã thêm sản phẩm', 'success');
  } catch (error) {
    toast(error.message, 'error');
  }
}

async function toggleActive(productId) {
  const product = state.products.find((item) => item.id === productId);
  if (!product) return;
  try {
    await api.patch(`/api/admin/products/${productId}`, { active: !product.active });
    await loadProducts();
    toast(product.active ? 'Đã ẩn khỏi danh mục' : 'Đã bán lại', 'success');
  } catch (error) {
    toast(error.message, 'error');
  }
}

async function removeProduct(productId) {
  const confirmed = await confirmDialog(
    'Xoá sản phẩm',
    'Sản phẩm sẽ bị xoá vĩnh viễn. Nếu chỉ muốn ngừng bán, hãy dùng nút ẩn thay vì xoá.',
    'Xoá',
  );
  if (!confirmed) return;
  try {
    await api.del(`/api/admin/products/${productId}`);
    await loadProducts();
    toast('Đã xoá sản phẩm', 'success');
  } catch (error) {
    toast(error.message, 'error');
  }
}
