import network
import usocket as socket
import uasyncio as asyncio
import json
import machine
import utime
import time
import select
import gc
import _thread
import struct
import machine
import os

from machine import I2C, Pin


# ウォッチドッグタイマーの設定
program_start_time = time.time()
PROGRAM_TIMEOUT = 300  # 10分（600秒）のタイムアウト
# 定期的なデータ保存用の変数
last_save_time = time.time()
SAVE_INTERVAL = 10  # 60秒ごとに保存
program_finished = False
csv_flag = False
duplicate_csv_flag = False
file_write_counter = 0


send_finished = False

# Global variables
sta_if = network.WLAN(network.STA_IF)
rssi_status = 0
received_sequence_numbers = set()
total_packets = 750
packet_loss_list = []
new_access = 0

# グローバル変数に追加
duplicate_packets = 0
# グローバル変数の修正
retransmission_loss_list = []
# グローバル変数に追加
program_finished = False
# グローバル変数のセクションに追加
timeout_thread_running = False
#グローバル変数に強制離脱用のフラグを追加
reset_phase_flag = False

packet_loss = []
last_seq = -1
timeout = 1  # seconds
# 定数
DMG_IP = '239.255.255.250'
DMG_PORT = 50006
PMG_IP = '239.255.255.240'
PMG_PORT = 50001
SERVER_IP = ''  # サーバのIPアドレス
SERVER_PORT = 50005
CLIENT_IP = ''
CLIENT_PORT = 50003

UNICAST_PORT = 50007  # ユニキャスト用のポート
in_pmg = False  # PMGに参加しているかどうかのフラグ
unicast_sock = None

unicast_duplicate_packets = 0

select_timeout = 3.0

# GPIO4を出力用に設定
sync_pin = Pin(4, Pin.OUT)

    
    #CSV1つにした
def write_experiment_results_to_csv(filename, completion_time, duplicate_packets_count,unicast_duplicate_packets):
    """
    completion_time: プログラムの完了時間
    duplicate_packets_count: 重複パケットの数
    total_power_mw:総処理電力
    """

    # ファイルが存在するかどうかをチェック
    if file_exists(filename):
        mode = 'a'
    else:
        mode = 'w'

    with open(filename, mode) as csvfile:
        # 新しいファイルの場合、ヘッダーを書き込む
        if mode == 'w':
            csvfile.write("Completion Time (seconds), Duplicate Packets,unicast_duplicate_packets_conut\n")
        # 結果を1行にまとめて書き込む
        csvfile.write(f"{completion_time}, {duplicate_packets_count},{unicast_duplicate_packets}\n")

    print(f"Experiment results (Completion Time: {completion_time} seconds, Duplicate Packets: {duplicate_packets_count}) have been written to {filename}")


            
# キューの代わりにリストを使用する関数
def add_to_retransmission_loss(loss):
    global retransmission_loss_list
    retransmission_loss_list.append(loss)

def get_from_retransmission_loss():
    global retransmission_loss_list
    if retransmission_loss_list:
        return retransmission_loss_list.pop(0)
    return None            



def inet_aton(ip):
    parts = [int(part) for part in ip.split('.')]
    return bytes(parts)

def connect_wifi(ssid, password):
    global sta_if
    if not sta_if.isconnected():
        print('Connecting to WiFi...')
        sta_if.active(True)
        sta_if.connect(ssid, password)
        timeout = 30  # 30 seconds timeout for WiFi connection
        start_time = utime.time()
        while not sta_if.isconnected():
            if utime.time() - start_time > timeout:
                print('Failed to connect to WiFi: Timeout')
                return False
            time.sleep(1)
    print('Network configuration:', sta_if.ifconfig())
    return True

# マルチキャストソケットの設定を変更
def setup_multicast_socket():
    global mcast_sock
    mcast_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    mcast_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    mcast_sock.bind(('0.0.0.0', DMG_PORT))
    mreq = inet_aton(DMG_IP) + inet_aton('0.0.0.0')
    mcast_sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    return mcast_sock

# ユニキャストソケットの設定
def setup_unicast_socket():
    global unicast_sock
    unicast_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    unicast_sock.bind(('0.0.0.0', UNICAST_PORT))
    unicast_sock.setblocking(False)
    return unicast_sock

