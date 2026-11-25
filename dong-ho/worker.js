import { WorkerEntrypoint } from 'cloudflare:workers';
// ĐỒNG HỒ ẢO — Nguyễn Sơn Invest (28/09/2026; 25/11/2026: BẢN DỰNG BUỔI SÁNG 07:30–08:30 — bản này)
// LỖI 25/11/2026: bản 11/11 (dựng sáng) chỉ nằm trong repo, CHƯA dán lên Cloudflare. Worker đang chạy vẫn gọi
// bản dựng MỘT lần 21:00. Tối 24/11 lúc 21:00 FireAnt chưa có phiên 24/11 -> `kiem` bỏ qua -> không lượt nào
// khác -> cả phiên 25/11 chuông chạy trên số 23/11 (TCH thủng khoá lãi mà không báo).
// Nay: bản dựng gọi 21:00 (nếu FireAnt đã có phiên thì dựng luôn) VÀ 07:30 / 07:50 / 08:10 / 08:30 sáng hôm sau
// (lưới an toàn — trang đã mới thì `kiem` bỏ qua ~30 giây). Cả 7 ngày.
//
// Cron Trigger cần có (Settings → Trigger Events), giờ UTC:
//   */5 1-14 * * MON-FRI     (bộ quét trong phiên — đã có)
//   0 14 * * *               (21:00 VN — đã có)
//   30,50 0 * * *            (07:30 / 07:50 VN — THÊM MỚI)
//   10,30 1 * * SAT,SUN      (08:10 / 08:30 VN cuối tuần — THÊM MỚI; ngày thường */5 đã phủ)
//
// Bí mật: GH_TOKEN = fine-grained token, repo nguyensoninvest + nsi-bot + nsi-tin, quyền "Actions: Read and write".

const OWNER = 'hson07071979';
const PUB = 'nguyensoninvest';      // bộ quét trong phiên (nhip.yml, gac.yml)
const PRIV = 'nsi-bot';             // bản dựng (daily.yml)
const TIN = 'nsi-tin';

// Lịch theo giờ VN (phút trong ngày). Trả về danh sách [repo, workflow, nhãn].
function lich(h, m) {
  const t = h * 60 + m, out = [];
  const moi = (tu, den, buoc) => t >= tu && t <= den && (t - tu) % buoc === 0;
  if (moi(9 * 60, 11 * 60 + 30, 20) ||          // 09:00–11:30 mỗi 20'
      moi(13 * 60, 13 * 60 + 55, 15) ||         // 13:00–13:45 mỗi 15'
      moi(14 * 60, 14 * 60 + 45, 5) ||          // 14:00–14:45 mỗi 5'  ← cửa sổ mua đỏ / ATC
      moi(15 * 60, 20 * 60 + 45, 15))           // 15:00–20:45 mỗi 15' ← chờ Điều kiện 9
    out.push([PUB, 'nhip.yml']);
  if (t === 14 * 60 + 15 || t === 14 * 60 + 30) out.push([PUB, 'gac.yml']);          // báo CHƯA QUÉT
  // BẢN DỰNG: 21:00 tối + 4 lượt sáng. Lượt nào thấy trang đã mới thì `kiem` bỏ qua.
  if (t === 21 * 60) out.push([PRIV, 'daily.yml', 'moi-toi']);
  if (t === 7 * 60 + 30 || t === 7 * 60 + 50 || t === 8 * 60 + 10 || t === 8 * 60 + 30) out.push([PRIV, 'daily.yml', 'sang']);
  if (t === 7 * 60) out.push([TIN, 'sang.yml', 'chay']);
  if (t === 7 * 60 + 45 || t === 8 * 60 + 15) out.push([TIN, 'sang.yml', 'gac']);
  // NSI Daily Market (12/10/2026): chạy sau phiên + gác
  if (t === 15 * 60 + 20) out.push([TIN, 'daily_market.yml', 'chay']);
  if (t === 16 * 60) out.push([TIN, 'daily_market.yml', 'gac']);
  return out;
}

function gioVN(d) {
  const x = new Date(d.getTime() + 7 * 3600 * 1000);
  return { h: x.getUTCHours(), m: x.getUTCMinutes(), thu: x.getUTCDay() };
}

