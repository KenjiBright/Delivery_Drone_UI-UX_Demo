// Tài khoản điều phối viên: hồ sơ nhân viên, trạng thái trực, đổi mật khẩu.

import { api } from '../../api.js';
import { icon } from '../../icons.js';
import { escapeHtml, formatDateTime, toast } from '../../ui.js';
import { state } from '../store.js';

export const DUTY = {
  ON_DUTY: { label: 'Đang trực', tone: 'success' },
  BREAK: { label: 'Tạm nghỉ', tone: 'pending' },
  OFF_DUTY: { label: 'Hết ca', tone: '' },
};

const GENDERS = [['', 'Không nêu'], ['male', 'Nam'], ['female', 'Nữ'], ['other', 'Khác']];

let profile = null;
let onProfileChange = () => {};

export function initAccount({ onChange }) {
  onProfileChange = onChange;
}

export async function loadProfile() {
  profile = await api.get('/api/profile');
  onProfileChange(profile);
  return profile;
}

export function currentProfile() {
  return profile;
}

export function renderAccount(container) {
  if (!profile) {
    container.innerHTML = `<div class="card skeleton" style="height:180px"></div>`;
    loadProfile().then(() => renderAccount(container)).catch((error) => toast(error.message, 'error'));
    return;
  }

  container.innerHTML = `
    <div class="settings-grid">
      <div class="panel panel--wide">
        <div class="panel__head"><h2>Ca trực</h2></div>
        <div class="panel__body">
          <p class="text-muted" style="margin-bottom:var(--sp-4)">
            Trạng thái này hiện trên thanh trên của console để cả đội biết ai đang cầm máy.
          </p>
          <div class="duty-switch" role="radiogroup" aria-label="Trạng thái trực">
            ${Object.entries(DUTY).map(([key, info]) => `
              <button type="button" class="duty-option ${profile.duty_status === key ? 'is-active' : ''}"
                      data-duty="${key}" role="radio" aria-checked="${profile.duty_status === key}">
                <span class="badge badge--${info.tone} badge--dot">${escapeHtml(info.label)}</span>
              </button>`).join('')}
          </div>
        </div>
      </div>

      <form class="panel" id="staff-form">
        <div class="panel__head"><h2>Hồ sơ nhân viên</h2></div>
        <div class="panel__body">
          ${field('full_name', 'Họ và tên thật', profile.full_name)}
          ${field('employee_code', 'Mã nhân viên', profile.employee_code, 'Ví dụ: DP-001')}
          ${field('job_title', 'Chức danh', profile.job_title)}
          ${field('department', 'Bộ phận', profile.department)}
          <button class="btn btn--block" type="submit">${icon('check', { size: 17 })}Lưu hồ sơ</button>
        </div>
      </form>

      <form class="panel" id="contact-form">
        <div class="panel__head"><h2>Liên hệ và hiển thị</h2></div>
        <div class="panel__body">
          ${field('display_name', 'Tên hiển thị', profile.display_name)}
          ${field('phone', 'Số điện thoại', profile.phone)}
          ${field('email', 'Email', profile.email, '', 'email')}
          <label class="field">
            <span class="field__label">Giới tính</span>
            <select class="input" id="f-gender">
              ${GENDERS.map(([value, label]) => `
                <option value="${value}" ${profile.gender === value ? 'selected' : ''}>${label}</option>`).join('')}
            </select>
          </label>
          <button class="btn btn--block" type="submit">${icon('check', { size: 17 })}Lưu thông tin</button>
        </div>
      </form>

      <form class="panel" id="password-form">
        <div class="panel__head"><h2>Đổi mật khẩu</h2></div>
        <div class="panel__body">
          <label class="field">
            <span class="field__label">Mật khẩu hiện tại</span>
            <input class="input" id="p-current" type="password" autocomplete="current-password" required>
          </label>
          <label class="field">
            <span class="field__label">Mật khẩu mới</span>
            <input class="input" id="p-new" type="password" minlength="6" autocomplete="new-password" required>
            <span class="field__hint">Tối thiểu 6 ký tự. Mọi thiết bị khác sẽ phải đăng nhập lại.</span>
          </label>
          <label class="field">
            <span class="field__label">Nhập lại mật khẩu mới</span>
            <input class="input" id="p-confirm" type="password" autocomplete="new-password" required>
          </label>
          <button class="btn btn--block" type="submit">${icon('lock', { size: 17 })}Đổi mật khẩu</button>
        </div>
      </form>

      <div class="panel">
        <div class="panel__head"><h2>Thông tin phiên</h2></div>
        <div class="panel__body">
          <dl class="detail-list">
            <div class="detail-row"><dt>Tên đăng nhập</dt><dd>${escapeHtml(profile.username)}</dd></div>
            <div class="detail-row"><dt>Vai trò</dt><dd>Điều phối viên</dd></div>
            <div class="detail-row"><dt>Tạo lúc</dt><dd>${formatDateTime(profile.created_at)}</dd></div>
            <div class="detail-row"><dt>Cập nhật</dt><dd>${profile.updated_at ? formatDateTime(profile.updated_at) : 'Chưa sửa lần nào'}</dd></div>
            <div class="detail-row"><dt>UAV đang quản lý</dt><dd class="tnum">${state.uavs.length}</dd></div>
          </dl>
        </div>
      </div>
    </div>`;

  container.querySelectorAll('[data-duty]').forEach((button) => {
    button.onclick = () => save(container, { duty_status: button.dataset.duty });
  });

  container.querySelector('#staff-form').onsubmit = (event) => {
    event.preventDefault();
    save(container, {
      full_name: value(container, 'full_name'),
      employee_code: value(container, 'employee_code'),
      job_title: value(container, 'job_title'),
      department: value(container, 'department'),
    });
  };

  container.querySelector('#contact-form').onsubmit = (event) => {
    event.preventDefault();
    save(container, {
      display_name: value(container, 'display_name'),
      phone: value(container, 'phone'),
      email: value(container, 'email'),
      gender: container.querySelector('#f-gender').value,
    });
  };

  container.querySelector('#password-form').onsubmit = (event) => {
    event.preventDefault();
    changePassword(container);
  };
}

function field(name, label, current, placeholder = '', type = 'text') {
  return `
    <label class="field">
      <span class="field__label">${escapeHtml(label)}</span>
      <input class="input" id="f-${name}" type="${type}" value="${escapeHtml(current || '')}"
             placeholder="${escapeHtml(placeholder)}">
    </label>`;
}

function value(container, name) {
  return container.querySelector(`#f-${name}`).value.trim();
}

async function save(container, patch) {
  try {
    profile = await api.patch('/api/profile', patch);
    onProfileChange(profile);
    renderAccount(container);
    toast('Đã lưu tài khoản', 'success');
  } catch (error) {
    toast(error.message, 'error');
  }
}

async function changePassword(container) {
  const current = container.querySelector('#p-current').value;
  const next = container.querySelector('#p-new').value;
  const confirm = container.querySelector('#p-confirm').value;

  if (next !== confirm) return toast('Hai lần nhập mật khẩu mới không khớp', 'error');
  if (next.length < 6) return toast('Mật khẩu mới cần ít nhất 6 ký tự', 'error');

  try {
    const result = await api.post('/api/profile/password', { current_password: current, new_password: next });
    container.querySelectorAll('#password-form input').forEach((input) => { input.value = ''; });
    toast(result.signed_out_devices
      ? `Đã đổi mật khẩu. ${result.signed_out_devices} thiết bị khác bị đăng xuất.`
      : 'Đã đổi mật khẩu', 'success');
  } catch (error) {
    toast(error.message, 'error');
  }
}
