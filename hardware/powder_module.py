import serial
import time
from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot


class _PowderWorker(QObject):
    """粉末模块后台工作线程，负责串口通信"""
    # 【对齐 monomer_module】统一使用这三个标准信号
    action_finished = pyqtSignal(bool, str)
    error_occurred = pyqtSignal(str)
    response_received = pyqtSignal(str)

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 1.0):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None
        self._running = False
        self._pending_cmd = None
        self._cmd_param = None

    @pyqtSlot()
    def run(self):
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout
            )
            self._running = True
            time.sleep(0.1)
            self.ser.reset_input_buffer()
        except Exception as e:
            self.error_occurred.emit(f"串口打开失败: {e}")
            self.action_finished.emit(False, str(e))
            return

        while self._running:
            if self._pending_cmd is not None:
                cmd = self._pending_cmd
                param = self._cmd_param
                self._pending_cmd = None
                self._cmd_param = None

                if cmd == "dispense":
                    self._execute_dispense(param)
                elif cmd == "stop":
                    self._execute_stop()
                elif cmd == "home":
                    self._execute_home()
                elif cmd == "reset":
                    self._execute_reset()
                elif cmd == "set_steps":
                    self._execute_set_steps(param)
                elif cmd == "weight_update":
                    self._execute_weight_update(param)
                elif cmd == "status":
                    self._poll_status()
            else:
                # 【关键修改】空闲时不再自动轮询 STATUS，防止与高频透传的 W: 指令抢占串口
                pass

            time.sleep(0.05)

        if self.ser and self.ser.is_open:
            self.ser.close()

    def stop(self):
        self._running = False

    # ─── 命令下发入口（线程安全标记） ───────────────────────
    def request_dispense(self, device_id: int, amount: float):
        self._pending_cmd = "dispense"
        self._cmd_param = (device_id, amount)

    def request_home(self):
        self._pending_cmd = "home"

    def request_stop(self):
        self._pending_cmd = "stop"

    def request_reset(self):
        self._pending_cmd = "reset"

    def request_set_steps(self, steps_config: dict):
        self._pending_cmd = "set_steps"
        self._cmd_param = steps_config

    def request_weight_update(self, weight: float):
        self._pending_cmd = "weight_update"
        self._cmd_param = weight

    def request_status(self):
        self._pending_cmd = "status"

    # ─── 指令执行实现 ──────────────────────────────────────
    def _send_line(self, line: str):
        if self.ser and self.ser.is_open:
            self.ser.write((line + "\n").encode("ascii"))
            self.ser.flush()

    def _read_lines_until_empty(self, max_wait: float = 2.0) -> list:
        lines = []
        deadline = time.time() + max_wait
        while time.time() < deadline:
            raw = self.ser.readline()
            if raw:
                decoded = raw.decode("ascii", errors="ignore").strip()
                if decoded:
                    lines.append(decoded)
                else:
                    break
            else:
                break
        return lines

    def _execute_dispense(self, params):
        try:
            if isinstance(params, tuple):
                device_id, amount = params
                self._send_line(f"DELIVER {device_id} {amount}")
            else:
                self._send_line(f"DELIVER {params}")
            # 闭环控制耗时较长，超时设为 300 秒
            deadline = time.time() + 300.0
            completed = False
            while time.time() < deadline and self._running:
                raw = self.ser.readline()
                if raw:
                    line = raw.decode("ascii", errors="ignore").strip()
                    if "DELIVERY COMPLETE" in line:
                        completed = True
                        break
                    elif "ERROR" in line or "BUSY" in line:
                        self.error_occurred.emit(f"下粉异常: {line}")
                        self.action_finished.emit(False, line)
                        return
                time.sleep(0.02)

            if not completed:
                self.error_occurred.emit("下粉超时，未收到完成反馈")
                self.action_finished.emit(False, "超时")
            else:
                self.action_finished.emit(True, "下粉完成")
        except Exception as e:
            self.error_occurred.emit(f"下粉指令异常: {e}")
            self.action_finished.emit(False, str(e))

    def _execute_weight_update(self, weight: float):
        try:
            self._send_line(f"W:{weight:.2f}")
        except Exception:
            pass

    def _execute_stop(self):
        try:
            self._send_line("S")
            self.action_finished.emit(True, "已发送停止指令")
        except Exception as e:
            self.error_occurred.emit(f"停止指令异常: {e}")
            self.action_finished.emit(False, str(e))

    def _execute_home(self):
        try:
            self._send_line("HOME")
            deadline = time.time() + 30.0
            success = False
            while time.time() < deadline and self._running:
                raw = self.ser.readline()
                if raw:
                    line = raw.decode("ascii", errors="ignore").strip()
                    # 匹配 Arduino 回零成功的日志 (去除了原版多余的空格)
                    if "HOMED & Zeroed" in line or "HOME OK" in line:
                        success = True
                        break
                    elif "ERROR" in line:
                        self.error_occurred.emit(f"回零异常: {line}")
                        self.action_finished.emit(False, line)
                        return
                time.sleep(0.02)
            self.action_finished.emit(success, "回零完成" if success else "回零超时")
        except Exception as e:
            self.error_occurred.emit(f"回零指令异常: {e}")
            self.action_finished.emit(False, str(e))

    def _execute_reset(self):
        try:
            self._send_line("R")
            time.sleep(0.2)
            self.action_finished.emit(True, "复位成功")
        except Exception as e:
            self.error_occurred.emit(f"复位指令异常: {e}")
            self.action_finished.emit(False, str(e))

    def _execute_set_steps(self, steps_config: dict):
        try:
            for key, value in steps_config.items():
                self._send_line(f"{key}={value}")
                time.sleep(0.05)
            self.action_finished.emit(True, "步数配置完成")
        except Exception as e:
            self.error_occurred.emit(f"步数配置异常: {e}")
            self.action_finished.emit(False, str(e))

    def _poll_status(self):
        try:
            self._send_line("STATUS")
            lines = self._read_lines_until_empty(max_wait=0.5)
            if lines:
                resp = "\n".join(lines)
                self.response_received.emit(resp)
                self.action_finished.emit(True, resp)
        except Exception as e:
            self.error_occurred.emit(f"状态轮询异常: {e}")


