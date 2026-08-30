/* ============================================================================
   CẦU NỐI GIÁ REAL-TIME — Nguyễn Sơn Invest
   Chạy trên Cloudflare Workers, gói miễn phí.

   VẤN ĐỀ nó giải: FireAnt trả dữ liệu bình thường nhưng KHÔNG gửi kèm nhãn CORS,
   nên trình duyệt từ chối cho trang web đọc. Đó là lý do trước đây phải nhờ
   GitHub Actions quét hộ — mà GitHub chạy theo lịch, trễ 10–20 phút.

   CÁCH nó giải: Worker này đứng giữa. Trang web gọi Worker, Worker gọi FireAnt
   (máy chủ gọi máy chủ thì không có CORS), rồi trả về kèm nhãn cho phép.
   Một vòng ~1 giây. Trang hỏi 45 giây một lần → trễ dưới một phút.

   GỌI THẾ NÀO
       GET /quotes?syms=ORS,HPG,MBB
   TRẢ VỀ
       { at: "2026-08-21T14:32:10.000Z",
         rows: { ORS: {d,price,ref,open,hi,lo,vol,tv}, ... } }
   Giá trả về theo ĐỒNG (14550), không phải nghìn đồng — trang tự chia.

   Ba thứ đáng lưu ý trong mã dưới đây:
     1. Chỉ nhận mã đúng dạng chữ-số 3–10 ký tự. Không cho truyền đường dẫn tuỳ ý
        vào FireAnt — Worker này chỉ làm đúng một việc.
     2. Trần 45 mã một lần gọi. Gói miễn phí của Cloudflare cho 50 lượt gọi ra
        ngoài mỗi lần chạy; vượt là hỏng cả vòng.
     3. Đệm 25 giây. Mười khách cùng mở trang thì FireAnt chỉ bị hỏi một lần.

   CÁCH DỰNG (5 phút, không cần thẻ ngân hàng)
     1. Vào dash.cloudflare.com → Workers & Pages → Create → Worker → Deploy.
     2. Bấm Edit code, xoá sạch, dán TOÀN BỘ file này vào, bấm Deploy.
     3. Copy địa chỉ dạng https://<tên>.<tài-khoản>.workers.dev
     4. Trong repo trang web, sửa config.json:  "proxy": "https://... .workers.dev"
     5. Xong. Mở trang, thanh trạng thái sẽ ghi "real-time".
   ========================================================================== */

const BASE = 'https://www.fireant.vn/api/Data/Companies/HistoricalQuotes';
const UA = {
  'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36',
  Referer: 'https://fireant.vn/',
  Accept: 'application/json',
};
const TRAN_MA = 45;        // trần lượt gọi ra ngoài của gói miễn phí là 50
const DEM_GIAY = 25;

function ngayVN(lech) {
  const t = new Date(Date.now() + 7 * 3600e3 + (lech || 0) * 86400e3);
  return t.toISOString().slice(0, 10);
}

async function motMa(sym) {
  // Hỏi cả một khoảng 7 ngày rồi lấy dòng mới nhất: trước 9h15, sau nửa đêm hay
  // ngày lễ thì "hôm nay" không có phiên nào, hỏi đúng hôm nay sẽ ra rỗng.
  const u = `${BASE}?symbol=${sym}&startDate=${ngayVN(-7)}&endDate=${ngayVN(0)}`;
  const r = await fetch(u, { headers: UA, cf: { cacheTtl: 20, cacheEverything: true } });
  if (!r.ok) return null;
  const d = await r.json();
  if (!Array.isArray(d) || !d.length) return null;
  let m = d[0];
  for (const x of d) if (String(x.Date || '') > String(m.Date || '')) m = x;
  const price = +m.PriceClose || 0, ref = +m.PriceBasic || 0;
  if (!price || !ref) return null;
  // Bốn con số cuối là để tính ĐIỀU KIỆN 7 — cỡ lệnh mua so cỡ lệnh bán.
  // Khối lượng cao có thể do một nghìn nhà đầu tư nhỏ cùng bấm, cũng có thể do một
  // quỹ gom. Không có bốn số này thì lớp real-time không phân biệt được hai chuyện đó,
  // và sẽ báo mua những phiên mà bộ máy chín lớp vốn không thèm đụng vào.
  return {
    d: String(m.Date || '').slice(0, 10),
    price, ref,
    open: +m.PriceOpen || 0,
    hi: +m.PriceHigh || 0,
    lo: +m.PriceLow || 0,
    vol: +m.Volume || 0,
    tv: +m.TotalValue || 0,
    bq: +m.BuyQuantity || 0,
    bc: +m.BuyCount || 0,
    sq: +m.SellQuantity || 0,
    sc: +m.SellCount || 0,
  };
}

