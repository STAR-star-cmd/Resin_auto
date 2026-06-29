import sys
import pyqtgraph as pg
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QGroupBox, QLabel, QPushButton, QPlainTextEdit, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
# 假设你的 dialog 文件路径正确
from ui.dialog import TemperatureDialog, SystemStatusDialog, SystemSettingsDialog, DebugDialog, StartConfigDialog, \
    MonomerControlDialog, PowderControlDialog


class MainWindow(QMainWindow):
    # --- 发往 Manager 的请求信号 (意图) ---
    request_set_temp = pyqtSignal(int, float)
    request_start_process = pyqtSignal()
    request_stop_process = pyqtSignal()
    request_tare = pyqtSignal(int)  # 建议：清零信号最好带上通道号，否则不知道清哪个

    # MonomerModule 控制信号
    request_deliver_monomer = pyqtSignal(float)
    request_retract_monomer = pyqtSignal(float)
    request_monomer_stop = pyqtSignal()
    request_monomer_home = pyqtSignal()
    request_monomer_test = pyqtSignal()
    request_monomer_status = pyqtSignal()
    request_monomer_config = pyqtSignal()
    request_monomer_set_param = pyqtSignal(str, int)
    request_start_monomer_delivery = pyqtSignal()
    request_feed_monomer = pyqtSignal(int)
    request_move_monomer_extruder = pyqtSignal(int, int)
    request_move_monomer_main = pyqtSignal(int)
    request_trigger_monomer_pump = pyqtSignal(int, int)
    request_monomer_help = pyqtSignal()

    # PowderModule 控制信号
    request_dispense_powder = pyqtSignal(int, float)  # device_id, amount
    request_home_powder = pyqtSignal()
    request_set_powder_steps = pyqtSignal(int, int)   # device_id, steps
    request_stop_powder = pyqtSignal()
    request_reset_powder = pyqtSignal()
    request_status_powder = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("System Control Dashboard")
        self.resize(1200, 800)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(15, 15, 15, 15)

        # ================= TOP ROW =================
        top_layout = QHBoxLayout()
        top_layout.setSpacing(15)

        # 1. Temperature Module (保持不变)
        temp_group = QGroupBox("Temperature Monitor")
        temp_layout = QGridLayout()
        temp_layout.setHorizontalSpacing(15)
        temp_layout.setVerticalSpacing(10)

        headers = ["Channel", "Real-time (°C)", "Set Temp (°C)", "Action"]
        for col, text in enumerate(headers):
            label = QLabel(f" {text}")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            temp_layout.addWidget(label, 0, col)

        self.temp_realtime_labels = []
        self.temp_set_labels = []

        for i in range(1, 5):
            ch_label = QLabel(f"CH {i}")
            ch_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            real_time = QLabel("--.-")
            real_time.setAlignment(Qt.AlignmentFlag.AlignCenter)
            set_temp = QLabel("25.0")
            set_temp.setAlignment(Qt.AlignmentFlag.AlignCenter)
            btn = QPushButton("Modify")
            btn.clicked.connect(lambda _, ch=f"CH {i}": self.open_temp_dialog(ch))

            temp_layout.addWidget(ch_label, i, 0)
            temp_layout.addWidget(real_time, i, 1)
            temp_layout.addWidget(set_temp, i, 2)
            temp_layout.addWidget(btn, i, 3)

            self.temp_realtime_labels.append(real_time)
            self.temp_set_labels.append(set_temp)

        temp_group.setLayout(temp_layout)

        # 2. Weight Module (★ 核心修改区域 ★)
        # 创建一个容器来放置两个独立的称重框
        weight_container = QWidget()
        weight_container_layout = QVBoxLayout(weight_container)
        weight_container_layout.setContentsMargins(0, 0, 0, 0)
        weight_container_layout.setSpacing(10)

        self.weight_realtime_labels = []

        for i in range(1, 3):
            # 为每个通道创建独立的 GroupBox
            w_group = QGroupBox(f"Weight Source CH {i}")
            w_layout = QHBoxLayout()  # 单个通道内部使用水平布局更紧凑
            w_layout.setContentsMargins(10, 15, 10, 10)
            w_layout.setSpacing(10)

            real_time = QLabel("--.- g")
            real_time.setAlignment(Qt.AlignmentFlag.AlignCenter)
            real_time.setStyleSheet("font-size: 16px; font-weight: bold; color: #333;")

            btn_tare = QPushButton("Tare / Zero")
            btn_tare.setMinimumWidth(100)
            # 修复：绑定清零信号时传入通道索引 i-1
            btn_tare.clicked.connect(lambda _, idx=i - 1: self.request_tare.emit(idx))

            w_layout.addWidget(QLabel("Real-time:"), 0, Qt.AlignmentFlag.AlignRight)
            w_layout.addWidget(real_time, 1)
            w_layout.addWidget(btn_tare, 0, Qt.AlignmentFlag.AlignRight)

            w_group.setLayout(w_layout)

            # 将子 GroupBox 加入容器布局
            weight_container_layout.addWidget(w_group)
            self.weight_realtime_labels.append(real_time)

        # 3. Plot Module (保持不变)
        plot_group = QGroupBox("Mechanical Curve")
        plot_layout = QVBoxLayout()

        pg.setConfigOption('background', '#f8f9fa')
        pg.setConfigOption('foreground', '#212529')
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel('left', 'Force (N)')
        self.plot_widget.setLabel('bottom', 'Displacement (mm)')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)

        plot_layout.addWidget(self.plot_widget)
        plot_group.setLayout(plot_layout)

        # 注意：这里把原来的 weight_group 替换成了 weight_container
        top_layout.addWidget(temp_group, stretch=1)
        top_layout.addWidget(weight_container, stretch=1)
        top_layout.addWidget(plot_group, stretch=2)
        main_layout.addLayout(top_layout, stretch=3)

        # ================= BOTTOM ROW =================
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(15)

        log_group = QGroupBox("System Log")
        log_layout = QVBoxLayout()
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        bottom_layout.addWidget(log_group, stretch=3)

        control_group = QGroupBox("System Controls")
        control_layout = QVBoxLayout()
        control_layout.setSpacing(15)

        self.btn_start = QPushButton("Start Config")
        self.btn_stop = QPushButton("Stop Activity")
        self.btn_settings = QPushButton("System Settings")
        self.btn_status = QPushButton("System Status")
        self.btn_debug = QPushButton("System Debug")

        for btn in (self.btn_start, self.btn_stop, self.btn_settings, self.btn_status, self.btn_debug):
            btn.setMinimumHeight(45)

        self.btn_start.clicked.connect(self.open_start_config_dialog)
        self.btn_stop.clicked.connect(self.request_stop_process.emit)
        self.btn_settings.clicked.connect(self.open_settings_dialog)
        self.btn_status.clicked.connect(self.open_status_dialog)
        self.btn_debug.clicked.connect(self.open_debug_dialog)

        control_layout.addWidget(self.btn_start)
        control_layout.addWidget(self.btn_stop)
        control_layout.addWidget(self.btn_settings)
        control_layout.addWidget(self.btn_status)
        control_layout.addStretch()
        control_layout.addWidget(self.btn_debug)

        control_group.setLayout(control_layout)
        bottom_layout.addWidget(control_group, stretch=1)

        main_layout.addLayout(bottom_layout, stretch=2)

    # ================= 内部事件交互 =================
    def open_temp_dialog(self, channel):
        dialog = TemperatureDialog(self, channel)
        if dialog.exec():
            val = dialog.spin_box.value()
            ch_idx = int(channel.split()[-1]) - 1
            self.temp_set_labels[ch_idx].setText(f"{val:.1f}")
            self.append_log(f"Set temperature for {channel} to {val} °C")
            self.request_set_temp.emit(ch_idx, val)

    def open_settings_dialog(self):
        dialog = SystemSettingsDialog(self)
        if dialog.exec():
            self.append_log("系统参数设置已确认并保存。")

    def open_status_dialog(self):
        dialog = SystemStatusDialog(self)
        dialog.exec()

    def open_debug_dialog(self):
        dialog = DebugDialog(self)
        dialog.exec()

    def open_start_config_dialog(self):
        dialog = StartConfigDialog(self)
        dialog.buttons[0].clicked.connect(lambda: (self.request_start_process.emit(), dialog.accept()))

        def on_module1_clicked():
            mono_dialog = MonomerControlDialog(self)

            # 1. 基础动作
            mono_dialog.btn_deliver.clicked.connect(
                lambda: self.request_deliver_monomer.emit(mono_dialog.amount_spin.value()))
            mono_dialog.btn_retract.clicked.connect(
                lambda: self.request_retract_monomer.emit(mono_dialog.amount_spin.value()))
            mono_dialog.btn_stop.clicked.connect(self.request_monomer_stop.emit)
            mono_dialog.btn_home.clicked.connect(self.request_monomer_home.emit)
            mono_dialog.btn_test.clicked.connect(self.request_monomer_test.emit)
            mono_dialog.btn_deliver_seq.clicked.connect(self.request_start_monomer_delivery.emit)

            # 2. 工位给料
            mono_dialog.btn_feed.clicked.connect(
                lambda: self.request_feed_monomer.emit(mono_dialog.feed_station_spin.value()))

            # 3. 独立电机控制 (使用 lambda 闭包绑定索引)
            for i, (spin, btn) in enumerate(mono_dialog.ext_spins):
                btn.clicked.connect(lambda _, idx=i, sp=spin: self.request_move_monomer_extruder.emit(idx, sp.value()))

            mono_dialog.btn_move_main.clicked.connect(
                lambda: self.request_move_monomer_main.emit(mono_dialog.main_spin.value()))

            mono_dialog.btn_pump1.clicked.connect(
                lambda: self.request_trigger_monomer_pump.emit(1, mono_dialog.pump_spin.value()))
            mono_dialog.btn_pump2.clicked.connect(
                lambda: self.request_trigger_monomer_pump.emit(2, mono_dialog.pump_spin.value()))

            # 4. 参数与查询
            mono_dialog.btn_status.clicked.connect(self.request_monomer_status.emit)
            mono_dialog.btn_config.clicked.connect(self.request_monomer_config.emit)
            mono_dialog.btn_help.clicked.connect(self.request_monomer_help.emit)
            mono_dialog.btn_set_param.clicked.connect(
                lambda: self.request_monomer_set_param.emit(
                    mono_dialog.param_key_combo.currentText(),
                    mono_dialog.param_value_spin.value()))

            mono_dialog.exec()

        def on_module2_clicked():
            powder_dialog = PowderControlDialog(self)
            # 动态绑定3个送料装置的按钮信号
            for feeder in powder_dialog.feeders:
                feeder['btn_dispense'].clicked.connect(
                    lambda _, f=feeder: self.request_dispense_powder.emit(f['id'], f['amount_spin'].value()))
                feeder['btn_set_steps'].clicked.connect(
                    lambda _, f=feeder: self.request_set_powder_steps.emit(f['id'], f['steps_spin'].value()))

            # 绑定全局按钮
            powder_dialog.btn_home.clicked.connect(self.request_home_powder.emit)
            powder_dialog.btn_stop.clicked.connect(self.request_stop_powder.emit)
            powder_dialog.btn_reset.clicked.connect(self.request_reset_powder.emit)
            powder_dialog.btn_status.clicked.connect(self.request_status_powder.emit)
            powder_dialog.exec()

        dialog.buttons[1].clicked.connect(on_module1_clicked)
        dialog.buttons[2].clicked.connect(on_module2_clicked)
        for i, name in enumerate(["Module3", "Module4", "Module5"], start=1):
            dialog.buttons[i].clicked.connect(lambda _, n=name: self.append_log(f"[Config] 进入 {n} 控制界面"))
        dialog.exec()

    @pyqtSlot(str)
    def append_log(self, message):
        time_str = datetime.now().strftime("%H:%M:%S")
        self.log_text.appendPlainText(f"[{time_str}] {message}")

    # ================= 接收来自 Manager 的数据更新槽 =================
    @pyqtSlot(dict)
    def update_temp_display(self, data: dict):
        for i in range(4):
            ch_key = f"CH{i + 1}"
            if ch_key in data:
                self.temp_realtime_labels[i].setText(f"{data[ch_key]:.1f}")

    @pyqtSlot(str, dict)
    def update_weight_display(self, channel: str, data: dict):
        """接收 Manager 发来的重量字典"""
        ch_idx = int(channel.split("_ch")[-1]) - 1
        if 0 <= ch_idx < len(self.weight_realtime_labels):
            self.weight_realtime_labels[ch_idx].setText(f"{data['weight']:.2f} g")

    @pyqtSlot(str)
    def show_error_message(self, msg: str):
        QMessageBox.critical(self, "硬件错误", msg)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet("""
        QGroupBox { font-weight: bold; border: 1px solid #cccccc; border-radius: 6px; margin-top: 12px; font-size: 14px; }
        QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px 0 5px; }
        QLabel { font-size: 13px; }
        QPushButton { background-color: #0078D7; color: white; border: none; border-radius: 4px; font-size: 13px; padding: 5px 15px;}
        QPushButton:hover { background-color: #005A9E; }
        QPushButton:pressed { background-color: #004578; }
    """)

    window = MainWindow()
    window.show()
    window.append_log("系统初始化完成。UI 框架已就绪。")
    sys.exit(app.exec())