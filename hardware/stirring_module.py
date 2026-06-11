import serial
from PyQt6.QtCore import QObject, pyqtSignal, QThread, pyqtSlot


class _StirringWorker(QObject):
    """
    后台工作线程 (内部类)
    负责串口连接、等待Arduino就绪以及指令发送，彻底隔离 I/O 阻塞
    """
    # 状态信号 (桥接给外层)
    ready = pyqtSignal()
    error_occurred = pyqtSignal(str)

    # 内部控制信号 (主线程 -> 后台线程)
    _request_cmd = pyqtSignal(str)
    _request_stop = pyqtSignal()

    def __init__(self, port, baudrate):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self._keep_alive = True  # 简单的线程安全标志

        # 绑定控制信号到槽函数
        self._request_cmd.connect(self._execute_cmd)
        self._request_stop.connect(self.stop_and_quit)

    @pyqtSlot()
    def run_init_and_listen(self):
        """线程启动时执行：连接串口并等待就绪"""
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
            # 阻塞等待，但每次 readline 超时(1秒)后会检查 _keep_alive，防止死锁
            while self._keep_alive:
                line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                if "系统就绪" in line:
                    self.ready.emit()
                    break
        except Exception as e:
            self.error_occurred.emit(f"搅拌模块({self.port})连接失败: {e}")

        # 注意：执行完毕后，控制权交还给 QThread 默认的事件循环 (exec())
        # 线程保持存活，等待后续的 _request_cmd 信号

    @pyqtSlot(str)
    def _execute_cmd(self, cmd):
        """执行写入指令"""
        if self.ser and self.ser.is_open:
            try:
                self.ser.write((cmd + '\n').encode('utf-8'))
            except Exception as e:
                self.error_occurred.emit(f"发送指令失败: {e}")

    @pyqtSlot()
    def stop_and_quit(self):
        """安全关闭串口并退出线程事件循环"""
        self._keep_alive = False
        if self.ser and self.ser.is_open:
            self.ser.close()
        QThread.currentThread().quit()


class StirringModule(QObject):
    """
    搅拌模块 (对外暴露的管理接口)
    """
    # 暴露给 Manager/UI 的信号
    device_ready = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self, port: str, baudrate: int = 115200):
        super().__init__()
        self.port = port

        # 1. 创建独立线程
        self._thread = QThread()

        # 2. 实例化 Worker 并移入独立线程
        self._worker = _StirringWorker(port, baudrate)
        self._worker.moveToThread(self._thread)

        # 3. 生命周期绑定
        self._thread.started.connect(self._worker.run_init_and_listen)
        self._worker.destroyed.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)

        # 4. 桥接内部信号到外部信号
        self._worker.ready.connect(self.device_ready)
        self._worker.error_occurred.connect(self.error_occurred)

    # === 对外暴露的控制接口 ===

    def start(self):
        """供 Manager 调用的启动方法"""
        if not self._thread.isRunning():
            self._thread.start()

    def stop(self):
        """供 Manager 调用的停止方法"""
        if self._thread.isRunning():
            self._worker._request_stop.emit()
            self._thread.wait(2000)  # 等待安全退出

    # --- 保留原有的控制 API ---

    def x(self, speed, seconds=None):
        """控制X轴电机. speed: -255~255, seconds: 可选运行秒数"""
        cmd = f"X{speed}"
        if seconds is not None:
            cmd += f" {seconds}"
        self._worker._request_cmd.emit(cmd)

    def y(self, speed, seconds=None):
        """控制Y轴电机. speed: -255~255, seconds: 可选运行秒数"""
        cmd = f"Y{speed}"
        if seconds is not None:
            cmd += f" {seconds}"
        self._worker._request_cmd.emit(cmd)

    def u(self, state):
        """控制超声/形变模块. state: 'ON', 'OFF' 或 整数秒数"""
        self._worker._request_cmd.emit(f"U {state}")