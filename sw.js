/* ============================================================================
   SERVICE WORKER — Nguyễn Sơn Invest
   Nằm ở GỐC repo public, cạnh index.html. File TĨNH: không do build_site2.py
   sinh ra, nên bản dựng tối nào cũng không đụng tới nó.

   MỘT QUYẾT ĐỊNH DUY NHẤT, và nó quan trọng:

     index.html và mọi file .json  ->  MẠNG TRƯỚC, bộ đệm chỉ để dự phòng
     icon + manifest               ->  đệm sẵn khi cài

   Vì sao index.html phải mạng trước: trang này là một file duy nhất chứa cả luật
   lẫn dữ liệu. Đệm trước (cache-first) nghĩa là mở app ra thấy watchlist của hôm
   kia mà không có một dấu hiệu nào — đúng loại lỗi "hai sổ lệch nhau" đã ghi
   trong sổ kiến trúc. Thà chờ mạng một giây còn hơn nhìn số cũ mà tưởng số mới.

   Bộ đệm chỉ cứu đúng một tình huống: MẤT MẠNG HẲN. Lúc đó app vẫn mở được bản
   lần trước, và lớp JS trên trang tự biết là không tải lại được — nó vốn đã lùi
   về ảnh chụp nhúng sẵn khi fetch hỏng.
   ========================================================================== */
const TEN = 'nsi-v1';
const TINH = ['/manifest.json', '/icon-192.png', '/icon-512.png',
              '/icon-maskable-512.png', '/apple-touch-icon.png'];

self.addEventListener('install', ev => {
  // addAll hỏng một file là hỏng cả lần cài. Cài từng cái để thiếu một icon
  // không làm chết service worker.
  ev.waitUntil(
    caches.open(TEN)
      .then(c => Promise.all(TINH.map(u => c.add(u).catch(() => null))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', ev => {
  ev.waitUntil(
    caches.keys()
      .then(ks => Promise.all(ks.filter(k => k !== TEN).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', ev => {
  const req = ev.request;
  if (req.method !== 'GET') return;
  let url;
  try { url = new URL(req.url); } catch (e) { return; }
  if (url.origin !== self.location.origin) return;   // cầu nối Cloudflare: không đụng vào

  ev.respondWith(
    fetch(req)
      .then(res => {
        // Chỉ đệm bản 200 bình thường. Đệm bản lỗi thì lần mất mạng sau sẽ mở ra
        // trang lỗi — mà trang lỗi nhìn y hệt trang trắng hôm 17/09.
        if (res && res.status === 200 && res.type === 'basic') {
          const ban = res.clone();
          caches.open(TEN).then(c => c.put(req, ban)).catch(() => {});
        }
        return res;
      })
      .catch(() => caches.match(req).then(r => r || caches.match('/index.html')))
  );
});

/* ---- Web Push: chỗ để sẵn, CHƯA nối ------------------------------------
   Bật ở bước sau, khi đã có khoá VAPID và Cloudflare KV. Để sẵn ở đây để lúc đó
   không phải đăng ký lại service worker — người đã cài app rồi thì chỉ cần bấm
   "Bật thông báo" là xong, không phải gỡ ra cài lại.                        */
self.addEventListener('push', ev => {
  let d = {};
  try { d = ev.data ? ev.data.json() : {}; }
  catch (e) { d = { body: ev.data && ev.data.text() }; }
  ev.waitUntil(self.registration.showNotification(d.title || 'Nguyễn Sơn Invest', {
    body: d.body || '',
    icon: '/icon-192.png',
    badge: '/icon-192.png',
    tag: d.tag || 'nsi',
    renotify: true,
    data: { url: d.url || '/index.html#chuong' },
  }));
});

self.addEventListener('notificationclick', ev => {
  ev.notification.close();
  const u = (ev.notification.data || {}).url || '/index.html#chuong';
  ev.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(cs => {
      for (const c of cs) {
        if (c.url.startsWith(self.location.origin) && 'focus' in c) {
          if ('navigate' in c) c.navigate(u);
          return c.focus();
        }
      }
      return self.clients.openWindow(u);
    })
  );
});
