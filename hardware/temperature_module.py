from PyQt6.QtCore import QObject, pyqtSignal, QThread, QTimer
from pymodbus.client import ModbusSerialClient


class _TempWorker(QObject):
    """
    后台工作线程 (内部类)
    负责实际的串口 I/O，确保读写操作在主线程之外排队执行
    """
    # 数据与状态信号 (桥接给外层)
    data_updated = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    command_executed = pyqtSignal(bool, str)

    # 内部控制信号 (主线程 -> 后台线程)
    _request_set_temp = pyqtSignal(int, float)
    _request_stop = pyqtSignal()

    def __init__(self, port, slave_id, poll_interval):
        super().__init__()
        self.client = ModbusSerialClient(
            port=port, baudrate=9600, parity='E',
            stopbits=1, bytesize=8, timeout=1
        )
        self.slave_id = slave_id
        self.pv_base_addr = 30
        self.sv_base_addr = 41

        # 自治定时器：运行在后台线程中
        self.timer = QTimer(self)
        self.timer.setInterval(poll_interval)
        self.timer.timeout.connect(self._poll)

        # 绑定控制信号到槽函数
        self._request_set_temp.connect(self._execute_set_temp)
        self._request_stop.connect(self._on_stop)

    def start_polling(self):
        """线程启动时调用"""
        if self.client.connect():
            self.timer.start()
        else:
            self.error_occurred.emit(f"温控模块({self.client.port})无法连接")

    def _poll(self):
        """内部轮询逻辑 (仅保留读取 PV 的功能，不做多余扩展)"""
        try:
            result = self.client.read_holding_registers(
                address=self.pv_base_addr, count=4, slave=self.slave_id
            )
            if not result.isError():
                self.data_updated.emit({"pv": result.registers})
            else:
                self.error_occurred.emit(f"读取PV失败: {result}")
        except Exception as e:
            self.error_occurred.emit(f"轮询异常: {e}")

    def _execute_set_temp(self, channel, value):
        """执行写入指令 (通过事件队列与 _poll 串行执行，杜绝冲突)"""
        try:
            addr = self.sv_base_addr + channel
            result = self.client.write_register(
                address=addr, value=value, slave=self.slave_id
            )
            if not result.isError():
                self.command_executed.emit(True, f"CH{channel} 设置成功: {value}")
            else:
                self.command_executed.emit(False, f"写入失败: {result}")
        except Exception as e:
            self.command_executed.emit(False, f"写入异常: {e}")

    def _on_stop(self):
        """安全停止轮询并关闭串口"""
        self.timer.stop()
        if self.client.connected:
            self.client.close()
        QThread.currentThread().quit()


class TemperatureDevice(QObject):
    """
    温控模块 (对外暴露的管理接口)
    封装了线程管理，向上提供极简的 start/stop/set_target_temp 方法。
    """
    # 暴露给 Manager/UI 的信号 (保持原样，不破坏 Manager 的连接)
    data_updated = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    command_executed = pyqtSignal(bool, str)

    def __init__(self, port='COM3', slave_id=20, poll_interval=1000):
        super().__init__()
        self.port = port

        # 1. 创建独立线程
        self._thread = QThread()

        # 2. 实例化 Worker 并移入独立线程
        self._worker = _TempWorker(port, slave_id, poll_interval)
        self._worker.moveToThread(self._thread)

        # 3. 生命周期绑定
        self._thread.started.connect(self._worker.start_polling)
        self._worker.destroyed.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)

        # 4. 桥接内部信号到外部信号
        self._worker.data_updated.connect(self.data_updated)
        self._worker.error_occurred.connect(self.error_occurred)
        self._worker.command_executed.connect(self.command_executed)

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

    def set_target_temp(self, channel: int, value: float):
        """
        供 UI 调用的写入方法
        注意：这里只是发送信号，将写请求放入后台线程的事件队列中排队
        """
        self._worker._request_set_temp.emit(channel, value)