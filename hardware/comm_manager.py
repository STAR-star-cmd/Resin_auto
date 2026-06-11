from PyQt6.QtCore import QObject, pyqtSignal

class HardwareManager(QObject):
    log_message = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.devices = {} # 通用设备注册表

    def register_device(self, name, device_instance):
        """注册设备到管理器"""
        self.devices[name] = device_instance
        self.log_message.emit(f"[Manager] 设备 '{name}' 已注册。")

    def start_all(self):
        """一键启动所有注册的设备"""
        for name, dev in self.devices.items():
            try:
                dev.start()
                self.log_message.emit(f"[Manager] 设备 '{name}' 启动指令已下发。")
            except Exception as e:
                self.log_message.emit(f"[Manager] 设备 '{name}' 启动失败: {e}")

    def stop_all(self):
        """一键安全关闭所有设备"""
        for name, dev in self.devices.items():
            try:
                dev.stop()
            except Exception:
                pass
        self.log_message.emit("[Manager] 所有设备已停止。")