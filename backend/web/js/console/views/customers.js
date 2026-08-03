// Danh sách khách hàng kèm số đơn, chi tiêu và điểm hài lòng.

import { icon } from '../../icons.js';
import { escapeHtml, formatDateTime, formatMoney } from '../../ui.js';
import { state } from '../store.js';

export function renderCustomers(container) {
  container.innerHTML = `
    <div class="panel">
      <div class="panel__head">
        <h2>Khách hàng</h2><span class="spacer"></span>
        <span class="text-muted">${state.customers.length} tài khoản</span>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr>
            <th>Tài khoản</th><th>Điện thoại</th><th>Số đơn</th><th>Đã chi tiêu</th>
            <th>Đánh giá TB</th><th>Đơn gần nhất</th>
          </tr></thead>
          <tbody>
            ${state.customers.length ? state.customers.map((customer) => `
              <tr>
                <td class="td-wrap">
                  <strong>${escapeHtml(customer.display_name)}</strong>
                  <div class="text-muted" style="font-size:13px">${escapeHtml(customer.username)}</div>
                </td>
                <td class="tnum">${escapeHtml(customer.phone || '—')}</td>
                <td class="tnum">${customer.order_count}</td>
                <td class="tnum">${formatMoney(customer.total_spent)}</td>
                <td class="tnum">${customer.avg_rating ? `${Number(customer.avg_rating).toFixed(1)} / 5` : '—'}</td>
                <td class="tnum">${customer.last_order_at ? formatDateTime(customer.last_order_at) : 'Chưa đặt đơn'}</td>
              </tr>`).join('')
            : `<tr><td colspan="6"><div class="empty">${icon('users', { size: 30 })}
                <strong>Chưa có khách hàng</strong></div></td></tr>`}
          </tbody>
        </table>
      </div>
    </div>`;
}
