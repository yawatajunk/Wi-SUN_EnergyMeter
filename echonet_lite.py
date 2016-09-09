# coding: UTF-8
#
# echonet_lite.py
#
# ECHONET Lite クラス EchonetLite
# ECHONET Lite 低圧スマート電力量計クラス EchonetLiteSmartEnergyMeter
#
# Copyright(C) 2016 pi@blue-black.ink
#

import datetime


# ECHONET Lite クラス
class EchonetLite:
    # ECHONETサービス(ESV)
    ESV_CODE = {
        'seti':          b'\x60',
        'setc':          b'\x61',
        'get':           b'\x62',
        'inf_req':       b'\x63',
        'setget':        b'\x6e',
        'set_res':       b'\x71',
        'get_res':       b'\x72',
        'inf':           b'\x73',
        'infc':          b'\x74', 
        'infc_reg':      b'\x7a',
        'setget_res':    b'\x7e',
        'seti_sna':      b'\x50',
        'setc_sna':      b'\x51',
        'get_sna':       b'\x52',
        'inf_sna':       b'\x53',
        'setget_sna':    b'\x5e'}
    
    # クラスグループコード
    CLS_GRP_CODE = {
        'sensor':           b'\x00',    # センサ関連機器クラスグループ
        'airconditioner':   b'\x01',    # 空調関連機器クラスグループ
        'housing':          b'\x02',    # 住宅・設備関連機器クラスグループ
        'cooking':          b'\x03',    # 調理・家事関連機器クラスグループ
        'health':           b'\x04',    # 健康関連機器クラスグループ
        'control':          b'\x05',    # 管理・操作関連機器クラスグループ
        'av':               b'\x06',    # AV健康関連機器クラスグループ
        'profile':          b'\x0e',    # プロファイルクラスグループ
        'user':             b'\x0f'}    # ユーザ定義クラスグループ

    # 管理・操作関連機器クラスグループ クラスコード
    CLS_CONTROL_CODE = {    
        'switch':       b'\xfd',
        'portable':     b'\xfe',
        'controller':   b'\xff'}

    # 機器オブジェクトスーパークラス EPC
    EPC_DICT = {
        'operation_status':     b'\x80',
        'location':             b'\x81',
        'version':              b'\x82',
        'idn':                  b'\x83',
        'fault_status':         b'\x88',
        'manufacturer_code':    b'\x8a',
        'facility_code':        b'\x8b',
        'product_code':         b'\x8c',
        'production_no':        b'\x8d',
        'production_date':      b'\x8e',
        'current_time':         b'\x97',
        'current_date':         b'\x98',
        'chg_pty_map':          b'\x9d',
        'set_pty_map':          b'\x9e',
        'get_pty_map':          b'\x9f'}
    
    # ECHONET Lite 電文構成（フレームフォーマット）
    frame = {
        'ehd':  bytes(2),   # ECHONET Lite電文ヘッダ1,2
        'tid':  bytes(2),   # トランザクションID
        'seoj': bytes(3),   # 送信元ECHONET Liteオブジェクト指定
        'deoj': bytes(3),   # 相手先ECHONET Liteオブジェクト指定
        'esv':  bytes(1),   # ECHONET Liteサービス
        'opc':  bytes(1),   # 処理プロパティー数
        'ptys': []}         # プロパティ列
        
    def __init__(self):
        self.frame['ehd'] = b'\x10\x81'
        self.frame['tid'] = b'\x00\x00'
        self.frame['seoj'] = b'\x00\x00\x00'
        self.frame['deoj'] = b'\x00\x00\x00'
        self.frame['esv'] = b'\x00'
        self.frame['opc'] = b'\x00'

    # TID
    def set_tid(self, num):
        self.frame['tid'] = num.to_bytes(2, 'big')
    
    def get_tid(self):
        return int.from_bytes(self.frame['tid'], 'big')

    # SEOJ, DEOJ
    def set_eoj(self, sel, eoj):
        if sel.upper() == 'S':
            self.frame['seoj'] = eoj
        elif sel.upper() == 'D':
            self.frame['deoj'] = eoj
        else:
            raise ValueError(sel)
    
    def get_eoj(self, sel):
        if sel.upper() == 'S':
            return self.frame['seoj']
        elif sel.upper() == 'D':
            return self.frame['deoj']
        else:
            raise ValueError(sel)
    
    # ESV      
    def set_esv(self, esv):
        self.frame['esv'] = esv
        
    def get_esv(self):
        return self.frame['esv']
    
    # プロパティ列を空にする
    def reset_property(self):
        self.frame['ptys'] = []
        self.frame['opc'] = b'\x00'

    # プロパティを作成(dict形式)
    @staticmethod
    def make_property(epc, edt = b''):
        return {'epc': epc, 'pdc': len(edt).to_bytes(1, 'big'), 'edt': edt}

    # プロパティを追加する
    def set_property(self, epc, edt = b''):
        pty = self.make_property(epc, edt)
        self.frame['ptys'].append(pty)
        self.frame['opc'] = len(self.frame['ptys']).to_bytes(1, 'big')

    # n番目のプロパティを取得 （dict形式）
    def get_property(self, n):
        return self.frame['ptys'][n]

    # n番目のプロパティを取得 (bytes形式)
    def get_serialized_property(self, n):
        pty = self.get_property(n)
        return pty['epc'] + pty['pdc'] + pty['edt']

    # ECHONET Lite電文を取得 (dict形式)
    def get_frame(self):
        return self.frame
    
    # ECHONET Lite電文を取得 (bytes形式)
    def get_serialized_frame(self):
        res = self.frame['ehd'] + self.frame['tid'] + self.frame['seoj'] + self.frame['deoj'] + \
              self.frame['esv'] + self.frame['opc']
        for i in range(len(self.frame['ptys'])):
            res += self.get_serialized_property(i)
        return res

    # ECHONET Lite電文かどうか判断
    @staticmethod
    def is_frame(frame):
        return True if frame[0:2] == b'\x10\x81' else False        

    # TID, ESV及びプロパティからECHONET Lite電文を組み立てる
    def make_frame(self, tid, esv, ptys):    #  ptys: [[epc1, edt1], [epc2, edt2], ....]
        self.set_tid(tid)        
        self.frame['esv'] = esv
        self.reset_property()
        for pty in ptys:
            self.set_property(pty[0], pty[1])
        return self.get_serialized_frame()

    # ECHONET Lite 電文のTIDを変更
    def change_tid_frame(self, tid, frame):
        self.set_tid(tid)
        new_frame = frame[0:2] + self.frame['tid'] + frame[4:len(frame)]
        return new_frame

    # ECV辞書'EPC_DICT'を元に，Get電文を一括作成する。
    def make_get_frame_dict(self):
        frame_dict = {}
        for key in self.EPC_DICT.keys():
            frame = self.make_frame(0, self.ESV_CODE['get'], [[self.EPC_DICT[key], b'']])
            frame_dict.update({'get_'+key: frame})
        return frame_dict

    # ECHONET Lite 電文パーサー
    def parse_frame(self, res):
        bt_res = bytes.fromhex(res)
        if len(bt_res) < 12: # EHD1～OPC:12byte
            return False
        if not self.is_frame(bt_res):
            return False

        frame = {'ehd': bt_res[0:2],
                 'tid': int.from_bytes(bt_res[2:4], 'big'),
                 'seoj': bt_res[4:7], 
                 'deoj': bt_res[7:10],
                 'esv': bt_res[10:11],
                 'opc': int.from_bytes(bt_res[11:12], 'big'),
                 'ptys': []}

        idx = 12
        try:    # ECHONET Liteプロパティ
            for i in range(frame['opc']):
                pty = {'epc': bt_res[idx:idx + 1],
                       'pdc': int.from_bytes(bt_res[idx + 1:idx + 2], 'big')}
                pty['edt'] = bt_res[idx+2:idx+2+pty['pdc']]
                frame['ptys'].append(pty)
                idx += 2 + pty['pdc']
        except:
            return False    # フォーマットエラー
                            
        if len(bt_res) != idx:
            return False    # フォーマットエラー

        return frame


