// Cấu hình vận hành: trạm xuất phát, tải trọng, ngưỡng pin, đường truy cập mạng.

import { api } from '../../api.js';
import { icon } from '../../icons.js';
import { escapeHtml, toast } from '../../ui.js';
import { loadSettings, loadStats, state } from '../store.js';

// Kết quả dò mạng được nhớ lại để chuyển tab qua lại không phải gọi API mỗi lần.
let network = null;

const KIND_LABEL = {
  vpn: 'VPN',
  lan: 'Mạng nội bộ',
  public: 'Công cộng',
};

export function renderSettings(container) {
  const settings = state.settings;

  container.innerHTML = `
    <div class="settings-grid">
      <form class="panel panel--wide" id="net-form">
        <div class="panel__head">
          <h2>Đường truy cập cho máy khách</h2>
          <span class="spacer"></span>
          <button class="btn btn--secondary btn--sm" type="button" id="net-rescan">
            ${icon('refresh', { size: 15 })}Dò lại
          </button>
        </div>
        <div class="panel__body">
          <p class="text-muted" style="margin-bottom:var(--sp-4)">
            Chọn địa chỉ máy chủ sẽ công bố cho điện thoại và máy khách. Nếu cả hai máy cùng
            nằm trong một VPN (Tailscale, WireGuard), hãy chọn địa chỉ VPN — địa chỉ đó không
            đổi khi bạn sang router hay mạng Wi-Fi khác.
          </p>
          <div id="net-body"><div class="skeleton" style="height:120px"></div></div>
        </div>
      </form>

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

  container.querySelector('#net-rescan').onclick = () => loadNetwork(container, true);
  container.querySelector('#net-form').onsubmit = (event) => {
    event.preventDefault();
    saveNetwork(container);
  };
  loadNetwork(container, network === null);
}

// ---------- Đường truy cập ----------

async function loadNetwork(container, refetch) {
  if (refetch) {
    try {
      network = await api.get('/api/admin/network');
    } catch (error) {
      container.querySelector('#net-body').innerHTML =
        `<p class="field__error">Không đọc được thông tin mạng: ${escapeHtml(error.message)}</p>`;
      return;
    }
  }
  renderNetwork(container);
}

function renderNetwork(container) {
  const body = container.querySelector('#net-body');
  if (!body || !network) return;

  const selected = network.access_host || network.served_host || '';
  const known = network.addresses.some((item) => item.address === selected);

  body.innerHTML = `
    <div class="net-list" role="radiogroup" aria-label="Địa chỉ máy chủ">
      ${network.addresses.map((item) => netOption(item, item.address === selected)).join('')}
      ${netOption({ address: '', kind: 'custom', hint: 'Tên miền VPN hoặc IP bạn tự nhập' }, !known)}
    </div>

    <label class="field" style="margin-top:var(--sp-4)">
      <span class="field__label">Địa chỉ tự nhập</span>
      <input class="input" id="net-host" placeholder="may-chu.tail1234.ts.net hoặc https://abc.trycloudflare.com"
             value="${escapeHtml(known ? '' : selected)}" ${known ? 'disabled' : ''}>
      <span class="field__hint">
        Dán được cả link tunnel đầy đủ — khi đó phần cổng bên dưới sẽ bị bỏ qua.
        Bỏ trống thì máy khách dùng đúng địa chỉ đang gõ trên trình duyệt.
      </span>
    </label>

    <label class="field">
      <span class="field__label">Cổng phục vụ</span>
      <input class="input tnum" id="net-port" type="number" min="1" max="65535"
             value="${escapeHtml(network.access_port)}">
      <span class="field__hint">
        Đang chạy ở cổng ${escapeHtml(String(network.served_port))}.
        Đổi cổng chỉ có hiệu lực sau khi khởi động lại <code>run_demo.py</code>.
      </span>
    </label>

    <div class="net-firewall" id="net-firewall"></div>

    <div class="net-links" id="net-links"></div>

    <button class="btn btn--block" type="submit" style="margin-top:var(--sp-4)">
      ${icon('check', { size: 17 })}Lưu đường truy cập
    </button>

    <p class="text-muted" style="margin-top:var(--sp-4);font-size:13px">
      Tên máy: <strong>${escapeHtml(network.hostname)}</strong>.
      Máy chủ lắng nghe trên mọi card mạng, nên chọn địa chỉ nào cũng không cần khởi động lại —
      trừ khi bạn đổi cổng.
    </p>`;

  body.querySelectorAll('[data-address]').forEach((option) => {
    option.onclick = () => {
      body.querySelectorAll('[data-address]').forEach((item) => item.classList.remove('is-active'));
      option.classList.add('is-active');
      const custom = option.dataset.address === '';
      const host = body.querySelector('#net-host');
      host.disabled = !custom;
      if (custom) host.focus();
      renderLinks(container);
    };
  });

  body.querySelector('#net-host').oninput = () => renderLinks(container);
  body.querySelector('#net-port').oninput = () => {
    renderLinks(container);
    queueFirewall(container);
  };
  renderLinks(container);
  loadFirewall(container);
}

// ---------- Trạng thái tường lửa ----------

let firewallTimer = null;

/** Gõ số cổng thì chờ người dùng gõ xong mới hỏi, vì mỗi lần kiểm tra mất khoảng 1 giây. */
function queueFirewall(container) {
  clearTimeout(firewallTimer);
  firewallTimer = setTimeout(() => loadFirewall(container), 600);
}

async function loadFirewall(container) {
  const box = container.querySelector('#net-firewall');
  const port = Number(container.querySelector('#net-port')?.value);
  if (!box || !port || port < 1 || port > 65535) return;

  // Tunnel nối ra ngoài từ chính máy này nên không có kết nối đến để tường lửa chặn.
  // Báo "chưa mở cổng 8000" lúc này là lạc đề và khiến người dùng đi sửa nhầm chỗ.
  if (isOrigin(chosenHost(container))) {
    box.innerHTML = `<p class="text-muted">${icon('shield', { size: 14 })}
      Đi qua tunnel nên không phụ thuộc tường lửa hay cổng của máy chủ.</p>`;
    return;
  }

  box.innerHTML = `<p class="text-muted"><span class="spinner"></span> Đang kiểm tra tường lửa cho cổng ${port}…</p>`;
  let status;
  try {
    status = await api.get(`/api/admin/firewall?port=${port}`);
  } catch (error) {
    box.innerHTML = `<p class="text-muted">${escapeHtml(error.message)}</p>`;
    return;
  }
  // Người dùng có thể đã gõ tiếp số cổng khác trong lúc chờ.
  if (Number(container.querySelector('#net-port')?.value) !== status.port) return;

  if (status.state === 'unknown') {
    box.innerHTML = `<p class="text-muted">${icon('shield', { size: 14 })} ${escapeHtml(status.hint)}</p>`;
    return;
  }

  const ok = status.state === 'allowed';
  box.innerHTML = `
    <div class="net-firewall__row">
      <span class="badge ${ok ? 'badge--success' : 'badge--pending'}">
        ${icon('shield', { size: 14 })}${ok ? 'Tường lửa đã mở' : 'Tường lửa chưa mở'}
      </span>
      <span class="net-firewall__hint">${escapeHtml(status.hint)}</span>
    </div>
    ${ok
      ? `<p class="net-firewall__rules">Rule đang cho phép: ${escapeHtml(status.rules.join(' · '))}</p>`
      : `<p class="net-firewall__rules">Mở PowerShell bằng quyền Administrator rồi chạy lệnh sau:</p>
         <div class="net-link">
           <code class="net-link__url">${escapeHtml(status.command)}</code>
           <button class="btn btn--icon btn--sm" type="button" data-copy-cmd aria-label="Sao chép lệnh mở tường lửa">
             ${icon('copy', { size: 16 })}
           </button>
         </div>`}`;

  const copy = box.querySelector('[data-copy-cmd]');
  if (copy) {
    copy.onclick = async () => {
      try {
        await navigator.clipboard.writeText(status.command);
        toast('Đã sao chép lệnh', 'success');
      } catch {
        toast('Trình duyệt chặn sao chép. Hãy bôi đen lệnh rồi copy thủ công.', 'error');
      }
    };
  }
}

function netOption(item, active) {
  const glyph = { vpn: 'shield', lan: 'wifi', public: 'globe', custom: 'link' }[item.kind] || 'wifi';
  const title = item.kind === 'custom' ? 'Tự nhập địa chỉ' : item.address;
  return `
    <button type="button" class="net-option ${active ? 'is-active' : ''}"
            data-address="${escapeHtml(item.address)}" role="radio" aria-checked="${active}">
      <span class="net-option__icon">${icon(glyph, { size: 18 })}</span>
      <span class="net-option__body">
        <strong class="tnum">${escapeHtml(title)}</strong>
        <small>${escapeHtml(item.hint)}</small>
      </span>
      ${item.kind === 'custom' ? '' : `<span class="badge">${escapeHtml(KIND_LABEL[item.kind] || item.kind)}</span>`}
      ${item.is_default ? '<span class="badge badge--progress">Mặc định</span>' : ''}
    </button>`;
}

function chosenHost(container) {
  const active = container.querySelector('.net-option.is-active');
  if (!active) return '';
  return active.dataset.address || container.querySelector('#net-host').value.trim();
}

/** Địa chỉ dạng origin đầy đủ (link tunnel) thì không được ghép thêm cổng. */
function isOrigin(host) {
  return host.includes('://');
}

function renderLinks(container) {
  const host = chosenHost(container) || network.served_host || 'localhost';
  const port = container.querySelector('#net-port').value || network.served_port;
  // Tunnel phục vụ ở cổng 443 chứ không phải cổng nội bộ; gắn thêm ":8000" là link hỏng.
  const base = isOrigin(host) ? host.replace(/\/$/, '') : `http://${host}:${port}`;
  const box = container.querySelector('#net-links');

  box.innerHTML = [
    { label: 'App khách hàng', url: `${base}/` },
    { label: 'Console điều phối', url: `${base}/operator` },
  ].map((link) => `
    <div class="net-link">
      <span class="net-link__label">${escapeHtml(link.label)}</span>
      <a class="net-link__url tnum" href="${escapeHtml(link.url)}" target="_blank" rel="noopener">${escapeHtml(link.url)}</a>
      <button class="btn btn--icon btn--sm" type="button" data-copy="${escapeHtml(link.url)}" aria-label="Sao chép ${escapeHtml(link.label)}">
        ${icon('copy', { size: 16 })}
      </button>
    </div>`).join('');

  box.querySelectorAll('[data-copy]').forEach((button) => {
    button.onclick = async () => {
      try {
        await navigator.clipboard.writeText(button.dataset.copy);
        toast('Đã sao chép liên kết', 'success');
      } catch {
        // clipboard API bị chặn khi truy cập qua http không phải localhost.
        toast('Trình duyệt chặn sao chép. Hãy chọn liên kết rồi copy thủ công.', 'error');
      }
    };
  });
}

async function saveNetwork(container) {
  const port = Number(container.querySelector('#net-port').value);
  if (!port || port < 1 || port > 65535) return toast('Cổng phải nằm trong khoảng 1–65535', 'error');
  try {
    await api.patch('/api/admin/settings', { access_host: chosenHost(container), access_port: port });
    network = await api.get('/api/admin/network');
    await loadSettings();
    renderNetwork(container);
    toast(port === network.served_port
      ? 'Đã lưu đường truy cập'
      : 'Đã lưu. Khởi động lại run_demo.py để dùng cổng mới.', 'success');
  } catch (error) {
    toast(error.message, 'error');
  }
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
