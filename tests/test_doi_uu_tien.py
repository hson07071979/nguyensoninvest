# -*- coding: utf-8 -*-
"""Phien 04/11/2026: chuong bao MUA DO VND 14:03, ORS "1/2" 14:08, TCH "1/2" 14:28 — ba ma, khong noi
ma truoc da mat luot (PROD toi da 1 lenh do). Tu 04/11 (anh Son: luon theo thu tu moi, bao ngay moi lan doi):
ma giu luot doi -> tin DOI UU TIEN: mua ma moi; ma cu chua khop huy, da khop ban 100% ATC T+3.
Run: python3 -m unittest tests/test_doi_uu_tien.py -v"""
import datetime as dt
import os, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import live_scan as LS

SES = '2026-11-04'
T = dict(asof='2026-11-03', cfg=dict(max_unconf=1, sell_from=3, rank_mode='score_volr', stage1=1.0),
         book=dict(positions=[]))


def h(sym, score, volr):
    return dict(sym=sym, score=score, volr=volr, level='SAP_DU', prod_ok=False, mua_do=True, dang_cam=False,
                price=12.75, pct=6.7, mua_do_du_phong=False)


class DoiUuTien(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self._g = (LS.gio_vn, LS.kenh_co, LS.gui_tin, LS.co_lenh)
        LS.kenh_co = lambda: True
        LS.gui_tin = lambda text, **k: (self.sent.append(text) or True)
        LS.co_lenh = lambda *a, **k: (8.4, 8.4, [], 1068e6, 12.71e9)
        self.cu = set()

    def tearDown(self):
        LS.gio_vn, LS.kenh_co, LS.gui_tin, LS.co_lenh = self._g

    def nhip(self, hhmm, hits):
        hh, mm = map(int, hhmm.split(':'))
        LS.gio_vn = lambda: dt.datetime(2026, 11, 4, hh, mm)
        LS.danh_dau_max_unconf(hits, T, SES, 3)
        n0 = len(self.sent)
        da = LS.gui_telegram(hits, SES, self.cu, SES, 'DO', 0.8, T) or []
        self.cu |= set(da)
        return self.sent[n0:]

    def test_chuoi_04_11(self):
        m = self.nhip('14:03', [h('VND', 46, 2.44)])
        self.assertEqual(len(m), 1)
        self.assertIn('MUA DÒ', m[0]); self.assertIn('VND', m[0])
        self.assertIn('G1:VND', self.cu)
        # 14:08: VND khong con la ung vien, ORS (74) dung dau
        m = self.nhip('14:08', [h('ORS', 74, 1.87), h('TCH', 55, 1.6)])
        self.assertEqual(len(m), 1)
        self.assertIn('ĐỔI ƯU TIÊN', m[0])
        self.assertIn('→ *ƯU TIÊN 1/2* · *ORS*', m[0])
        self.assertIn('*VND* không còn đủ điều kiện', m[0])
        self.assertIn('bán 100% ATC T+3', m[0])
        self.assertEqual(LS.giu_luot_cu(self.cu), (2, ['ORS']))
        # nhip sau cung thu tu -> im lang
        self.assertEqual(self.nhip('14:10', [h('ORS', 74, 1.87), h('TCH', 55, 1.6)]), [])
        # 14:28: TCH vuot ORS
        m = self.nhip('14:28', [h('ORS', 54, 1.5), h('TCH', 55, 2.79)])
        self.assertEqual(len(m), 1)
        self.assertIn('→ *ƯU TIÊN 1/2* · *TCH*', m[0])
        self.assertIn('*ORS* xuống *2/2*', m[0])
        self.assertIn('Thứ tự lúc này: 1. TCH · 2. ORS', m[0])
        # ORS quay lai #1 -> bao ngay (A -> B -> A)
        m = self.nhip('14:31', [h('ORS', 74, 3.0), h('TCH', 55, 2.79)])
        self.assertEqual(len(m), 1)
        self.assertIn('→ *ƯU TIÊN 1/2* · *ORS*', m[0]); self.assertIn('*TCH* xuống *2/2*', m[0])
        self.assertEqual(LS.giu_luot_cu(self.cu), (4, ['ORS']))
        # ngoai 14:00-14:45: khong bao doi
        self.assertEqual([x for x in self.nhip('14:50', [h('TCH', 90, 5.0), h('ORS', 50, 1.0)])
                          if 'ĐỔI ƯU TIÊN' in x], [])

    def test_dau_tien_kem_dong_khong_mua(self):
        m = self.nhip('14:05', [h('AAA', 80, 3.0), h('BBB', 60, 2.0)])
        self.assertEqual(len(m), 1)
        self.assertIn('*AAA*', m[0]); self.assertIn('*BBB*', m[0]); self.assertIn('KHÔNG MUA', m[0])
        self.assertNotIn('ĐỔI ƯU TIÊN', m[0])
        # BBB chi duoc bao KHONG MUA -> khong phai 'D:' (toi khong bi nhac ban / giu tren trang nhu ma da mua)
        self.assertIn('D:AAA', self.cu); self.assertNotIn('D:BBB', self.cu); self.assertIn('DK:BBB', self.cu)
        # BBB vuot AAA -> tin doi, BBB thanh 'D:'
        m = self.nhip('14:09', [h('AAA', 60, 2.0), h('BBB', 80, 3.0)])
        self.assertEqual(len(m), 1); self.assertIn('→ *ƯU TIÊN 1/2* · *BBB*', m[0]); self.assertIn('D:BBB', self.cu)

    def test_het_luot_tu_phien_truoc(self):
        global T
        T0 = T
        try:
            T = dict(T0, book=dict(positions=[dict(sym='PVT', held=1, probe_fail=True)]))
            m = self.nhip('14:05', [h('AAA', 80, 3.0)])
            self.assertEqual(len(m), 1); self.assertIn('HẾT LƯỢT', m[0]); self.assertIn('PVT', m[0])
            self.assertEqual(self.nhip('14:06', [h('AAA', 80, 3.0)]), [])
            self.assertIn('DK:AAA', self.cu); self.assertNotIn('D:AAA', self.cu)
        finally:
            T = T0



class HetLuotToi(unittest.TestCase):
    def test_nhac_ban_ma_het_luot(self):
        hs = [dict(sym='ORS', level='MUA', prod_ok=True, khong_mua='max_unconf'),
              dict(sym='TCH', level='MUA', prod_ok=True),
              dict(sym='MBS', level='MUA', prod_ok=True, khong_mua='max_unconf')]     # MBS chua tung bao do
        cu = {'D:ORS', 'D:TCH', 'G1:ORS', 'G2:TCH'}
        nh = LS.nhac_het_luot(hs, [dict(sym='ORS', mua=SES, ban='x', ly_do='cu')], cu, SES, 3)
        self.assertEqual([x['sym'] for x in nh], ['ORS'])
        self.assertEqual(nh[0]['ban'], LS.phien_cong(SES, 3))
        self.assertIn('hết lượt', nh[0]['ly_do'])



class PhatLai0411Toi(unittest.TestCase):
    """16:33 phien 04/11: TCH dat DK9 (MUA), HAH du DK1-8 luc dong cua nhung truot DK9 (truot9).
    Bo may (engine2, xep truoc DK9) chon HAH #1/2 (hoa diem+Vol, pha hoa theo ma) -> TCH het luot.
    Truoc sua: live bo HAH khoi ung vien -> bao 'GIU TCH'. Sau sua: khop bo may."""

    def setUp(self):
        self.sent = []
        self._g = (LS.gio_vn, LS.kenh_co, LS.gui_tin, LS.co_lenh)
        LS.gio_vn = lambda: dt.datetime(2026, 11, 4, 16, 33)
        LS.kenh_co = lambda: True
        LS.gui_tin = lambda text, **k: (self.sent.append(text) or True)
        LS.co_lenh = lambda *a, **k: (8.4, 8.4, [], 1068e6, 12.71e9)

    def tearDown(self):
        LS.gio_vn, LS.kenh_co, LS.gui_tin, LS.co_lenh = self._g

    def test_khop_bo_may(self):
        tch = dict(sym='TCH', score=55.0, volr=3.09, level='MUA', prod_ok=True, mua_do=False, truot9=False,
                   dang_cam=False, price=12.75, pct=6.69, gtgd=268.9, ordimb=2.2934, ordimb_min=1.4)
        hah = dict(sym='HAH', score=59.1, volr=2.10, level='SAP_DU', prod_ok=False, mua_do=False, truot9=True,
                   dang_cam=False, price=48.8, pct=5.63, ordimb=1.0588, ordimb_min=1.4)
        hits = [tch, hah]
        LS.danh_dau_max_unconf(hits, T, SES, 3)
        self.assertEqual((hah['uu_tien'], tch['uu_tien']), (1, 2))       # = engine2 signals_today HAH 1/2
        self.assertNotIn('khong_mua', hah)
        self.assertEqual(tch['khong_mua'], 'max_unconf'); self.assertEqual(tch['khong_mua_vi'], ['HAH'])
        cu = {'D:TCH', 'G1:TCH'}
        LS.gui_telegram(hits, SES, cu, SES, 'DO', 1.0, T)
        txt = '\n'.join(self.sent)
        self.assertNotIn('GIỮ lệnh dò', txt)
        self.assertIn('HỆ THỐNG KHÔNG MUA', txt); self.assertIn('*TCH*', txt); self.assertIn('bán 100% ATC T+3', txt)
        self.assertIn('KHÔNG ĐẠT ĐIỀU KIỆN 9', txt); self.assertIn('CHỌN MÃ NÀY', txt)
        nh = LS.nhac_het_luot(hits, [], cu, SES, 3)
        self.assertEqual([(x['sym'], x['ban']) for x in nh], [('TCH', '2026-11-09')])


if __name__ == '__main__':
    unittest.main()
