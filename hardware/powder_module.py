import serial
from PyQt6.QtCore import QObject, pyqtSignal, QThread, pyqtSlot, QTimer


class _PowderWorker(QObject):
    """
    后台工作线程 (内部类)
    负责串口通信、下粉执行与状态轮询，彻底隔离 I/O 阻塞
    """
    # 状态与结果信号 (桥接给外层)
    status_updated = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    dispense_finished = pyqtSignal(bool)

    # 内部控制信号 (主线程 -> 后台线程)
    _request_dispense = pyqtSignal(float)
    _request_stop = pyqtSignal()
    _request_shutdown = pyqtSignal()

    def __init__(self, port, baudrate, poll_interval_ms=500):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self._keep_alive = True

        # 自治定时器：用于周期性查询设备状态（如剩余粉量、运行状态等）
        self.timer = QTimer(self)
        self.timer.setInterval(poll_interval_ms)
        self.timer.timeout.connect(self._poll_status)

        # 绑定控制信号到槽函数
        self._request_dispense.connect(self._execute_dispense)
        self._request_stop.connect(self._execute_stop)
        self._request_shutdown.connect(self._on_shutdown)

    @pyqtSlot()
    def init_and_run(self):
        """线程启动时执行：连接串口并启动状态轮询"""
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
            self.timer.start()
        except Exception as e:
            self.error_occurred.emit(f"粉末模块({self.port})连接失败: {e}")

    @pyqtSlot()
    def _poll_status(self):
        """周期性状态查询 (非阻塞)"""
        if not self.ser or not self.ser.is_open: return
        try:
            # 🔧 替换为你的原始状态查询协议
            # 例如: self.ser.write(b"STATUS\n")
            # resp = self.ser.readline().decode('utf-8', errors='ignore').strip()
            # self.status_updated.emit({"raw_status": resp, "online": True})
            pass
        except Exception as e:
            self.error_occurred.emit(f"状态轮询异常: {e}")

    @pyqtSlot(float)
    def _execute_dispense(self, amount):
        """执行下粉指令 (异步)"""
        if not self.ser or not self.ser.is_open:
            self.error_occurred.emit("下粉失败：串口未打开")
            self.dispense_finished.emit(False)
            return

        try:
            # 🔧 替换为你的原始下粉协议
            # 例如: cmd = f"POWDER {amount}\n"
            # self.ser.write(cmd.encode('utf-8'))

            # 如果设备会返回 ACK，可在此处 readline() 解析；
            # 若为开环控制，直接发射完成信号即可：
            self.dispense_finished.emit(True)
        except Exception as e:
            self.error_occurred.emit(f"下粉指令发送失败: {e}")
            self.dispense_finished.emit(False)

    @pyqtSlot()
    def _execute_stop(self):
        """紧急停止下粉"""
        if self.ser and self.ser.is_open:
            try:
                # 🔧 替换为你的原始停止协议
                # self.ser.write(b"STOP\n")
                pass
            except Exception as e:
                self.error_occurred.emit(f"停止指令失败: {e}")

    @pyqtSlot()
    def _on_shutdown(self):
        """安全关闭串口并退出线程事件循环"""
        self._keep_alive = False
        self.timer.stop()
        if self.ser and self.ser.is_open:
            self.ser.close()
        QThread.currentThread().quit()


class PowderModule(QObject):
    """
    粉末下料模块 (对外暴露的管理接口)
    """
    # 暴露给 Manager/UI 的信号
    status_updated = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    dispense_finished = pyqtSignal(bool)

    def __init__(self, port: str, baudrate: int = 9600, poll_interval_ms: int = 500):
        super().__init__()
        self.port = port

        # 1. 创建独立线程
        self._thread = QThread()

        # 2. 实例化 Worker 并移入独立线程
        self._worker = _PowderWorker(port, baudrate, poll_interval_ms)
        self._worker.moveToThread(self._thread)

        # 3. 生命周期绑定
        self._thread.started.connect(self._worker.init_and_run)
        self._worker.destroyed.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)

        # 4. 桥接内部信号到外部信号
        self._worker.status_updated.connect(self.status_updated)
        self._worker.error_occurred.connect(self.error_occurred)
        self._worker.dispense_finished.connect(self.dispense_finished)

    # === 对外暴露的控制接口 ===

    def start(self):
        """供 Manager 调用的启动方法"""
        if not self._thread.isRunning():
            self._thread.start()

    def stop(self):
        """供 Manager 调用的停止方法"""
        if self._thread.isRunning():
            self._worker._request_shutdown.emit()
            self._thread.wait(2000)  # 等待安全退出

    def dispense(self, amount: float):
        """
        触发下粉 (异步)
        原代码中的 time.sleep() 等待逻辑已移除，改为监听 dispense_finished 信号
        """
        self._worker._request_dispense.emit(amount)

    def stop_dispense(self):
        """紧急停止"""
        self._worker._request_stop.emit()