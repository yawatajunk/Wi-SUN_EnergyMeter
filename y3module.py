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


class Y3Module(threading.Thread):
    # port Numbers
    Y3_UDP_ECHONET_PORT = 3610  # ECHONET UDPポート
    Y3_UDP_PANA_PORT = 716      # PANAポート
    Y3_TCP_PORT = 3610          # TCPポート

    # UARTデフォルト設定
    uart_dev = '/dev/ttyAMA0'
    uart_baud = 115200
    uart_timeout = 1            # 1s
    uart_hdl = None             # ハンドラ

    msg_list_queue = []         # 受信データ用リスト

    term_flag = False           # 別スレッドrun()の終了フラグ

    # ERXUDP, ERXTCPのフォーマット, True: ASCII， False: Binary
    def set_opt(self, flag):
        current = self.get_opt()

        if flag and not current:        # 変更無しの場合はモジュールに書き込まない（FLASHの書き込み制限）
            self.writeline('WOPT 01', True)
            self.wait_message('OK')
        elif not flag and current:
            self.writeline('WOPT 00', True)
            self.wait_message('OK')
        return True

    def get_opt(self):
        self.writeline('ROPT', True)
        res = self.wait_message('OK')
        return True if res['MESSAGE'][0] == '01' else False

    # エコーバック
    def set_echoback(self, flag):
        b = '1' if flag else '0'
        self.writeline('SKSREG SFE ' + b, True)
        self.wait_message('OK')

    # Wi-Sunチャンネル
    def set_channel(self, ch):
        self.writeline('SKSREG S02 {:02X}'.format(ch), True)
        self.wait_message('OK')

    # ペアリングID
    def set_pairing_id(self, pairid):
        self.writeline('SKSREG S0A ' + pairid, True)
        self.wait_message('OK')

    # PAN ID
    def set_pan_id(self, pan):
        self.writeline('SKSREG S03 {:04X}'.format(pan), True)
        self.wait_message('OK')

    # ビーコンへの反応
    def set_accept_beacon(self, flag):
        b = '1' if flag else '0'
        self.writeline('SKSREG S15 ' + b, True)
        self.wait_message('OK')

    # パスワード
    def set_password(self, password):
        length = len(password)
        if length < 1 or length > 32:
            result = False
        else:
            self.writeline('SKSETPWD {:X} {}'.format(length, password), True)
            self.wait_message('OK')
            result = True
        return result

    # ルートB ID
    def set_routeb_id(self, rbid):
        if len(rbid) != 32:
            result = False
        else:
            self.writeline('SKSETRBID ' + rbid, True)
            self.wait_message('OK')
            result = True
        return result

    # PAA開始
    def start_paa(self):
        self.writeline('SKSTART', True)
        self.wait_message('OK')

    # PaC開始
    def start_pac(self, ip6):
        self.writeline('SKJOIN ' + ip6, True)
        self.wait_message('OK')

    # IP6アドレス
    def get_ip6(self, add):
        self.writeline('SKLL64 ' + add, True)
        res = self.wait_message('UNKNOWN')
        return res['MESSAGE'][0]

    # TCPコネクション開始
    def tcp_connect(self, ip6, rport, lport):
        rport_str = ' {:04X}'.format(rport)
        lport_str = ' {:04X}'.format(lport)
        self.writeline('SKCONNECT ' + ip6 + rport_str + lport_str, True)
        res = self.wait_message('ETCP')
        return res

    # TCPコネクション停止
    def tcp_disconnect(self, handle):
        self.writeline('SKCLOSE ' + str(handle), True)
        fin_flag = False
        while not fin_flag:
            res = self.wait_message('ETCP')
            if res['STATUS'] == 3:
                fin_flag = True

    # TCPで送信
    def tcp_send(self, handle, message):
        length = len(message)
        self.writeline('SKSEND ' + str(handle) + ' {:04X} {}'.format(length, message), False)
        res = self.wait_message('ETCP')
        return res['STATUS'] == 5

    # UDPで送信
    def udp_send(self, handle, ip6, security, port, message):
        sec_str = ' 1' if security else ' 0'
        len_str = ' {:04X} '.format(len(message))
        port_str = ' {:04X}'.format(port)
        self.writeline('SKSENDTO ' + str(handle) + ' ' + ip6 + port_str + sec_str + len_str + message, False)
        fin_flag = False
        while not fin_flag:
            res = self.wait_message('EVENT')
            if res['NUM'] == 0x21:
                fin_flag = True
        self.wait_message('OK')

    # EDスキャン
    def ed_scan(self):
        self.writeline('SKSCAN 0 FFFFFFFF 4', True)
        self.wait_message('EEDSCAN')
        fin_flag = False
        res = []
        while not fin_flag:
            if self.get_queue_size():
                msg = self.dequeue_message()
                res = msg['MESSAGE']
                fin_flag = True
            else:
                time.sleep(0.01)

        lqi_list = []
        for i in range(0, len(res), 2):
            lqi_list.append([int(res[i + 1], base=16), int(res[i], base=16)])  # [[LQI, channel], [LQI, channel],....]
            lqi_list.sort()  # sort by LQI

        return [lqi_list[0][1], lqi_list[0][0]]  # minimum LQI channel

    # アクティブスキャン
    def active_scan(self):
        self.writeline('SKSCAN 2 FFFFFFFF 6', True)
        scan_end = False
        channel_list = []
        channel = {}

        while not scan_end:
            if self.get_queue_size():
                msg_list = self.dequeue_message()
                if msg_list['COMMAND'] == 'EVENT' and msg_list['NUM'] == 0x20:
                    pass    # beacon received
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
                elif msg_list['COMMAND'] == 'EVENT' and msg_list['NUM'] == 0x22:
                    scan_end = True
            else:
                time.sleep(0.01)
        return channel_list

    # UART関係
    def set_uart_baud(self, baud):
        self.uart_baud = baud

    def get_uart_baud(self):
        return self.uart_baud

    def set_uart_dev(self, dev):
        self.uart_dev = dev

    def get_uart_dev(self):
        return self.uart_dev

    def set_uart_timeout(self, timeout):
        self.uart_timeout = timeout

    def get_uart_timeout(self):
        return self.uart_timeout

    # UARTオープン
    def uart_open(self, dev=uart_dev, baud=uart_baud, timeout=uart_timeout):
        self.uart_hdl = serial.Serial(dev, baud, timeout=timeout)

    # UARTクローズ
    def uart_close(self):
        self.uart_hdl.close()

    # 1行書き込み
    def writeline(self, msg_str, crlf):
        lineend = '\r\n' if crlf == True else ''
        self.uart_hdl.write(bytes(msg_str + lineend, 'UTF-8'))

    # 1行読み込み
    def readline(self):
        return self.uart_hdl.readline().decode('UTF-8').strip()

    # メッセージの受信待ち
    def wait_message(self, message):
        fin = False
        msg_list = []
        while not fin:
            if self.get_queue_size():
                msg_list = self.dequeue_message()
                if msg_list['COMMAND'] == message:
                    fin = True
            else:
                time.sleep(0.01)
        return msg_list

    # 受信メッセージの判別処理
    @staticmethod
    def parse_message(msg):
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
            msg_list['COMMAND'] = cols[0]
            msg_list['NUM'] = int(cols[1], base=16)
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

        msg_list['COMMAND'] = 'UNKNOWN'  # unknown message
        msg_list['MESSAGE'] = cols
        return msg_list

    # ASCII文字コード（Hex）を文字列に変換
    @staticmethod
    def ascii_hex_to_str(ascii_str):
        str = ''
        for i in range(0, int(len(ascii_str) / 2)):
            str += chr(int(ascii_str[2 * i:2 * (i + 1)], base=16))
        return str

    # メッセージをリストに追加
    def enqueue_message(self, msg_list):
        #print(msg_list)     # debug
        self.msg_list_queue.append(msg_list)

    # メッセージをリストから取り出す
    def dequeue_message(self):
        if self.msg_list_queue:
            return self.msg_list_queue.pop(0)
        else:
            return {}

    # リスト内のメッセージ数
    def get_queue_size(self):
        return len(self.msg_list_queue)

    #  メッセージ受信用スレッド
    def run(self):
        while not self.term_flag:
            msg = self.readline()
            if msg:
                msg_list = self.parse_message(msg)
                self.enqueue_message(msg_list)
            else:       # timeout
                pass    # do nothing

    # run()の停止
    def terminate(self):
        self.term_flag = True
        self.join()
