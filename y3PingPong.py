#!/usr/bin/python3
#
# y3PingPong.py#
# Sample script for the class Y3Module
#
# Cppyright(c) 2016 pi@blue-black.ink
#

import argparse
import time
import threading
import random
import RPi.GPIO as gpio
from y3module import *   # Wi-SUN module


# for wi-sun reset
Y3RESET_GPIO = 18

# for LED
LED_GPIO = 4


# command line arguments
def argParse():
    p = argparse.ArgumentParser()
    p.add_argument('-m', '--mode', help='select [c]ordinator or [d]evice', default ='d', choices=['c', 'C', 'd', 'D'])
    p.add_argument('-i', '--id', help='pairing ID', type=str, default='PingPong')
    p.add_argument('-t', '--transport', help='select [u]dp or [t]cp', default='u', choices=['u', 'U', 't', 'T'])
    args = p.parse_args()

    return(args)


# initialize GPIO
def gpioInit():
    gpio.setwarnings(False)
    gpio.setmode(gpio.BCM)

    gpio.setup(Y3RESET_GPIO, gpio.OUT)
    gpio.setup(LED_GPIO, gpio.OUT)

    # negate Wi-Sun reset
    gpio.output(Y3RESET_GPIO, gpio.HIGH)
    time.sleep(0.1)

    # turn off LED
    gpio.output(LED_GPIO, gpio.LOW)


# class for LED controll thread
class ledThread(threading.Thread):
    _trigger = False
    _termFlag = False

    def run(self):
        while not self._termFlag:
            if self._trigger == True:
                self.on(True)
                time.sleep(0.1)
                self.on(False)
                self._trigger = False
            else:
                time.sleep(0.1)

    def on(self, ctl):  # on/off
        if ctl == True:
            gpio.output(LED_GPIO, gpio.HIGH)
        else:
            gpio.output(LED_GPIO, gpio.LOW)

    def oneshot(self):
        self._trigger = True

    def terminate(self):
        self._termFlag = True


# Reset Wi-Sun module
def y3reset():
    gpio.output(Y3RESET_GPIO, gpio.LOW)  # assert reset
    time.sleep(0.1)
    gpio.output(Y3RESET_GPIO, gpio.HIGH)  # negate reset
    time.sleep(1.0)  # wait for Wi-SUN module booting


# boot Wi-SUN modue as a cordinator
def y3cordinator(args):
    print('Wi-SUN Cordinator setup...')

    # ED Scan
    print('ED scan start...')
    edRes = y3.ed_scan()
    print('    Channel is 0x{:02X}, LQI is {}.'.format(edRes[0], edRes[1]))
    y3.set_channel(edRes[0])

    # check pairing ID
    print('Setting pairing ID...')
    id = args.id
    if len(id) != 8:
        print('    Error: \'{} \' is not allowed for pairing ID. Pairing ID must be 8 figures.'.format(id))
        return -1
    print('    Pairing ID is \'{}\'.'.format(id))
    y3.set_pairing_id(id)

    # active scan
    print('Active scan start...')
    channelList = y3.active_scan()
    panList = []
    print('  {} cordinator(s) found.'.format(len(channelList)))
    for ch in channelList:
        print('    [Ch.0x{}, Addr.{}, LQI.0x{}, PAN.0x{}]'.format(
                ch['Channel'], ch['Addr'], ch['LQI'], ch['Pan ID']))
        panList.append(ch['Pan ID'])

    # check PAN ID
    print('Setting PAN ID...')
    while True:
        pan = random.randint(0, 0xfffe)     # 0xffff is not available
        if (pan in panList) == False:
            break
    print('    PAN ID is 0x{:04X}'.format(pan))
    y3.set_pan_id(pan)    # set Pan ID

    # start up cordinator
    y3.set_accept_beacon(True)
    print('Wi-SUN cordinator has successfully started.')
    print('Type CTRL+C to exit.')

    # ping pong loop
    termFlag = False
    while not termFlag:
        try:
            if y3.get_queue_size():
                led.oneshot()
                msgList = y3.dequeue_message()
                if msgList['COMMAND'] == 'ERXUDP':
                    msg = (msgList['DATA']).replace('Ping', 'Pong')
                    print(msg)
                    y3.udp_send(1, msgList['SENDER'], 0, y3.Y3_UDP_ECHONET_PORT, msg)

                elif msgList['COMMAND'] == 'ERXTCP':
                    msg = (msgList['DATA']).replace('Ping', 'Pong')
                    print(msg)
                    y3.tcp_send(1, msg)
                else:
                    print(msgList)
            else:
                time.sleep(0.01)

        except KeyboardInterrupt:
            print('\n')
            termFlag = True

    return 0


