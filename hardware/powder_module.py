import serial
import time

"""
负责固态材料的供给
"""

class StepperController:
    def __init__(self, port, baudrate=115200):
        """
        初始化串口连接。
        """
        self.ser = serial.Serial(port, baudrate, timeout=1)
        time.sleep(2)  # 等待 Arduino 复位并跳过 Bootloader
        self.ser.reset_input_buffer()  # 清除启动时的乱码

    def _send(self, cmd: str) -> str:
        """核心收发管道：清理缓冲 -> 发送 -> 等待 -> 读取"""
        self.ser.reset_input_buffer()
        self.ser.write((cmd + '\n').encode('utf-8'))
        self.ser.flush()

        time.sleep(0.2)  # 给 Arduino 留出执行和 Serial.println 的时间

        response = b""
        while self.ser.in_waiting:
            response += self.ser.read(self.ser.in_waiting)
            time.sleep(0.05)  # 确保长文本分片接收完整

        return response.decode('utf-8', errors='ignore').strip()

    def close(self):
        if self.ser.is_open:
            self.ser.close()

    # ================= 核心控制指令 =================

    def stop(self) -> str:
        """急停 (ESTOP)"""
        return self._send("STOP")

    def reset(self) -> str:
        """清除急停状态"""
        return self._send("RESET")

    def home(self) -> str:
        """主电机 M2 自动回零 (寻找 DOWN 限位)"""
        return self._send("HOME")

    def deliver(self) -> str:
        """启动完整的投料序列"""
        return self._send("DELIVER")

    # ================= 状态与配置指令 =================

    def get_pos(self) -> str:
        """获取 M2 当前位置"""
        return self._send("POS")

    def zero(self) -> str:
        """强制将 M2 当前位置设为零点"""
        return self._send("ZERO")

    def status(self) -> str:
        """打印所有电机状态、限位开关及序列进度"""
        return self._send("STATUS")

    def help(self) -> str:
        """获取 Arduino 端帮助文档"""
        return self._send("HELP")

    def set_feeder_steps(self, feeder_id: int, steps: int) -> str:
        """动态修改给料电机投递步数 (F0/F1/F2)"""
        assert feeder_id in (0, 1, 2), "Feeder ID 必须是 0, 1 或 2"
        return self._send(f"F{feeder_id}_STEP={steps}")

    # ================= 运动控制指令 =================

    def move_m_relative(self, steps: int) -> str:
        """主电机 M2 相对移动"""
        return self._send(f"M{steps}")

    def move_m_absolute(self, pos: int) -> str:
        """主电机 M2 绝对位置移动"""
        return self._send(f"M={pos}")

    def move_feeder(self, feeder_id: int, steps: int) -> str:
        """给料电机相对移动 (默认使用 FEEDER_SPEED)"""
        assert feeder_id in (0, 1, 2), "Feeder ID 必须是 0, 1 或 2"
        return self._send(f"F{feeder_id} {steps}")

if __name__ == "__main__":
    ctrl = StepperController('COM10')

    try:
        # 2. 系统初始化：回零
        print(">> 执行回零...")
        print(ctrl.home())
        time.sleep(5)  # 等待物理回零完成

        # 4. 触发核心业务：投递序列
        print("\n>> 启动投递序列...")
        print(ctrl.deliver())

        # 5. 轮询监控状态 (简单优先：不使用多线程，仅做低频抽样)
        print("\n>> 监控运行状态 (Ctrl+C 退出)...")
        while True:
            status_log = ctrl.status()
            print("-" * 20)
            print(status_log)

            # 简单退出条件：如果检测到序列完成或急停
            if "DELIVERY COMPLETE" in status_log or "ESTOP ACTIVE" in status_log:
                break

            time.sleep(2)

    except KeyboardInterrupt:
        print("\n>> 用户中断，触发急停！")
        ctrl.stop()
    finally:
        ctrl.close()