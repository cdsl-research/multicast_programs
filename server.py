import socket
import json
import time
import threading
import select
from collections import defaultdict, Counter
import os
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed


DMG_IP = '239.255.255.250'
DMG_PORT = 50006
PMG_IP = '239.255.255.240'
PMG_PORT = 50001
TOTAL_PACKETS = 750
PACKET_SIZE = 1000
SERVER_IP = '192.168.100.82'
SERVER_PORT = 50005
UNICAST_PORT = 50007
has_recorded_loss_list = False
# グローバル変数として、キューを追加
packet_loss_queue = queue.Queue()


#本当はこっちの方が良い
time_sleep = 1

#送信間隔
delay_per_packet = 0.1

new_access = 0



# グローバル変数の宣言
sorted_duplicates = []
unique_losses = defaultdict(list)

LOCALHOST = socket.gethostbyname(socket.gethostname())
print(f"Local IP: {LOCALHOST}")

def write_packet_loss_to_file(packet_loss_list, filename="ato_combined_packet_loss.txt"):
    with open(filename, 'a') as file:
        file.write(f"Combined packet loss list: {packet_loss_list}\n")
    print(f"Packet loss list written to {filename}")

packet_loss_dict = defaultdict(list)

def record_unique_resend_sequences():
    global sorted_duplicates, unique_losses,has_recorded_loss_list

    if has_recorded_loss_list:
        return []  # 既に記録済みの場合は空リストを返す
    all_resend_sequences = set()
    # マルチキャスト再送信のシーケンス番号を収集
    for seq in sorted_duplicates:
        all_resend_sequences.add(seq)
        
    # マルチキャスト再送信のシーケンス番号を収集
    #for seq, _ in sorted_duplicates:
     #   all_resend_sequences.add(seq)
    
    # ユニキャスト再送信のシーケンス番号を収集
    for losses in unique_losses.values():
        all_resend_sequences.update(losses)
    # セットをリストに変換し、ソート
    unique_resend_list = sorted(list(all_resend_sequences))
    # ファイルに書き込み
    write_packet_loss_to_file(unique_resend_list)
    has_recorded_loss_list = True  # 記録済みフラグを立てる

    return unique_resend_list

def send_multicast_message(message, sock, ip, port):
    try:
        sock.sendto(json.dumps(message).encode('utf-8'), (ip, port))
    except socket.error as e:
        if e.errno != 10035:  # WSAEWOULDBLOCK
            raise

def send_resend_notification(sock, resend_list):
    notification = {
        "resend_notification": True,
        "resend_list": resend_list,
    }
    #time.sleep(time_sleep)
    send_multicast_message(notification, sock, DMG_IP, DMG_PORT)
    print(f"Sent resend notification for packets: {resend_list}")
     # デバッグ用に追加
    print(f"Notification sent to {DMG_IP}:{DMG_PORT}")
    print(f"Notification content: {notification}")

def handle_packet_loss(data, addr):
    try:
        packet_loss = json.loads(data.decode('utf-8'))
        print(f"PL_list:{packet_loss}")
        ip_address = addr[0]
        
        #packet_loss_dict[ip_address].update(packet_loss)
        for values in packet_loss.values():
            packet_loss_dict[ip_address].extend(x for x in values if x not in packet_loss_dict[ip_address])

        print(f"Updated packet loss report for {ip_address}")
        
    except Exception as e:
        print(f"Error in handle_packet_loss: {e}")

def receive_packet_loss():
    global packet_loss_queue
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('', SERVER_PORT))
    print(f"Listening for packet loss reports on port {SERVER_PORT}")

    with ThreadPoolExecutor(max_workers=4) as executor:  # スレッド数は必要に応じて調整
        future_to_data = {}
        while True:
            try:
                ready = select.select([s], [], [], 5.0)
                if ready[0]:
                    data, addr = s.recvfrom(2048)
                    future = executor.submit(handle_packet_loss, data, addr)
                    future_to_data[future] = (data, addr)                   
                else:
                    print("No data received in the last 5 seconds")

                # 完了したタスクの処理
                for future in as_completed(future_to_data):
                    data, addr = future_to_data[future]
                    try:
                        future.result()
                    except Exception as exc:
                        print(f'Task generated an exception: {exc}')
                    del future_to_data[future]

            except Exception as e:
                print(f"Error in receive_packet_loss: {e}")

    s.close()


