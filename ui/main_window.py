import sys
import pyqtgraph as pg
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QGroupBox, QLabel, QPushButton, QPlainTextEdit, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from ui.dialog import TemperatureDialog, SystemStatusDialog, SystemSettingsDialog, DebugDialog

# ================= 主窗口 =================
class MainWindow(QMainWindow):
    # --- 发往 Manager 的请求信号 (意图) ---
    request_set_temp = pyqtSignal(float)
    request_start_process = pyqtSignal()
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

        # 1. Temperature Module
        temp_group = QGroupBox("Temperature Monitor")
        temp_layout = QGridLayout()
        temp_layout.setHorizontalSpacing(15)
        temp_layout.setVerticalSpacing(10)

        headers = ["Channel", "Real-time (°C)", "Set Temp (°C)", "Action"]
        for col, text in enumerate(headers):
            label = QLabel(f"<b>{text}</b>")
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

        # 2. Weight Module
        weight_group = QGroupBox("Weight Monitor")
        weight_layout = QGridLayout()
        weight_layout.setHorizontalSpacing(15)
        weight_layout.setVerticalSpacing(10)

        w_headers = ["Channel", "Real-time (g)", "Action"]
        for col, text in enumerate(w_headers):
            label = QLabel(f"<b>{text}</b>")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            weight_layout.addWidget(label, 0, col)

        self.weight_realtime_labels = []
        for i in range(1, 3):
            ch_label = QLabel(f"CH {i}")
            ch_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            real_time = QLabel("--.-")
            real_time.setAlignment(Qt.AlignmentFlag.AlignCenter)
            btn = QPushButton("Tare / Zero")

            weight_layout.addWidget(ch_label, i, 0)
            weight_layout.addWidget(real_time, i, 1)
            weight_layout.addWidget(btn, i, 2)

            self.weight_realtime_labels.append(real_time)

        weight_group.setLayout(weight_layout)

        # 3. Plot Module
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

        top_layout.addWidget(temp_group, stretch=1)
        top_layout.addWidget(weight_group, stretch=1)
        top_layout.addWidget(plot_group, stretch=2)
        main_layout.addLayout(top_layout, stretch=3)

        # ================= BOTTOM ROW =================
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(15)

        # 1. Text Display
        log_group = QGroupBox("System Log")
        log_layout = QVBoxLayout()
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        bottom_layout.addWidget(log_group, stretch=3)

        # 2. Control Buttons
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

        # 绑定事件
        self.btn_settings.clicked.connect(self.open_settings_dialog)
        self.btn_status.clicked.connect(self.open_status_dialog)
        self.btn_debug.clicked.connect(self.open_debug_dialog)

        # 布局排列
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

    def open_settings_dialog(self):
        dialog = SystemSettingsDialog(self)
        if dialog.exec():
            self.append_log("系统参数设置已确认并保存。")

    def open_status_dialog(self):
        dialog = SystemStatusDialog(self)
        dialog.exec()

    def open_debug_dialog(self):
        """打开调试对话框"""
        dialog = DebugDialog(self)
        dialog.exec()

    def append_log(self, message):
        time_str = datetime.now().strftime("%H:%M:%S")
        self.log_text.appendPlainText(f"[{time_str}] {message}")

    # ================= 外部数据接入预留接口 =================
    def update_temperature(self, channel_idx, value):
        if 0 <= channel_idx < 4:
            self.temp_realtime_labels[channel_idx].setText(f"{value:.1f}")

    def update_weight(self, channel_idx, value):
        if 0 <= channel_idx < 2:
            self.weight_realtime_labels[channel_idx].setText(f"{value:.2f}")

    def update_plot(self, x_data, y_data):
        self.plot_widget.plot(x_data, y_data, pen=pg.mkPen('b', width=2), clear=True)

    # --- 接收来自 Manager 的数据更新槽 ---
    @pyqtSlot(float)
    def update_temp_display(self, temp: float):
        self.lbl_temp.setText(f"当前温度: {temp:.1f} °C")

    @pyqtSlot(str)
    def show_error_message(self, msg: str):
        """硬件层发生错误时，由 Manager 调用此槽弹窗"""
        QMessageBox.critical(self, "硬件错误", msg)

if __name__ == "__main__":
    app = QApplication(sys.argv)

    app.setStyleSheet("""
        QGroupBox { 
            font-weight: bold; 
            border: 1px solid #cccccc; 
            border-radius: 6px; 
            margin-top: 12px; 
            font-size: 14px;
        }
        QGroupBox::title { 
            subcontrol-origin: margin; 
            left: 10px; 
            padding: 0 5px 0 5px;
        }
        QLabel {
            font-size: 13px;
        }
        QPushButton {
            background-color: #0078D7;
            color: white;
            border: none;
            border-radius: 4px;
            font-size: 13px;
        }
        QPushButton:hover {
            background-color: #005A9E;
        }
        QPushButton:pressed {
            background-color: #004578;
        }
    """)

    window = MainWindow()
    window.show()
    window.append_log("系统初始化完成。UI 框架已就绪。")

    sys.exit(app.exec())