async def receive_multicast(mcast_sock):
    global sta_if, rssi_status, received_sequence_numbers, last_seq, packet_loss_list, in_pmg, duplicate_packets,send_finished,PROGRAM_TIMEOUT,new_access, program_start_time,reset_phase_flag,total_packets,select_timeout
    start_time = time.time()
    missing_packets = print_missing_packets()
    select_timeout = 10.0

    
    

    while len(received_sequence_numbers) < total_packets:
        try:
            ready = select.select([mcast_sock], [], [], select_timeout)
            #ここ2.0秒にする案
            if ready[0]:
                if new_access == 0:
                    print("start")
                    # 同期信号をHIGHに設定
                    sync_pin.value(1)
                    program_start_time = time.time()#プログラム開始
                    new_access += 1
                    # 電力監視タスクを開始
                    select_timeout = 3.0 #########
                data, addr = mcast_sock.recvfrom(2048)
                if not data:
                    continue
                 

                received_message = json.loads(data.decode('utf-8'))
                #print(f"Received message: {received_message}")
                missing_packets = print_missing_packets()
        
                # receive_multicast 関数内の該当部分を以下のように更新
                if "resend_notification" in received_message:
                    print("resend_notification")
                    common_packets, last_resend_number= handle_resend_notification(received_message)

                    
                    send_finished = True
                    reset_phase_flag = True
                    if len(received_sequence_numbers) >= total_packets:
                        PROGRAM_TIMEOUT = 0
                    if common_packets:
                        #スレッドにする？
                        await receive_retransmission(2, common_packets,last_resend_number)
                        #_thread.start_new_thread(receive_retransmission, ())
                        #select_timeout = 1.0
                    else:
                        select_timeout = 3.0
                    continue
                
                if "unicast_notification" in received_message and missing_packets:
                    print("unicast_notification")
                    client_ip = received_message.get("client_ip")
                    if client_ip != CLIENT_IP:  # CLIENT_IPはこのクライアントのIP
                        print(f"Received unicast notification for {client_ip}, waiting for our turn")
                        equal_CLIENT_IP = False
                        select_timeout = 3.0
                        continue
                    else:
                        select_timeout = 1.0
                        equal_CLIENT_IP = True
                    print("Received unicast notification")
                    send_finished = True
                    reset_phase_flag = True
                    first_received_message = received_message
                    print("unicast_marge")
                    SERVER_IP = received_message.get("server_ip")
                    #loss_list = received_message.get("loss_list", [])
                    print(f"Unicast notification - Server IP: {SERVER_IP}")
                    if missing_packets:
                        print(f"Starting unicast reception from {SERVER_IP}")
                        await receive_unicast()
                    continue

                if "sequence_number" in received_message:
                   
                    received_sequence_number = received_message["sequence_number"]
                    print(f"Received sequence: {received_sequence_number}, in_pmg: {in_pmg}")
                    if in_pmg:
                        if received_sequence_number in missing_packets:
                            print(f"Received retransmitted packet: {received_sequence_number}")
                            received_sequence_numbers.add(received_sequence_number)
                            missing_packets.remove(received_sequence_number)
                        else:
                            print(f"Received packet {received_sequence_number} not in loss list")
                    else:
                        if "end" in received_message and received_sequence_number == total_packets:
                            print("Received end of transmission message.")
                            return

                        received_sequence_numbers.add(received_sequence_number)
                        #rssi_status = sta_if.status("rssi")

                        if last_seq != -1 and received_sequence_number != last_seq + 1:
                            for missing_seq in range(last_seq + 1, received_sequence_number):
                                packet_loss_list.append(missing_seq)
                                #missing_packets.append(missing_seq)
                        last_seq = received_sequence_number
                    if len(received_sequence_numbers) > 740:
                        missing_packets = print_missing_packets()
                        print(f"Current missing_packets: {missing_packets}")
            else:
                if send_finished:                    
                    missing_packets = print_missing_packets()
                    send_packet_loss(missing_packets)

        except Exception as e:
            print(f"Error receiving multicast message: {e}")

    print("Multicast reception timeout reached.")


