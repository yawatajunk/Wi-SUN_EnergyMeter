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
    p.add_argument('-t', '--transport', help='select [u]dp or [t]cp', default='t', choices=['u', 'U', 't', 'T'])
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
    _trigger = False
    _termFlag = False

    def run(self):
        while not self._termFlag:
            if self._trigger:
                self.on(True)
                time.sleep(0.1)
                self.on(False)
                self._trigger = False
            else:
                time.sleep(0.1)

    @staticmethod
    def on(ctl):
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
    gpio.output(Y3RESET_GPIO, gpio.LOW)  # assert reset
    time.sleep(0.1)
    gpio.output(Y3RESET_GPIO, gpio.HIGH)  # negate reset
    time.sleep(1.0)  # wait for Wi-SUN module booting


# Wi-SUNモジュールをコーディネータとして起動
def y3cordinator(args):
    print('Wi-SUN Cordinator setup...')

    # EDスキャン
    print('ED scan start...')
    ed_res = y3.ed_scan()
    print('    Channel is 0x{:02X}, LQI is {}.'.format(ed_res[0], ed_res[1]))
    y3.set_channel(ed_res[0])

    # ペアリングID
    print('Setting pairing ID...')
    i = args.id
    if len(i) != 8:
        print('    Error: \'{} \' is not allowed for pairing ID. Pairing ID must be 8 figures.'.format(i))
        return -1
    print('    Pairing ID is \'{}\'.'.format(i))
    y3.set_pairing_id(i)

    # アクティブスキャン
    print('Active scan start...')
    channel_list = y3.active_scan()
    pan_list = []
    print('  {} cordinator(s) found.'.format(len(channel_list)))
    for ch in channel_list:
        print('    [Ch.0x{}, Addr.{}, LQI.0x{}, PAN.0x{}]'.format(
                ch['Channel'], ch['Addr'], ch['LQI'], ch['Pan ID']))
        pan_list.append(ch['Pan ID'])

    # PAN ID
    print('Setting PAN ID...')
    pan = 0
    while True:
        pan = random.randint(0, 0xfffe)     # 0xffff is not available
        if not (pan in pan_list):
            break
    print('    PAN ID is 0x{:04X}'.format(pan))
    y3.set_pan_id(pan)    # set Pan ID

    # コーディネータ起動
    y3.set_accept_beacon(True)
    print('Wi-SUN cordinator has successfully started.')
    print('Type CTRL+C to exit.')

    # ping pongループ
    term_flag = False
    handle_list = []

    while not term_flag:
        try:
            if y3.get_queue_size():
                led.oneshot()
                msg_list = y3.dequeue_message()
                if msg_list['COMMAND'] == 'ERXUDP' or msg_list['COMMAND'] == 'ERXTCP':
                    msg = y3.ascii_hex_to_str(msg_list['DATA']).replace('Ping', 'Pong')
                    print(msg)

                    if msg_list['COMMAND'] == 'ERXUDP':
                        y3.udp_send(1, msg_list['SENDER'], False, y3.Y3_UDP_ECHONET_PORT, msg)
                    else:
                        for hdl in handle_list:
                            if hdl['IPADDR'] == msg_list['SENDER']:
                                y3.tcp_send(hdl['HANDLE'], msg)
                                break
                            else:
                                print('Error: TCP Connection.')

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
            print('\n')
            term_flag = True

    return 0


