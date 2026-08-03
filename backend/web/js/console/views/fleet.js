// Quản lý đội UAV: thêm, sửa, đổi trạng thái bảo trì, xoá.

import { api } from '../../api.js';
import { icon } from '../../icons.js';
import { confirmDialog, escapeHtml, openModal, relativeTime, toast, uavStatusBadge } from '../../ui.js';
import { loadUavs, state } from '../store.js';

export function renderFleet(container) {
  const threshold = Number(state.settings.low_battery_threshold ?? 30);

  container.innerHTML = `
    <div class="panel">
      <div class="panel__head">
        <h2>Đội UAV</h2><span class="spacer"></span>
        <span class="text-muted">${state.uavs.length} thiết bị</span>
        <button class="btn btn--sm" id="btn-add-uav">${icon('plus', { size: 16 })}Thêm UAV</button>
      </div>
      <div class="panel__body">
        ${state.uavs.length ? `<div class="fleet-grid">${state.uavs.map((uav) => tile(uav, threshold)).join('')}</div>`
          : `<div class="empty">${icon('drone', { size: 32 })}<strong>Chưa có UAV nào</strong>
             <p>Thêm UAV để bắt đầu điều phối đơn hàng.</p></div>`}
      </div>
    </div>`;

  container.querySelector('#btn-add-uav').onclick = () => openUavForm();
  container.querySelectorAll('[data-edit-uav]').forEach((button) => {
    button.onclick = () => openUavForm(state.uavs.find((uav) => uav.id === button.dataset.editUav));
  });
  container.querySelectorAll('[data-toggle-uav]').forEach((button) => {
    button.onclick = () => toggleMaintenance(button.dataset.toggleUav);
  });
  container.querySelectorAll('[data-del-uav]').forEach((button) => {
    button.onclick = () => removeUav(button.dataset.delUav);
  });
}

function tile(uav, threshold) {
  const level = uav.battery < threshold ? 'low' : uav.battery < 60 ? 'mid' : '';
  const busy = Boolean(uav.active_order_id);
  const inMaintenance = uav.status === 'MAINTENANCE';

  return `
    <div class="card uav-tile">
      <div class="uav-tile__head">
        <span class="uav-tile__avatar">${icon('drone', { size: 19 })}</span>
        <span class="uav-tile__id">
          <strong>${escapeHtml(uav.id)}</strong>
          <small>${escapeHtml(uav.model)} · tải ${uav.max_payload_kg} kg</small>
        </span>
        ${uavStatusBadge(uav.status)}
      </div>

      <div>
        <div class="battery-bar">
          <span class="battery-bar__fill ${level ? `battery-bar__fill--${level}` : ''}" style="width:${uav.battery}%"></span>
        </div>
        <p class="text-muted" style="margin-top:6px;font-size:12px">
          Pin ${uav.battery.toFixed(0)}%${uav.battery < threshold ? ' · dưới ngưỡng an toàn' : ''}
        </p>
      </div>

      <div class="uav-tile__stats">
        <div><small>Độ cao</small><strong class="tnum">${uav.altitude.toFixed(1)} m</strong></div>
        <div><small>Tốc độ</small><strong class="tnum">${uav.speed.toFixed(1)} m/s</strong></div>
        <div><small>Tín hiệu</small><strong>${escapeHtml(relativeTime(uav.last_seen))}</strong></div>
      </div>

      ${uav.note ? `<p class="text-muted" style="font-size:13px">${escapeHtml(uav.note)}</p>` : ''}
      ${busy ? `<p class="text-muted" style="font-size:13px">Đang thực hiện ${escapeHtml(uav.active_order_id)}</p>` : ''}

      <div class="uav-tile__foot">
        <button class="btn btn--secondary btn--sm" data-edit-uav="${escapeHtml(uav.id)}">${icon('edit', { size: 15 })}Sửa</button>
        <button class="btn btn--secondary btn--sm" data-toggle-uav="${escapeHtml(uav.id)}" ${busy ? 'disabled' : ''}>
          ${icon(inMaintenance ? 'check' : 'alert-triangle', { size: 15 })}${inMaintenance ? 'Cho hoạt động' : 'Bảo trì'}
        </button>
        <button class="btn btn--icon btn--sm" data-del-uav="${escapeHtml(uav.id)}" ${busy ? 'disabled' : ''}
                aria-label="Xoá ${escapeHtml(uav.id)}">${icon('trash', { size: 15 })}</button>
      </div>
    </div>`;
}

