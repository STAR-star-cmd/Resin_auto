from PyQt6.QtCore import QObject, pyqtSignal, QThread, QTimer
from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException


class _WeightWorker(QObject):
    """
    后台工作线程 (内部类)
    负责实际的串口通信，确保 I/O 操作绝不阻塞主线程 (UI)
    """
    # 数据发射信号
    data_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    tare_finished = pyqtSignal(bool)

    # 内部控制信号
    request_stop = pyqtSignal()
    request_tare = pyqtSignal()

    def __init__(self, port, baudrate, slave_id, poll_interval_ms):
        super().__init__()
        self.client = ModbusSerialClient(
            port=port, baudrate=baudrate,
            bytesize=8, parity='N', stopbits=1, timeout=1
        )
        self.slave_id = slave_id

        # 自治定时器：在独立线程的事件循环中周期性触发
        self.timer = QTimer(self)
        self.timer.setInterval(poll_interval_ms)
        self.timer.timeout.connect(self._read_once)

        # 绑定控制信号到槽函数
        self.request_stop.connect(self._on_stop)
        self.request_tare.connect(self._on_tare)

        self.is_connected = False

    def start_polling(self):
        """供线程启动时调用"""
        if self.client.connect():
            self.is_connected = True
            self.timer.start()
        else:
            self.error_occurred.emit(f"称重模块({self.client.port})连接失败")

    def _on_stop(self):
        """安全停止轮询并关闭串口"""
        self.timer.stop()
        if self.client.connected:
            self.client.close()
        # 通知当前线程退出事件循环
        QThread.currentThread().quit()

    def _read_once(self):
        """单次读取逻辑 (完全保留原解析逻辑)"""
        if not self.is_connected:
            return
        try:
            r = self.client.read_holding_registers(
                address=0x0000, count=4, device_id=self.slave_id
            )
            if r.isError():
                self.error_occurred.emit(f"读取失败: {r}")
                return

            regs = r.registers
            # 高 16 位在 regs[0], 低 16 位在 regs[1], 有符号
            raw = (regs[0] << 16) | regs[1]
            if raw >= 0x80000000:
                raw -= 0x100000000
            precision = regs[2]  # 0~3 对应小数位数
            status = regs[3]

            # 打包为字典，发射给外层
            data = {
                'weight': raw / (10 ** precision),
                'raw': raw,
                'precision': precision,
                'stable': bool(status & 0x01),  # bit0
                'zero': bool(status & 0x02),  # bit1
                'overweight': bool(status & 0x04),  # bit2
                'valid': bool(status & 0x20),  # bit5
                'status': status,
            }
            self.data_ready.emit(data)
        except Exception as e:
            self.error_occurred.emit(f"轮询异常: {e}")

    def _on_tare(self):
        """执行清零指令 (功能码 06, 地址 0x0004 写 1)"""
        if not self.is_connected:
            self.error_occurred.emit("清零失败：未连接")
            self.tare_finished.emit(False)
            return

        try:
            r = self.client.write_register(
                address=0x0004, value=1, device_id=self.slave_id
            )
            if r.isError():
                self.error_occurred.emit(f"清零失败: {r}")
                self.tare_finished.emit(False)
            else:
                self.tare_finished.emit(True)
        except Exception as e:
            self.error_occurred.emit(f"清零异常: {e}")
            self.tare_finished.emit(False)


class WeighingModule(QObject):
    """
    粉末区域称重模块 (对外暴露的管理接口)
    封装了线程管理，向上提供简洁的 start/stop/tare 方法。
    """
    # 暴露给 Manager/UI 的信号
    data_updated = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    tare_result = pyqtSignal(bool)

    def __init__(self, port: str, baudrate: int = 115200, slave_id: int = 1, poll_interval_ms: int = 1000):
        super().__init__()
        self.port = port

        # 1. 创建独立线程
        self._thread = QThread()

        # 2. 实例化 Worker 并移入独立线程
        self._worker = _WeightWorker(port, baudrate, slave_id, poll_interval_ms)
        self._worker.moveToThread(self._thread)

        # 3. 生命周期绑定 (自动化内存管理)
        self._thread.started.connect(self._worker.start_polling)
        self._worker.destroyed.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)

        # 4. 桥接内部信号到外部信号
        self._worker.data_ready.connect(self.data_updated)
        self._worker.error_occurred.connect(self.error_occurred)
        self._worker.tare_finished.connect(self.tare_result)

    # === 对外暴露的控制接口 ===

    def start(self):
        """启动硬件轮询"""
        if not self._thread.isRunning():
            self._thread.start()

    def stop(self):
        """停止硬件轮询并安全退出线程"""
        if self._thread.isRunning():
            self._worker.request_stop.emit()
            # 等待线程安全退出，最多等待2秒防止死锁
            self._thread.wait(2000)

    def tare(self):
        """异步执行清零"""
        self._worker.request_tare.emit()