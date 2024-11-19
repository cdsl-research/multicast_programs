from ina219 import INA219
from machine import SoftI2C, Pin, Timer
import time
from logging import INFO


SHUNT_OHMS = 0.1
i2c = SoftI2C(scl=Pin(22), sda=Pin(21))
ina = INA219(SHUNT_OHMS, i2c, log_level=INFO)
ina.configure()

# GPIO5を入力用に設定（プルダウン抵抗を有効化）
sync_pin = Pin(5, Pin.IN, Pin.PULL_DOWN)

total_power_mw = 0
measure_power = False



def measure_power_callback():
    global total_power_mw, measure_power
    
    voltage = ina.voltage()
    current = ina.current()
    power = voltage * current
    total_power_mw += power
    print(f"Current Power: {power:.3f} mW")
    
def file_exists(filename):
    try:
        os.stat(filename)
        return True
    except OSError:
        return False
    
    
def write_experiment_results_to_csv(filename, completion_time, total_power_mw):
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
            csvfile.write("completion_time, total_power_mw\n")
        # 結果を1行にまとめて書き込む
        csvfile.write(f"{completion_time}, {total_power_mw}\n")

    print(f"Experiment results have been written to {filename}")





def main():
    print("待機中...")
    
    # 初期化時に強制的にLOW状態を待つ
    print("LOW状態になるまで待機...")
    while sync_pin.value() == 1:
        time.sleep_ms(100)
        print(f"現在のピン状態: {sync_pin.value()}")
    
    print("LOW状態を検出、HIGH待機開始")
    
    # HIGH信号を待つ
    while sync_pin.value() == 0:
        time.sleep_ms(10)
    
    print("同期信号を検出: 測定を開始")
    start_time = time.ticks_ms()
    
    # LOW信号になるまで待つ
    while sync_pin.value() == 1:
        measure_power_callback()
        time.sleep_ms(10)
    
    end_time = time.ticks_ms()
    completion_time = time.ticks_diff(end_time, start_time)
    print(f"測定完了: 実行時間 = {completion_time} ミリ秒")
    
    write_experiment_results_to_csv("experiment_total_power_mwE1.csv", completion_time, total_power_mw)
    


if __name__ == "__main__":
    main()