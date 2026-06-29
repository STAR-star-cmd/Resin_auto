import serial
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer


class _MonomerWorker(QObject):
    """后台串口通信Worker，保持原有异步架构不变"""
    action_finished = pyqtSignal(bool, str)
    error_occurred = pyqtSignal(str)
    response_received = pyqtSignal(str)

    # 保留原有信号以兼容已有调用
    _request_deliver = pyqtSignal(float)
    _request_retract = pyqtSignal(float)
    _request_stop = pyqtSignal()
    # 新增通用指令信号
    _request_cmd = pyqtSignal(str)

    def __init__(self, port: str, baudrate: int = 115200):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.ser = None

        # 连接所有信号到对应槽函数
        self._request_deliver.connect(self._execute_deliver)
        self._request_retract.connect(self._execute_retract)
        self._request_stop.connect(self._execute_stop)
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
        try:
            full_cmd = cmd.strip() + "\n"
            self.ser.write(full_cmd.encode('utf-8'))
            self.ser.flush()

            # STATUS/CONFIG 有多行返回，延迟读取；其余指令即时完成
            upper = cmd.upper().split()[0]
            if upper in ("STATUS", "CONFIG"):
                QTimer.singleShot(600, self._read_response)
            else:
                self.action_finished.emit(True, f"已发送: {cmd}")
        except Exception as e:
            self.error_occurred.emit(f"发送失败: {e}")
            self.action_finished.emit(False, str(e))

    @pyqtSlot(float)
    def _execute_deliver(self, amount: float):
        """修正：DELIVER为无参序列命令；amount>0时用E0正步数替代"""
        if amount > 0:
            steps = int(abs(amount))
            self._execute_raw_cmd(f"E0 {steps}")
        else:
            self._execute_raw_cmd("DELIVER")

    @pyqtSlot(float)
    def _execute_retract(self, amount: float):
        """修正：Arduino无RETRACT指令，用E0负步数实现回抽"""
        steps = int(abs(amount))
        self._execute_raw_cmd(f"E0 -{steps}")

    @pyqtSlot()
    def _execute_stop(self):
        self._execute_raw_cmd("STOP")

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
    def open(self):
        self._worker.open_serial()

    def close(self):
        self._worker.close_serial()

    # ==================== 原有接口（协议已修正） ====================
    def deliver_monomer(self, amount: float = 0):
        """输送单体：amount>0为指定步数，0或负数为完整DELIVER序列"""
        self._worker._request_deliver.emit(amount)

    def retract_monomer(self, amount: float):
        """回抽单体（内部转换为E0负步数）"""
        self._worker._request_retract.emit(amount)

    def stop_motor(self):
        """紧急停止"""
        self._worker._request_stop.emit()

    # ==================== 新增完整指令接口 ====================
    def home(self):
        """主电机归零"""
        self._worker._request_cmd.emit("HOME")

    def test_motors(self):
        """测试所有电机"""
        self._worker._request_cmd.emit("TEST")

    def get_status(self):
        """查询电机状态（结果通过response_received信号异步返回）"""
        self._worker._request_cmd.emit("STATUS")

    def get_config(self):
        """查询当前配置参数（结果通过response_received信号异步返回）"""
        self._worker._request_cmd.emit("CONFIG")

    def set_param(self, key: str, value: int):
        """
        设置参数
        key: EXT0/EXT1/EXT2/EXT3/RET0/RET1/RET2/RET3/PUMP1/PUMP2/POS0/POS1/POS2/POS3
        value: 整数值
        """
        self._worker._request_cmd.emit(f"SET {key} {value}")

    def move_extruder(self, extruder_id: int, steps: int):
        """移动指定挤出机 E0-E3"""
        self._worker._request_cmd.emit(f"E{extruder_id} {steps}")

    def move_main(self, steps: int):
        """移动主电机"""
        self._worker._request_cmd.emit(f"M {steps}")

    def trigger_pump(self, pump_id: int, duration_ms: int):
        """触发气泵 pump_id: 1或2"""
        self._worker._request_cmd.emit(f"P{pump_id} {duration_ms}")

    def deliver_sequence(self):
        """启动完整输送序列（无参DELIVER）"""
        self._worker._request_cmd.emit("DELIVER")