# coding: UTF-8
#
# y3module.py
#
# Wi-SUNモジュールBP35A1(ROHM) 通信クラス Y3Module
#
# Copyright(C) 2016 pi@blue-black.ink
#

import serial
import threading
import time
import sys
from pprint import pprint


class Y3Module(threading.Thread):
    def __init__(self):
        super().__init__()
        self.Y3_UDP_ECHONET_PORT = 3610 # ECHONET UDPポート
        self.Y3_UDP_PANA_PORT = 716     # PANAポート
        self.Y3_TCP_ECHONET_PORT = 3610 # TCPポート
        
        self.msg_list_queue = []        # 受信データ用リスト
        self.term_flag = False          # run()の終了フラグ

        self.uart_hdl = None            # UART
        self.uart_dev = None
        self.uart_baud = 9600

        self.search = {                 # write()用, UART送信後の受信待ちデータ
            'search_words': [],               # UART送信後の受信待ちデータリスト
            'ignore_intermidiate': False,   # 途中の受信データを無視する
            'found_word_list': [],          # 受け取った受信待ちデータリスト
            'start_time': None,             # UART送信時のtime
            'timeout': 0}                   # 設定タイムアウト時間[s]

        self.msg_list_pana_queue = []    # debug: UDP(PANAポート)のデータを保存

    # ERXUDP, ERXTCPのフォーマット, True: ASCII， False: Binary
    def set_opt(self, flag):
        current = self.get_opt()
        if flag and not current:        # 変更無しの場合はモジュールに書き込まない（FLASHへの書き込み制限）
            self.write(b'WOPT 01\r\n', ['OK 01'])
        elif not flag and current:
            self.write(b'WOPT 00\r\n', ['OK 00'])
        return True

    def get_opt(self):
        res = self.write(b'ROPT\r\n', ['OK'])
        return True if res[0]['MESSAGE'][0] == '01' else False

    # エコーバックを停止(リセット後，最初に1回だけコールする)
    def set_echoback_off(self):
        self.write(b'SKSREG SFE 0\r\n', ['SKSREG', 'OK'], ignore = True)

    # Wi-Sunチャンネル
    def set_channel(self, ch):
        bc = '{:02X}'.format(ch).encode()
        self.write(b'SKSREG S02 ' + bc + b'\r\n', ['OK'])

    # ペアリングID
    def set_pairing_id(self, pairid):
        self.write(b'SKSREG S0A ' + pairid.encode() + b'\r\n', ['OK'])

    # PAN ID
    def set_pan_id(self, pan):
        bp = '{:04X}'.format(pan).encode()
        self.write(b'SKSREG S03 ' + bp + b'\r\n', ['OK'])

    # ビーコンへの反応
    def set_accept_beacon(self, flag):
        bf = b'1' if flag else b'0'
        self.write(b'SKSREG S15 ' + bf + b'\r\n', ['OK'])

    # 送信制限フラグ
    def get_tx_limit(self):
        res = self.write(b'SKSREG SFB\r\n' , ['ESREG', 'OK'])
        result = True if res[0]['VAL'][0] == '1' else False
        return result

    # パスワード
    def set_password(self, password):
        length = len(password)
        if length < 1 or length > 32:
            result = False
        else:
            bp = '{:X} {}'.format(length, password).encode()
            self.write(b'SKSETPWD ' + bp + b'\r\n', ['OK'])
            result = True
        return result

    # ルートB ID
    def set_routeb_id(self, rbid):
        if len(rbid) != 32:
            result = False
        else:
            self.write(b'SKSETRBID ' + rbid.encode() + b'\r\n', ['OK'])
            result = True
        return result

    # PAA開始
    def start_paa(self):
        self.write(b'SKSTART\r\n', ['OK'])

    # PaC開始
    def start_pac(self, ip6):
        res = self.write(b'SKJOIN ' + ip6.encode() + b'\r\n', [['EVENT 24', 'EVENT 25']], 
                         ignore = True, timeout = 10)
        try:
            result = True if res[0]['COMMAND'] == 'EVENT 25' else False
        except:     # IndexErrorが発生するときのための暫定処理。要修正
            result = False
        return result

    # IP6アドレス
    def get_ip6(self, add):
        res = self.write(b'SKLL64 ' + add.encode() + b'\r\n', ['UNKNOWN'])
        return res[0]['MESSAGE'][0]

    # TCPコネクション開始
    def tcp_connect(self, ip6, rport, lport):
        br = ' {:04X}'.format(rport).encode()
        bl = ' {:04X}'.format(lport).encode()
        res = self.write(b'SKCONNECT ' + ip6.encode() + br + bl + b'\r\n', ['ETCP'])
        return res[0]

    # TCPコネクション停止
    def tcp_disconnect(self, handle):
        res = self.write(b'SKCLOSE ' + str(handle).encode() + b'\r\n', ['ETCP'])
        return res[0]['STATUS'] == 3

    # TCPで送信
    # message: bytes型
    def tcp_send(self, handle, message):
        len_bt =' {:04X} '.format(len(message)).encode()         
        res = self.write(b'SKSEND ' + str(handle).encode() + len_bt + message, ['ETCP'])
        return res[0]['STATUS'] == 5

    # UDPで送信
    # message: bytes型
    def udp_send(self, handle, ip6, security, port, message):
        sec_bt = b' 1' if security else b' 0'
        len_bt = ' {:04X} '.format(len(message)).encode()
        port_bt = ' {:04X}'.format(port).encode()
        res = self.write(b'SKSENDTO ' + str(handle).encode() + b' ' + ip6.encode() + port_bt + 
                         sec_bt + len_bt + message, ['EVENT 21', 'OK'])

        if res[0]['PARAM'] == '01':
            sys.stderr.write('[Error]: UDP transmission.\n')
            if self.get_tx_limit():
                sys.stderr.write('[Error]: TX limit.\n')
            return False
        else:
            return True     # 送信成功

    # EDスキャン
    def ed_scan(self, duration = 4):
        bd = '{:X}'.format(duration).encode()
        self.write(b'SKSCAN 0 FFFFFFFF ' + bd + b'\r\n', ['EEDSCAN'], ['OK'])
        res = []
        while True:
            if self.get_queue_size():
                msg = self.dequeue_message()
                res = msg['MESSAGE']
                break
            else:
                time.sleep(0.01)

        lqi_list = []
        for i in range(0, len(res), 2):
            lqi_list.append([int(res[i + 1], base=16), int(res[i], base=16)])  # [[LQI, channel], [LQI, channel],....]
            lqi_list.sort()  # LQIでソート
        return [lqi_list[0][1], lqi_list[0][0]]  # LQI最小チャンネル [channel, LQImin]

    # アクティブスキャン
    def active_scan(self, duration = 6):
        bd = '{:X}'.format(duration).encode()
        self.write(b'SKSCAN 2 FFFFFFFF ' + bd + b'\r\n')
        scan_end = False
        channel_list = []
        channel = {}

        try:
            while not scan_end:
                if self.get_queue_size():
                    msg_list = self.dequeue_message()
                    if msg_list['COMMAND'] == 'EVENT 20':
                        pass    # beacon 受信
                    elif msg_list['COMMAND'] == 'EPANDESC':
                        channel = {}
                    elif msg_list['COMMAND'] == 'ACTIVESCAN':
                        if 'Channel' in msg_list:
                            channel['Channel'] = msg_list['Channel']
                        elif 'Channel Page' in msg_list:
                            channel['Channel Page'] = msg_list['Channel Page']
                        elif 'Pan ID' in msg_list:
                            channel['Pan ID'] = msg_list['Pan ID']
                        elif 'Addr' in msg_list:
                            channel['Addr'] = msg_list['Addr']
                        elif 'LQI' in msg_list:
                            channel['LQI'] = msg_list['LQI']
                        elif 'PairID' in msg_list:
                            channel['PairID'] = msg_list['PairID']
                            channel_list.append(channel)
                    elif msg_list['COMMAND'] == 'EVENT 22':
                        scan_end = True
                else:
                    time.sleep(0.01)
        except KeyboardInterrupt:
            channel_list = False   # スキャンキャンセル

        return channel_list

    # 受信メッセージの判別処理
    @staticmethod
    def parse_message(msg):
        #print('parse:'+msg) #debug
        msg_list = {}

        if msg.startswith('Channel Page'):
            msg_list['COMMAND'] = 'ACTIVESCAN'
            cols = msg.split(':')
            msg_list['Channel Page'] = int(cols[1], base=16)
            return msg_list

        if msg.startswith('Channel'):
            msg_list['COMMAND'] = 'ACTIVESCAN'
            cols = msg.split(':')
            msg_list['Channel'] = int(cols[1], base=16)
            return msg_list

        if msg.startswith('Pan ID'):
            msg_list['COMMAND'] = 'ACTIVESCAN'
            cols = msg.split(':')
            msg_list['Pan ID'] = int(cols[1], base=16)
            return msg_list

        if msg.startswith('Addr'):
            msg_list['COMMAND'] = 'ACTIVESCAN'
            cols = msg.split(':')
            msg_list['Addr'] = cols[1]
            return msg_list

        if msg.startswith('LQI'):
            msg_list['COMMAND'] = 'ACTIVESCAN'
            cols = msg.split(':')
            msg_list['LQI'] = int(cols[1], base=16)
            return msg_list

        if msg.startswith('PairID'):
            msg_list['COMMAND'] = 'ACTIVESCAN'
            cols = msg.split(':')
            msg_list['PairID'] = cols[1]
            return msg_list

        cols = msg.split()

        if cols[0] == 'OK':
            msg_list['COMMAND'] = cols[0]
            if len(cols) > 1:
                msg_list['MESSAGE'] = cols[1:len(cols)]
            return msg_list

        if cols[0] == 'EVENT':
            msg_list['COMMAND'] = cols[0] + ' ' + cols[1]
            msg_list['SENDER'] = cols[2]
            if len(cols) == 4:
                msg_list['PARAM'] = cols[3]
            return msg_list

        if cols[0] == 'ERXUDP':  # UDP
            msg_list['COMMAND'] = cols[0]
            msg_list['SENDER'] = cols[1]
            msg_list['DEST'] = cols[2]
            msg_list['RPORT'] = int(cols[3], base=16)
            msg_list['LPORT'] = int(cols[4], base=16)
            msg_list['SENDERLLA'] = cols[5]
            msg_list['SECURED'] = int(cols[6], base=16)
            msg_list['DATALEN'] = int(cols[7], base=16)
            msg_list['DATA'] = cols[8]
            return msg_list

        if cols[0] == 'ERXTCP':
            msg_list['COMMAND'] = cols[0]
            msg_list['SENDER'] = cols[1]
            msg_list['RPORT'] = int(cols[2], base=16)
            msg_list['LPORT'] = int(cols[3], base=16)
            msg_list['DATALEN'] = int(cols[4], base=16)
            msg_list['DATA'] = cols[5]
            return msg_list

        if cols[0] == 'ETCP':
            msg_list['COMMAND'] = cols[0]
            msg_list['STATUS'] = int(cols[1], base=16)
            msg_list['HANDLE'] = int(cols[2], base=16)
            if msg_list['STATUS'] == 1:
                msg_list['IPADDR'] = cols[3]
                msg_list['RPORT'] = int(cols[4], base=16)
                msg_list['LPORT'] = int(cols[5], base=16)
            return msg_list

        if cols[0] == 'ESREG':
            msg_list['COMMAND'] = cols[0]
            msg_list['VAL'] = cols[1]
            return msg_list

        if cols[0] == 'EPANDESC':
            msg_list['COMMAND'] = 'EPANDESC'
            return msg_list

        if cols[0] == 'EEDSCAN':
            msg_list['COMMAND'] = 'EEDSCAN'
            return msg_list

        # ローカルエコー停止前のローカルエコー対策: 'SKSREG SFE 0'
        if cols[0] == 'SKSREG':
            msg_list['COMMAND'] = 'SKSREG'
            msg_list['REG'] = cols[1]
            msg_list['VAL'] = cols[2]
            return msg_list

        # その他
        msg_list['COMMAND'] = 'UNKNOWN'  # unknown message
        msg_list['MESSAGE'] = cols
        #pprint(msg_list)    # debug
        return msg_list

    # 文字列(Ascii Hex)をデコードする
    # 例 '616263' -> 'abc'
    @staticmethod
    def decode(ascii_str):
        return bytes.fromhex(ascii_str).decode()

    # メッセージをリストに追加
    def enqueue_message(self, msg_list):
        #print('in: {}'.format(msg_list))    # debug
        self.msg_list_queue.append(msg_list)

    # メッセージをリストから取り出す
    def dequeue_message(self):
        if self.msg_list_queue:
            #print('out: {}'.format(self.msg_list_queue[0]))  # debug
            return self.msg_list_queue.pop(0)
        else:
            return False

    # リスト内のメッセージ数
    def get_queue_size(self):
        return len(self.msg_list_queue)

    # UARTオープン
    def uart_open(self, dev, baud, timeout):
        try:
            self.uart_hdl = serial.Serial(dev, baud, timeout=timeout)
            self.uart_dev = dev
            self.uart_baud = baud
            return True
        except OSError as msg:
            sys.stderr.write('[Error]: {}\n'.format(msg))
            return False

    # UARTクローズ
    def uart_close(self):
        try:
            self.uart_hdl.close()
        except OSError as msg:
            sys.stderr.write('[Error]: {}\n'.format(msg))

    # UART書き込み & 受信待ち
    #   send_msg: 送信データ: bytes
    #   search_word: 受信待ちコマンド
    #       (例) ['word1', 'word2', ['word31', 'word32']]: 'word1 -> 'word2' -> 'word31' or 'word32'
    #   ignore: 途中の受信データを無視する
    #   timeout: タイムアウト時間[s]
    def write(self, send_msg, search_words = [], ignore = False, timeout = 0):
        try:
            #print(b'write:'+send_msg)   # debug
            self.uart_hdl.write(send_msg)
            if search_words:
                self.search['found_word_list'] = []
                self.search['ignore_intermidiate'] = ignore
                self.search['start_time'] = time.time()
                self.search['timeout'] = timeout
                self.search['search_words'] = search_words    # run()で監視しているので、一番最後に設定する

                while self.search['search_words'] != []:
                    time.sleep(0.01)
                return self.search['found_word_list']

        except OSError as msg:
            sys.stderr.write('[Error]: {}\n'.format(msg))
            return False

    # 1行読み込み（文字列）
    def read(self):
        try:
            res = self.uart_hdl.readline().decode().strip()
            #print('read:'+res)   # debug
            return res
        except OSError as msg:
            sys.stderr.write('[Error]: {}\n'.format(msg))
            return False

    #  UART受信用スレッド
    def run(self):
        while not self.term_flag:
            msg = self.read()
            if msg:
                msg_list = self.parse_message(msg)

                # debug: UDP(PANA)の受信データを保存する
                if msg_list['COMMAND'] == 'ERXUDP' and msg_list['LPORT'] == self.Y3_UDP_PANA_PORT:
                    self.msg_list_pana_queue.append(msg_list)
               
                elif self.search['search_words']:     # サーチ中である
                    # サーチワードを受信した。
                    search_words = self.search['search_words'][0]                    
                    if isinstance(search_words, list):
                        for word in search_words:
                            if msg_list['COMMAND'].startswith(word):
                                self.search['found_word_list'].append(msg_list)
                                self.search['search_words'].pop(0)
                                break
                    elif msg_list['COMMAND'].startswith(search_words):
                        self.search['found_word_list'].append(msg_list)
                        self.search['search_words'].pop(0)
                    
                    elif self.search['ignore_intermidiate']:
                        pass    # 途中の受信データを破棄 
                
                    else:    # サーチワードではなかった
                        self.enqueue_message(msg_list)
                
                else:   # サーチ中ではない
                    self.enqueue_message(msg_list)
                
            elif self.search['timeout']:  # read()がタイムアウト，write()でタイムアウトが設定されている
                if time.time() - self.search['start_time'] > self.search['timeout']:
                    self.search['found_word_list'] = []
                    self.search['search_words'] = []
                    self.search['timeout'] = 0

    # run()の停止
    def terminate(self):
        self.term_flag = True
        self.join()






