def send_packet_loss(loss_list):
    global SERVER_IP, SERVER_PORT, packet_loss_list, CLIENT_IP
    
    if not loss_list:
        print("No packet loss to send")
        return
    
    loss_message = json.dumps({"lost_packets": list(loss_list)})
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        #print(f"Actual data being sent: {loss_message}")
        #print(f"Attempting to send packet loss to {SERVER_IP}:{SERVER_PORT}")
        bytes_sent = s.sendto(loss_message.encode('utf-8'), (SERVER_IP, SERVER_PORT))
        packet_loss_list = []
    except Exception as e:
        print(f"Error sending packet loss list: {e}")
    finally:
        s.close()


# check_timeout 関数を修正
def check_timeout():
    global packet_loss_list, retransmission_loss_list, program_finished, timeout_thread_running,send_finished
    timeout_thread_running = True
    while not send_finished:
        time.sleep(timeout)
        if program_finished:
            break
        if packet_loss_list:
            print("check_timeout")
            send_packet_loss(packet_loss_list)
            packet_loss_list = []
        
    timeout_thread_running = False
    print("check_timeout thread terminated")

    
    
    

def handle_resend_notification(notification):
    global in_pmg,common_packets
    missing_packets = print_missing_packets()
    if missing_packets is None:
        print("Error: missing_packets is None")
        return  # または適切なエラー処理
        
    resend_list = notification.get("resend_list", [])
    print(f"Received resend notification. Resend list: {resend_list}")
    
    if not isinstance(missing_packets, (list, set)):
        print(f"Error: missing_packets is of type {type(missing_packets)}")
        return  # または適切なエラー処理
        
    
    
    # 両方をセットに変換して共通部分を取得
    try:
        common_packets = sorted(set(resend_list) & set(missing_packets))
    except TypeError as e:
        print(f"Error converting to sets: {e}")
        print(f"resend_list type: {type(resend_list)}, content: {resend_list}")
        print(f"missing_packets type: {type(missing_packets)}, content: {missing_packets}")
        return  # または適切なエラー処理


    # 空のリストチェック
    if not common_packets or not resend_list:
        print("No common packets found or resend list is empty")
        return  # または適切なエラー処理




    #共通あり再送信フェーズの条件分岐
    last_element_A = resend_list[-1]
    last_element_B = list(common_packets)[-1]
    
    if last_element_A == last_element_B:
        last_resend_number = last_element_B
    else:
        index_in_listB = list(common_packets).index(last_element_A)
        last_resend_number = list(common_packets)[index_in_listB + 1:]
    
    if common_packets:
        in_pmg = True
        join_pmg()
        print(f"Set in_pmg to True and joined PMG. in_pmg is now: {in_pmg}")
        print(f"Common packets to receive: {common_packets}")
        return list(common_packets), last_resend_number
    else:
        in_pmg = False
        print(f"No matching packets in missing_packets. in_pmg is now: {in_pmg}")
        return []
    
def join_pmg():
    global mcast_sock, in_pmg
    try:
        mreq = inet_aton(PMG_IP) + inet_aton('0.0.0.0')
        mcast_sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        print(f"Joined PMG group: {PMG_IP}")
        in_pmg = True
        # ソケットの現在の設定を確認
        print("Successfully joined PMG group")
    except Exception as e:
        print(f"Error joining PMG group: {e}")

def handle_unicast_notification(notification):
    global SERVER_IP, CLIENT_IP
    missing_packets = print_missing_packets()
    server_ip = notification.get("server_ip")
    client_ip = notification.get("client_ip")
    
    if client_ip != CLIENT_IP:
        print(f"Received unicast notification for {client_ip}, not for us")
        return

    if set(loss_list) & set(missing_packets):
        SERVER_IP = server_ip
        receive_unicast()
        
