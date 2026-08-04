// Tài khoản khách hàng: hồ sơ, tuỳ chọn giao hàng, mật khẩu, thiết bị đăng nhập.

import { api } from '../api.js';
import { icon } from '../icons.js';
import { confirmDialog, escapeHtml, formatDateTime, toast } from '../ui.js';
import { state } from './store.js';

let profile = null;
let onProfileChange = () => {};

export function currentProfile() {
  return profile;
}

export async function loadProfile() {
  profile = await api.get('/api/profile');
  fillForms();
  onProfileChange(profile);
  return profile;
}

export function initProfileForms({ onChange }) {
  onProfileChange = onChange;

  document.getElementById('profile-form').onsubmit = (event) => {
    event.preventDefault();
    save({
      full_name: field('pf-full-name'),
      display_name: field('pf-display-name'),
      gender: document.getElementById('pf-gender').value,
      date_of_birth: field('pf-dob'),
      phone: field('pf-phone'),
      email: field('pf-email'),
    }, 'Đã lưu thông tin cá nhân');
  };

  document.getElementById('delivery-form').onsubmit = (event) => {
    event.preventDefault();
    const address = document.getElementById('pf-default-address').value;
    save({
      default_address_id: address ? Number(address) : 0,
      default_note: field('pf-default-note'),
      notify_orders: document.getElementById('pf-notify').checked,
    }, 'Đã lưu tuỳ chọn giao hàng');
  };

  document.getElementById('password-form').onsubmit = (event) => {
    event.preventDefault();
    changePassword();
  };

  document.getElementById('btn-refresh-sessions').onclick = () => renderSessions();
}

function field(id) {
  return document.getElementById(id).value.trim();
}

function fillForms() {
  if (!profile) return;
  const set = (id, value) => { document.getElementById(id).value = value ?? ''; };
  set('pf-full-name', profile.full_name);
  set('pf-display-name', profile.display_name);
  set('pf-gender', profile.gender);
  set('pf-dob', profile.date_of_birth);
  set('pf-phone', profile.phone);
  set('pf-email', profile.email);
  set('pf-default-note', profile.default_note);
  document.getElementById('pf-notify').checked = Boolean(profile.notify_orders);
  renderAddressOptions();
}

/** Danh sách địa chỉ mặc định lấy từ sổ địa chỉ, nên phải vẽ lại mỗi khi sổ đổi. */
export function renderAddressOptions() {
  const select = document.getElementById('pf-default-address');
  if (!select) return;
  // Đang mở dropdown mà dựng lại options thì nó tự đóng, mất lựa chọn dở dang.
  if (document.activeElement === select) return;
  const chosen = profile?.default_address_id;
  select.innerHTML = `<option value="">Không đặt mặc định</option>` + state.addresses.map((address) => `
    <option value="${address.id}" ${address.id === chosen ? 'selected' : ''}>
      ${escapeHtml(address.label)} — ${escapeHtml(address.address)}
    </option>`).join('');
}

async function save(patch, message) {
  try {
    profile = await api.patch('/api/profile', patch);
    fillForms();
    onProfileChange(profile);
    toast(message, 'success');
  } catch (error) {
    toast(error.message, 'error');
  }
}

async function changePassword() {
  const current = document.getElementById('pw-current').value;
  const next = document.getElementById('pw-new').value;
  const confirm = document.getElementById('pw-confirm').value;

  if (next !== confirm) return toast('Hai lần nhập mật khẩu mới không khớp', 'error');
  if (next.length < 6) return toast('Mật khẩu mới cần ít nhất 6 ký tự', 'error');

  try {
    const result = await api.post('/api/profile/password', { current_password: current, new_password: next });
    document.querySelectorAll('#password-form input').forEach((input) => { input.value = ''; });
    toast(result.signed_out_devices
      ? `Đã đổi mật khẩu. ${result.signed_out_devices} thiết bị khác đã bị đăng xuất.`
      : 'Đã đổi mật khẩu', 'success');
    renderSessions();
  } catch (error) {
    toast(error.message, 'error');
  }
}

export async function renderSessions() {
  const container = document.getElementById('session-list');
  if (!container) return;

  let sessions;
  try {
    sessions = await api.get('/api/profile/sessions');
  } catch (error) {
    container.innerHTML = `<p class="field__error">${escapeHtml(error.message)}</p>`;
    return;
  }

  container.innerHTML = sessions.map((session) => `
    <div class="card address-row">
      <div class="address-row__icon">${icon(session.is_current ? 'monitor' : 'globe', { size: 18 })}</div>
      <div class="address-row__body">
        <strong>${escapeHtml(session.device)}</strong>
        <small>Đăng nhập ${formatDateTime(session.created_at)}</small>
      </div>
      ${session.is_current
        ? '<span class="badge badge--success">Thiết bị này</span>'
        : `<button class="btn btn--icon btn--sm" data-revoke="${escapeHtml(session.session_id)}"
                   aria-label="Đăng xuất ${escapeHtml(session.device)}">${icon('logout', { size: 16 })}</button>`}
    </div>`).join('');

  container.querySelectorAll('[data-revoke]').forEach((button) => {
    button.onclick = async () => {
      const confirmed = await confirmDialog(
        'Đăng xuất thiết bị', 'Thiết bị đó sẽ phải đăng nhập lại để dùng tài khoản.', 'Đăng xuất',
      );
      if (!confirmed) return;
      try {
        await api.del(`/api/profile/sessions/${button.dataset.revoke}`);
        toast('Đã đăng xuất thiết bị', 'success');
        renderSessions();
      } catch (error) {
        toast(error.message, 'error');
      }
    };
  });
}
