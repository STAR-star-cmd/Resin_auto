import serial
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer


class _MonomerWorker(QObject):
    """后台串口通信Worker，保持原有异步架构不变"""
    action_finished = pyqtSignal(bool, str)
    error_occurred = pyqtSignal(str)
    response_received = pyqtSignal(str)

    # 统一使用通用指令信号
    _request_cmd = pyqtSignal(str)

    def __init__(self, port: str, baudrate: int = 115200):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.ser = None

        self._request_cmd.connect(self._execute_raw_cmd)

    @pyqtSlot()
    def open_serial(self):
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
            self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
            self.action_finished.emit(True, f"串口 {self.port} 已打开")
        except Exception as e:
            self.error_occurred.emit(f"打开串口失败: {e}")
            self.action_finished.emit(False, str(e))

    @pyqtSlot()
    def close_serial(self):
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
            self.action_finished.emit(True, "串口已关闭")
        except Exception as e:
            self.error_occurred.emit(f"关闭串口失败: {e}")

    @pyqtSlot(str)
    def _execute_raw_cmd(self, cmd: str):
        """通用原始指令执行（覆盖全部Arduino指令）"""
        if not self.ser or not self.ser.is_open:
            self.error_occurred.emit("串口未打开")
            self.action_finished.emit(False, "串口未打开")
            return

        full_cmd = cmd.strip()
        if not full_cmd:
            return

        try:
            self.ser.write((full_cmd + "\n").encode('utf-8'))
            self.ser.flush()

            # STATUS/CONFIG/HELP 有多行返回，延迟读取；其余指令即时完成
            upper = full_cmd.upper().split()[0]
            if upper in ("STATUS", "CONFIG", "HELP"):
                QTimer.singleShot(600, self._read_response)
            else:
                self.action_finished.emit(True, f"已发送: {full_cmd}")
        except Exception as e:
            self.error_occurred.emit(f"发送失败: {e}")
            self.action_finished.emit(False, str(e))

    def _read_response(self):
        """非阻塞读取Arduino多行响应"""
        try:
            if not self.ser or not self.ser.is_open:
                return
            lines = []
            while self.ser.in_waiting > 0:
                line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    lines.append(line)
            if lines:
                resp = "\n".join(lines)
                self.response_received.emit(resp)
                self.action_finished.emit(True, resp)
            else:
                self.action_finished.emit(True, "指令已发送(无返回数据)")
        except Exception as e:
            self.error_occurred.emit(f"读取响应失败: {e}")


class MonomerModule(QObject):
    """对外接口层，保持与comm_manager兼容的信号和方法"""
    action_finished = pyqtSignal(bool, str)
    error_occurred = pyqtSignal(str)
    response_received = pyqtSignal(str)

    def __init__(self, port: str, baudrate: int = 115200):
        super().__init__()
        self._worker = _MonomerWorker(port, baudrate)

        # 桥接Worker信号
        self._worker.action_finished.connect(self.action_finished)
        self._worker.error_occurred.connect(self.error_occurred)
        self._worker.response_received.connect(self.response_received)

    # ==================== 生命周期管理 ====================
    def start(self):
        self._worker.open_serial()

    def stop(self):
        self._worker.close_serial()

    # ==================== 完整指令接口 (1:1 映射 Arduino 全部功能) ====================
    def start_delivery(self):
        """启动材料输送序列 (DELIVER)"""
        self._worker._request_cmd.emit("DELIVER")

    def feed_station(self, station_id: int):
        """单次工位给料 (FEED <0-5>) 0-3为挤出机, 4为泵1, 5为泵2"""
        if 0 <= station_id <= 5:
            self._worker._request_cmd.emit(f"FEED {station_id}")
        else:
            self.error_occurred.emit("工位ID必须在0-5之间")

    def test_motors(self):
        """测试所有活动电机 (TEST)"""
        self._worker._request_cmd.emit("TEST")

    def emergency_stop(self):
        """紧急停止所有序列与电机 (STOP)"""
        self._worker._request_cmd.emit("STOP")

    def home_main(self):
        """主电机归零 (HOME)"""
        self._worker._request_cmd.emit("HOME")

    def get_status(self):
        """查询电机状态 (STATUS) - 结果通过 response_received 异步返回"""
        self._worker._request_cmd.emit("STATUS")

    def get_config(self):
        """查询当前配置参数 (CONFIG) - 结果通过 response_received 异步返回"""
        self._worker._request_cmd.emit("CONFIG")

    def set_param(self, key: str, value: int):
        """设置参数 (SET <k> <v>) key: EXT0-3/RET0-3/PUMP1-2/POS0-5"""
        self._worker._request_cmd.emit(f"SET {key} {value}")

    def move_extruder(self, extruder_id: int, steps: int):
        """移动挤出机 (E<0-3> <stp>)"""
        if 0 <= extruder_id <= 3:
            self._worker._request_cmd.emit(f"E{extruder_id} {steps}")
        else:
            self.error_occurred.emit("挤出机ID必须在0-3之间")

    def move_main(self, steps: int):
        """移动主电机 (M <steps>)"""
        self._worker._request_cmd.emit(f"M {steps}")

    def trigger_pump(self, pump_id: int, duration_ms: int):
        """触发气泵 (P1/P2 <ms>)"""
        if pump_id in (1, 2):
            self._worker._request_cmd.emit(f"P{pump_id} {duration_ms}")
        else:
            self.error_occurred.emit("气泵ID必须是1或2")

    def get_help(self):
        """获取帮助菜单"""
        self._worker._request_cmd.emit("HELP")

    # ==================== 兼容旧版 UI 接口 ====================
    def deliver_monomer(self, amount: float = 0):
        """兼容旧UI：amount >0为指定E0步数，0或负数为完整DELIVER序列"""
        if amount > 0:
            self.move_extruder(0, int(abs(amount)))
        else:
            self.start_delivery()

    def retract_monomer(self, amount: float):
        """兼容旧UI：回抽单体（内部转换为E0负步数）"""
        self.move_extruder(0, -int(abs(amount)))