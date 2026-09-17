# -*- coding: utf-8 -*-
"""Doi NaN / Infinity trong khoi DATA cua index.html thanh null.

Vi sao can buoc nay: json.dump cua Python ghi NaN va Infinity nhu tu khoa tran,
nhung JSON.parse cua trinh duyet KHONG chap nhan -> nem loi -> CA TRANG TRANG.
Ngay 17/09/2026 dung mot o ("Mom" trong bang tieu chi) co NaN da lam sap trang.
Buoc nay chay sau moi lan ban dung day index.html len, nen loi kieu do khong ra
den nguoi xem nua, du repo bot co sinh ra NaN.
"""
import json
import math
import re
import sys

P = 'index.html'
h = open(P, encoding='utf-8').read()
m = re.search(r'(<script id="DATA"[^>]*>)(.*?)(</script>)', h, re.S)
if not m:
    sys.exit('HONG: khong thay khoi DATA trong index.html')

raw = m.group(2)
if not re.search(r'\b(NaN|Infinity|-Infinity)\b', raw):
    print('DATA sach — khong co NaN/Infinity')
    sys.exit(0)


def sach(o):
    if isinstance(o, float) and not math.isfinite(o):
        return None
    if isinstance(o, dict):
        return {k: sach(v) for k, v in o.items()}
    if isinstance(o, list):
        return [sach(v) for v in o]
    return o


# json.loads CHAP NHAN NaN/Infinity, nen doc vao duoc; luc ghi ra thi chan lai
# bang allow_nan=False de neu con sot cai gi thi bao loi ngay o day.
d = sach(json.loads(raw))
out = json.dumps(d, ensure_ascii=False, allow_nan=False).replace('</', '<\\/')
open(P, 'w', encoding='utf-8').write(h[:m.start(2)] + out + h[m.end(2):])
print('da doi NaN/Infinity thanh null · DATA %d -> %d byte' % (len(raw), len(out)))