# Wi-Sunモジュールをデバイスとして起動
def y3device(args):
    print('Wi-SUN device startup...')

    # ペアリングID
    print('Setting pairing ID...')
    i = args.id
    if len(i) != 8:
        print('    Error: \'{} \' is not allowed for pairing ID. Pairing ID must be 8 figures.'.format(i))
        return -1
    print('    Pairing ID is \'{}\'.'.format(i))
    y3.set_pairing_id(i)

    # アクティブスキャン
    print('Active scan start...')
    channel_list = y3.active_scan()
    pan_list = []
    print('  {} cordinator(s) found.'.format(len(channel_list)))
    if len(channel_list) == 0:
        return -1

    for ch in channel_list:
        print('    [Ch.0x{:02X}, Addr.{}, LQI.{}, PAN.0x{:04X}]'.format(ch['Channel'], ch['Addr'],
              ch['LQI'], ch['Pan ID']))
        pan_list.append(ch['Pan ID'])

    # チャンネル設定
    channel = channel_list[0]
    y3.set_channel(channel['Channel'])
    print('Set channel to 0x{:02X}'.format(channel['Channel']))

    # コーディネータのIP6アドレス
    ip6 = y3.get_ip6(channel['Addr'])
    print('Cordinator\'s IP6 address is \'{}\''.format(ip6))

    # PAN ID
    y3.set_pan_id(channel['Pan ID'])
    print('Set PAN ID to 0x{:04X}'.format(channel['Pan ID']))

    # Ping Pong ループ(TCP)
    if args.transport.upper() == 'T':
        tcp = y3.tcp_connect(ip6, y3.Y3_TCP_PORT, y3.Y3_TCP_PORT)
        print('Open TCP Connection.')
        print('    IP6 address : {}'.format(ip6))
        print('    local port  : {}'.format(y3.Y3_TCP_PORT))
        print('    remote port : {}'.format(y3.Y3_TCP_PORT))
        print('    status      : {}'.format(tcp['STATUS']))
        print('    handle no.  : {}'.format(tcp['HANDLE']))

        if tcp['STATUS'] != 1:
            print('Error: TCP connection.')
            return -1

        cnt = 0
        tcp_close_flag = False
        term_flag = False
        print('Wi-Sun device has successfully started.')
        print('Type CTRL+C to exit.')

        while not term_flag:
            st_time = time.time()
            msg = 'Ping...({:04d}) '.format(cnt)
            print(msg, end='')

            cnt += 1
            if cnt == 10000:
                cnt = 0

            try:
                pong_flag = False
                result = y3.tcp_send(tcp['HANDLE'], msg)
                if not result:
                    print('Error: TCP connection.')
                    pong_flag = True
                    term_flag = True

                while not pong_flag:
                    if y3.get_queue_size():
                        msg_list = y3.dequeue_message()

                        if msg_list['COMMAND'] == 'ERXTCP':
                            pong_flag = True
                            res = y3.ascii_hex_to_str(msg_list['DATA'])
                            if res.replace('Pong', 'Ping') == msg:
                                end_time = time.time()
                                lap_time = end_time - st_time
                                print('{:.2f}'.format(lap_time))
                            else:
                                print('NG!')

                    else:
                        end_time = time.time()
                        lap_time = end_time - st_time
                        if lap_time > 3.0:        # time up
                            print('Time up!')
                            break
                        time.sleep(0.01)

                    if tcp_close_flag:
                        print('Close TCP connection...')
                        y3.tcp_disconnect(tcp['HANDLE'])
                        term_flag = True
                        break

            except KeyboardInterrupt:
                print('\n')
                tcp_close_flag = True

    # Ping Pongループ (UDP)
    else:
        cnt = 0
        print('Wi-Sun device has successfully started.')
        print('Type CTRL+C to exit.')

        while True:
            try:
                st_time = time.time()
                msg = 'Ping...({:04d}) '.format(cnt)
                print(msg, end='')

                cnt += 1
                if cnt == 10000:
                    cnt = 0

                y3.udp_send(1, ip6, False, y3.Y3_UDP_ECHONET_PORT, msg)

                while True:
                    if y3.get_queue_size():
                        msg_list = y3.dequeue_message()
                        if msg_list['COMMAND'] == 'ERXUDP':
                            res = y3.ascii_hex_to_str(msg_list['DATA'])
                            if res.replace('Pong', 'Ping') == msg:
                                end_time = time.time()
                                lap_time = end_time - st_time
                                print('{:.2f}'.format(lap_time))
                                break
                            else:
                                print('NG!')

                    else:
                        end_time = time.time()
                        lap_time = end_time - st_time
                        if lap_time > 3.0:        # time up
                            print('Time up!')
                            break
                        time.sleep(0.01)

            except KeyboardInterrupt:
                print('\n')
                break
    return 0


if __name__ == '__main__':  # ここからスタート
    args = arg_parse()
    gpio_init()

    led = LedThread()
    led.start()
    led.oneshot()

    y3 = Y3Module()
    y3.uart_open(dev='/dev/ttyAMA0', baud=115200, timeout=1)
    y3.start()
    print('Wi-SUN reset...')
    y3reset()
    y3.set_echoback(False)
    y3.set_opt(True)

    if args.mode.upper() == 'C':
        result = y3cordinator(args)     # コーディネーター起動
    else:
        result = y3device(args)         # デバイス起動

    # 終了処理
    print('Wi-Sun reset...')
    y3reset()
    y3.terminate()
    y3.uart_close()
    led.terminate()
    gpio.cleanup()

    print('Bye.')

    exit(result)