class PowderModule(QObject):
    """
    粉末制备模块对外接口
    【已对齐 monomer_module 规范】，可被 manager 无缝统一管理
    """
    # 对齐 monomer_module 的标准信号
    action_finished = pyqtSignal(bool, str)
    error_occurred = pyqtSignal(str)
    response_received = pyqtSignal(str)

    # 兼容 comm_manager 中旧版的 powder 信号绑定
    dispense_finished = pyqtSignal(bool)

    def __init__(self, port: str, baudrate: int = 115200, parent=None):
        super().__init__(parent)
        self._thread = QThread()
        self._worker = _PowderWorker(port=port, baudrate=baudrate)
        self._worker.moveToThread(self._thread)

        # 转发 Worker 信号
        self._worker.action_finished.connect(self.action_finished)
        self._worker.error_occurred.connect(self.error_occurred)
        self._worker.response_received.connect(self.response_received)

        # 桥接 action_finished 到 dispense_finished 以兼容 Manager 旧逻辑
        self._worker.action_finished.connect(
            lambda ok, msg: self.dispense_finished.emit(ok) if "下粉" in msg else None
        )

        self._thread.started.connect(self._worker.run)
        self._thread.finished.connect(self._worker.deleteLater)

    # ==================== 生命周期管理 (对齐 Manager 的 start_all/stop_all) ====================
    def start(self):
        """启动后台线程与串口 (Manager 统一调用 start_all)"""
        if not self._thread.isRunning():
            self._thread.start()

    def stop(self):
        """停止后台线程并安全退出 (Manager 统一调用 stop_all)"""
        self._worker.stop()
        self._thread.quit()
        self._thread.wait(3000)

    # ==================== 原有业务接口 (保留) ====================
    def dispense(self, amount: float = 0.0):
        """触发下粉序列，amount > 0 时开启重量闭环控制"""
        self._worker.request_dispense(amount)

    def emergency_stop(self):
        """紧急停止"""
        self._worker.request_stop()

    def home(self):
        """主电机回零"""
        self._worker.request_home()

    def reset_estop(self):
        """复位急停标志"""
        self._worker.request_reset()

    def set_feeder_steps(self, steps_config: dict):
        """设置送料器步数"""
        self._worker.request_set_steps(steps_config)

    # ==================== 新增：重量闭环透传接口 ====================
    def update_weight(self, weight: float):
        """将实时重量同步给下位机 (由 weight_module 绑定调用)"""
        self._worker.request_weight_update(weight)

    # ==================== 新增：状态查询 (对齐 monomer_module) ====================
    def get_status(self):
        """查询电机状态（结果通过 response_received 信号异步返回）"""
        self._worker.request_status()