async function openUavForm(uav) {
  const editing = Boolean(uav);
  const result = await openModal({
    title: editing ? `Sửa ${uav.id}` : 'Thêm UAV mới',
    body: `
      ${editing ? '' : `<label class="field">
        <span class="field__label">Mã UAV</span>
        <input class="input" id="f-id" placeholder="UAV-04" maxlength="32">
        <span class="field__hint">Mã này phải trùng với UAV_ID của tiến trình mô phỏng hoặc thiết bị thật.</span>
      </label>`}
      <label class="field">
        <span class="field__label">Kiểu máy</span>
        <input class="input" id="f-model" value="${escapeHtml(uav?.model || 'Demo Quad X4')}" maxlength="80">
      </label>
      <label class="field">
        <span class="field__label">Tải trọng tối đa (kg)</span>
        <input class="input" id="f-payload" type="number" step="0.1" min="0.1" value="${uav?.max_payload_kg ?? 2.5}">
      </label>
      <label class="field" style="margin:0">
        <span class="field__label">Ghi chú</span>
        <input class="input" id="f-note" value="${escapeHtml(uav?.note || '')}" maxlength="250" placeholder="Ví dụ: mới thay pin 03/2026">
      </label>`,
    actions: [
      { label: 'Huỷ', variant: 'secondary', onClick: () => null },
      {
        label: editing ? 'Lưu thay đổi' : 'Thêm UAV',
        onClick: (scrim) => {
          const payload = {
            model: scrim.querySelector('#f-model').value.trim(),
            max_payload_kg: Number(scrim.querySelector('#f-payload').value),
            note: scrim.querySelector('#f-note').value.trim(),
          };
          if (!editing) {
            payload.id = scrim.querySelector('#f-id').value.trim().toUpperCase();
            if (payload.id.length < 2) {
              toast('Hãy nhập mã UAV', 'error');
              return false;
            }
          }
          if (!(payload.max_payload_kg > 0)) {
            toast('Tải trọng phải lớn hơn 0', 'error');
            return false;
          }
          return payload;
        },
      },
    ],
  });
  if (!result) return;

  try {
    if (editing) await api.patch(`/api/admin/uavs/${uav.id}`, result);
    else await api.post('/api/admin/uavs', result);
    await loadUavs();
    toast(editing ? 'Đã cập nhật UAV' : `Đã thêm ${result.id}`, 'success');
  } catch (error) {
    toast(error.message, 'error');
  }
}

async function toggleMaintenance(uavId) {
  const uav = state.uavs.find((item) => item.id === uavId);
  if (!uav) return;
  const next = uav.status === 'MAINTENANCE' ? 'AVAILABLE' : 'MAINTENANCE';
  try {
    await api.patch(`/api/admin/uavs/${uavId}`, { status: next });
    await loadUavs();
    toast(next === 'MAINTENANCE' ? `${uavId} chuyển sang bảo trì` : `${uavId} đã sẵn sàng`, 'success');
  } catch (error) {
    toast(error.message, 'error');
  }
}

async function removeUav(uavId) {
  const confirmed = await confirmDialog('Xoá UAV', `${uavId} sẽ bị xoá khỏi hệ thống. Thao tác này không hoàn tác được.`, 'Xoá');
  if (!confirmed) return;
  try {
    await api.del(`/api/admin/uavs/${uavId}`);
    await loadUavs();
    toast(`Đã xoá ${uavId}`, 'success');
  } catch (error) {
    toast(error.message, 'error');
  }
}
