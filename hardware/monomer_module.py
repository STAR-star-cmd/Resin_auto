import serial
import time
from typing import List, Union

"""
负责液态材料的供给
"""

class FilamentController:
    """
    串口通讯协议类：映射Arduino端的所有控制命令。
    """

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 0.1):
        try:
            self.ser = serial.Serial(port, baudrate, timeout=timeout)
            time.sleep(2)  # 等待Arduino DTR复位重启
            self.ser.reset_input_buffer()
        except serial.SerialException as e:
            raise ConnectionError(f"无法打开串口 {port}: {e}")

    def _send(self, cmd: str) -> None:
        """底层发送方法，自动追加换行符"""
        self.ser.write((cmd + '\n').encode('utf-8'))

    def read_response(self, wait_time: float = 0.5) -> List[str]:
        """
        读取串口缓冲区内的所有可用数据。
        :param wait_time: 等待数据到达的时间(秒)，用于捕获命令执行后的即时反馈。
        """
        time.sleep(wait_time)
        lines = []
        while self.ser.in_waiting:
            line = self.ser.readline().decode('utf-8', errors='ignore').strip()
            if line:
                lines.append(line)
        return lines

    def send_and_read(self, cmd: str, wait_time: float = 0.5) -> List[str]:
        """发送命令并立即读取反馈"""
        self._send(cmd)
        return self.read_response(wait_time)

    # ================= 核心控制命令 =================

    def deliver(self) -> List[str]:
        """启动材料输送序列"""
        return self.send_and_read("DELIVER")

    def test_motors(self) -> List[str]:
        """测试所有活动电机 (正反转各500步)"""
        return self.send_and_read("TEST")

    def stop(self) -> List[str]:
        """紧急停止所有序列与电机"""
        return self.send_and_read("STOP")

    def home(self) -> List[str]:
        """主电机归零 (寻找下限位并设为零点)"""
        return self.send_and_read("HOME")

    # ================= 状态与配置查询 =================

    def get_status(self) -> List[str]:
        """显示所有电机当前位置与状态"""
        return self.send_and_read("STATUS")

    def get_config(self) -> List[str]:
        """显示当前序列参数配置"""
        return self.send_and_read("CONFIG")

    def show_help(self) -> List[str]:
        """打印命令手册"""
        return self.send_and_read("HELP")

    # ================= 参数设置 =================

    def set_param(self, key: str, value: Union[int, float]) -> List[str]:
        """
        设置系统参数
        :param key: 参数名 (EXT0-3, RET0-3, PUMP1-2, POS0-5)
        :param value: 参数值
        """
        return self.send_and_read(f"SET {key.upper()} {int(value)}")

    # ================= 手动移动与触发 =================

    def move_extruder(self, ext_id: int, steps: int) -> List[str]:
        """
        移动挤出机
        :param ext_id: 挤出机ID (0-3)
        :param steps: 步数 (正数挤出，负数回吸)
        """
        if not 0 <= ext_id <= 3:
            raise ValueError("ext_id 必须在 0-3 之间")
        return self.send_and_read(f"E{ext_id} {int(steps)}")

    def move_main(self, steps: int) -> List[str]:
        """移动主电机 (相对移动)"""
        return self.send_and_read(f"M {int(steps)}")

    def trigger_pump(self, pump_id: int, ms: int) -> List[str]:
        """
        触发气泵
        :param pump_id: 气泵ID (1 或 2)
        :param ms: 触发持续时间(毫秒)
        """
        if pump_id not in (1, 2):
            raise ValueError("pump_id 必须是 1 或 2")
        return self.send_and_read(f"P{pump_id} {int(ms)}")

    def close(self):
        """关闭串口连接"""
        if self.ser.is_open:
            self.ser.close()


if __name__ == "__main__":
    PORT = 'COM7'
    ctrl = FilamentController(PORT)
    try:
        # 2. 测试基础查询命令
        print("--- 获取当前配置 ---")
        for line in ctrl.get_config():
            print(line)

        # 4. 测试手动控制
        print("\n--- 触发 1号气泵 500ms ---")
        print(ctrl.trigger_pump(1, 500))

        # 5. 处理长时间运行的序列 (如 TEST)
        print("\n--- 启动电机测试 (异步轮询读取状态) ---")
        ctrl._send("TEST")  # 仅发送，不等待

        # 轮询读取串口输出，直到测试完成
        start_time = time.time()
        while time.time() - start_time < 15:  # 假设测试最多15秒
            logs = ctrl.read_response(wait_time=0.2)
            for log in logs:
                print(f"[LOG] {log}")
                if "TEST COMPLETE" in log:
                    break
            if any("TEST COMPLETE" in log for log in logs):
                break

    except KeyboardInterrupt:
        print("\n用户中断，执行紧急停止...")
        ctrl.stop()
    finally:
        ctrl.close()