# ECHONET Lite スマート電力量メータクラス
class EchonetLiteSmartEnergyMeter(EchonetLite):
    CLS_LVSM_CODE = b'\x88'      # クラスコード（低圧スマート電力量メータ）

    ## EPC
    LVSM_EPC_DICT = {
        'operation_status':             b'\x80',
        'epc_coefficient':              b'\xd3',
        'digits':                       b'\xd7',
        'amount_energy_normal':         b'\xe0',
        'unit_amount_energy':           b'\xe1',
        'hist_amount_energy1_norm':     b'\xe2',
        'amount_energy_rev':            b'\xe3',
        'hist_amount_energy1_rev':      b'\xe4',
        'day_hist_amount_energy1':      b'\xe5',
        'instant_power':                b'\xe7',
        'instant_current':              b'\xe8',
        'recent_amount_energy_norm':    b'\xea',
        'recent_amount_energy_rev':     b'\xeb',
        'hist_amount_energy2':          b'\xec',
        'day_hist_amount_energy2':      b'\xed'}

    def __init__(self):
        super().__init__()
        
        self.frame['seoj'] = self.CLS_GRP_CODE['control'] + self.CLS_CONTROL_CODE['controller'] + b'\x01'
        self.frame['deoj'] = self.CLS_GRP_CODE['housing'] + self.CLS_LVSM_CODE + b'\x01'
        self.frame['esv'] = self.ESV_CODE['get']
        self.frame['opc'] = '\x01'

        self.EPC_DICT.update(self.LVSM_EPC_DICT)        # スーパークラスと自クラスのEPCを連結        
        self.FRAME_DICT = self.make_get_frame_dict()    # Get電文辞書を一括作成

        self.set_property(self.EPC_DICT['operation_status'])    # 仮のプロパティを設定

    @staticmethod
    def parse_datetime(dt_bytes):
        """30分毎の計測値などに付随する日付&時間パーサー
        dt_bytes: bytes型日付&時間 YYYYMMDDhhmmss (7 byte)
        return: datetime.datetime型"""
        
        year = int.from_bytes(dt_bytes[0:2], 'big')
        month = int.from_bytes(dt_bytes[2:3], 'big')
        day = int.from_bytes(dt_bytes[3:4], 'big')
        hour = int.from_bytes(dt_bytes[4:5], 'big')
        minute = int.from_bytes(dt_bytes[5:6], 'big')
        second = int.from_bytes(dt_bytes[6:7], 'big')
        
        return datetime.datetime(year, month, day, hour, minute, second)
        