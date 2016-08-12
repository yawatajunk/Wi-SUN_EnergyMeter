#!/usr/bin/python3
# coding: UTF-8
#
# y3PingPong.py
#
# Wi-SUNモジュール通信クラスY3Moduleのサンプル, PingPong
#
# Cppyright(c) 2016 pi@blue-black.ink
#

import argparse
import random
import RPi.GPIO as gpio
from y3module import *


# Wi-SUNリセット用GPIO
Y3RESET_GPIO = 18

# LED用GPIO
LED_GPIO = 4


# コマンドライン引数
def arg_parse():
    p = argparse.ArgumentParser()
    p.add_argument('-m', '--mode', help='select [c]ordinator or [d]evice', default='d', choices=['c', 'C', 'd', 'D'])
    p.add_argument('-i', '--id', help='pairing ID', type=str, default='PingPong')
    p.add_argument('-t', '--transport', help='select [u]dp or [t]cp', default='u', choices=['u', 'U', 't', 'T'])
    args = p.parse_args()
    return args


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
    gpio.output(Y3RESET_GPIO, gpio.LOW)     # High -> low
    time.sleep(0.1)
    gpio.output(Y3RESET_GPIO, gpio.HIGH)    # low -> High
    time.sleep(1.0)


# Wi-SUNモジュールをコーディネータとして起動
def y3cordinator(args):
    sys.stderr.write('Wi-SUN Cordinator setup...\n')

    # EDスキャン
    sys.stderr.write('ED scan start...\n')
    ed_res = y3.ed_scan()
    sys.stderr.write('    Channel is 0x{:02X}, LQI is {}.\n'.format(ed_res[0], ed_res[1]))
    y3.set_channel(ed_res[0])

    # ペアリングID
    sys.stderr.write('Setting pairing ID...\n')
    i = args.id
    if len(i) != 8:
        sys.stderr.write('    Error: \'{} \' is not allowed for pairing ID. Pairing ID must be 8 figures.\n'.format(i))
        return -1
    sys.stderr.write('    Pairing ID is \'{}\'.\n'.format(i))
    y3.set_pairing_id(i)

    # アクティブスキャン
    sys.stderr.write('Active scan start...\n')
    channel_list = y3.active_scan()
    pan_list = []
    sys.stderr.write('  {} cordinator(s) found.\n'.format(len(channel_list)))
    for ch in channel_list:
        sys.stderr.write('    [Ch.0x{}, Addr.{}, LQI.0x{}, PAN.0x{}]\n'.format(
                ch['Channel'], ch['Addr'], ch['LQI'], ch['Pan ID']))
        pan_list.append(ch['Pan ID'])

    # PAN ID
    sys.stderr.write('Setting PAN ID...\n')
    pan = 0
    while True:
        pan = random.randint(0, 0xfffe)     # 0xffffは使用禁止
        if not (pan in pan_list):
            break
    sys.stderr.write('    PAN ID is 0x{:04X}\n'.format(pan))
    y3.set_pan_id(pan)

    # コーディネータ起動
    y3.set_accept_beacon(True)
    sys.stderr.write('Wi-SUN cordinator has successfully started.\n')
    sys.stderr.write('Type CTRL+C to exit.\n')

    # ping pongループ
    handle_list = []
    while True:
        try:
            if y3.get_queue_size():
                led.oneshot()
                msg_list = y3.dequeue_message()
                if msg_list['COMMAND'] == 'ERXUDP' or msg_list['COMMAND'] == 'ERXTCP':
                    msg = y3.decode(msg_list['DATA']).replace('Ping', 'Pong')
                    sys.stderr.write(msg + '\n')

                    if msg_list['COMMAND'] == 'ERXUDP':
                        y3.udp_send(1, msg_list['SENDER'], False, y3.Y3_UDP_ECHONET_PORT, msg.encode())
                    else:
                        for hdl in handle_list:
                            if hdl['IPADDR'] == msg_list['SENDER']:
                                y3.tcp_send(hdl['HANDLE'], msg.encode())
                                break
                            else:
                                sys.stderr.write('Error: TCP Connection.\n')

                elif msg_list['COMMAND'] == 'ETCP':
                    if msg_list['STATUS'] == 1:
                        handle_list.append(msg_list)
                    elif msg_list['STATUS'] == 3:
                        for i, hdl in enumerate(handle_list):
                            if hdl['HANDLE'] == msg_list['HANDLE']:
                                del handle_list[i]

            else:
                time.sleep(0.01)

        except KeyboardInterrupt:
            sys.stderr.write('\n')
            break

    return 0