# ユニキャスト受信の新しい関数
async def receive_unicast():
    global unicast_sock, received_sequence_numbers, program_finished,duplicate_packets,csv_flag,PROGRAM_TIMEOUT,unicast_duplicate_packets

    print(f"Listening for unicast on port {UNICAST_PORT}")
    retransmission_loss = []  # Initialize here
    missing_packets = print_missing_packets()
    equal_CLIENT_IP = False
    
    select_timeout = 3.0 #初回はながく

    
    start_time = time.time()
    #while keep_packet_loss_list or (time.time() - start_time) < PROGRAM_TIMEOUT:  # 最大60秒間受信を試みる
    while missing_packets :  # 最大60秒間受信を試みる
        try:
            ready = select.select([unicast_sock], [], [], select_timeout)
            if ready[0]:
                
                select_timeout = 1.0 #次回から短く
                
                data, addr = unicast_sock.recvfrom(2048)
                received_message = json.loads(data.decode('utf-8'))
                                    
                received_sequence_number = received_message["sequence_number"]
                print(f"Received unicast packet: {received_sequence_number}")
                print(f"NOW loss list: {missing_packets}")
                if received_sequence_number in received_sequence_numbers:
                    unicast_duplicate_packets += 1
                    print(f"Duplicate packet detected. Total duplicates: {unicast_duplicate_packets}")

                if received_sequence_number in missing_packets:
                    received_sequence_numbers.add(received_sequence_number)
                    missing_packets = print_missing_packets()
                    #common_packets.remove(received_sequence_number)
                    print(f"Remaining loss list: {missing_packets}")
                    now_count = 750 - len(received_sequence_numbers)
                    print(f"now:{now_count}")
                
                missing_packets = print_missing_packets()


            else:
                print("再送中")
                missing_packets = print_missing_packets()
                send_packet_loss(missing_packets)
                break
                            
                
        except Exception as e:
            print(f"Error in unicast reception: {e}")
                
    print("All packets received. Writing duplicate packets count and ending program.")

    return 0
#ここ

async def receive_retransmission(timeout_sec, common_packets,last_resend_number):
    global received_sequence_numbers, packet_loss_list, duplicate_packets, program_finished, PROGRAM_TIMEOUT, reset_phase_flag

    print("Starting retransmission reception...")
    start_time = time.time()
    
    PMG_mcast_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    PMG_mcast_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    PMG_mcast_sock.bind(('0.0.0.0', PMG_PORT))
    
    mreq = inet_aton(PMG_IP) + inet_aton('0.0.0.0')
    PMG_mcast_sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    
    select_timeout = 3.0 #初回はながく

    while common_packets:
        try:
            ready = select.select([PMG_mcast_sock], [], [], select_timeout)

            if ready[0]:
                select_timeout = 1.0 #次回から短く

                data, addr = PMG_mcast_sock.recvfrom(2048)
                if data:
                    received_message = json.loads(data.decode('utf-8'))
                    received_sequence_number = received_message["sequence_number"]
                    print(f"resend:{received_sequence_number}")
                    print(f"common_packets:{common_packets}")

                    if received_sequence_number in common_packets:
                        received_sequence_numbers.add(received_sequence_number)
                        common_packets.remove(received_sequence_number)
                        print(f"Received retransmitted packet: {received_sequence_number}")
                    elif received_sequence_number in last_resend_number:
                        #自分が受け取るものがもうないからbreak
                        print("Final packet loss request for remaining packets...")
                        send_packet_loss(common_packets)
                        break
                    
                    else:
                        print(f"Received unexpected packet: {received_sequence_number}")
                        if received_sequence_number in received_sequence_numbers:
                            duplicate_packets += 1
                            print(f"Duplicate packet detected. Total duplicates: {duplicate_packets}")  
            else:
                print("Timeout reached. Sending packet loss request...")
                break

        except Exception as e:
            print(f"Error in retransmission reception: {e}")

    PMG_mcast_sock.close()
    
def file_exists(filename):
    try:
        os.stat(filename)
        return True
    except OSError:
        return False
    
def receive_experiment_count():
    global SERVER_IP
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('239.255.255.251', 50008))
    mreq = b''.join([inet_aton('239.255.255.251'), inet_aton('0.0.0.0')])

    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    while True:
        try:
            data, addr = sock.recvfrom(1024)
            SERVER_IP = addr[0]
            message = json.loads(data.decode('utf-8'))
            if "experiment_count" in message:
                print(f"Received experiment count: {message['experiment_count']}")
                return message['experiment_count']
        except Exception as e:
            print(f"Error receiving experiment count: {e}")
        
        time.sleep(1)  # 1秒待機してから再試行
    sock.close()
 
        
