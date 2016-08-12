#!/usr/bin/python3
# coding: UTF-8

import time
import sys
import threading
import socket
from pprint import pprint


import RPi.GPIO as gpio
from y3module import Y3Module
from echonet_lite import *
import user_conf


#import pdb     # debug
#pdb_flag = False


Y3RESET_GPIO = 18   # Wi-SUNリセット用GPIO
LED_GPIO = 4        # LED用GPIO

SOCK_FILE = '/tmp/sem.sock'     # UNIXソケット


# GPIO初期化
def gpio_init():
    gpio.setwarnings(False)
    gpio.setmode(gpio.BCM)

    gpio.setup(Y3RESET_GPIO, gpio.OUT)
    gpio.setup(LED_GPIO, gpio.OUT)

    gpio.output(Y3RESET_GPIO, gpio.HIGH)
    time.sleep(0.1)

    gpio.output(LED_GPIO, gpio.LOW)


# LEDを点滅させるスレッド
class LedThread(threading.Thread):
    def __init__(self):
        super().__init__()
        self._trigger = False
        self._termFlag = False

    def run(self):
        while not self._termFlag:
            if self._trigger:
                self.ledon(True)
                time.sleep(0.1)
                self.ledon(False)
                self._trigger = False
            else:
                time.sleep(0.1)

    @staticmethod
    def ledon(ctl):
        if ctl:
            gpio.output(LED_GPIO, gpio.HIGH)
        else:
            gpio.output(LED_GPIO, gpio.LOW)

    def oneshot(self):
        self._trigger = True

    def terminate(self):
        self._termFlag = True
        self.join()


# Wi-Sunモジュールのリセット
def y3reset():
    gpio.output(Y3RESET_GPIO, gpio.LOW)    # high -> low -> high
    time.sleep(0.1)
    gpio.output(Y3RESET_GPIO, gpio.HIGH)
    time.sleep(1.0)


# Y3Module()のサブクラス
class Y3ModuleSub(Y3Module):
    global sem_inf_list
    
    def __init__(self):
        super().__init__()
        self.EHD = '1081'
        self.ECV_INF = '73'   # ECHONET ECVコード　（INF)
    
    # UART受信スレッドrun()をECHONET Lite電文用に拡張
    #   UART受信用スレッド
    def run(self):
        while not self.term_flag:
            msg = self.read()
            if msg:
                msg_list = self.parse_message(msg)

                # debug: UDP(PANA)の受信データを保存する
                if msg_list['COMMAND'] == 'ERXUDP' and msg_list['LPORT'] == self.Y3_UDP_PANA_PORT:
                    self.msg_list_pana_queue.append(msg_list)
               
                # サマーとメーターが自発的に発するプロパティ通知
                if msg_list['COMMAND'] == 'ERXUDP' and msg_list['DATA'][0:4] == self.EHD \
                   and msg_list['DATA'][20:22] == self.ECV_INF:
                        sem_inf_list.append(msg_list)

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


# プロパティ値要求 'Get', 'GetRes'受信
#   tid: トランザクションID
#   epc: EHONET Liteプロパティ
def sem_get_getres(epc):
    sem_get(epc)    # 'Get'送信
    start = time.time()
    
    while True:
        if y3.get_queue_size():     # データ受信
            msg_list = y3.dequeue_message() # 受信データ取り出し
            if msg_list['COMMAND'] == 'ERXUDP':
                return msg_list['DATA']
            else:
                sys.stderr.write('[Error]: Unknown data received.\n')
                return False

        else:   # データ未受信
            if time.time() - start > 20:    # タイムアウト 20s
                sys.stderr.write('[Error]: Time out.\n')
                break
            time.sleep(0.01)


# プロパティ値要求 'Get'
def sem_get(epc):
    global tid_counter
    
    frame = sem.FRAME_DICT['get_' + epc]

    res = False
    while not res:  # UDP送信が成功する(res==True)まで再送信する
        tid_counter = tid_counter + 1 if tid_counter + 1 != 65536 else 0  # TICカウントアップ
        frame = sem.change_tid_frame(tid_counter, frame)
        res = y3.udp_send(1, ip6, True, y3.Y3_UDP_ECHONET_PORT, frame)


