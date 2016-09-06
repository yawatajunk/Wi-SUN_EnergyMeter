#!/usr/bin/python3
# coding: UTF-8

import datetime
import glob
import json
import threading
import time
import os
import pickle
import socket
import sys

import RPi.GPIO as gpio
from y3module import Y3Module
from echonet_lite import *
import user_conf


# 定数定義
Y3RESET_GPIO = 18   # Wi-SUNリセット用GPIO
LED_GPIO = 4        # LED用GPIO

# ログファイル関連
TMP_LOG_DIR = '/tmp/'               # 一次ログディレクトリ
LOG_DIR = 'sem_app/public/logs/'    # ログ用ディレクトリ, 本スクリプトからの相対パス
SOCK_FILE = TMP_LOG_DIR + 'sem.sock'    # UNIXソケット
TMP_LOG_FILE = TMP_LOG_DIR + 'sem.csv'  # 一時ログファイル
POW_DAYS_JSON_FILE = LOG_DIR + 'pow_days.json'  # JSON形式の電力ログファイル

POW_DAY_LOG_HEAD = 'pow_day_'   # 日別ログファイル名の先頭
POW_DAY_LOG_FMT = '%Y%m%d'      #        日時フォーマット


def gpio_init():
    """GPIO初期化"""
    gpio.setwarnings(False)
    gpio.setmode(gpio.BCM)

    gpio.setup(Y3RESET_GPIO, gpio.OUT)
    gpio.setup(LED_GPIO, gpio.OUT)

    gpio.output(Y3RESET_GPIO, gpio.HIGH)
    time.sleep(0.1)

    gpio.output(LED_GPIO, gpio.LOW)


class LedThread(threading.Thread):
    """LEDを点滅させるスレッド"""
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


def y3reset():
    """Wi-Sunモジュールのリセット"""
    gpio.output(Y3RESET_GPIO, gpio.LOW)    # high -> low -> high
    time.sleep(0.5)
    gpio.output(Y3RESET_GPIO, gpio.HIGH)
    time.sleep(2.0)


class Y3ModuleSub(Y3Module):
    """Y3Module()のサブクラス"""
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

                # debug: UDP(PANA)の受信
                if msg_list['COMMAND'] == 'ERXUDP' and msg_list['LPORT'] == self.Y3_UDP_PANA_PORT:
                    sys.stdout.write('[PANA]: {}\n'.format(msg_list['DATA']))

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


def sem_get_getres(epc):
    """プロパティ値要求 'Get', 'GetRes'受信
        epc: EHONET Liteプロパティ
    """
    sem_get(epc)    # 'Get'送信
    start = time.time()
    
    while True:
        if y3.get_queue_size():     # データ受信
            msg_list = y3.dequeue_message() # 受信データ取り出し
            if msg_list['COMMAND'] == 'ERXUDP':
                return msg_list['DATA']
            else:
                sys.stdout.write('[Error]: Unknown data received.\n')
                return False

        else:   # データ未受信
            if time.time() - start > 20:    # タイムアウト 20s
                sys.stdout.write('[Error]: Time out.\n')
                return False
            time.sleep(0.01)


def sem_get(epc):
    """プロパティ値要求 'Get' """
    global tid_counter
    
    frame = sem.FRAME_DICT['get_' + epc]
    tid_counter = tid_counter + 1 if tid_counter + 1 != 65536 else 0  # TICカウントアップ
    frame = sem.change_tid_frame(tid_counter, frame)
    res = y3.udp_send(1, ip6, True, y3.Y3_UDP_ECHONET_PORT, frame)


