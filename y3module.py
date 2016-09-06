# coding: UTF-8
#
# y3module.py
#
# Wi-SUNモジュールBP35A1(ROHM) 通信クラス Y3Module
#
# Copyright(C) 2016 pi@blue-black.ink
#

import datetime
import serial
import threading
import time
import sys


class Y3Module(threading.Thread):
    """Wi-SUN Module BP35A1(ROHM) 通信クラス"""
    def __init__(self):
        """コンストラクタ"""
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
            'search_words': [],             # UART送信後の受信待ちデータリスト
            'ignore_intermidiate': False,   # 途中の受信データを無視する
            'found_word_list': [],          # 受け取った受信待ちデータリスト
            'start_time': None,             # UART送信時のtime
            'timeout': 0}                   # 設定タイムアウト時間[s]

        self.msg_list_lock = threading.Lock()   # msg_listの排他制御用


    def set_opt(self, flag):
        """ERXUDP, ERXTCPのフォーマット設定
            flag: True: ASCII
                  False: Binary
        """
        current = self.get_opt()
        if flag and not current:        # 変更無しの場合はモジュールに書き込まない（FLASHへの書き込み制限）
            self.write(b'WOPT 01\r\n', ['OK 01'])
        elif not flag and current:
            self.write(b'WOPT 00\r\n', ['OK 00'])
        return True


    def get_opt(self):
        """ERXUDP, ERXTCPのフォーマット取得
            retern True: ASCII
                   False: Binary
        """
        res = self.write(b'ROPT\r\n', ['OK'])
        return True if res[0]['MESSAGE'][0] == '01' else False


    def set_echoback_off(self):
        """エコーバックを停止"""
        self.write(b'SKSREG SFE 0\r\n', ['OK'], ignore = True)


    def set_channel(self, ch):
        """Wi-SUNチャンネル設定"""
        bc = '{:02X}'.format(ch).encode()
        self.write(b'SKSREG S02 ' + bc + b'\r\n', ['OK'])


    def set_pairing_id(self, pairid):
        """ペアリングID設定"""
        self.write(b'SKSREG S0A ' + pairid.encode() + b'\r\n', ['OK'])

    def set_pan_id(self, pan):
        """PAN ID設定"""
        bp = '{:04X}'.format(pan).encode()
        self.write(b'SKSREG S03 ' + bp + b'\r\n', ['OK'])


    def set_accept_beacon(self, flag):
        """ビーコンリクエストへの反応
            flag True:  応答する
                 False: 応答しない
        """
        bf = b'1' if flag else b'0'
        self.write(b'SKSREG S15 ' + bf + b'\r\n', ['OK'])


    def get_tx_limit(self):
        """送信制限フラグ取得"""
        res = self.write(b'SKSREG SFB\r\n' , ['ESREG', 'OK'])
        result = True if res[0]['VAL'][0] == '1' else False
        return result


    def set_password(self, password):
        """パスワード設定"""
        length = len(password)
        if length < 1 or length > 32:
            result = False
        else:
            bp = '{:X} {}'.format(length, password).encode()
            self.write(b'SKSETPWD ' + bp + b'\r\n', ['OK'])
            result = True
        return result


    def set_routeb_id(self, rbid):
        """ルートB ID設定"""
        if len(rbid) != 32:
            result = False
        else:
            self.write(b'SKSETRBID ' + rbid.encode() + b'\r\n', ['OK'])
            result = True
        return result


    def start_paa(self):
        """PAA開始"""
        self.write(b'SKSTART\r\n', ['OK'])


    def start_pac(self, ip6):
        """PaC開始"""
        res = self.write(b'SKJOIN ' + ip6.encode() + b'\r\n', [['EVENT 24', 'EVENT 25', 'FAIL ER10']], 
                         ignore = True, timeout = 10)
        try:
            result = True if res[0]['COMMAND'] == 'EVENT 25' else False
            return result
        except:     # IndexErrorが発生するときのための暫定処理。要検討
            result = False

            
    
    def restart_pac(self):
        """PaCをリスタート"""
        res = self.write(b'SKREJOIN\r\n', [['EVENT 24', 'EVENT 25', 'FAIL ER10']], ignore = True, timeout = 10)
        try:
            result = True if res[0]['COMMAND'] == 'EVENT 25' else False
            return result
        except:     # IndexErrorが発生するときのための暫定処理。要検討
            result = False

            
    def pac_terminate(self):
        """PANAセッションを終了する"""
        res = self.write(b'SKTERM\r\n', [['OK', 'FAIL ER10']], ignore = True, timeout = 10)
        if res[0]['COMMAND'] == 'OK':
            return True
        else:
            return False
        

    def get_ip6(self, add):
        """IP6アドレス習得"""
        res = self.write(b'SKLL64 ' + add.encode() + b'\r\n', ['UNKNOWN'])
        return res[0]['MESSAGE'][0]


    def tcp_connect(self, ip6, rport, lport):
        """TCPコネクション開始"""
        br = ' {:04X}'.format(rport).encode()
        bl = ' {:04X}'.format(lport).encode()
        res = self.write(b'SKCONNECT ' + ip6.encode() + br + bl + b'\r\n', ['ETCP'])
        return res[0]


    def tcp_disconnect(self, handle):
        """TCPコネクション停止"""
        res = self.write(b'SKCLOSE ' + str(handle).encode() + b'\r\n', ['ETCP'])
        return res[0]['STATUS'] == 3


    def tcp_send(self, handle, message):
        """TCPで送信"""
        len_bt =' {:04X} '.format(len(message)).encode()         
        res = self.write(b'SKSEND ' + str(handle).encode() + len_bt + message, ['ETCP'])
        return res[0]['STATUS'] == 5


    def udp_send(self, handle, ip6, security, port, message):
        """UDPで送信"""
        sec_bt = b' 1' if security else b' 0'
        len_bt = ' {:04X} '.format(len(message)).encode()
        port_bt = ' {:04X}'.format(port).encode()
        res = self.write(b'SKSENDTO ' + str(handle).encode() + b' ' + ip6.encode() + port_bt + 
                         sec_bt + len_bt + message, ['EVENT 21', 'OK'])

        if res[0]['PARAM'] == '01':
            sys.stdout.write('[Error]: UDP transmission.\n')
            if self.get_tx_limit():
                sys.stdout.write('[Error]: TX limit.\n')
            return False
        else:
            return True     # 送信成功


    def ed_scan(self, duration = 4):
        """EDスキャン"""
        bd = '{:X}'.format(duration).encode()
        self.write(b'SKSCAN 0 FFFFFFFF ' + bd + b'\r\n', [['EEDSCAN'], ['OK']])
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


    def active_scan(self, duration = 6):
        """アクティブスキャン"""
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


    @staticmethod
    def parse_message(msg):
        """受信メッセージのパーサー"""
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


    @staticmethod
    def decode(ascii_str):
        """文字列(Ascii Hex)をデコードする
            例 '616263' -> 'abc'
        """
        return bytes.fromhex(ascii_str).decode()


    def enqueue_message(self, msg_list):
        """メッセージをリストに追加"""
        self.msg_list_lock.acquire()
        self.msg_list_queue.append(msg_list)
        self.msg_list_lock.release()


    def dequeue_message(self):
        """メッセージをリストから取り出す"""
        self.msg_list_lock.acquire()
        
        if self.msg_list_queue:
            result = self.msg_list_queue.pop(0)
        else:
            result = False
            
        self.msg_list_lock.release()
        
        return result
            

    def get_queue_size(self):
        """リスト内のメッセージ数"""
        return len(self.msg_list_queue)


    def uart_open(self, dev, baud, timeout):
        """UARTオープン"""
        try:
            self.uart_hdl = serial.Serial(dev, baud, timeout=timeout)
            self.uart_dev = dev
            self.uart_baud = baud
            return True
        except OSError as msg:
            sys.stdout.write('[Error]: {}\n'.format(msg))
            return False


    def uart_close(self):
        """UARTクローズ"""
        try:
            self.uart_hdl.close()
        except OSError as msg:
            sys.stdout.write('[Error]: {}\n'.format(msg))


    def write(self, send_msg, search_words = [], ignore = False, timeout = 0):
        """UART書き込み & 受信待ち
            send_msg: 送信データ: bytes
            search_word: 受信待ちコマンド
                (例) ['word1', 'word2', ['word31', 'word32']]: 'word1 -> 'word2' -> 'word31' or 'word32'
            ignore: 途中の受信データを無視する
            timeout: タイムアウト時間[s]
        """
        try:
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
            sys.stdout.write('[Error]: {}\n'.format(msg))
            return False


    def read(self):
        """1行読み込み（文字列)"""
        try:
            res = self.uart_hdl.readline().decode().strip()
            #print('read:'+res)   # debug
            return res
        except OSError as msg:
            sys.stdout.write('[Error]: {}\n'.format(msg))
            return False


    def run(self):
        """UART受信用スレッド"""
        while not self.term_flag:
            msg = self.read()
            if msg:
                msg_list = self.parse_message(msg)

                # debug: UDP(PANA)の受信
                if msg_list['COMMAND'] == 'ERXUDP' and msg_list['LPORT'] == self.Y3_UDP_PANA_PORT:
                    #sys.stdout.write('[Note]: PANA message received.\n')
                    pass
               
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


    def terminate(self):
        """run()の停止"""
        self.term_flag = True
        self.join()
