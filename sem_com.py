#!/usr/bin/python3
# coding: UTF-8

import time
import datetime
import os
import shutil
import glob
import sys
import threading
import socket
import json
from pprint import pprint

import RPi.GPIO as gpio
from y3module import Y3Module
from echonet_lite import *
import user_conf

#import pdb     # debug
#pdb_flag = False


# 定数定義
Y3RESET_GPIO = 18   # Wi-SUNリセット用GPIO
LED_GPIO = 4        # LED用GPIO

SOCK_FILE = '/tmp/sem.sock'     # UNIXソケット
TMP_LOG_FILE = '/tmp/sem.csv'   # 一時ログファイル名
ERR_LOG_FILE = 'sem_err.log'    # エラー記録ファイル

POW_DAY_LOG_DIR = 'sem_app/public/sem_log'  # ログ用ディレクトリ, 本スクリプトからの相対パス
POW_DAY_LOG_HEAD = 'pow_day_'   # 日別ログファイル名の先頭
POW_DAY_LOG_FMT = '%Y%m%d'      #        日時フォーマット


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
    time.sleep(0.5)
    gpio.output(Y3RESET_GPIO, gpio.HIGH)
    time.sleep(2.0)


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
               
                # スマートメーターが自発的に発するプロパティ通知
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
    tid_counter = tid_counter + 1 if tid_counter + 1 != 65536 else 0  # TICカウントアップ
    frame = sem.change_tid_frame(tid_counter, frame)
    res = y3.udp_send(1, ip6, True, y3.Y3_UDP_ECHONET_PORT, frame)


# 電力ログファイル初期設定
def pow_logfile_init(dt, logdir):    
    # 一時ファイル初期化
    f = open(TMP_LOG_FILE , 'w')
    f.close()

    if os.path.isdir(logdir) and os.access(logdir, os.W_OK):    # ログ用ディレクトリ確認
        os.chdir(logdir)
        
        day_file_list = []        
        for i in range(10):     # 10日分の電力ログ
            dt_str = (dt - datetime.timedelta(days = i)).strftime(POW_DAY_LOG_FMT)
            filename = POW_DAY_LOG＿HEAD + dt_str + '.csv'
            day_file_list.append(filename)

            if not os.path.exists(filename):    # 電力ログが存在しなければ作成する
                fp = open(filename, 'w')
                fp.write('timestamp,power\n')
                fp.close()

        file_list = glob.glob(POW_DAY_LOG_HEAD + '*.csv')   # 電力ログ検索
        for f in file_list:
            if f in day_file_list:
                continue
            else:
                os.remove(f)    # 古い電力ログとリンクファイルを削除

        for i in range(10):     # 電力ログへのシンボリックリンクを作成
            link_file = POW_DAY_LOG_HEAD + str(i) + '.csv'
            os.system('ln -s ' + day_file_list[i] + ' ' + link_file)
            
        return True

    else:   # エラー（ディレクトリが存在しない、書き込み不可）
        return False


# 電力ログファイル更新
def pow_logfile_maintainance(last_dt, new_dt, logdir):
    os.chdir(logdir)
    
    # 電力ログ更新
    if last_dt.minute != new_dt.minute and new_dt.minute % 10 == 0: # 10分毎
        today_file = POW_DAY_LOG_HEAD + last_dt.strftime(POW_DAY_LOG_FMT) + '.csv'
        file_cat(today_file, TMP_LOG_FILE)
        os.remove(TMP_LOG_FILE)         # 一時ログファイルを削除
        
        if last_dt.day != new_dt.day:   # 日付変更
            pow_logfile_init(new_dt, logdir)    # 電力ログ初期化


# ファイルを連結する
def file_cat(file_a, file_b):
    try:
        fp_a = open(file_a, 'ab')
        fp_b = open(file_b, 'rb')
        fp_a.write(fp_b.read())
        fp_a.close()
        fp_b.close()
        return True
    except:
        return False
        
        
# debug: エラーを記録する
def debug_err_record(err_file, errmsg, data):
    js = json.dumps([errmsg, round(time.time()), data]) + '\n'
    f = open(err_file, 'a')
    f.write(js)
    f.close()