# boot Wi-Sun module as a device
def y3device(args):
    print('Wi-SUN device startup...')

    # check pairing ID
    print('Setting pairing ID...')
    id = args.id
    if len(id) != 8:
        print('    Error: \'{} \' is not allowed for pairing ID. Pairing ID must be 8 figures.'.format(id))
        return -1
    print('    Pairing ID is \'{}\'.'.format(id))
    y3.set_pairing_id(id)

    # active scan
    print('Active scan start...')
    channelList = y3.active_scan()
    panList = []
    print('  {} cordinator(s) found.'.format(len(channelList)))
    if len(channelList) == 0:
        return -1

    for ch in channelList:
        print('    [Ch.0x{:02X}, Addr.{}, LQI.{}, PAN.0x{:04X}]'.format(ch['Channel'], ch['Addr'], \
                                                                                ch['LQI'], ch['Pan ID']))
        panList.append(ch['Pan ID'])

    # set channel
    channel = channelList[0]
    y3.set_channel(channel['Channel'])
    print('Set channel to 0x{:02X}'.format(channel['Channel']))

    # get IP6 of cordinator
    ip6 = y3.get_ip6(channel['Addr'])
    print('Cordinator\'s IP6 address is \'{}\''.format(ip6))

    # set PAN ID
    y3.set_pan_id(channel['Pan ID'])
    print('Set PAN ID to 0x{:04X}'.format(channel['Pan ID']))

    # Open TCP connection
    tcp = {}
    if args.transport.upper() == 'T':
        tcp = y3.tcp_connect(ip6, y3.Y3_TCP_PORT, y3.Y3_TCP_PORT)
        print('Open TCP Connection.')
        print('    IP6 adrs   : {}'.format(ip6))
        print('    local port : {}'.format(y3.Y3_TCP_PORT))
        print('    remote port: {}'.format(y3.Y3_TCP_PORT))
        print('    status     : {}'.format(tcp['STATUS']))
        print('    handle no. : {}'.format(tcp['HANDLE']))
    else:
        tcp['STATUS'] = 1

    print('Wi-Sun device has successfully started.')

    # ping pong loop
    termFlag = False
    tcpCloseFlag = False
    cnt = 0

    while not termFlag:
        try:
            if tcp['STATUS']:
                stTime = time.time()
                msg = 'Ping...({:04d})'.format(cnt)
                print(msg+' ', end='')

                if args.transport.upper == 'T':
                    y3.tcp_send(tcp['Handle'], msg)
                else:
                    y3.udp_send(1, ip6, False, y3.Y3_UDP_ECHONET_PORT, msg)

                cnt = cnt + 1
                if cnt == 10000:
                    cnt = 0

                pongFlag = False
                while not pongFlag:
                    if y3.get_queue_size():
                        msgList = y3.dequeue_message()
                        if msgList['COMMAND'] == 'ERXUDP' or msgList['COMMAND'] == 'ERXTCP':
                            res = msgList['DATA']
                            if res.replace('Pong', 'Ping') == msg:
                                pongFlag = True
                                #print(res + ' ', end='')
                                endTime = time.time()
                                rapseTime = endTime - stTime
                                print('{:.2f}'.format(rapseTime))
                            else:
                                pongFlag = True
                                print('NG!')
                        else:
                            pass    # do nothing
                    else:
                        endTime = time.time()
                        rapseTime = endTime - stTime
                        if rapseTime > 3.0: # time up
                            print('Time up!')
                            pongFlag = True
                        time.sleep(0.01)

                    if tcpCloseFlag == True:
                        if args.transport.upper() == 'T':
                            print('Close TCP connection...')
                            y3.tcp_disconnect(tcp['HANDLE'])
                        pongFlag = True
                        termFlag = True

            else:
                print('Error: TCP connection.')
                return -1

        except KeyboardInterrupt:
            print('\n')
            tcpCloseFlag = True

    return 0


# start from here
if __name__ == '__main__':
    # command line args
    args = argParse()

    # GPIO
    gpioInit()

    # LED
    led = ledThread()
    led.start()
    led.oneshot()

    # Wi-SUN
    y3 = Y3Module()
    y3.uart_open()
    y3.start()
    print('Wi-SUN reset...')
    y3reset()
    y3.set_echoback(False)

    # activate as cordinator or device
    if args.mode.upper() == 'C':
        result = y3cordinator(args) # cordinator
    else:
        result = y3device(args)     # device

    # closing
    print('Wi-Sun reset...')
    y3reset()
    y3.terminate()
    y3.join()
    y3.uart_close()   # close uart
    led.terminate()
    led.join()
    gpio.cleanup()      # release gpio

    print('Bye.')

    exit(result)
