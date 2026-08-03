// Lớp gọi API và WebSocket. Cùng origin với backend nên mọi đường dẫn đều tương đối.

const TOKEN_KEY = 'uav.token';
const ROLE_KEY = 'uav.role';

let token = sessionStorage.getItem(TOKEN_KEY) || '';

export function getToken() {
  return token;
}

export function setSession(accessToken, role) {
  token = accessToken;
  sessionStorage.setItem(TOKEN_KEY, accessToken);
  sessionStorage.setItem(ROLE_KEY, role);
}

export function clearSession() {
  token = '';
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(ROLE_KEY);
}

export function storedRole() {
  return sessionStorage.getItem(ROLE_KEY) || '';
}

/** Lỗi mang theo mã HTTP để nơi gọi phân biệt được 401 với lỗi nghiệp vụ. */
export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body) headers['Content-Type'] = 'application/json';
  if (token) headers['Authorization'] = `Bearer ${token}`;

  let response;
  try {
    response = await fetch(path, { ...options, headers });
  } catch {
    throw new ApiError('Mất kết nối tới máy chủ', 0);
  }

  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const detail = data && data.detail ? data.detail : `Lỗi máy chủ ${response.status}`;
    throw new ApiError(typeof detail === 'string' ? detail : 'Dữ liệu không hợp lệ', response.status);
  }
  return data;
}

export const api = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: 'POST', body: JSON.stringify(body || {}) }),
  patch: (path, body) => request(path, { method: 'PATCH', body: JSON.stringify(body || {}) }),
  del: (path) => request(path, { method: 'DELETE' }),
};

export async function login(username, password, expectedRole) {
  const result = await request('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password, expected_role: expectedRole }),
  });
  setSession(result.access_token, result.user.role);
  return result.user;
}

/** Xây query string, bỏ qua giá trị rỗng để URL gọn. */
export function query(params) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== '' && value !== null && value !== undefined) search.set(key, value);
  }
  const text = search.toString();
  return text ? `?${text}` : '';
}

/**
 * Mở WebSocket và tự kết nối lại khi đứt.
 * Backoff tăng dần tới 15 giây để không dội request khi server đang tắt.
 */
export function connectSocket(path, { onMessage, onStatus }) {
  let socket = null;
  let closed = false;
  let attempt = 0;

  function open() {
    if (closed) return;
    const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
    socket = new WebSocket(`${scheme}://${location.host}${path}?token=${encodeURIComponent(token)}`);

    socket.onopen = () => {
      attempt = 0;
      onStatus?.(true);
    };
    socket.onmessage = (event) => {
      try {
        onMessage?.(JSON.parse(event.data));
      } catch {
        onMessage?.(null);
      }
    };
    socket.onerror = () => socket.close();
    socket.onclose = () => {
      onStatus?.(false);
      if (closed) return;
      attempt += 1;
      setTimeout(open, Math.min(15000, 1000 * 2 ** Math.min(attempt, 4)));
    };
  }

  open();
  return () => {
    closed = true;
    socket?.close();
  };
}
