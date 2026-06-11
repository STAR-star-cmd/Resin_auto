import sys
import logging
from PyQt6.QtWidgets import QApplication

from hardware.comm_manager import HardwareManager
from hardware.temperature_module import TemperatureDevice
from hardware.weight_module import WeighingModule
from hardware.stirring_module import StirringModule
from hardware.powder_module import PowderModule
from hardware.monomer_module import MonomerModule
from ui.main_window import MainWindow

# 配置基础日志，以防 UI 还没加载出来时发生底层错误
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def setup_hardware(manager: HardwareManager):
    """
    硬件注册中心。
    使用 try-except 确保单个硬件离线不会导致整个程序崩溃。
    """
    # 🔧 请根据实际硬件连接的 COM 口号修改这里的 port 值
    # 如果某个设备暂时不用，可以直接注释掉对应的字典项
    hardware_config = {
        "temp": {"class": TemperatureDevice, "kwargs": {"port": "COM3"}},
        "weight": {"class": WeighingModule, "kwargs": {"port": "COM4"}},
        "stir": {"class": StirringModule, "kwargs": {"port": "COM5"}},
        "powder": {"class": PowderModule, "kwargs": {"port": "COM6"}},
        "monomer": {"class": MonomerModule, "kwargs": {"port": "COM7"}},
    }

    for name, config in hardware_config.items():
        try:
            # 实例化底层硬件模块
            device = config["class"](**config["kwargs"])
            # 注册到 Manager，Manager 会自动桥接其信号
            manager.register_device(name, device)
            logging.info(f"[Main] 成功注册设备: {name}")
        except Exception as e:
            logging.error(f"[Main] 注册设备 {name} 失败 (可能未连接): {e}")


def main():
    app = QApplication(sys.argv)

    # 1. 核心组件实例化
    hw_manager = HardwareManager()

    # 2. 硬件注册与初始化
    setup_hardware(hw_manager)

    # 3. UI 实例化
    window = MainWindow()

    # 4. 信号与槽的连接 (打通大动脉)
    # 使用 hasattr 进行防御性连接，防止 UI 还没写完某个信号导致 main.py 崩溃

    # --- 4.1 UI 控制请求 -> Manager 执行 ---
    if hasattr(window, 'request_set_temp'):
        window.request_set_temp.connect(hw_manager.set_temperature)
    if hasattr(window, 'request_start_process'):
        window.request_start_process.connect(hw_manager.start_all)
    if hasattr(window, 'request_stop_process'):
        window.request_stop_process.connect(hw_manager.stop_all)
    if hasattr(window, 'request_tare'):
        window.request_tare.connect(hw_manager.tare_weight)
    if hasattr(window, 'request_stir_x'):
        window.request_stir_x.connect(hw_manager.stir_x)
    if hasattr(window, 'request_stir_y'):
        window.request_stir_y.connect(hw_manager.stir_y)
    if hasattr(window, 'request_stir_u'):
        window.request_stir_u.connect(hw_manager.stir_u)
    if hasattr(window, 'request_dispense_powder'):
        window.request_dispense_powder.connect(hw_manager.dispense_powder)
    if hasattr(window, 'request_deliver_monomer'):
        window.request_deliver_monomer.connect(hw_manager.deliver_monomer)
    if hasattr(window, 'request_retract_monomer'):
        window.request_retract_monomer.connect(hw_manager.retract_monomer)

    # --- 4.2 Manager 数据/状态 -> UI 展示 ---
    if hasattr(window, 'update_temp_display'):
        hw_manager.temp_data.connect(window.update_temp_display)
    if hasattr(window, 'update_weight_display'):
        hw_manager.weight_data.connect(window.update_weight_display)
    if hasattr(window, 'on_device_ready'):
        hw_manager.device_ready.connect(window.on_device_ready)

    # 统一日志路由：将 Manager 收集到的所有底层日志打印到 UI 的日志区
    if hasattr(window, 'append_log'):
        hw_manager.log_message.connect(window.append_log)

    # 5. 启动流程
    window.show()
    logging.info("[Main] UI 加载完成，正在启动所有硬件后台线程...")
    hw_manager.start_all()

    # 6. 优雅退出处理 (关键！)
    # 拦截程序退出信号，确保所有 QThread 被安全销毁，串口被正确 close()
    # 这能彻底解决“关闭程序后再次启动提示串口被占用”的痛点
    def on_exit():
        logging.info("[Main] 正在关闭程序，安全释放硬件资源...")
        hw_manager.stop_all()

    app.aboutToQuit.connect(on_exit)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()