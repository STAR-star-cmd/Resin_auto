from PyQt6.QtCore import QObject, pyqtSignal


class HardwareManager(QObject):
    """
    硬件中枢管理器
    向下管理所有硬件的生命周期与数据流
    向上为 UI 提供极简的控制 API 与聚合信号
    """

    # === 暴露给 UI 的聚合信号 ===
    log_message = pyqtSignal(str)  # 统一日志流 (包含错误、状态、动作反馈)
    temp_data = pyqtSignal(dict)  # 聚合后的温度数据 {"CH1": 25.0, ...}
    weight_data = pyqtSignal(dict)  # 聚合后的重量数据 {"weight": 10.5, "stable": True}
    device_ready = pyqtSignal(str)  # 设备就绪信号 (携带设备名称)

    def __init__(self):
        super().__init__()
        self.devices = {}  # 存储所有注册的硬件实例

    def register_device(self, name: str, device_instance):
        """
        注册设备并自动桥接底层信号
        """
        self.devices[name] = device_instance

        # 1. 统一绑定错误信号
        if hasattr(device_instance, 'error_occurred'):
            device_instance.error_occurred.connect(
                lambda err, n=name: self.log_message.emit(f"[Error-{n}] {err}")
            )

        # 2. 针对不同类型设备，桥接特定信号
        if name.startswith("temp"):
            # 温度数据直接透传给 UI
            device_instance.data_updated.connect(self.temp_data.emit)
            device_instance.command_executed.connect(
                lambda ok, msg, n=name: self.log_message.emit(f"[{n}] {msg}" if ok else f"[Error-{n}] {msg}")
            )

        elif name.startswith("weight"):
            device_instance.data_updated.connect(self.weight_data.emit)
            device_instance.tare_result.connect(
                lambda ok, n=name: self.log_message.emit(f"[{n}] 清零{'成功' if ok else '失败'}")
            )

        elif name.startswith("stir"):
            device_instance.device_ready.connect(lambda n=name: self.device_ready.emit(n))

        elif name.startswith("powder"):
            device_instance.dispense_finished.connect(
                lambda ok, n=name: self.log_message.emit(f"[{n}] 下粉{'完成' if ok else '失败'}")
            )

        elif name.startswith("monomer"):
            device_instance.action_finished.connect(
                lambda ok, msg, n=name: self.log_message.emit(f"[{n}] {msg}")
            )

    # === 生命周期管理 ===

    def start_all(self):
        """一键启动所有注册的硬件设备"""
        self.log_message.emit("[Manager] 正在启动所有硬件设备...")
        for name, dev in self.devices.items():
            if hasattr(dev, "start"):
                dev.start()
                self.log_message.emit(f"[Manager] 设备 '{name}' 启动指令已发送")

    def stop_all(self):
        """一键安全停止所有硬件设备"""
        self.log_message.emit("[Manager] 正在停止所有硬件设备...")
        for name, dev in self.devices.items():
            if hasattr(dev, "stop"):
                dev.stop()
                self.log_message.emit(f"[Manager] 设备 '{name}' 已安全停止")

    # === UI 控制代理接口 (UI 只需要调用这些方法) ===

    def set_temperature(self, channel: int, value: float):
        dev = self._get_device("temp")
        if dev: dev.set_target_temp(channel, value)

    def tare_weight(self):
        dev = self._get_device("weight")
        if dev: dev.tare()

    def stir_x(self, speed, seconds=None):
        dev = self._get_device("stir")
        if dev: dev.x(speed, seconds)

    def stir_y(self, speed, seconds=None):
        dev = self._get_device("stir")
        if dev: dev.y(speed, seconds)

    def stir_u(self, state):
        dev = self._get_device("stir")
        if dev: dev.u(state)

    def dispense_powder(self, amount):
        dev = self._get_device("powder")
        if dev: dev.dispense(amount)

    def deliver_monomer(self, amount):
        dev = self._get_device("monomer")
        if dev: dev.deliver(amount)

    def retract_monomer(self, amount):
        dev = self._get_device("monomer")
        if dev: dev.retract(amount)

    # === 内部辅助方法 ===
    def _get_device(self, prefix: str):
        """根据前缀查找设备，找不到则记录错误"""
        for name, dev in self.devices.items():
            if name.startswith(prefix):
                return dev
        self.log_message.emit(f"[Manager Error] 未找到以 '{prefix}' 开头的设备，无法执行指令")
        return None