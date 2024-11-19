# 用途・目的

これらのファイルはマルチキャストに関するプログラムである．
クライアントはclient_multicast.pyとclient_ina219，サーバはserver.pyである．これらのプログラムの説明をする．
サーバはsendingFile_750kB.txtから1kBに分割し，750個のパケットを作成する．そのあと，クライアントに向けてマルチキャストをする．もしパケットロスがあれば再送信を行う．

# プログラムの紹介

### client_multicast.py
サーバから750個のパケットを受信するプログラムである．

### client_ina219.py
クライアントの消費電力を測るプログラミングである．測定はクライアントがパケットを受け取り始めてから750個のパケットを受け取るまでである．


### server.py
クライアントに対し，マルチキャストでsendingFile_750kB.txtから1kBに分割し，それらにシーケンス番号を付け，750個のパケットを送信するプログラムである．
またパケットロスが発生した場合，クライアントごとのパケットロスの性質に注目し，同じシーケンス番号であればマルチキャストで，異なっていればユニキャストでの再送信を行う．


## 使用言語
クライアントMicroPython言語で記述されている．
サーバはPythonで記述されている．

## 実行方法

クライアントはESP32を使い，MicroPythonのファームウェアはv1.22.2を使用している．プログラムの記述にはThonnyを用いた．

サーバはESXiに仮想環境を建て，そこにserver.pyとsendingFile_750kB.txtを置いて実行している．仮想環境でPythonファイルを実行する時は，下記の方法からpowershell等で実行する．
```
Python3 ファイル名.py
```

## 注意点
Wi-Fi接続に必要なssidとpasswordを設定する．
マルチキャストアドレスとポートは適切なものを設定する．

## クライアントの実行結果

結果の一部を抜粋


![image](https://github.com/user-attachments/assets/17ce67c3-87c4-4635-885e-b24e1b5319c9)

![image](https://github.com/user-attachments/assets/c6ec4887-ecb5-4beb-ac44-90f3da1ae982)

※消費電力の値は正しいピン配置を行えば取得出来る．




## サーバの実行結果
結果の一部を抜粋

![image](https://github.com/user-attachments/assets/e91ad22e-3f51-42e3-8160-96190bbd833b)