async function goi(env, repo, wf, nhan) {
  const body = { ref: 'main' };
  if (wf === 'nhip.yml') body.inputs = { nguon: 'dong-ho' };
  if (wf === 'sang.yml') body.inputs = { che_do: nhan || 'chay' };
  if (wf === 'daily_market.yml') body.inputs = { che_do: nhan || 'chay' };
  // daily.yml: 'moi-toi' / 'sang' = nghe bước `kiem` (trang đã mới thì bỏ qua ~30 giây)
  if (wf === 'daily.yml') body.inputs = { nguon: nhan || 'dong-ho' };
  const r = await fetch(`https://api.github.com/repos/${OWNER}/${repo}/actions/workflows/${wf}/dispatches`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${env.GH_TOKEN}`, 'Accept': 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'nsi-dong-ho', 'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });
  return `${repo}/${wf}: ${r.status}${r.status === 204 ? ' OK' : ' ' + (await r.text()).slice(0, 160)}`;
}

const daGoi = new Set();   // chống gọi trùng khi hai cron cùng nổ một phút (vd 08:10 ngày thường)

export default {
  async scheduled(event, env, ctx) {
    const { h, m, thu } = gioVN(new Date(event.scheduledTime));
    // ngày thường, cron '*/5' đã phủ 21:00 -> cron '0 14 * * *' chỉ làm việc cho T7/CN (không gọi trùng)
    if (event.cron === '0 14 * * *' && thu >= 1 && thu <= 5) return;
    const m5 = m - (m % 5);                                     // cron có thể trễ vài giây
    let viec = lich(h, m5);
    if (thu === 0 || thu === 6) viec = viec.filter(x => x[0] === PRIV || x[0] === TIN);   // cuối tuần: bản dựng + bản tin
    const phut = new Date(event.scheduledTime).toISOString().slice(0, 16);
    viec = viec.filter(x => { const k = phut + x.join('/'); if (daGoi.has(k)) return false; daGoi.add(k); return true; });
    if (daGoi.size > 500) daGoi.clear();
    if (!viec.length) return;
    const kq = await Promise.all(viec.map(([r, w, n]) => goi(env, r, w, n)));
    console.log(`${h}:${String(m5).padStart(2, '0')} VN →`, kq.join(' | '));
  },
  // Mở URL của Worker để xem lịch hôm nay (KHÔNG gọi gì, không lộ token).
  async fetch(req, env) {
    const dong = [];
    for (let t = 7 * 60; t <= 21 * 60 + 30; t += 5) {
      const v = lich(Math.floor(t / 60), t % 60);
      if (v.length) dong.push(`${String(Math.floor(t / 60)).padStart(2, '0')}:${String(t % 60).padStart(2, '0')}  ${v.map(x => x.slice(0, 2).join('/') + (x[2] ? ' (' + x[2] + ')' : '')).join(', ')}`);
    }
    const coToken = env.GH_TOKEN ? 'có GH_TOKEN ✓' : 'CHƯA có GH_TOKEN ✗';
    return new Response(`Đồng hồ ảo Nguyễn Sơn Invest (bản 25/11/2026) — ${coToken}\nLịch (giờ VN; bản dựng + bản tin chạy cả T7/CN):\n${dong.join('\n')}\n\nKiểm tra: Cloudflare → Worker → Settings → Trigger Events → nút thử cron; log ở tab Logs.\n`,
      { headers: { 'content-type': 'text/plain; charset=utf-8' } });
  },
};


// Nút "Viết lại theo view" ở trang /daily (nsi-quantri) gọi qua Service binding — KHÔNG có đường công khai.
// Chỉ được gọi đúng workflow daily_market.yml của nsi-tin, chế độ viet_lai.
export class DaiLyDispatch extends WorkerEntrypoint {
  async vietLai(view, ngay) {
    view = String(view || '').trim().slice(0, 2500);
    ngay = String(ngay || '').trim();
    if (view.length < 10) return { ok: false, loi: 'view quá ngắn' };
    if (ngay && !/^\d{4}-\d{2}-\d{2}$/.test(ngay)) return { ok: false, loi: 'ngày sai dạng' };
    const r = await fetch('https://api.github.com/repos/' + OWNER + '/' + TIN + '/actions/workflows/daily_market.yml/dispatches', {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + this.env.GH_TOKEN, 'Accept': 'application/vnd.github+json',
                 'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'nsi-dong-ho', 'Content-Type': 'application/json' },
      body: JSON.stringify({ ref: 'main', inputs: { che_do: 'viet_lai', view: view, ngay: ngay } }),
    });
    if (r.status === 204) return { ok: true };
    return { ok: false, loi: 'GitHub ' + r.status + ': ' + (await r.text()).slice(0, 160) };
  }
}
