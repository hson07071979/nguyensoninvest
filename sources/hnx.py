# -*- coding: utf-8 -*-
"""HNX official 'Thống kê cung cầu' (per-symbol order-placement stats), public, no login.
POST https://www.hnx.vn/ModuleIssuer/Report_NY/TK_CungCauListSearch_Datas  (p_market=NY listed, UC=UPCoM)
Columns: Ngày GD | Giá đóng cửa | Số lệnh đặt mua | KL đặt mua | Số lệnh đặt bán | KL đặt bán | Dư mua | Dư bán | KLGD | GTGD
TLS: www.hnx.vn serves an incomplete chain (missing 'GlobalSign GCC R3 EV TLS CA 2025'); we complete it with the
intermediate from the cert's own AIA URL (full verification kept; never verify=False).
Usage: python3 probe_hnx.py SHS PVS CEO MBS [--date 2026-09-23]
"""
import requests, re, html, os, sys, json, datetime as dt
HERE=os.path.dirname(os.path.abspath(__file__))
BUNDLE=os.path.join(os.environ.get('TMPDIR','/tmp'),'hnx_bundle.pem')
AIA='http://secure.globalsign.com/cacert/gsgccr3evtlsca2025.crt'
def _bundle():
    if os.path.exists(BUNDLE): return BUNDLE
    import ssl
    der=requests.get(AIA,timeout=30).content
    pem=ssl.DER_cert_to_PEM_cert(der)
    base=os.environ.get('REQUESTS_CA_BUNDLE') or os.environ.get('SSL_CERT_FILE')
    if not base or not os.path.exists(base):
        import certifi; base=certifi.where()
    open(BUNDLE,'w').write(open(base).read()+'\n'+pem); return BUNDLE
S=requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0','X-Requested-With':'XMLHttpRequest'})
now=lambda: dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
num=lambda s: float(s.replace('.','').replace(',','.')) if s and s.strip() not in ('','-') else None

def cungcau(sym, market='NY', n=50, page=1):
    v=_bundle()
    r=S.post('https://www.hnx.vn/ModuleIssuer/Report_NY/TK_CungCauListSearch_Datas',verify=v,timeout=60,
        headers={'Referer':f'https://www.hnx.vn/cophieu-etfs/chi-tiet-chung-khoan-{market.lower()}-{sym.lower()}.html'},
        data={'p_issearch':1,'p_market':market,'p_symbol':sym,'p_orderby':'','p_ordertype':'','p_currentpage':page,'p_record_on_page':n})
    rows=[]
    for tr in re.findall(r'<tr[^>]*>(.*?)</tr>',r.text,flags=re.S):
        c=[html.unescape(re.sub(r'<[^>]+>','',x)).strip() for x in re.findall(r'<td[^>]*>(.*?)</td>',tr,flags=re.S)]
        if len(c)>=10 and re.match(r'\d\d/\d\d/\d{4}',c[0]):
            d=dt.datetime.strptime(c[0],'%d/%m/%Y').date().isoformat()
            k=['close','BuyCount','BuyQuantity','SellCount','SellQuantity','ResidualBuy','ResidualSell','Volume','ValueK']
            rows.append(dict(date=d,**{a:num(b) for a,b in zip(k,c[1:10])}))
    tot=re.search(r'Tổng số\s*([\d.]+)\s*bản ghi',html.unescape(r.text))
    return r.status_code, rows, (int(tot.group(1).replace('.','')) if tot else None)

def probe(sym, date=None, market='NY'):
    st,rows,tot=cungcau(sym,market)
    row=next((x for x in rows if x['date']==date),None) if date else (rows[0] if rows else None)
    oi=None
    if row and row['BuyCount'] and row['SellCount'] and row['SellQuantity']:
        oi=(row['BuyQuantity']/row['BuyCount'])/(row['SellQuantity']/row['SellCount'])
    return {'source':'hnx.TK_CungCau','symbol':sym,'fetched_at':now(),'date':row and row['date'],'fields':row,
            'ordimb_or_proxy':oi,'available':oi is not None,'http':st,'history_rows':tot}

if __name__=='__main__':
    a=sys.argv[1:]; date=None
    if '--date' in a: i=a.index('--date'); date=a[i+1]; del a[i:i+2]
    print(json.dumps([probe(s,date) for s in (a or ['SHS','PVS'])],indent=1,ensure_ascii=False))
