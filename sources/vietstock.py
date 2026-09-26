"""Vietstock 'Thong ke giao dich' grid (includes Thong ke dat lenh) - public page, no login/API key.
Needs an anti-forgery token + cookie scraped from the public page (standard CSRF, not auth):
 GET  https://finance.vietstock.vn/{SYM}/thong-ke-giao-dich.htm  -> __RequestVerificationToken
 POST https://finance.vietstock.vn/data/gettradingresult  Code, PageIndex, PageSize, FromDate, ToDate (yyyy-mm-dd),
      Cols=LDM,LDB,KLDM,KLDB,TKLGD, ExchangeID=1, ExportType=default, __RequestVerificationToken
Fields: TotalBuyTrade, TotalBuyVol, TotalSellTrade, TotalSellVol (+ TotalVol, MT_TotalVol, BuyAvg, SellAvg).
"""
import re, json, datetime, argparse, time, threading, requests
_LOCK = threading.Lock()
BASE = "https://finance.vietstock.vn"
_S = None; _TOK = None

def _session():
    global _S, _TOK
    with _LOCK:
        return _session_locked()

def _session_locked():
    global _S, _TOK
    if _S is None:
        _S = requests.Session()
        _S.headers.update({"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest",
                           "Referer": BASE + "/HPG/thong-ke-giao-dich.htm"})
        h = _S.get(BASE + "/HPG/thong-ke-giao-dich.htm", timeout=30).text
        _TOK = re.search(r'__RequestVerificationToken type=hidden value=([^ >"]+)', h).group(1)
    return _S, _TOK

def fetch_rows(symbol, days=5, frm=None, to=None):
    s, tok = _session()
    today = datetime.date.today()
    d = {"Code": symbol, "OrderBy": "", "OrderDirection": "desc", "PageIndex": 1, "PageSize": days,
         "FromDate": frm or (today - datetime.timedelta(days=days * 2 + 10)).isoformat(), "ToDate": to or today.isoformat(),
         "ExportType": "default", "Cols": "LDM,LDB,KLDM,KLDB,TKLGD", "ExchangeID": 1, "__RequestVerificationToken": tok}
    for i in range(3):
        try:
            r = s.post(BASE + "/data/gettradingresult", data=d, timeout=30); r.raise_for_status()
            return r.json().get("Data") or []
        except Exception:
            if i == 2: raise
            time.sleep(2)

def probe(symbol, date=None, days=5):
    fetched = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7))).isoformat(timespec="seconds")
    try: rows = fetch_rows(symbol, days)
    except Exception as e:
        return [{"source": "vietstock", "symbol": symbol, "fetched_at": fetched, "available": False, "error": str(e)}]
    out = []
    for r in rows:
        ms = int(re.search(r"\d+", r["TradingDate"]).group())
        d = (datetime.datetime.utcfromtimestamp(ms / 1000) + datetime.timedelta(hours=7)).date().isoformat()
        if date and d != date: continue
        bc, bq, sc, sq = r["TotalBuyTrade"], r["TotalBuyVol"], r["TotalSellTrade"], r["TotalSellVol"]
        oi = (bq / bc) / (sq / sc) if bc and sc and sq and bq else None
        out.append({"source": "vietstock", "symbol": symbol, "fetched_at": fetched, "date": d,
                    "BuyCount": bc, "BuyQuantity": bq, "SellCount": sc, "SellQuantity": sq,
                    "Volume": r.get("TotalVol"), "ordimb_or_proxy": oi, "available": oi is not None})
    if date and not out:
        out.append({"source": "vietstock", "symbol": symbol, "fetched_at": fetched, "date": date, "available": False})
    return out

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("symbols", nargs="+"); ap.add_argument("--date"); ap.add_argument("--days", type=int, default=5)
    a = ap.parse_args()
    print(json.dumps({s: probe(s, a.date, a.days) for s in a.symbols}, ensure_ascii=False, indent=1))