# start
if __name__ == '__main__':
    logdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), POW_DAY_LOG_DIR)
    err_file = os.path.join(logdir, ERR_LOG_FILE)
    
    saved_dt = datetime.datetime.now()    # 現在日時を保存

    sem_inf_list = []       # スマートメータのプロパティ通知用
    tid_counter = 0

    result = pow_logfile_init(saved_dt, logdir)    # ログファイル初期化
    if not result:
        sys.stderr.write('[Error]: log file error\n')
        sys.exit(-1)

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
        
        # 参考までに取得（ECHONET Liteを参照すること）
        #pprint(sem_get_getres('get_pty_map'))   # Get プロパティマップ
        #pprint(sem_get_getres('set_pty_map'))   # Set プロパティマップ
        #pprint(sem_get_getres('chg_pty_map'))   # 状態変化 プロパティマップ
        #print('Operation status: ', sem_get_getres('operation_status'))     # 動作状態
        #print('     Coefficient: ', sem_get_getres('epc_coefficient'))      # 係数
        #print('           Digit: ', sem_get_getres('digits'))               # 有効桁数
        #print('  Unit of energy: ', sem_get_getres('unit_amount_energy'))   # 単位

        start = time.time()-1000  # 初期値を1000s前に設定
        while True:
            try:
                now = time.time()
                while True:
                    if (time.time() - start) >= user_conf.SEM_INTERVAL:
                        start = time.time()
                        break
                    else:
                        time.sleep(0.1)
                                     
                sem_get('instant_power')
                
                while True:
                    if y3.get_queue_size():
                        msg_list = y3.dequeue_message()
                        if msg_list['COMMAND'] == 'ERXUDP':
                            led.oneshot()
                            parsed_data = sem.parse_frame(msg_list['DATA'])
                            
                            if parsed_data:
                                if parsed_data['tid'] != tid_counter:
                                    errmsg = '[Error]: ECHONET Lite TID mismatch\n'
                                    sys.stderr.write(errmsg)
                                    debug_err_record(err_file, errmsg, msg_list);
                                    
                                else:
                                    watt_int = int.from_bytes(parsed_data['ptys'][0]['edt'], 'big', signed=True)
                                    rcd_time = time.time()      # rcd_time[s]
                                    new_dt = datetime.datetime.fromtimestamp(rcd_time)

                                    # ログファイルメンテナンス
                                    pow_logfile_maintainance(saved_dt, new_dt, logdir)
                                    saved_dt = new_dt

                                    sys.stderr.write('[{:5d}] {:4d} W\n'.format(tid_counter, watt_int))
                            
                                    try:    # 一時ログファイルに書き込み
                                        f = open(TMP_LOG_FILE, 'a')        # rcd_time[ms] (JavaScript用)
                                        f.write('{},{}\n'.format(round(rcd_time * 1000), watt_int));
                                        f.close()
                                    except:
                                        sys.stderr.write('[Error]: can not write to file.\n')
                            
                                    if (sock):  # UNIXドメインソケットで送信
                                        sock_data = json.dumps({'time': rcd_time, 'power': watt_int}).encode('utf-8');
                                        try:
                                            sock.send(sock_data)
                                        except:
                                            sys.stderr.write('[Error]: Broken socket.\n')
                                    break
                            
                            else:   # 電文が壊れている
                                errmsg = '[Error]: ECHONET Lite frame error\n'
                                sys.stderr.write(errmsg);
                                debug_err_record(err_file, errmsg, msg_list);
                            
                        else:   # 電文が壊れている???
                            errmsg = '[Error]: Unknown data received.\n'
                            sys.stderr.write(errmsg)
                            debug_err_record(err_file, errmsg, msg_list);

                    else:   # GetRes待ち
                        while sem_inf_list:
                            pprint(sem_inf_list[0]) # Inf(30分計量値等)をキャッチしたときに表示する
                            sem_inf_list.pop(0)
                        
                        if time.time() - start > 20:    # GetRes最大待ち時間: 20s
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
    
    if os.path.exists(TMP_LOG_FILE):
        os.remove(TMP_LOG_FILE)

    sys.stderr.write('Bye.\n')
    sys.exit(0)
