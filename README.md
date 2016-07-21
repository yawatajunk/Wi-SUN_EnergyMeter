## NAME  
Wi-Sun_EnergyMeter（ワイサンエナジーメーター）  
Branch 0.2a  

## Overview
Wi-SUNモジュールBP35A1(ROHM)をRaspberry Piに接続し、スマートメーターと無線通信を行い、電力値等を取得するPythonスクリプトです。  
現段階では、2組の（ラズパイ+モジュール）間でTCPまたはUDPで通信を行うだけで，スマートメータには接続しません。    

## Description
### スマートメーター，HEMS，ECHONET Lite
いままでどおり地域の電力会社を選ぶもよし、それ以外の小売電気事業者を選ぶもよし。「電力自由化」によって、誰もが電気の購入先を自由に選択できるようになりました。  
この制度を実現するためには**スマートメーター**が不可欠です。スマートメーターと電力会社間のデータ通信「Aルート」による自動検針が必要だからです。  

さらに、スマートメーターと宅内間の通信機能「Bルート」も実現されました。一般に、Bルート通信には「HEMSコントローラ」と呼ばれる装置が用いられます。  
**HEMS（ヘムス）**とは「Home Energy Management System」の略で、家庭のエネルギーを賢く管理するための仕組みです。  

スマートメーター（Bルート），HEMSコントローラ，HEMS対応の機器（エアコン、照明、給湯器，太陽光発電、蓄電池や充電器など）は、**ECHONET Lite（エコーネット ライト）**と呼ばれる製造メーカーの垣根を越えた共通のコマンドにより相互通信を行います。  
HEMSとECHONET Liteにより，「省・創・蓄エネルギー」を賢くコントロールする**スマートハウス**が現実のものになりました。  

### Wi-SUN
ECHONET Liteはあくまでも通信コマンドの規格であり，物理的なネットワークについての規定がありません。  
HEMSコントローラと対応機器間は，有線LAN，Wi-Fi，Bluetoothなど，既存のネットワークで接続することができます。このことがHEMS導入の障壁を低くしています。  

宅外のスマートメーターと宅内のHEMSコントローラ間のBルート通信は，宅内外を接続するため無線通信が最適です。とはいえ，宅内外の装置であるが故に距離に隔たりがあったり、壁が障害になることが考えられ，Wi-Fi接続では安定な通信が望めません。  
そのため，新しい無線通信規格**Wi-SUN（ワイサン）**がBルート通信の1つに採用されました。  

Wi-SUNは，920 MHz帯を使い，壁を通過しやすく建物の陰にも回りやすく，Wi-Fiよりも遠距離まで電波が届く性質があります。さらに省エネです。  
ただし，低速（100 kbps）です。とはいえ，スマートメーターからデータを取得するには十分なスピードです。  

### Project
本プロジェクトの目的は，Wi-SUNモジュールBP35A1(ROHM)をRaspberry Piに接続し、スマートメーターと無線通信を行い、電力値等を取得することです。  
なんちゃってHEMSコントローラだと考えてください。

## Requirement
* Raspberry Pi
    * Raspbian JESSIE
* Pythonモジュール（Raspbian JESSIEには組込済）
    * pyserial
    * RPi.GPIO
* Wi-SUNモジュール BP35A1 (ROHM)

## Raspberry Pi Setup
### Circuit
Raspberry PiとBP35A1との接続は次のファイルを参照してください。  
なお、BP35A1とブレッドボードは、ピッチ変換アダプターボードBP35A7Aを使い，CN1及びCN2で接続します。  

* wiring.jpg: 実体配線図
* circuit.jpg: 回路図

### GPIO

* GPIO18: BP35A1のリセットに接続します。  
* GPIO4: LEDを接続します。省略できます。
* GPIO14, GPIO15: BP35A1とのシリアル通信に使用します。これらのピンはデフォルトでシステムログインのために使用されているため次の手順で停止します。  

`$ sudo nano /boot/cmdline.txt`でファイルを開き，`console=serial0,115200`の部分を削除します。  

次のコマンドを実施します。
```
$ sudo systemctl stop serial-getty@ttyAMA0.service
$ sudo systemctl disable serial-getty@ttyAMA0.service
$ sudo reboot
```

## Install
gitコマンドをインストールします。  
```
$ sudo apt-get update
$ sudo apt-get install git
```

2組の(BP35A1 + Raspberry Pi)の適当なディレクトリで，次のコマンドを実行します。  
```
$ git clone --depth 1 https://github.com/yawatajunk/Wi-SUN_EnergyMeter.git
$ cd Wi-SUN_EnergyMeter
$ chmod +x y3PingPong.py
```

## Contents
* y3module.py: BP35A1通信クラス
* y3PingPong.py: デモプログラム
* README.md: このファイル
* LICENCE.md: MITライセンス
* wiring.png: 実体配線図
* circuit.png: 回路図
~~ec_energy_meter.py: ECHONET Liteによる電力量計との通信~~（暫くお待ちください）

## サンプルプログラム（y3PingPong）
2組の(BP35A1 + Raspberry Pi)で相互に通信を行うサンプルプログラムです。  

### Usage
1台（raspi1と呼びます）をコーディネーターとして起動します。  
`./y3PingPong.py --mode c`

もう1台(raspi2と呼びます)をデバイスとして起動するとUDPによる送受信が始まります。  
`./y3PingPong.py --mode d`  

TCPで送受信するには、raspi2にて、上のコマンドに代わりに次のコマンドを実行します。  
`./y3PingPong.py --mode d --transport t`  

プログラムを終了するときは，`CTRL`と`c`を同時に押します。  

PingPongの全オプションは次のとおりです。  

```
$ ./y3PingPong.py --help 
usage: y3PingPong.py [-h] [-m {c,C,d,D}] [-i ID] [-t {u,U,t,T}]

optional arguments:
  -h, --help            show this help message and exit
  -m {c,C,d,D}, --mode {c,C,d,D}
                        select [c]ordinator or [d]evice
  -i ID, --id ID        pairing ID
  -t {u,U,t,T}, --transport {u,U,t,T}
                        select [u]dp or [t]cp
```

## History  
0.1a: 初版
0.2a: 軽微な変更，README.mdを刷新  

## Reference
[Raspberry Pi](https://www.raspberrypi.org)
[Wi-SUNモジュール BP35A1 (ROHM)](http://www.rohm.co.jp/web/japan/news-detail?news-title=2015-01-07_ad&defaultGroupId=false)
[ECHONET Lite](https://echonet.jp)