def pow_logfile_init(dt):
    """電力ログファイル初期設定"""
    f = open(TMP_LOG_FILE , 'w')    # 一時ログ初期化
    f.close()

    if not (os.path.isdir(LOG_DIR) and os.access(LOG_DIR, os.W_OK)):    # ログ用ディレクトリ確認
        return False
        
    csv_day_files = []  # 10日分のログファイルリスト(CSV)
    pkl_day_files = []  #                       (pickle)
    
    for i in range(10):     # 10日分の電力ログ作成
        t = dt - datetime.timedelta(days = i)   # 対象日のdatetime
        
        # ログファイル名
        dt_str = t.strftime(POW_DAY_LOG_FMT)
        csv_filename = LOG_DIR + POW_DAY_LOG_HEAD + dt_str + '.csv'
        pkl_filename = TMP_LOG_DIR + POW_DAY_LOG_HEAD + dt_str + '.pickle'
        
        csv_day_files.append(csv_filename)
        pkl_day_files.append(pkl_filename)
        
        if not os.path.exists(csv_filename):    # 電力ログ(CSV)が無かったら作成する
            try:
                fcsv = open(csv_filename, 'w')
                fcsv.close()
            except:
                return False
        
        if not os.path.exists(pkl_filename):    # 電力ログ(pickle)が無かったら作成する
            result = csv2pickle(csv_filename, pkl_filename)
            if not result:
                return False       

    files = glob.glob(LOG_DIR + POW_DAY_LOG_HEAD + '*.csv')         # 電力ログ(CSV)検索
    for f in files:
        if f in csv_day_files:
            continue
        else:
            os.remove(f)    # 古い電力ログ(CSV)を削除

    files = glob.glob(TMP_LOG_DIR + POW_DAY_LOG_HEAD + '*.pickle')  # 電力ログ(pickle)検索
    for f in files:
        if f in pkl_day_files:
            continue
        else:
            os.remove(f)    # 古い電力ログ(pickle)を削除

    # CSVファイルをJSONファイルに変換
    pickle2json(sorted(pkl_day_files), POW_DAYS_JSON_FILE)
    
    return True


def pow_logfile_maintainance(last_dt, new_dt):
    """電力ログファイル更新"""    
    if last_dt.minute != new_dt.minute and new_dt.minute % 10 == 0: # 10分毎
        dt_str = last_dt.strftime(POW_DAY_LOG_FMT)

        today_csv_file = LOG_DIR + POW_DAY_LOG_HEAD + dt_str + '.csv'
        today_pkl_file = TMP_LOG_DIR + POW_DAY_LOG_HEAD + dt_str + '.pickle'
        
        file_cat(today_csv_file, TMP_LOG_FILE)
        os.remove(TMP_LOG_FILE)         # 一時ログファイルを削除
        
        csv2pickle(today_csv_file, today_pkl_file)  # pickle更新

        if last_dt.day != new_dt.day:   # 日付変更
            pow_logfile_init(new_dt)    # 電力ログ初期化

        else:
            pkl_day_files = glob.glob(TMP_LOG_DIR + POW_DAY_LOG_HEAD + '*.pickle')   # 電力ログ(pickle)検索
            pickle2json(sorted(pkl_day_files), POW_DAYS_JSON_FILE)     # CSVファイルをJSONファイルに変換


def file_cat(file_a, file_b):
    """ファイルを連結する"""
    try:
        fp_a = open(file_a, 'ab')
        fp_b = open(file_b, 'rb')
        fp_a.write(fp_b.read())
        fp_a.close()
        fp_b.close()
        return True
    except:
        return False


def csv2pickle(csvfile, pklfile):
    """csvファイルをpickleファイルに変換"""
    try:
        fcsv = open(csvfile, 'r')
        fpkl = open(pklfile, 'wb')
        data = fcsv.readlines()
    except:
        return False
        
    if data == []:      # 日付変更時でcsvファイルが空の場合
        dt = datetime.date.today()    # 現時刻から、0時0分のタイムスタンプを作成
        ts_origin = datetime.datetime.combine(dt, datetime.time(0, 0)).timestamp()
    else:
        ts = int(data[0].strip().split(',')[0])     # ログからタイムスタンプを取得
        dt = datetime.datetime.fromtimestamp(ts)    # 0時0分のタイムスタンプを作成
        ts_origin = datetime.datetime(dt.year, dt.month, dt.day).timestamp()

    data_work = [[None, []] for row in range(60 * 24)]  # 作業用空箱
    
    for minute in range(60 * 24):
        data_work[minute][0] = ts_origin + 60 * minute  # 1分刻みのタイムスタンプを設定

    for row in data:
        row_list = row.strip().split(',')   # [タイムスタンプ(s), 電力]
        minute = int((int(row_list[0]) - ts_origin) / 60)   # 00:00からの経過時間[分]
        if row_list[1] != 'None':
            data_work[minute][1].append(int(row_list[1]))   # 電力を追加

    data_summary = [[None, None] for row in range(60 * 24)] # 集計用空箱
    for minute, data in enumerate(data_work):
        data_summary[minute][0] = data[0]
        if len(data[1]):
            data_summary[minute][1] = round(sum(data[1]) / len(data[1]))    # 電力平均値
    
    pickle.dump(data_summary, fpkl)
    
    fcsv.close()
    fpkl.close()

    return True


