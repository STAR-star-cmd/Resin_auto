import serial
from PyQt6.QtCore import QObject, pyqtSignal, QThread, pyqtSlot, QTimer


class _MonomerWorker(QObject):
    """
    后台工作线程 (内部类)
    负责串口连接、单体挤出/回抽指令发送，彻底隔离 I/O 阻塞
    """
    # 状态与结果信号 (桥接给外层)
    action_finished = pyqtSignal(bool, str)
    error_occurred = pyqtSignal(str)

    # 内部控制信号 (主线程 -> 后台线程)
    _request_deliver = pyqtSignal(float)
    _request_retract = pyqtSignal(float)
    _request_stop = pyqtSignal()
    _request_shutdown = pyqtSignal()

    def __init__(self, port, baudrate):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.ser = None

        # 绑定控制信号到槽函数
        self._request_deliver.connect(self._execute_deliver)
        self._request_retract.connect(self._execute_retract)
        self._request_stop.connect(self._execute_stop)
        self._request_shutdown.connect(self._on_shutdown)

    @pyqtSlot()
    def init_serial(self):
        """线程启动时执行：打开串口"""
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
        except Exception as e:
            self.error_occurred.emit(f"单体模块({self.port})连接失败: {e}")

    @pyqtSlot(float)
    def _execute_deliver(self, amount):
        """执行挤出/送料指令 (异步)"""
        if not self.ser or not self.ser.is_open:
            self.error_occurred.emit("挤出失败：串口未打开")
            self.action_finished.emit(False, "未连接")
            return

        try:
            # 🔧 替换为你的原始挤出协议
            # 例如 G-code: cmd = f"G1 E{amount} F300\n"
            # 例如 自定义: cmd = f"DELIVER {amount}\n"
            cmd = f"DELIVER {amount}\n"
            self.ser.write(cmd.encode('utf-8'))

            # 【关键优化】替代 time.sleep()
            # 如果下位机没有 ACK 反馈，你可以用 QTimer 在后台非阻塞延时后发射完成信号
            # QTimer.singleShot(2000, lambda: self.action_finished.emit(True, f"挤出 {amount} 完成"))

            # 如果下位机有反馈，或者不需要严格等待，直接发射：
            self.action_finished.emit(True, f"挤出指令已发送: {amount}")
        except Exception as e:
            self.error_occurred.emit(f"挤出指令发送失败: {e}")
            self.action_finished.emit(False, str(e))

    @pyqtSlot(float)
    def _execute_retract(self, amount):
        """执行回抽/退料指令 (异步)"""
        if not self.ser or not self.ser.is_open:
            self.error_occurred.emit("回抽失败：串口未打开")
            self.action_finished.emit(False, "未连接")
            return

        try:
            # 🔧 替换为你的原始回抽协议
            cmd = f"RETRACT {amount}\n"
            self.ser.write(cmd.encode('utf-8'))
            self.action_finished.emit(True, f"回抽指令已发送: {amount}")
        except Exception as e:
            self.error_occurred.emit(f"回抽指令发送失败: {e}")
            self.action_finished.emit(False, str(e))

    @pyqtSlot()
    def _execute_stop(self):
        """紧急停止电机"""
        if self.ser and self.ser.is_open:
            try:
                # 🔧 替换为你的原始停止协议
                self.ser.write(b"STOP\n")
            except Exception as e:
                self.error_occurred.emit(f"停止指令失败: {e}")

    @pyqtSlot()
    def _on_shutdown(self):
        """安全关闭串口并退出线程事件循环"""
        if self.ser and self.ser.is_open:
            self.ser.close()
        QThread.currentThread().quit()


class MonomerModule(QObject):
    """
    单体/耗材控制模块 (对外暴露的管理接口)
    """
    # 暴露给 Manager/UI 的信号
    action_finished = pyqtSignal(bool, str)
    error_occurred = pyqtSignal(str)

    def __init__(self, port: str, baudrate: int = 115200):
        super().__init__()
        self.port = port

        # 1. 创建独立线程
        self._thread = QThread()

        # 2. 实例化 Worker 并移入独立线程
        self._worker = _MonomerWorker(port, baudrate)
        self._worker.moveToThread(self._thread)

        # 3. 生命周期绑定
        self._thread.started.connect(self._worker.init_serial)
        self._worker.destroyed.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)

        # 4. 桥接内部信号到外部信号
        self._worker.action_finished.connect(self.action_finished)
        self._worker.error_occurred.connect(self.error_occurred)

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

    def deliver(self, amount: float = 10.0):
        """
        触发挤出 (异步)
        原代码中的 time.sleep() 已移除，改为监听 action_finished 信号
        """
        self._worker._request_deliver.emit(amount)

    def retract(self, amount: float = 10.0):
        """触发回抽 (异步)"""
        self._worker._request_retract.emit(amount)

    def stop_motor(self):
        """紧急停止"""
        self._worker._request_stop.emit()