from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException


class TemperatureDevice(QObject):
    # 定义该设备专属的信号
    data_updated = pyqtSignal(dict)  # 传递 {"pv": [25, 26, 27, 28]}
    error_occurred = pyqtSignal(str)
    command_executed = pyqtSignal(bool, str)  # 成功与否, 消息

    def __init__(self, port='COM3', slave_id=20, poll_interval=1000):
        super().__init__()
        self.port = port
        self.slave_id = slave_id
        self.client = ModbusSerialClient(
            port=port, baudrate=9600, parity='E',
            stopbits=1, bytesize=8, timeout=1
        )
        self.pv_base_addr = 30
        self.sv_base_addr = 41

        # 自治定时器
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)
        self.poll_interval = poll_interval

    def start(self):
        """供 Manager 调用的启动方法"""
        try:
            if not self.client.connect():
                raise ConnectionError(f"无法连接串口 {self.port}")
            self.timer.start(self.poll_interval)
        except Exception as e:
            self.error_occurred.emit(f"温控模块({self.port})启动失败: {e}")

    def stop(self):
        """供 Manager 调用的停止方法"""
        self.timer.stop()
        if self.client.connected:
            self.client.close()

    def _poll(self):
        """内部轮询逻辑"""
        try:
            result = self.client.read_holding_registers(address=self.pv_base_addr, count=4, slave=self.slave_id)
            if not result.isError():
                self.data_updated.emit({"pv": result.registers})
            else:
                self.error_occurred.emit(f"读取PV失败: {result}")
        except Exception as e:
            self.error_occurred.emit(f"轮询异常: {e}")

    def set_target_temp(self, channel, value):
        """供 UI 调用的写入方法"""
        try:
            addr = self.sv_base_addr + channel
            result = self.client.write_register(address=addr, value=value, slave=self.slave_id)
            if not result.isError():
                self.command_executed.emit(True, f"CH{channel} 设置成功: {value}")
            else:
                self.command_executed.emit(False, f"写入失败: {result}")
        except Exception as e:
            self.command_executed.emit(False, f"写入异常: {e}")