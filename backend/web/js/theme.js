// Chế độ sáng/tối cho app khách hàng.
//
// CSS chỉ cần biết `data-theme` là "light" hay "dark"; việc quy đổi lựa chọn
// "theo hệ thống" do JS làm, nên không phải viết hai bản quy tắc trong CSS.

const KEY = 'uav-theme';
const MODES = ['system', 'light', 'dark'];

const media = window.matchMedia('(prefers-color-scheme: dark)');
const listeners = new Set();

export function getMode() {
  const stored = localStorage.getItem(KEY);
  return MODES.includes(stored) ? stored : 'system';
}

export function resolvedTheme(mode = getMode()) {
  if (mode === 'system') return media.matches ? 'dark' : 'light';
  return mode;
}

export function applyTheme(mode = getMode()) {
  const theme = resolvedTheme(mode);
  document.documentElement.dataset.theme = theme;
  // Thanh trạng thái trình duyệt di động phải đổi theo, nếu không sẽ lệch hẳn với trang.
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = theme === 'dark' ? '#0b1220' : '#2563eb';
  return theme;
}

export function setMode(mode) {
  localStorage.setItem(KEY, MODES.includes(mode) ? mode : 'system');
  applyTheme();
  listeners.forEach((listener) => listener(getMode()));
}

export function onThemeChange(listener) {
  listeners.add(listener);
}

// Đổi cài đặt hệ điều hành thì trang đang mở phải đổi theo, nhưng chỉ khi
// người dùng chưa chọn cứng sáng hoặc tối.
media.addEventListener('change', () => {
  if (getMode() === 'system') {
    applyTheme();
    listeners.forEach((listener) => listener('system'));
  }
});

applyTheme();
