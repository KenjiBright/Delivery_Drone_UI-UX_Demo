// Biểu đồ vẽ bằng SVG thuần, không dùng thư viện ngoài.
// Mỗi biểu đồ đều kèm bảng dữ liệu ẩn để trình đọc màn hình đọc được.

import { escapeHtml, formatMoney } from '../ui.js';

const PALETTE = ['#2f81f7', '#3fb950', '#d29922', '#f85149', '#a371f7', '#39c5cf'];

function niceMax(value) {
  if (value <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  return Math.ceil(value / magnitude) * magnitude;
}

/** Biểu đồ đường số đơn theo ngày. */
export function lineChart(points, { height = 180, label = 'Đơn hàng' } = {}) {
  if (!points.length) return emptyChart();

  const width = 640;
  const padding = { top: 12, right: 12, bottom: 26, left: 34 };
  const innerW = width - padding.left - padding.right;
  const innerH = height - padding.top - padding.bottom;
  const max = niceMax(Math.max(...points.map((point) => point.value)));

  const x = (index) => padding.left + (points.length === 1 ? innerW / 2 : (index / (points.length - 1)) * innerW);
  const y = (value) => padding.top + innerH - (value / max) * innerH;

  const line = points.map((point, index) => `${index ? 'L' : 'M'}${x(index).toFixed(1)},${y(point.value).toFixed(1)}`).join(' ');
  const area = `${line} L${x(points.length - 1).toFixed(1)},${padding.top + innerH} L${x(0).toFixed(1)},${padding.top + innerH} Z`;

  const gridLines = [0, 0.5, 1].map((ratio) => {
    const yPos = padding.top + innerH * (1 - ratio);
    return `<line class="grid-line" x1="${padding.left}" y1="${yPos}" x2="${width - padding.right}" y2="${yPos}"/>
            <text x="${padding.left - 6}" y="${yPos + 3}" text-anchor="end">${Math.round(max * ratio)}</text>`;
  }).join('');

  // Chỉ ghi nhãn thưa để trục X không bị chen chúc trên màn hẹp.
  const step = Math.ceil(points.length / 6);
  const xLabels = points.map((point, index) =>
    index % step === 0 || index === points.length - 1
      ? `<text x="${x(index)}" y="${height - 8}" text-anchor="middle">${escapeHtml(point.label)}</text>`
      : ''
  ).join('');

  const dots = points.map((point, index) =>
    `<circle class="dot" cx="${x(index).toFixed(1)}" cy="${y(point.value).toFixed(1)}" r="3">
       <title>${escapeHtml(point.label)}: ${point.value} ${escapeHtml(label)}</title>
     </circle>`
  ).join('');

  return `
    <svg class="chart" viewBox="0 0 ${width} ${height}" role="img" preserveAspectRatio="xMidYMid meet"
         aria-label="${escapeHtml(label)} theo ngày, cao nhất ${max}">
      ${gridLines}<path class="area" d="${area}"/><path class="line" d="${line}"/>${dots}${xLabels}
    </svg>
    ${dataTable(['Ngày', label], points.map((point) => [point.label, point.value]))}`;
}

/** Biểu đồ cột ngang cho phân bổ trạng thái. */
export function barChart(items, { label = 'Số lượng' } = {}) {
  if (!items.length) return emptyChart();
  const max = Math.max(...items.map((item) => item.value)) || 1;

  const rows = items.map((item, index) => `
    <div class="rank">
      <span class="legend__swatch" style="background:${PALETTE[index % PALETTE.length]}"></span>
      <span class="rank__name">${escapeHtml(item.label)}</span>
      <span class="rank__bar">
        <span class="rank__fill" style="width:${(item.value / max) * 100}%;background:${PALETTE[index % PALETTE.length]}"></span>
      </span>
      <span class="rank__value tnum">${item.value}</span>
    </div>`).join('');

  return `<div class="rank-list" role="img" aria-label="${escapeHtml(label)} theo nhóm">${rows}</div>
          ${dataTable(['Nhóm', label], items.map((item) => [item.label, item.value]))}`;
}

/** Biểu đồ vòng cho tỉ trọng, kèm chú giải. */
export function donutChart(items, { label = 'Tỉ trọng' } = {}) {
  const total = items.reduce((sum, item) => sum + item.value, 0);
  if (!total) return emptyChart();

  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;

  const arcs = items.map((item, index) => {
    const fraction = item.value / total;
    const dash = `${(fraction * circumference).toFixed(2)} ${circumference.toFixed(2)}`;
    const arc = `<circle cx="70" cy="70" r="${radius}" fill="none" stroke-width="22"
      stroke="${PALETTE[index % PALETTE.length]}" stroke-dasharray="${dash}"
      stroke-dashoffset="${(-offset * circumference).toFixed(2)}" transform="rotate(-90 70 70)">
      <title>${escapeHtml(item.label)}: ${item.value} (${Math.round(fraction * 100)}%)</title></circle>`;
    offset += fraction;
    return arc;
  }).join('');

  const legend = items.map((item, index) => `
    <span class="legend__item">
      <span class="legend__swatch" style="background:${PALETTE[index % PALETTE.length]}"></span>
      ${escapeHtml(item.label)} · <strong class="tnum">${item.value}</strong>
    </span>`).join('');

  return `
    <div style="display:flex;align-items:center;gap:var(--sp-5);flex-wrap:wrap">
      <svg viewBox="0 0 140 140" width="140" height="140" role="img" aria-label="${escapeHtml(label)}">
        ${arcs}
        <text x="70" y="66" text-anchor="middle" style="font-size:22px;font-weight:700;fill:var(--text)">${total}</text>
        <text x="70" y="84" text-anchor="middle" style="font-size:11px">tổng đơn</text>
      </svg>
      <div class="legend" style="flex-direction:column;align-items:flex-start;gap:var(--sp-2)">${legend}</div>
    </div>
    ${dataTable(['Nhóm', 'Số đơn'], items.map((item) => [item.label, item.value]))}`;
}

/** Biểu đồ cột doanh thu. */
export function revenueChart(points, { height = 180 } = {}) {
  if (!points.length) return emptyChart();
  const width = 640;
  const padding = { top: 12, right: 12, bottom: 26, left: 52 };
  const innerW = width - padding.left - padding.right;
  const innerH = height - padding.top - padding.bottom;
  const max = niceMax(Math.max(...points.map((point) => point.value)));
  const slot = innerW / points.length;
  const barWidth = Math.max(4, slot * 0.6);

  const bars = points.map((point, index) => {
    const barHeight = (point.value / max) * innerH;
    const x = padding.left + slot * index + (slot - barWidth) / 2;
    return `<rect class="bar" x="${x.toFixed(1)}" y="${(padding.top + innerH - barHeight).toFixed(1)}"
              width="${barWidth.toFixed(1)}" height="${Math.max(0, barHeight).toFixed(1)}" rx="2">
              <title>${escapeHtml(point.label)}: ${formatMoney(point.value)}</title></rect>`;
  }).join('');

  const gridLines = [0, 0.5, 1].map((ratio) => {
    const yPos = padding.top + innerH * (1 - ratio);
    const value = Math.round(max * ratio);
    const short = value >= 1_000_000 ? `${(value / 1_000_000).toFixed(1)}tr` : value >= 1000 ? `${Math.round(value / 1000)}k` : value;
    return `<line class="grid-line" x1="${padding.left}" y1="${yPos}" x2="${width - padding.right}" y2="${yPos}"/>
            <text x="${padding.left - 6}" y="${yPos + 3}" text-anchor="end">${short}</text>`;
  }).join('');

  const step = Math.ceil(points.length / 6);
  const xLabels = points.map((point, index) =>
    index % step === 0 || index === points.length - 1
      ? `<text x="${padding.left + slot * index + slot / 2}" y="${height - 8}" text-anchor="middle">${escapeHtml(point.label)}</text>`
      : ''
  ).join('');

  return `
    <svg class="chart" viewBox="0 0 ${width} ${height}" role="img" preserveAspectRatio="xMidYMid meet"
         aria-label="Doanh thu theo ngày, cao nhất ${formatMoney(max)}">
      ${gridLines}${bars}${xLabels}
    </svg>
    ${dataTable(['Ngày', 'Doanh thu'], points.map((point) => [point.label, formatMoney(point.value)]))}`;
}

function emptyChart() {
  return `<p class="text-muted" style="padding:var(--sp-6) 0;text-align:center">Chưa có dữ liệu để hiển thị.</p>`;
}

/** Bảng chỉ dành cho trình đọc màn hình — biểu đồ SVG một mình không đủ tiếp cận. */
function dataTable(headers, rows) {
  return `<table class="sr-only">
    <caption>Dữ liệu biểu đồ</caption>
    <thead><tr>${headers.map((header) => `<th>${escapeHtml(header)}</th>`).join('')}</tr></thead>
    <tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join('')}</tr>`).join('')}</tbody>
  </table>`;
}
