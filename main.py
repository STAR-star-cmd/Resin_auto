import sys
from PyQt6.QtWidgets import QApplication
from ui.main_window import MainWindow
from hardware.comm_manager import HardwareManager


def main():
    app = QApplication(sys.argv)

    # 1. 实例化核心组件
    hw_manager = HardwareManager()
    window = MainWindow()

    # 2. 连接信号：UI 的请求 -> Manager 的执行
    window.request_set_temp.connect(hw_manager.set_temperature)
    window.request_start_process.connect(hw_manager.start_process)

    # 3. 连接信号：Manager 的数据/错误 -> UI 的展示
    hw_manager.temps_updated.connect(window.update_temp_display)
    hw_manager.error_occurred.connect(window.show_error_message)

    # 4. 启动 UI
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()