export default {
  async fetch(req) {
    const url = new URL(req.url);
    const cors = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, OPTIONS',
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': `public, max-age=${DEM_GIAY}`,
    };
    if (req.method === 'OPTIONS') return new Response(null, { headers: cors });

    // ---- /bars?sym=FPT&n=400 : nến ngày cho trang Chi tiết mã ----
    // Nhúng sẵn nến của cả 694 mã vào trang thì file phồng lên hàng chục MB.
    // Lấy về khi cần thì trang vẫn nhẹ mà mã nào cũng xem được.
    if (url.pathname.replace(/\/+$/, '').endsWith('/bars')) {
      const sym = (url.searchParams.get('sym') || '').toUpperCase();
      if (!/^[A-Z0-9]{3,10}$/.test(sym)) {
        return new Response(JSON.stringify({ error: 'ma khong hop le' }), { status: 400, headers: cors });
      }
      const n = Math.min(1200, Math.max(60, +url.searchParams.get('n') || 400));
      const frm = ngayVN(-Math.ceil(n * 1.55) - 10);      // ~250 phiên mỗi năm
      const key = new Request(url.origin + '/bars?sym=' + sym + '&n=' + n, { method: 'GET' });
      const san = await caches.default.match(key);
      if (san) return san;
      const r = await fetch(`${BASE}?symbol=${sym}&startDate=${frm}&endDate=${ngayVN(0)}`,
                            { headers: UA, cf: { cacheTtl: 300, cacheEverything: true } });
      const d = r.ok ? await r.json() : null;
      if (!Array.isArray(d)) {
        return new Response(JSON.stringify({ sym, bars: [] }), { headers: cors });
      }
      const bars = d
        .map(x => [String(x.Date || '').slice(0, 10),
                   +x.AdjOpen || +x.PriceOpen || 0, +x.AdjHigh || +x.PriceHigh || 0,
                   +x.AdjLow || +x.PriceLow || 0, +x.AdjClose || +x.PriceClose || 0,
                   +x.Volume || 0])
        .filter(b => b[4] > 0)
        .sort((a, b) => a[0] < b[0] ? -1 : 1)
        .slice(-n)
        .map(b => [b[0], +(b[1] / 1000).toFixed(2), +(b[2] / 1000).toFixed(2),
                   +(b[3] / 1000).toFixed(2), +(b[4] / 1000).toFixed(2), b[5]]);
      const res = new Response(JSON.stringify({ sym, n: bars.length, bars }),
                               { headers: { ...cors, 'Cache-Control': 'public, max-age=300' } });
      await caches.default.put(key, res.clone());
      return res;
    }

    if (!url.pathname.replace(/\/+$/, '').endsWith('/quotes')) {
      return new Response(JSON.stringify({
        ok: true,
        doc: 'Cầu nối giá Nguyễn Sơn Invest. Gọi /quotes?syms=ORS,HPG',
      }), { headers: cors });
    }

    const syms = (url.searchParams.get('syms') || '')
      .toUpperCase().split(',').map(s => s.trim())
      .filter(s => /^[A-Z0-9]{3,10}$/.test(s));
    const uniq = [...new Set(syms)].slice(0, TRAN_MA);
    if (!uniq.length) {
      return new Response(JSON.stringify({ at: new Date().toISOString(), rows: {} }), { headers: cors });
    }

    // đệm chung: mười khách cùng mở trang thì FireAnt chỉ bị hỏi một lần
    const key = new Request(url.origin + '/quotes?syms=' + uniq.join(','), { method: 'GET' });
    const cache = caches.default;
    const san = await cache.match(key);
    if (san) return san;

    const kq = await Promise.all(uniq.map(s => motMa(s).catch(() => null)));
    const rows = {};
    uniq.forEach((s, i) => { if (kq[i]) rows[s] = kq[i]; });

    const res = new Response(JSON.stringify({
      at: new Date().toISOString(),
      n: Object.keys(rows).length,
      asked: uniq.length,
      rows,
    }), { headers: cors });
    await cache.put(key, res.clone());
    return res;
  },
};
