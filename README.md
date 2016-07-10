# Wi-Sun_EnergyMeter
## Fetch data from house energy meter using a raspberry pi with Wi-SUN module BP35A1

### Python3用クラス*Y3Module 0.1a*
Wi-SUNモジュールBP35A1(ROHM)をUART経由でコントロールします。  
Wi-SUNモジュールをコントロールするホストとしてRaspberry Piを想定しています。  
Wi-SUNモジュールのリセットするためのIO及びUART周りをどうにかすれば、他のプラットフォームへの移植の可能でしょう。  

### y3module.py: *class Y3Module*の定義ファイル  
`from y3module import *`って感じでインポートして使います。  
現バージョンでは、２つのWi-SUNモジュール間をTCP, UDPで送受信するだけですが、将来は、スマートメーター（電力量計）にアクセスし、瞬時電力等を取得する予定です。

### y3PingPong.py: Y3Moduleを使ったサンプルスクリプト  
2台のRaspberry Piを使い、1台をコーディネータ、もう1台をデバイスとして起動します。  
デバイスは、コーディネータに対して、UDP（デフォルト）あるいはTCPで「Ping」を送信します。  
それを受信したコーディネーターは、デバイスに対して「Pong」を返信します。  
Pongを受信したデバイスは、Ping送信からPong受信までの経過時間を表示します。  
これを延々と繰り返します。終了するにはCTRL+Cをタイプします。

コーディネーターとして起動するには、  
`python3 y3PingPong.py --mode c`  

デバイスとして起動するには、  
`python3 y3PingPong.py --mode d`  

デフォルトではUDPで送受信します。TCPで送受信するには、デバイスを次のコマンドで起動します。  
`python3 y3PingPong.py --mode d --transport t`  

PingPongのオプションの詳細はヘルプを参照してください。  
`python3 y3PingPong.py --help`  


### バージョン履歴  
0.1a: 初版。２つのWi-SUNモジュール間をUDP,TCPで送受信  
