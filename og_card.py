# -*- coding: utf-8 -*-
"""Ve og.png 1200x630 tu so lieu trong index.html. Chay boi .github/workflows/og.yml."""
import json, re
from PIL import Image, ImageDraw, ImageFont

BG, SURF, LINE = (17,17,16), (26,26,25), (51,50,47)
TX, TX2, TX3 = (255,255,255), (195,194,183), (139,138,128)
GOOD, CRIT, ACC = (25,158,112), (230,103,103), (57,135,229)
FP = ('/usr/share/fonts/truetype/dejavu/DejaVuSans%s.ttf',
      '/usr/share/fonts/truetype/liberation/LiberationSans%s.ttf')

def F(b, s):
    for p in FP:
        try:
            return ImageFont.truetype(p % ('-Bold' if b else ''), s)
        except OSError:
            pass
    raise SystemExit('HONG: thieu font co dau tieng Viet')

def N(x, n=1):
    return ('%.*f' % (n, x)).replace('.', ',')

H = open('index.html', encoding='utf-8').read()
m = re.search(r'id="DATA"[^>]*>(.*?)</script>', H, re.S)
if not m:
    raise SystemExit('HONG: khong thay khoi DATA trong index.html')
D = json.loads(m.group(1))
M, BM = D['prod']['metrics'], D['bench_metrics']
DM = D['prod'].get('deal_metrics') or {}

im = Image.new('RGB', (1200, 630), BG)
d = ImageDraw.Draw(im)
for i in range(240):
    a = (1 - i / 240) * .9
    d.line([(0,i),(1200,i)], fill=tuple(int(BG[k]+(SURF[k]-BG[k])*a) for k in range(3)))

LS = 84
lo = Image.new('RGB', (LS, LS)); ld = ImageDraw.Draw(lo)
for y in range(LS):
    t = y / LS
    ld.line([(0,y),(LS,y)], fill=tuple(int(ACC[k]+(GOOD[k]-ACC[k])*t) for k in range(3)))
mk = Image.new('L', (LS, LS), 0)
ImageDraw.Draw(mk).rounded_rectangle([0,0,LS-1,LS-1], radius=24, fill=255)
im.paste(lo, (72, 64), mk)
f34 = F(1, 34)
d.text((72+(LS-d.textlength('NS', font=f34))/2, 86), 'NS', font=f34, fill=TX)
d.text((184, 68), 'Nguyễn Sơn Invest', font=F(1, 50), fill=TX)
d.text((186, 122), 'Hệ thống giao dịch cổ phiếu Việt Nam', font=F(0, 25), fill=TX2)

wr = (DM.get('winrate') or M['winrate']) * 100
K = [('TỔNG LỢI NHUẬN', '+'+N(M['total_return']*100)+'%', GOOD,
      N(len(D['prod']['curve'])/250)+' năm · VN-Index +'+N(BM['total']*100)+'%'),
     ('SỤT GIẢM TỐI ĐA', '−'+N(M['maxdd']*100)+'%', CRIT, 'VN-Index −'+N(BM['mdd']*100)+'%'),
     ('PROFIT FACTOR', N(M['pf'], 2), TX, 'lãi gộp / lỗ gộp'),
     ('SỐ DEAL', str(DM.get('deals') or M['trades']), TX, 'tỷ lệ thắng '+N(wr)+'%')]
x = 72
for lab, val, col, sub in K:
    d.rounded_rectangle([x,236,x+258,404], radius=16, fill=SURF, outline=LINE)
    d.text((x+22,260), lab, font=F(1,15), fill=TX3)
    d.text((x+22,292), val, font=F(1,46), fill=col)
    d.text((x+22,356), sub, font=F(0,15), fill=TX3)
    x += 278

d.line([(72,470),(1128,470)], fill=LINE)
d.text((72,496), 'Backtest từng phiên từ 02/01/2019 · TOP '+str(D['universe_n'])
       +' mã · phí 0,15% mua / 0,25% bán', font=F(0,20), fill=TX2)
d.text((72,528), 'Số liệu phiên '+'/'.join(reversed(D['asof'].split('-')))
       +' · dữ liệu FireAnt + Vietcap IQ', font=F(0,19), fill=TX3)
d.text((72,572), 'Đây là công cụ nghiên cứu, không phải khuyến nghị đầu tư.',
       font=F(0,18), fill=CRIT)
dom, fd = 'nguyễnsơnfinance.com.vn', F(1,21)
d.text((1128-d.textlength(dom, font=fd), 572), dom, font=fd, fill=TX3)
im.save('og.png', 'PNG', optimize=True)
print('og.png', im.size, D['asof'])