def start_up():
    global last_count, file_write_counter
    print("start_up_ok")

    # まず、received_count.txtから最後の実験回数を読み取る
    try:
        with open('received_count.txt', 'r') as f:
            lines = f.readlines()
            last_count = int(lines[-1].strip()) if lines else 0
    except Exception as e:
            print(f"Error receiving experiment count: {e}")
            last_count = 0
    
    print(f"Last recorded experiment count: {last_count}")

    # サーバーから新しい実験回数を受け取る
    received_count = receive_experiment_count()
    print(f"Received experiment count from server: {received_count}")

    

    if received_count == last_count + 1:
        print("正常に次の実験を開始します")
    elif received_count > last_count + 1:
        print(f"警告: 実験回数が飛んでいます。{last_count + 1}から{received_count - 1}までの実験データが欠落している可能性があります")
        for missing_count in range(last_count+1, received_count):
            write_experiment_results_to_csv("experiment_resultsE1.csv", "missing", "missing", "missing")
            write_file('received_count.txt', missing_count)
            print(f"last:{missing_count}")

    else:
        print(f"エラー: 受信した実験回数({received_count})が前回の実験回数({last_count})以下です")
    
    last_count = received_count
    file_write_counter = received_count
    print(f"実験を開始します。実験回数: {last_count}")

def write_file(filename, content):
    with open(filename, 'a') as f:
        f.write(f"\n{content}")  # Write content on a new line

def print_missing_packets():
    global received_sequence_numbers
    all_packets = set(range(750))
    missing_packets = all_packets - received_sequence_numbers
    
    return missing_packets  # Return the missing_packets set
    
async def main():
    global sta_if, packet_loss_list, in_pmg, mcast_sock, unicast_sock, program_finished, duplicate_packets, program_start_time,CLIENT_IP,unicast_duplicate_packets,received_sequence_numbers

    ssid = "your_ssid"
    password = "your_password"

    if connect_wifi(ssid, password):
        machine.Pin(2, machine.Pin.OUT).value(1)
        start_up()
        print('Network configuration:', sta_if.ifconfig())
        ip_info = sta_if.ifconfig()
        CLIENT_IP = ip_info[0]
        program_start_time = time.time()
        while not program_finished:
            try:
                # タイムアウトチェック
                if time.time() - program_start_time > PROGRAM_TIMEOUT:
                    print("Program timeout reached. Saving data and exiting.")
                    program_finished = True
                    break

                mcast_sock = setup_multicast_socket()
                unicast_sock = setup_unicast_socket()
                
                print("Socket created successfully")
                print("Joined multicast group successfully")
                print("Starting multicast reception...")
                
                await receive_multicast(mcast_sock)  # 120 seconds timeout

                #非同期処理からかえあた
                print("Multicast reception completed.")
                print("-----------------------------------------------------")
                missing_packets = print_missing_packets()
                print(f"in_pmg flag after multicast reception: {in_pmg}")
                

                if len(received_sequence_numbers) >= total_packets:
                     # プログラム終了時に同期信号をLOWに設定
                    sync_pin.value(0)
                    completion_time = time.time() - program_start_time
                    print("All packets received. Writing duplicate packets count and ending program.")                   
                    write_experiment_results_to_csv("experiment_resultsE1.csv", completion_time, duplicate_packets,unicast_duplicate_packets)
                    # received_count.txtに新しい実験回数を追加
                    write_file('received_count.txt', file_write_counter)

                    program_finished = True
                    print(f"dupli_counter:mauti is {duplicate_packets}, uni is {unicast_duplicate_packets}")
                    #print(f"thread:{program_finished}")
                    machine.Pin(2, machine.Pin.OUT).value(0)
                    
                    no_list = []
                    
                    #終わりに
                    finish_message = json.dumps({"no_packets": list(no_list)})
                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    bytes_sent = s.sendto(finish_message.encode('utf-8'), (SERVER_IP, SERVER_PORT))
                    print(f"finished_data")   
                    s.close()
                    break

            except Exception as e:
                print(f"Error in main loop: {e}")
                
            finally:
                if mcast_sock:
                    mcast_sock.close()
                if unicast_sock:
                    unicast_sock.close()
                if program_finished:
                    break
                await asyncio.sleep(1)
                
    else:
        print("Failed to connect to Wi-Fi")

if __name__ == "__main__":
    try:
        _thread.start_new_thread(check_timeout, ())
        asyncio.run(main())
    except Exception as e:
        print(f"Error running main: {e}")
    finally:
        program_finished = True
        # check_timeoutスレッドの終了を待つ
        _thread.exit()
        while timeout_thread_running:
            time.sleep(0.1)
        print("Program execution completed")
