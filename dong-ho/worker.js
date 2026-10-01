// ĐỒNG HỒ ẢO — Nguyễn Sơn Invest (28/09/2026; sửa 29/09: bản dựng tối chỉ còn 21:00, gửi nhãn nguon;
// sửa 01/10: thêm bản tin sáng nsi-tin 07:00 / 07:45 / 08:15)
// Cloudflare Worker, Cron Trigger "*/5 0-14 * * MON-FRI" + "0 14 * * *" (21:00 VN mỗi tối) (mỗi 5 phút, T2–T6). Cron của GitHub nổ muộn
// hoặc bỏ nhịp; Cloudflare nổ đúng phút. Mỗi lần nổ, Worker xem giờ VN và gọi đúng workflow
// qua GitHub API (workflow_dispatch).
//
// Bí mật cần đặt trong Cloudflare (Settings → Variables and Secrets):
//   GH_TOKEN  = fine-grained token, repo nguyensoninvest + nsi-bot + nsi-tin, quyền "Actions: Read and write"
// Không có bí mật nào khác. Worker không đọc / ghi dữ liệu giao dịch.

const OWNER = 'hson07071979';
const PUB = 'nguyensoninvest';      // bộ quét trong phiên (nhip.yml, gac.yml)
const PRIV = 'nsi-bot';             // bản dựng tối (daily.yml)
const TIN = 'nsi-tin';              // bản tin sáng (sang.yml)

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
  // bản dựng tối: MỘT lượt duy nhất 21:00 mỗi tối, cả T7/CN (anh Sơn 29/09). Đã bỏ 16:30 (FireAnt
  // chưa có dòng tiền -> verify_build chặn, 14 phút vô ích), 19:30 và 21:30 (dựng lại trùng).
  if (t === 21 * 60) out.push([PRIV, 'daily.yml', 'moi-toi']);
  // bản tin sáng (01/10): 07:00 chạy; 07:45 và 08:15 gác — chưa có bản đạt thì chạy lại (hạn 8h30)
  if (t === 7 * 60) out.push([TIN, 'sang.yml', 'chay']);
  if (t === 7 * 60 + 45 || t === 8 * 60 + 15) out.push([TIN, 'sang.yml', 'gac']);
  return out;
}

function gioVN(d) {
  const x = new Date(d.getTime() + 7 * 3600 * 1000);
  return { h: x.getUTCHours(), m: x.getUTCMinutes(), thu: x.getUTCDay() };
}

async function goi(env, repo, wf, nhan) {
  const body = { ref: 'main' };
  if (wf === 'nhip.yml') body.inputs = { nguon: 'dong-ho' };
  // daily.yml (29/09): gửi nhãn để bước `kiem` được BỎ QUA khi trang đã mới — 19:30 đăng xong
  // thì 21:00 / 21:30 chỉ tốn ~30 giây. Bấm tay ở tab Actions (nhãn 'tay') vẫn luôn chạy.
  if (wf === 'sang.yml') body.inputs = { che_do: nhan || 'chay' };
  if (wf === 'daily.yml') body.inputs = { nguon: nhan === 'moi-toi' ? 'moi-toi' : 'dong-ho' };
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
    // ngày thường, cron '*/5' đã phủ 21:00 -> cron '0 14 * * *' chỉ làm việc cho T7/CN (không gọi trùng)
    if (event.cron === '0 14 * * *' && thu >= 1 && thu <= 5) return;
    const m5 = m - (m % 5);                                     // cron có thể trễ vài giây
    let viec = lich(h, m5);
    if (thu === 0 || thu === 6) viec = viec.filter(x => x[2] === 'moi-toi');   // cuối tuần: chỉ bản dựng 21:00
    if (!viec.length) return;
    const kq = await Promise.all(viec.map(([r, w, n]) => goi(env, r, w, n)));
    console.log(`${h}:${String(m5).padStart(2, '0')} VN →`, kq.join(' | '));
  },
  // Mở URL của Worker để xem lịch hôm nay (KHÔNG gọi gì, không lộ token).
  async fetch(req, env) {
    const dong = [];
    for (let t = 7 * 60; t <= 21 * 60 + 30; t += 5) {
      const v = lich(Math.floor(t / 60), t % 60);
      if (v.length) dong.push(`${String(Math.floor(t / 60)).padStart(2, '0')}:${String(t % 60).padStart(2, '0')}  ${v.map(x => x.slice(0, 2).join('/') + (x[2] === 'moi-toi' ? ' (mỗi tối)' : x[2] ? ` (${x[2]})` : '')).join(', ')}`);
    }
    const coToken = env.GH_TOKEN ? 'có GH_TOKEN ✓' : 'CHƯA có GH_TOKEN ✗';
    return new Response(`Đồng hồ ảo Nguyễn Sơn Invest — ${coToken}\nLịch (giờ VN, T2–T6; riêng 21:00 chạy cả T7/CN):\n${dong.join('\n')}\n\nKiểm tra: Cloudflare → Worker → Settings → Trigger Events → nút thử cron; log ở tab Logs.\n`,
      { headers: { 'content-type': 'text/plain; charset=utf-8' } });
  },
};