# start
if __name__ == '__main__':
    sem_inf_list = []       # スマートメータのプロパティ通知用
    tid_counter = 0

    gpio_init()

    led = LedThread()
    led.start()
    led.oneshot()

    y3 = Y3ModuleSub()
    y3.uart_open(dev='/dev/ttyAMA0', baud=115200, timeout=1)
    y3.start()
    sys.stderr.write('Wi-SUN reset...\n')
    
    y3reset()
    y3.set_echoback_off()
    y3.set_opt(True)
    y3.set_password(user_conf.SEM_PASSWORD)
    y3.set_routeb_id(user_conf.SEM_ROUTEB_ID)

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(SOCK_FILE)
    except:
        sock = None

    channel_list = []
    sem_exist = False

    for i in range(10):
        sys.stderr.write('({}/10) Active scan start with a duration of {}...\n'.format(i+1, user_conf.SEM_DURATION))
        channel_list = y3.active_scan(user_conf.SEM_DURATION)
        if channel_list is False:   # active_scan()をCtrl+cで終了したとき
            break
        if channel_list:
            sem_exist = True
            break
    
    if not sem_exist:   # スキャン失敗
        sys.stderr.write('[Error]: Can not connect to a smart energy meter\n')

    if sem_exist:
        ch = channel_list[0]

        sys.stderr.write('Energy Meter: [Ch.0x{:02X}, Addr.{}, LQI.{}, PAN.0x{:04X}]\n'.format(ch['Channel'],
                         ch['Addr'], ch['LQI'], ch['Pan ID']))

        # チャンネル設定
        y3.set_channel(ch['Channel'])
        sys.stderr.write('Set channel to 0x{:02X}\n'.format(ch['Channel']))

        # スマートメータのIP6アドレス
        ip6 = y3.get_ip6(ch['Addr'])
        sys.stderr.write('IP6 address is \'{}\'\n'.format(ip6))

        # PAN ID
        y3.set_pan_id(ch['Pan ID'])
        sys.stderr.write('Set PAN ID to 0x{:04X}\n'.format(ch['Pan ID']))

        # PANA認証(PaC)
        sem_exist = False
        for i in range(10):       
            sys.stderr.write('({}/10) PANA connection...\n'.format(i+1))
            sem_exist = y3.start_pac(ip6)
            if sem_exist:
                sys.stderr.write('Done.\n')
                time.sleep(3)
                break
            
        # debug: PANA認証時の受信データを表示        
        #while y3.msg_list_pana_queue:
        #    pprint(y3.msg_list_pana_queue[0])
        #    y3.msg_list_pana_queue.pop(0)

    if sem_exist:
        sem = EchonetLiteSmartEnergyMeter()
        
        pprint(sem_get_getres('get_pty_map'))        
        pprint(sem_get_getres('set_pty_map'))        
        pprint(sem_get_getres('chg_pty_map'))

        print('Operation status: ', sem_get_getres('operation_status'))
        print('     Coefficient: ', sem_get_getres('epc_coefficient'))
        print('           Digit: ', sem_get_getres('digits'))
        print('  Unit of energy: ', sem_get_getres('unit_amount_energy'))

        while True:
            try:
                start = time.time()
                sem_get('instant_power')
                
                while True:
                    if y3.get_queue_size():
                        msg_list = y3.dequeue_message()
                        size = y3.get_queue_size()
                        if msg_list['COMMAND'] == 'ERXUDP':
                            led.oneshot()
                            data = msg_list['DATA']
                            watt_int = int.from_bytes(bytes.fromhex(msg_list['DATA'][28:36]), 'big')
                            sys.stderr.write('[{:5d}] {:4d} W\n'.format(tid_counter, watt_int))
                            if (sock):
                                watt_bytes = str(watt_int).encode('utf-8')
                                try:
                                    sock.send(watt_bytes)
                                except:
                                    sys.stderr.write('[Error]: Broken socket.\n')
                            break
                        else:
                            sys.stderr.write('[Error]: Unknown data received.\n{}'.format(msg_list))

                    else:
                        # debug                        
                        while sem_inf_list:
                            pprint(sem_inf_list[0])
                            sem_inf_list.pop(0)
                        
                        if time.time() - start > 20:    # タイムアウト 20s
                            sys.stderr.write('[Error]: Time out.\n')
                            break
                        time.sleep(0.1)

            except KeyboardInterrupt:
                break

    else:
        sys.stderr.write('[Error]: Can not connect with a smart energy meter.\n')

    # 終了処理
    if (sock):
        try:
            sock.close()
        except:
            sys.stderr.write('[Error]: Broken socket.\n')

    sys.stderr.write('\nWi-SUN reset...\n')
    y3reset()
    y3.terminate()
    y3.uart_close()
    led.terminate()
    gpio.cleanup()

    sys.stderr.write('Bye.\n')
    sys.exit(0)
