// Cấu hình vận hành: trạm xuất phát, tải trọng, ngưỡng pin.

import { api } from '../../api.js';
import { icon } from '../../icons.js';
import { escapeHtml, toast } from '../../ui.js';
import { loadSettings, loadStats, state } from '../store.js';

export function renderSettings(container) {
  const settings = state.settings;

  container.innerHTML = `
    <div class="settings-grid">
      <form class="panel" id="ops-form">
        <div class="panel__head"><h2>Thông số vận hành</h2></div>
        <div class="panel__body">
          <label class="field">
            <span class="field__label">Tên dịch vụ</span>
            <input class="input" id="s-name" value="${escapeHtml(settings.service_name || 'UAV Delivery')}" maxlength="60">
          </label>
          <label class="field">
            <span class="field__label">Tải trọng tối đa mỗi đơn (kg)</span>
            <input class="input" id="s-payload" type="number" step="0.1" min="0.1" value="${escapeHtml(settings.max_payload_kg || '2.5')}">
            <span class="field__hint">Đơn vượt ngưỡng này sẽ bị từ chối ngay khi khách đặt.</span>
          </label>
          <label class="field" style="margin:0">
            <span class="field__label">Ngưỡng cảnh báo pin yếu (%)</span>
            <input class="input" id="s-battery" type="number" min="0" max="100" value="${escapeHtml(settings.low_battery_threshold || '30')}">
            <span class="field__hint">UAV dưới ngưỡng sẽ hiện cảnh báo ở đầu console.</span>
          </label>
          <button class="btn btn--block" type="submit" style="margin-top:var(--sp-5)">
            ${icon('check', { size: 17 })}Lưu thông số
          </button>
        </div>
      </form>

      <form class="panel" id="home-form">
        <div class="panel__head"><h2>Trạm xuất phát</h2></div>
        <div class="panel__body">
          <p class="text-muted" style="margin-bottom:var(--sp-4)">
            Toạ độ nơi UAV cất cánh và quay về. Đổi giá trị này sẽ ảnh hưởng tới mọi chuyến bay tiếp theo.
          </p>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--sp-3)">
            <label class="field">
              <span class="field__label">Vĩ độ</span>
              <input class="input tnum" id="s-lat" type="number" step="0.000001" value="${escapeHtml(settings.home_lat || '21.0278')}">
            </label>
            <label class="field">
              <span class="field__label">Kinh độ</span>
              <input class="input tnum" id="s-lon" type="number" step="0.000001" value="${escapeHtml(settings.home_lon || '105.8342')}">
            </label>
          </div>
          <button class="btn btn--block" type="submit">${icon('map-pin', { size: 17 })}Lưu trạm xuất phát</button>
        </div>
      </form>

      <div class="panel">
        <div class="panel__head"><h2>Thông tin hệ thống</h2></div>
        <div class="panel__body">
          <dl class="detail-list">
            <div class="detail-row"><dt>Tài khoản</dt><dd>${escapeHtml(state.user?.display_name || '—')}</dd></div>
            <div class="detail-row"><dt>Vai trò</dt><dd>Điều phối viên</dd></div>
            <div class="detail-row"><dt>Số UAV</dt><dd class="tnum">${state.uavs.length}</dd></div>
            <div class="detail-row"><dt>Số sản phẩm</dt><dd class="tnum">${state.products.length}</dd></div>
            <div class="detail-row"><dt>Tổng đơn</dt><dd class="tnum">${state.stats?.totals.orders ?? '—'}</dd></div>
          </dl>
          <p class="text-muted" style="margin-top:var(--sp-4);font-size:13px">
            Phiên đăng nhập được lưu trong RAM của backend. Khởi động lại backend sẽ yêu cầu đăng nhập lại.
          </p>
        </div>
      </div>
    </div>`;

  container.querySelector('#ops-form').onsubmit = (event) => {
    event.preventDefault();
    save({
      service_name: container.querySelector('#s-name').value.trim(),
      max_payload_kg: Number(container.querySelector('#s-payload').value),
      low_battery_threshold: Number(container.querySelector('#s-battery').value),
    });
  };

  container.querySelector('#home-form').onsubmit = (event) => {
    event.preventDefault();
    save({
      home_lat: Number(container.querySelector('#s-lat').value),
      home_lon: Number(container.querySelector('#s-lon').value),
    });
  };
}

async function save(patch) {
  try {
    await api.patch('/api/admin/settings', patch);
    await Promise.all([loadSettings(), loadStats()]);
    toast('Đã lưu cấu hình', 'success');
  } catch (error) {
    toast(error.message, 'error');
  }
}
