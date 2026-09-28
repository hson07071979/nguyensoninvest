// ĐỒNG HỒ ẢO — Nguyễn Sơn Invest (28/09/2026)
// Cloudflare Worker, Cron Trigger "*/5 * * * 1-5" (mỗi 5 phút, T2–T6). Cron của GitHub nổ muộn
// hoặc bỏ nhịp; Cloudflare nổ đúng phút. Mỗi lần nổ, Worker xem giờ VN và gọi đúng workflow
// qua GitHub API (workflow_dispatch).
//
// Bí mật cần đặt trong Cloudflare (Settings → Variables and Secrets):
//   GH_TOKEN  = fine-grained token, repo nguyensoninvest + nsi-bot, quyền "Actions: Read and write"
// Không có bí mật nào khác. Worker không đọc / ghi dữ liệu giao dịch.

const OWNER = 'hson07071979';
const PUB = 'nguyensoninvest';      // bộ quét trong phiên (nhip.yml, gac.yml)
const PRIV = 'nsi-bot';             // bản dựng tối (daily.yml)

// Lịch theo giờ VN (phút trong ngày). Trả về danh sách [repo, workflow].
function lich(h, m) {
  const t = h * 60 + m, out = [];
  const moi = (tu, den, buoc) => t >= tu && t <= den && (t - tu) % buoc === 0;
  if (moi(9 * 60, 11 * 60 + 30, 20) ||          // 09:00–11:30 mỗi 20'
      moi(13 * 60, 13 * 60 + 55, 15) ||         // 13:00–13:45 mỗi 15'
      moi(14 * 60, 14 * 60 + 45, 5) ||          // 14:00–14:45 mỗi 5'  ← cửa sổ mua đỏ / ATC
      moi(15 * 60, 20 * 60 + 45, 15))           // 15:00–20:45 mỗi 15' ← chờ Điều kiện 9
    out.push([PUB, 'nhip.yml']);
  if (t === 14 * 60 + 15 || t === 14 * 60 + 30) out.push([PUB, 'gac.yml']);          // báo CHƯA QUÉT
  if (t === 16 * 60 + 30 || t === 19 * 60 + 30 || t === 21 * 60 + 30) out.push([PRIV, 'daily.yml']); // bản dựng tối
  return out;
}

function gioVN(d) {
  const x = new Date(d.getTime() + 7 * 3600 * 1000);
  return { h: x.getUTCHours(), m: x.getUTCMinutes(), thu: x.getUTCDay() };
}

async function goi(env, repo, wf) {
  const body = { ref: 'main' };
  if (wf === 'nhip.yml') body.inputs = { nguon: 'dong-ho' };
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

export default {
  async scheduled(event, env, ctx) {
    const { h, m, thu } = gioVN(new Date(event.scheduledTime));
    if (thu === 0 || thu === 6) return;
    const m5 = m - (m % 5);                                     // cron có thể trễ vài giây
    const viec = lich(h, m5);
    if (!viec.length) return;
    const kq = await Promise.all(viec.map(([r, w]) => goi(env, r, w)));
    console.log(`${h}:${String(m5).padStart(2, '0')} VN →`, kq.join(' | '));
  },
  // Mở URL của Worker để xem lịch hôm nay (KHÔNG gọi gì, không lộ token).
  async fetch(req, env) {
    const dong = [];
    for (let t = 9 * 60; t <= 21 * 60 + 30; t += 5) {
      const v = lich(Math.floor(t / 60), t % 60);
      if (v.length) dong.push(`${String(Math.floor(t / 60)).padStart(2, '0')}:${String(t % 60).padStart(2, '0')}  ${v.map(x => x.join('/')).join(', ')}`);
    }
    const coToken = env.GH_TOKEN ? 'có GH_TOKEN ✓' : 'CHƯA có GH_TOKEN ✗';
    return new Response(`Đồng hồ ảo Nguyễn Sơn Invest — ${coToken}\nLịch (giờ VN, T2–T6):\n${dong.join('\n')}\n\nKiểm tra: Cloudflare → Worker → Settings → Trigger Events → nút thử cron; log ở tab Logs.\n`,
      { headers: { 'content-type': 'text/plain; charset=utf-8' } });
  },
};