# Wi-Sunモジュールをデバイスとして起動
def y3device(args):
    sys.stderr.write('Wi-SUN device startup...\n')

    # ペアリングID
    sys.stderr.write('Setting pairing ID...\n')
    i = args.id
    if len(i) != 8:
        sys.stderr.write('    Error: \'{} \' is not allowed for pairing ID. Pairing ID must be 8 figures.\n'.format(i))
        return -1
    sys.stderr.write('    Pairing ID is \'{}\'.\n'.format(i))
    y3.set_pairing_id(i)

    # アクティブスキャン
    sys.stderr.write('Active scan start...\n')
    channel_list = y3.active_scan()
    pan_list = []
    sys.stderr.write('  {} cordinator(s) found.\n'.format(len(channel_list)))
    if len(channel_list) == 0:
        return -1

    for ch in channel_list:
        sys.stderr.write('    [Ch.0x{:02X}, Addr.{}, LQI.{}, PAN.0x{:04X}]\n'.format(ch['Channel'], ch['Addr'],
              ch['LQI'], ch['Pan ID']))
        pan_list.append(ch['Pan ID'])

    # チャンネル設定
    channel = channel_list[0]
    y3.set_channel(channel['Channel'])
    sys.stderr.write('Set channel to 0x{:02X}\n'.format(channel['Channel']))

    # コーディネータのIP6アドレス
    ip6 = y3.get_ip6(channel['Addr'])
    sys.stderr.write('Cordinator\'s IP6 address is \'{}\'\n'.format(ip6))

    # PAN ID
    y3.set_pan_id(channel['Pan ID'])
    sys.stderr.write('Set PAN ID to 0x{:04X}\n'.format(channel['Pan ID']))

    # Ping Pong ループ(TCP)
    if args.transport.upper() == 'T':
        tcp = y3.tcp_connect(ip6, y3.Y3_TCP_ECHONET_PORT, y3.Y3_TCP_ECHONET_PORT)
        sys.stderr.write('Open TCP Connection.\n')
        sys.stderr.write('    IP6 address : {}\n'.format(ip6))
        sys.stderr.write('    local port  : {}\n'.format(y3.Y3_TCP_ECHONET_PORT))
        sys.stderr.write('    remote port : {}\n'.format(y3.Y3_TCP_ECHONET_PORT))
        sys.stderr.write('    status      : {}\n'.format(tcp['STATUS']))
        sys.stderr.write('    handle no.  : {}\n'.format(tcp['HANDLE']))

        if tcp['STATUS'] != 1:
            sys.stderr.write('Error: TCP connection.\n')
            return -1

        cnt = 0
        tcp_close_flag = False
        term_flag = False
        sys.stderr.write('Wi-Sun device has successfully started.\n')
        sys.stderr.write('Type CTRL+C to exit.\n')

        while not term_flag:
            st_time = time.time()
            msg = 'Ping...({:04d}) '.format(cnt)
            sys.stderr.write(msg)

            cnt += 1
            if cnt == 10000:
                cnt = 0

            try:
                pong_flag = False
                result = y3.tcp_send(tcp['HANDLE'], msg.encode())
                if not result:
                    sys.stderr.write('Error: TCP connection.\n')
                    pong_flag = True
                    term_flag = True

                while not pong_flag:
                    if y3.get_queue_size():
                        msg_list = y3.dequeue_message()

                        if msg_list['COMMAND'] == 'ERXTCP':
                            pong_flag = True
                            res = y3.decode(msg_list['DATA'])
                            if res.replace('Pong', 'Ping') == msg:
                                end_time = time.time()
                                lap_time = end_time - st_time
                                sys.stderr.write('{:.2f}\n'.format(lap_time))
                            else:
                                sys.stderr.write('NG!\n')

                    else:
                        end_time = time.time()
                        lap_time = end_time - st_time
                        if lap_time > 3.0:        # time up
                            sys.stderr.write('Time up!\n')
                            break
                        time.sleep(0.01)

                    if tcp_close_flag:
                        sys.stderr.write('Close TCP connection...\n')
                        y3.tcp_disconnect(tcp['HANDLE'])
                        term_flag = True
                        break

            except KeyboardInterrupt:
                sys.stderr.write('\n')
                tcp_close_flag = True

    # Ping Pongループ (UDP)
    else:
        cnt = 0
        sys.stderr.write('Wi-Sun device has successfully started.\n')
        sys.stderr.write('Type CTRL+C to exit.\n')
        time.sleep(0.5)

        while True:
            try:
                st_time = time.time()
                msg = 'Ping...({:04d}) '.format(cnt)
                sys.stderr.write(msg)

                cnt += 1
                if cnt == 10000:
                    cnt = 0

                y3.udp_send(1, ip6, False, y3.Y3_UDP_ECHONET_PORT, msg.encode())

                while True:
                    if y3.get_queue_size():
                        msg_list = y3.dequeue_message()
                        if msg_list['COMMAND'] == 'ERXUDP':
                            res = y3.decode(msg_list['DATA'])
                            if res.replace('Pong', 'Ping') == msg:
                                end_time = time.time()
                                lap_time = end_time - st_time
                                sys.stderr.write('{:.2f}\n'.format(lap_time))                                
                                break
                            else:
                                sys.stderr.write('NG!\n')

                    else:
                        end_time = time.time()
                        lap_time = end_time - st_time
                        if lap_time > 3.0:        # time up
                            sys.stderr.write('Time up!\n')
                            break
                        time.sleep(0.01)

            except KeyboardInterrupt:
                sys.stderr.write('\n')
                break
    return 0
    
    
if __name__ == '__main__':  # ここからスタート
    import sys

    gpio_init()

    led = LedThread()
    led.start()
    led.oneshot()

    y3 = Y3Module()
    if not y3.uart_open('/dev/ttyAMA0', 115200, 1):
        sys.exit(1)
    y3.start()
    sys.stderr.write('Wi-SUN reset...\n')
    y3reset()
    y3.set_echoback_off()
    y3.set_opt(True)

    if args.mode.upper() == 'C':
        result = y3cordinator(args)     # コーディネーター起動
    else:
        result = y3device(args)         # デバイス起動

    # 終了処理
    sys.stderr.write('Wi-SUN reset...\n')
    y3reset()
    y3.terminate()
    y3.uart_close()
    led.terminate()
    gpio.cleanup()

    sys.stderr.write('\nBye.\n')
    sys.exit(0)