def deduplicate_unique_losses(unique_losses):
    """
    unique_lossesの各IPアドレスに対するシーケンス番号のリストから重複を排除します。
    """
    return {ip: sorted(set(losses)) for ip, losses in unique_losses.items()}

def analyze_packet_loss():
    global sorted_duplicates, unique_losses
    print("analyze_packet_loss")
    duplicates = defaultdict(set)
    unique_losses = defaultdict(list)
    all_losses = []  # リストではなくセットを使用
    
    delete_list = []
    
    
    for ip, losses in packet_loss_dict.items():
        for loss in losses:
            if loss in all_losses:
                duplicates[loss].add(ip)
                
           
                for key, loss_list in unique_losses.items():
                    if loss in loss_list:
                        #print(f"loss {loss} は {key} の unique_losses にあります。")
                        delete_list.append((key,loss))
                #11/14の続き     
           

                
            else:
                unique_losses[ip].append(loss)
            all_losses.append(loss)
    
    # delete_list にある loss を unique_losses から削除
    if delete_list:
       for ip, value in delete_list:
        if ip in unique_losses and value in unique_losses[ip]:
            unique_losses[ip].remove(value)
    

    duplicate_counts = {seq: len(ips) - 1 for seq, ips in duplicates.items()}
    #print(duplicate_counts)
    sorted_duplicates =sorted(duplicate_counts.keys())
    
    # パケットロス情報をクリア
    #packet_loss_dict.clear()

    return duplicates, unique_losses, sorted_duplicates

def resend_lost_packets(chunks):
    global sorted_duplicates, unique_losses,new_access
    duplicates, unique_losses, sorted_duplicates = analyze_packet_loss()
    temp_unique_losses = unique_losses.copy()


    if new_access == 0:
        record_unique_resend_sequences()
        new_access += 1

    #DMG

    resend_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    resend_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    resend_sock.setblocking(False)

    if sorted_duplicates:
        send_resend_notification(resend_sock, sorted_duplicates)
        time.sleep(delay_per_packet)

    
    
    # マルチキャスト再送信
    while sorted_duplicates:
        seq_num = sorted_duplicates[0]  # 最初の要素を取得
        if 0 <= seq_num < TOTAL_PACKETS:
            chunk = chunks[seq_num].ljust(PACKET_SIZE, '\0')
            message = {
                "sequence_number": seq_num,
                "data": chunk,
            }
            send_multicast_message(message, resend_sock, PMG_IP, PMG_PORT)
            print(f"Resent packet {seq_num}")
            time.sleep(delay_per_packet)
            
            # 送信したパケットの削除
            sorted_duplicates.remove(seq_num)
            # packet_loss_dictからも削除
            for ip in list(packet_loss_dict.keys()):
                if seq_num in packet_loss_dict[ip]:
                    packet_loss_dict[ip].remove(seq_num)   
    time.sleep(time_sleep)          
        
    # ユニキャスト再送信と追加のパケットロス処理
    persistent_unicast_resend(resend_sock, chunks,unique_losses)

def persistent_unicast_resend(resend_sock, chunks,unique_losses):
    #global unique_losses, sorted_duplicates
    no_new_reports_count = 1
    max_no_new_reports = 1

    while unique_losses:
        clients_to_remove = []
        unique_losses = deduplicate_unique_losses(unique_losses)
        print(unique_losses)

        # ユニキャスト再送信
        for ip, losses in unique_losses.items():
            if losses:
                send_unicast_notification(resend_sock, ip, losses)
                time.sleep(delay_per_packet)
                #time.sleep(time_sleep)
                successfully_sent = []

                for seq_num in losses:
                    if 0 <= seq_num < TOTAL_PACKETS:
                        chunk = chunks[seq_num].ljust(PACKET_SIZE, '\0')
                        message = {
                            "sequence_number": seq_num,
                            "data": chunk,
                            "resend": True
                        }
                        resend_sock.sendto(json.dumps(message).encode('utf-8'), (ip, UNICAST_PORT))
                        print(f"Unicast resent packet {seq_num} to {ip}")
                        successfully_sent.append(seq_num)
                        time.sleep(delay_per_packet)

                unique_losses[ip] = [seq for seq in losses if seq not in successfully_sent]

