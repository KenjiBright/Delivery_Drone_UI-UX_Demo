// Thống kê: đơn theo ngày, doanh thu, phân bổ trạng thái, sản phẩm bán chạy.

import { icon } from '../../icons.js';
import { escapeHtml, formatDuration, formatMoney, statusLabel } from '../../ui.js';
import { barChart, donutChart, lineChart, revenueChart } from '../charts.js';
import { state } from '../store.js';

export function renderAnalytics(container) {
  const stats = state.stats;
  if (!stats) {
    container.innerHTML = `<div class="card skeleton" style="height:220px"></div>`;
    return;
  }

  const { totals, timeline, status_breakdown, top_products } = stats;
  const dayLabel = (date) => {
    const [, month, day] = date.split('-');
    return `${day}/${month}`;
  };

  const orderPoints = timeline.map((row) => ({ label: dayLabel(row.date), value: row.orders }));
  const revenuePoints = timeline.map((row) => ({ label: dayLabel(row.date), value: row.revenue }));
  const statusItems = status_breakdown.map((row) => ({ label: statusLabel(row.status), value: row.count }));

  container.innerHTML = `
    <div class="kpis">
      ${kpi('Tổng đơn', totals.orders, 'receipt', 'brand', `${totals.cancelled} đơn bị huỷ`)}
      ${kpi('Doanh thu', formatMoney(totals.revenue), 'wallet', 'ok', `từ ${totals.completed} đơn hoàn thành`)}
      ${kpi('Thời gian giao TB', totals.avg_delivery_seconds ? formatDuration(totals.avg_delivery_seconds) : '—', 'gauge', '', 'tính từ lúc cất cánh')}
      ${kpi('Điểm hài lòng', totals.avg_rating ? `${totals.avg_rating} / 5` : '—', 'star', 'warn', `${totals.rating_count} lượt đánh giá`)}
    </div>

    <div class="chart-grid">
      <div class="panel">
        <div class="panel__head"><h2>Đơn hàng theo ngày</h2><span class="spacer"></span>
          <span class="text-muted">${timeline.length} ngày gần nhất</span></div>
        <div class="panel__body">${lineChart(orderPoints, { label: 'Đơn hàng' })}</div>
      </div>

      <div class="panel">
        <div class="panel__head"><h2>Doanh thu theo ngày</h2></div>
        <div class="panel__body">${revenueChart(revenuePoints)}</div>
      </div>

      <div class="panel">
        <div class="panel__head"><h2>Phân bổ trạng thái</h2></div>
        <div class="panel__body">${donutChart(statusItems, { label: 'Phân bổ trạng thái đơn' })}</div>
      </div>

      <div class="panel">
        <div class="panel__head"><h2>Sản phẩm được giao nhiều nhất</h2></div>
        <div class="panel__body">
          ${top_products.length
            ? barChart(top_products.map((row) => ({ label: row.name, value: row.quantity })), { label: 'Số lượng' })
            : `<div class="empty">${icon('package', { size: 28 })}<strong>Chưa có dữ liệu</strong></div>`}
        </div>
      </div>
    </div>`;
}

function kpi(label, value, glyph, tone, sub) {
  return `
    <div class="card kpi">
      <span class="kpi__icon ${tone ? `kpi__icon--${tone}` : ''}">${icon(glyph, { size: 20 })}</span>
      <div class="kpi__body">
        <p class="kpi__label">${escapeHtml(label)}</p>
        <p class="kpi__value">${escapeHtml(String(value))}</p>
        <p class="kpi__sub">${escapeHtml(sub)}</p>
      </div>
    </div>`;
}
