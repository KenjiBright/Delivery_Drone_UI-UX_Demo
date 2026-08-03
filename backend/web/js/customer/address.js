// Chọn điểm giao: tìm theo tên, chạm bản đồ, hoặc dùng vị trí hiện tại.

import { api } from '../api.js';
import { icon } from '../icons.js';
import { createMap, escapeHtml, markerIcon, openModal, toast } from '../ui.js';
import { homePoint, loadAddresses, state } from './store.js';

let searchTimer = null;

/** Mở hộp thoại chọn điểm giao. Trả về {address, lat, lon} hoặc null. */
export function openAddressPicker(initial) {
  const start = initial || state.destination || { lat: homePoint()[0] + 0.005, lon: homePoint()[1] + 0.007, address: '' };
  let picked = { lat: start.lat, lon: start.lon, address: start.address || '' };
  let map = null;
  let marker = null;

  return openModal({
    title: 'Chọn điểm giao',
    body: `
      <div class="input-group" style="margin-bottom:var(--sp-3)">
        ${icon('search', { size: 18 })}
        <input class="input" id="geo-query" placeholder="Tìm địa chỉ, ví dụ: Hồ Gươm" autocomplete="off">
      </div>
      <div class="geo-results" id="geo-results"></div>
      <div class="map picker-map" id="picker-map"></div>
      <button class="btn btn--secondary btn--block btn--sm" id="btn-locate" style="margin-bottom:var(--sp-3)">
        ${icon('crosshair', { size: 16 })}Dùng vị trí hiện tại của tôi
      </button>
      <label class="field" style="margin:0">
        <span class="field__label">Mô tả điểm giao</span>
        <input class="input" id="geo-address" value="${escapeHtml(picked.address)}" placeholder="Ví dụ: Sảnh toà B, số 5 Trần Phú">
      </label>`,
    actions: [
      { label: 'Huỷ', variant: 'secondary', onClick: () => null },
      {
        label: 'Dùng điểm này',
        onClick: (scrim) => {
          const address = scrim.querySelector('#geo-address').value.trim();
          if (address.length < 3) {
            toast('Hãy mô tả điểm giao (ít nhất 3 ký tự)', 'error');
            return false;
          }
          return { ...picked, address };
        },
      },
    ],
    onMount: (scrim) => {
      const results = scrim.querySelector('#geo-results');
      const addressInput = scrim.querySelector('#geo-address');

      map = createMap(scrim.querySelector('#picker-map'), [picked.lat, picked.lon], {
        zoom: 15,
        onClick: (point) => setPoint(point),
      });
      L.marker(homePoint(), { icon: markerIcon('home') }).addTo(map);
      marker = L.marker([picked.lat, picked.lon], { icon: markerIcon('target') }).addTo(map);

      function setPoint([lat, lon]) {
        picked = { ...picked, lat, lon };
        marker.setLatLng([lat, lon]);
      }

      // Gõ xong 400ms mới gọi API để không dội request lên Nominatim.
      scrim.querySelector('#geo-query').addEventListener('input', (event) => {
        const text = event.target.value.trim();
        clearTimeout(searchTimer);
        if (text.length < 3) {
          results.innerHTML = '';
          return;
        }
        searchTimer = setTimeout(async () => {
          results.innerHTML = `<p class="text-muted" style="padding:var(--sp-2)">Đang tìm…</p>`;
          try {
            const places = await api.get(`/api/geocode?q=${encodeURIComponent(text)}`);
            if (!places.length) {
              results.innerHTML = `<p class="text-muted" style="padding:var(--sp-2)">Không tìm thấy địa chỉ phù hợp.</p>`;
              return;
            }
            results.innerHTML = places.map((place, index) =>
              `<button class="geo-result" data-index="${index}">${icon('map-pin', { size: 16 })}<span>${escapeHtml(place.name)}</span></button>`
            ).join('');
            results.querySelectorAll('.geo-result').forEach((button) => {
              button.onclick = () => {
                const place = places[Number(button.dataset.index)];
                setPoint([place.lat, place.lon]);
                map.setView([place.lat, place.lon], 16);
                addressInput.value = place.name.split(',').slice(0, 3).join(',').trim();
                results.innerHTML = '';
              };
            });
          } catch (error) {
            results.innerHTML = `<p class="text-muted" style="padding:var(--sp-2)">${escapeHtml(error.message)}</p>`;
          }
        }, 400);
      });

      scrim.querySelector('#btn-locate').onclick = () => {
        if (!navigator.geolocation) return toast('Trình duyệt không hỗ trợ định vị', 'error');
        navigator.geolocation.getCurrentPosition(
          (position) => {
            const point = [position.coords.latitude, position.coords.longitude];
            setPoint(point);
            map.setView(point, 16);
            toast('Đã lấy vị trí hiện tại', 'success');
          },
          () => toast('Không lấy được vị trí. Hãy cho phép quyền định vị.', 'error'),
        );
      };
    },
  });
}

/** Hộp thoại lưu địa chỉ mới vào sổ. */
export async function openSaveAddress() {
  const point = await openAddressPicker();
  if (!point) return;

  const label = await openModal({
    title: 'Đặt tên cho địa chỉ',
    body: `
      <label class="field">
        <span class="field__label">Tên gợi nhớ</span>
        <input class="input" id="addr-label" placeholder="Nhà, Cơ quan, Kho hàng…" maxlength="60">
      </label>
      <p class="text-muted">${escapeHtml(point.address)}</p>`,
    actions: [
      { label: 'Huỷ', variant: 'secondary', onClick: () => null },
      {
        label: 'Lưu',
        onClick: (scrim) => {
          const value = scrim.querySelector('#addr-label').value.trim();
          if (!value) {
            toast('Hãy nhập tên gợi nhớ', 'error');
            return false;
          }
          return value;
        },
      },
    ],
  });
  if (!label) return;

  await api.post('/api/addresses', { label, address: point.address, lat: point.lat, lon: point.lon });
  await loadAddresses();
  toast('Đã lưu địa chỉ', 'success');
}

export function addressIcon(label) {
  const text = label.toLowerCase();
  if (text.includes('nhà') || text.includes('home')) return 'home';
  if (text.includes('cơ quan') || text.includes('công ty') || text.includes('office')) return 'briefcase';
  return 'map-pin';
}