# この辺にunique_losses[ip]のpacket_loss_dictを消す
                if ip in packet_loss_dict:
                    packet_loss_dict[ip] = [seq for seq in packet_loss_dict[ip] if seq not in successfully_sent]
                    print(f"unicast_resent_finish IP {ip}: {packet_loss_dict[ip]}")
                    if not packet_loss_dict[ip]:
                        del packet_loss_dict[ip]
                        print(f"Removed empty loss list for IP {ip} from packet_loss_dict")

        print(f"unique_losses:{unique_losses}")
        print("Waiting for additional packet loss reports...")
        wait_start_time = time.time()
        new_reports_received = False
        break


def send_unicast_notification(sock, ip, loss_list):
    notification = {
        "unicast_notification": True,
        "server_ip": LOCALHOST,
        "client_ip": ip
    }
    sock.sendto(json.dumps(notification).encode('utf-8'), (DMG_IP, DMG_PORT))
    #sock.sendto(json.dumps(notification).encode('utf-8'), (ip, UNICAST_PORT))

    print(f"Sent unicast notification to IP: {ip}")

def main():
    global sorted_duplicates, unique_losses,packet_loss_dict
    receive_thread = threading.Thread(target=receive_packet_loss, daemon=True)
    receive_thread.start()

    chunks = []
    FILE_NAME = 'sendingFile_750KB.txt'
    with open(FILE_NAME, 'r') as f:
        for line in f:
            line = line.strip()
            chunks.append(line[:PACKET_SIZE])

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    sock.setblocking(False)

    initial_message = {"total_packets": TOTAL_PACKETS}
    send_multicast_message(initial_message, sock, DMG_IP, DMG_PORT)
    print(f"Sent initial message: {initial_message}")
    # 送信開始時間を記録
    start_time = time.time()
    for i in range(TOTAL_PACKETS):
        chunk = chunks[i].ljust(PACKET_SIZE, '\0')
        message = {
            "sequence_number": i,
            "data": chunk
        }
        send_multicast_message(message, sock, DMG_IP, DMG_PORT)
        print(f"Sent packet {i}")
        time.sleep(delay_per_packet)
     # 送信終了時間を記録
    end_time = time.time()

    # 送信にかかった時間を計算
    transmission_time = end_time - start_time
    print(f"Total transmission time: {transmission_time:.2f} seconds")
    for ip_address, packet_loss in packet_loss_dict.items():
        print(f"Final packet loss report for {ip_address}: {packet_loss}")


    # dict が空かどうかをチェックする間隔（秒）
    check_interval = 0.1  # 100ms など
    # 最大待機時間（秒）
    max_wait_time = 2
    elapsed_time = 0

    while True:
        print("Waiting for packet loss reports...")
        time.sleep(time_sleep*2)
        #print(f"Macdonald:{packet_loss_dict}")
        resend_lost_packets(chunks)
        print("sleep:eternal_send_wait_PLlist")
        if not packet_loss_dict:
            
            if elapsed_time >= max_wait_time:
                print("Breaking out after waiting")
                #break
            # スリープ間隔を小さくして、dict を定期的にチェックする
            time.sleep(check_interval)
            elapsed_time += check_interval
        else:
            # dict が空でなくなったらループを継続
            print("Dict is now not empty, continuing")

def read_experiment_count():
    filename = 'ato_experiment_count.txt'
    if not os.path.exists(filename):
        with open(filename, 'w') as f:
            f.write("1\n")
        return 1

    try:
        with open(filename, 'r') as f:
            lines = f.readlines()
            if lines:
                return int(lines[-1].strip())
            else:
                # ファイルが空の場合
                with open(filename, 'w') as f:
                    f.write("1\n")
                return 1
    except ValueError:
        # ファイルの内容が不正な場合
        with open(filename, 'w') as f:
            f.write("1\n")
        return 1

def write_experiment_count(count):
    with open('ato_experiment_count.txt', 'a') as f:
        f.write(f"{count}\n")


def start_up():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)

    current_count = read_experiment_count()

    message = {
        "experiment_count": current_count
    }

    try:
        sock.sendto(json.dumps(message).encode('utf-8'), ('239.255.255.251', 50008))
        print(f"Sent experiment count {current_count} to {DMG_IP}:{DMG_PORT}")
    except Exception as e:
        print(f"Error sending experiment count: {e}")
    finally:
        sock.close()

    write_experiment_count(current_count + 1)

    # マルチキャスト実験の実行（ここに実験のコードを追加）
    time.sleep(5)  # 実験の代わりに5秒待機



if __name__ == "__main__":
    start_up()
    main()