## NAME  
Wi-Sun_EnergyMeter（ワイサンエナジーメーター）  
Branch 0.5a  


## Overview
Wi-SUNモジュールBP35A1(ROHM)をRaspberry Piに接続してスマートメーターと無線通信を行い、消費電力を取得するPythonスクリプト。さらに、その取得データをリアルタイムで配信するWEBサーバです。

## Screenshot
瞬時電力  
![Wi-SUN_EnergyMeter Screenshot 1](http://blue-black.ink/wp-content/uploads/2016/10/IMG_5488.png)

瞬時電力履歴  
![Wi-SUN_EnergyMeter Screenshot 2](http://blue-black.ink/wp-content/uploads/2016/10/IMG_5489.png)

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
ECHONET Liteにおいて、一般家庭のスマートメーターは**低圧スマート電力量メータークラス**という機器オブジェクトとして規定されており、ECHONET Liteの電文フォーマットに則り、瞬時電力・電流、30分毎の電力量計量値等を取得できます。本プロジェクトでは瞬時電力を取得し、そのログを取るプログラムをPythonで構築しました。  
さらに、取得したデータを配信するためのWEBサーバを、Node.js + Express + socket.ioで構築しました。


## Requirement
* Raspberry Pi
    * Raspbian JESSIE
    * Pythonモジュール（Raspbian JESSIEには組込済）
	    * pyserial
	    * RPi.GPIO
	* Node.js v4.4.7 以上
		* socket.io
		* express
* Wi-SUNモジュール BP35A1 (ROHM)


## Raspberry Pi Setup
### Circuit
Raspberry PiとBP35A1との接続は次のファイルを参照してください。  
なお、BP35A1とブレッドボードは、ピッチ変換アダプターボードBP35A7Aを使い，CN1及びCN2で接続します。  

* wiring.jpg: 実体配線図
* circuit.jpg: 回路図

### GPIO
* GPIO18: BP35A1のリセットに接続します。  
* GPIO4: LEDを接続します(省略可)。
* GPIO14, GPIO15: BP35A1とのシリアル通信に使用します。これらのピンはデフォルトでシステムログインのために使用されているため次の手順で停止します。  

`$ sudo raspi-config`でToolを起動し、`9 Advanced Options >> A7 Serifal >> ＜いいえ＞`を選択します。  

## Install
git及びnode.js v4.4.7がインストールされている必要があります。  
また、本プロジェクトをインストールしたい適当なディレクトリで、次の手順でインストールします。
```
$ git clone https://github.com/yawatajunk/Wi-SUN_EnergyMeter.git
$ cd Wi-SUN_EnergyMeter
$ git checkout 0.5a
$ cd sem_app
$ npm install
```


## Contents
* circuit.png: 回路図  
* echonet_lite.py: ECHONET Liteクラス  
* LICENCE.md: MITライセンス  
* README.md: このファイル  
* sem_appフォルダ: Node.jsによるWEBサーバ関連  
* sem_com.py: スマート電力量メーター通信プログラム
* user_conf.py: スマート電力量メーターのID、パスワード等の設定ファイル
* wiring.png: 実体配線図  
* y3module.py: BP35A1通信クラス  

## スマートメーター通信プログラム (sem_com.py)  
スマートメーターから消費電力を受信するプログラムです。  

### Usage
user_conf.pyを編集し、スマートメーターのID及びパスワードを設定します。  
SEM_INTERVALには瞬時電力を取得する時間間隔[秒]を設定します。0を設定すれば最大頻度でデータを取得することができます。  
SEM_DURATIONは、アクティブスキャンのとき、チャンネルごとのスキャン時間を設定するものです。数値が1増すごとにスキャン時間が2倍になります。闇雲に大きい値を設定するとスキャン時間が大幅に長くなりますのでご注意ください。アクティブスキャンでスマートメーターが見つかりずらいときは、+1してお試しください。なお、アクティブスキャンに数十秒かかってとしてもそれが正常です。じっくり気長に待ちましょう。
```
SEM_ROUTEB_ID = '00000000000000000000000000000000'
SEM_PASSWORD = 'XXXXXXXXXXXX'
SEM_INTERVAL = 3
SEM_DURATION = 6
```

次のコマンドでプログラムを起動します。  
スマメとの距離が遠かったり電波の状態が良くないと、アクティブスキャンをリトライするため時間がかかることがあります。  
暫く待つと、瞬時電力が表示されます。  
プログラムを停止するときは、`CTRL`と`c`を同時に押します。
```
$ ./sem_com.py
Log files setup...
Wi-SUN reset...
(1/10) Active scan with a duration of 6...
.
.
.
.
(略)
.
.
.
.
[   18]  960 W
[   19]  928 W
[   20]  912 W
[   21]  912 W
[   22]  904 W
[   23]  912 W
[   24]  920 W
.
.
.
.
```


## 消費電力を配信するWEBサーバ
Node.js + ExpressでWEBサーバを構築しました。
また、画面デザインの大枠作成にはJetstrapを、グラフの表示にはHighcharts, Highstockを使っています。  
プロジェクトをインストールした、起点となるディレクトリに移動します。
`$ cd /path/to/Wi-SUN_EnergyMeter`

### 設定ファイル
####「./user_conf.py」####
先述のとおり、スマートメータのIDとパスワードを設定します。  

####「./sem_app/bin/www」####
WEBサーバのポート番号を設定します。
```
//
// ポート番号設定
//
var PORT_NO = '3610';
```

### 起動方法
WEBサーバを起動します。  
`$ ./sem_app/bin/www`

スマートメーター通信プログラムを起動します。  
`$ ./sem_com.py`

### WEBブラウザで確認
WEBサーバにブラウザで`http://サーバURL:ポート番号/`にアクセスします。例えば次のとおりです。  
`http://raspi0.local:3610/`


## History  
0.1a: 初版  
0.2a: 軽微な変更，README.mdを刷新  
0.3a: スマートメーター通信プログラム＆配信WEBサーバ追加  
0.5a: 瞬時電力の履歴を記録。WEB表示機能を追加  


## Reference
[Raspberry Pi](https://www.raspberrypi.org)  
[Wi-SUNモジュール BP35A1 (ROHM)](http://www.rohm.co.jp/web/japan/news-detail?news-title=2015-01-07_ad&defaultGroupId=false)  
[ECHONET Lite](https://echonet.jp)  
[Node.js](https://nodejs.org/en/)  
[Express](https://expressjs.com)  
[socket.io](http://socket.io/)  
[Jetstrap](https://jetstrap.com)  
[Highcharts](http://www.highcharts.com)