def pickle2json(pklfiles, jsonfile):
    """pickleファイルをJSONファイルに変換する"""
    data = []
    for fpkl in pklfiles:
        try:
            f = open(fpkl, 'rb')
            d = pickle.load(f)
            data = data + d
        except:
            return False

    json_data = []        
    for row in data:
        row = [int(row[0])*1000, None if row[1] is None else int(row[1])]
        json_data.append(row)
            
    s = json.dumps(json_data)
    
    try:
        f = open(jsonfile, 'w')
        f.write(s)
        f.close()
        return True
    except:
        return False


if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
        
    sem_inf_list = []       # スマートメータのプロパティ通知用
    tid_counter = 0         # TIDカウンタ
    
    pana_ts = 0.0           # PANA認証時のタイムスタンプを記録
    saved_dt = datetime.datetime.now()      # 現在日時を保存
    
    sys.stdout.write('Log files setup...\n')
    result = pow_logfile_init(saved_dt)     # ログファイル初期化

    if not result:
        sys.stdout.write('[Error]: Log file error\n')
        sys.exit(-1)

    gpio_init()

    led = LedThread()
    led.start()
    led.oneshot()

    y3 = Y3ModuleSub()
    y3.uart_open(dev='/dev/ttyAMA0', baud=115200, timeout=1)
    y3.start()
    sys.stdout.write('Wi-SUN reset...\n')
    
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
        sys.stdout.write('({}/10) Active scan with a duration of {}...\n'.format(i+1, user_conf.SEM_DURATION))
        channel_list = y3.active_scan(user_conf.SEM_DURATION)
        if channel_list is False:   # active_scan()をCtrl+cで終了したとき
            break
        if channel_list:
            sem_exist = True
            break
    
    if not sem_exist:   # スキャン失敗
        sys.stdout.write('[Error]: Can not connect to a smart energy meter\n')

    if sem_exist:
        ch = channel_list[0]

        sys.stdout.write('Energy Meter: [Ch.0x{:02X}, Addr.{}, LQI.{}, PAN.0x{:04X}]\n'.format(ch['Channel'],
                         ch['Addr'], ch['LQI'], ch['Pan ID']))

        # チャンネル設定
        y3.set_channel(ch['Channel'])
        sys.stdout.write('Set channel to 0x{:02X}\n'.format(ch['Channel']))

        # スマートメータのIP6アドレス
        ip6 = y3.get_ip6(ch['Addr'])
        sys.stdout.write('IP6 address is \'{}\'\n'.format(ip6))

        # PAN ID
        y3.set_pan_id(ch['Pan ID'])
        sys.stdout.write('Set PAN ID to 0x{:04X}\n'.format(ch['Pan ID']))

        # PANA認証(PaC)
        sem_exist = False
        pana_done = False
        for i in range(10):
            sys.stdout.write('({}/10) PANA connection...\n'.format(i+1))
            sem_exist = y3.start_pac(ip6)
            
            if sem_exist:       # インスタンスリスト通知の受信待ち
                st = time.time()
                while True:
                    if sem_inf_list:
                        pana_ts = time.time()   # タイムスタンプを保存
                        sys.stdout.write('Successfully done.\n')               
                        time.sleep(3)
                        pana_done = True
                        break
                    elif time.time() - st > 15:     # PANA認証失敗によるタイムアウト
                        sys.stdout.write('Fail to connect.\n')
                        sem_exist = False
                        pana_done = False
                        break
                    else:
                        time.sleep(0.1)
            
            if pana_done:
                break

            
    if sem_exist:
        sem = EchonetLiteSmartEnergyMeter()
        
        # 参考までに各種データ取得
        get_list = ['fault_status', 'get_pty_map', 'set_pty_map', 'chg_pty_map',
                    'operation_status', 'epc_coefficient', 'digits', 'unit_amount_energy']
        for epc in get_list:
            data = sem_get_getres(epc)
            if data:
                sys.stdout.write('[Get]: {}, {}\n'.format(epc, data))
            else:
                sys.stdout.write('[Get]: {}, Fail to receive'.format(epc))

        start = time.time() - 1000  # 初期値を1000s前に設定
        while True:
            try:
                pana_done = False
                if (time.time() - pana_ts > 12 * 60 * 60):    # 12時間毎にPANA認証を更新
                    sys.stdout.write('PANA re-connection...\n')
                    sem_exist = y3.restart_pac()

                    if sem_exist:       # インスタンスリスト通知の受信待ち
                        st = time.time()
                        while True:
                            if sem_inf_list:
                                pana_ts = time.time()   # タイムスタンプを保存
                                pana_done = True
                                sys.stdout.write('Successfully done.\n')               
                                time.sleep(3)
                                break
                            elif time.time() - st > 15:     # PANA認証失敗によるタイムアウト
                                sys.stdout.write('Fail to connect.\n')
                                break
                            else:
                                time.sleep(0.1)                        
                    
                    if not pana_done:
                        break       # PANA認証失敗でbreakする

                while True:
                    if (time.time() - start) >= user_conf.SEM_INTERVAL:
                        start = time.time()
                        break
                    else:
                        time.sleep(0.1)
                                     
                sem_get('instant_power')    # Get
                
                while True:     # GetRes待ちループ        
                    rcd_time = time.time()      # rcd_time[s]
                    new_dt = datetime.datetime.fromtimestamp(rcd_time)
                    
                    # ログファイルメンテナンス
                    pow_logfile_maintainance(saved_dt, new_dt)
                    saved_dt = new_dt

                    if y3.get_queue_size():
                        msg_list = y3.dequeue_message()
                        if msg_list['COMMAND'] == 'ERXUDP':
                            led.oneshot()
                            parsed_data = sem.parse_frame(msg_list['DATA'])
                            
                            if parsed_data:
                                if parsed_data['tid'] != tid_counter:
                                    errmsg = '[Error]: ECHONET Lite TID mismatch\n'
                                    sys.stdout.write(errmsg)
                                    
                                else:
                                    watt_int = int.from_bytes(parsed_data['ptys'][0]['edt'], 'big', signed=True)
                                    sys.stdout.write('[{:5d}] {:4d} W\n'.format(tid_counter, watt_int))
                                    sys.stdout.flush()
                            
                                    try:    # 一時ログファイルに書き込み
                                        f = open(TMP_LOG_FILE, 'a')        # rcd_time[ms] (JavaScript用)
                                        f.write('{},{}\n'.format(round(rcd_time), watt_int))
                                        f.close()
                                    except:
                                        sys.stdout.write('[Error]: can not write to file.\n')
                            
                                    if sock:  # UNIXドメインソケットで送信
                                        sock_data = json.dumps({'time': rcd_time, 'power': watt_int}).encode('utf-8')
                                        try:
                                            sock.send(sock_data)
                                        except:
                                            sys.stdout.write('[Error]: Broken socket.\n')
                                    break
                            
                            else:   # 電文が壊れている
                                errmsg = '[Error]: ECHONET Lite frame error\n'
                                sys.stdout.write(errmsg)
                            
                        else:   # 電文が壊れている???
                            errmsg = '[Error]: Unknown data received.\n'
                            sys.stdout.write(errmsg)

                    else:   # GetRes待ち
                        while sem_inf_list:
                            inf = sem_inf_list.pop(0)
                            sys.stdout.write('[Inf]: {}\n'.format(inf['DATA']))
                        
                        if time.time() - start > 20:    # GetRes最大待ち時間: 20s
                            sys.stdout.write('[Error]: Time out.\n')
                            
                            try:    # 一時ログファイルに書き込み
                                f = open(TMP_LOG_FILE, 'a')
                                f.write('{},None\n'.format(round(rcd_time)))
                                f.close()
                            except:
                                sys.stdout.write('[Error]: can not write to file.\n')
                            break
                            
                        time.sleep(0.1)

            except KeyboardInterrupt:
                break

    else:
        sys.stdout.write('[Error]: Can not connect with a smart energy meter.\n')

    # 終了処理
    if sock:
        try:
            sock.close()
        except:
            sys.stdout.write('[Error]: Broken socket.\n')

    sys.stdout.write('\nWi-SUN reset...\n')
    y3reset()
    y3.terminate()
    y3.uart_close()
    led.terminate()
    gpio.cleanup()
    
    if os.path.exists(TMP_LOG_FILE):
        os.remove(TMP_LOG_FILE)

    sys.stdout.write('Bye.\n')
    sys.exit(0)
