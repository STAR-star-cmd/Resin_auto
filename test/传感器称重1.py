import sys
import serial.tools.list_ports
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QComboBox, QPushButton,
                             QTabWidget, QGroupBox, QGridLayout, QLineEdit,
                             QMessageBox, QSplitter, QSpinBox)
from PyQt6.QtCore import QTimer, Qt
import pyqtgraph as pg
from pymodbus.client import ModbusSerialClient
from collections import deque


class WeightTransmitterApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("中盛称重变送器(RS485)上位机 - PyQt6")
        self.resize(1200, 800)

        self.client = None
        self.is_connected = False
        self.slave_id = 1

        # 数据缓存 (用于画图，保留最近200个点)
        self.data_buffers = [deque(maxlen=200) for _ in range(4)]
        self.time_buffer = deque(maxlen=200)
        self.time_step = 0

        self.init_ui()
        self.init_timer()

    def init_ui(self):
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        self.setCentralWidget(main_widget)

        # ================= 1. 串口设置区 =================
        serial_group = QGroupBox("串口通讯设置")
        serial_layout = QHBoxLayout()

        self.port_combo = QComboBox()
        self.refresh_ports()
        btn_refresh = QPushButton("刷新串口")
        btn_refresh.clicked.connect(self.refresh_ports)

        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["9600", "4800", "14400", "19200", "38400", "57600", "115200"])
        self.baud_combo.setCurrentText("9600")

        self.slave_spin = QSpinBox()
        self.slave_spin.setRange(1, 255)
        self.slave_spin.setValue(1)

        self.btn_connect = QPushButton("连接设备")
        self.btn_connect.setFixedWidth(100)
        self.btn_connect.clicked.connect(self.toggle_connection)

        serial_layout.addWidget(QLabel("串口:"))
        serial_layout.addWidget(self.port_combo)
        serial_layout.addWidget(btn_refresh)
        serial_layout.addWidget(QLabel("波特率:"))
        serial_layout.addWidget(self.baud_combo)
        serial_layout.addWidget(QLabel("从站地址:"))
        serial_layout.addWidget(self.slave_spin)
        serial_layout.addStretch()
        serial_layout.addWidget(self.btn_connect)
        serial_group.setLayout(serial_layout)
        main_layout.addWidget(serial_group)

        # ================= 2. 主工作区 (左侧曲线 + 右侧控制) =================
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- 左侧：曲线与数据显示 ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        # 数值显示
        weight_layout = QHBoxLayout()
        self.lbl_weights = []
        colors = ['r', 'g', 'b', 'm']
        for i in range(4):
            lbl = QLabel(f"通道{i + 1}: 0 g")
            lbl.setStyleSheet(
                f"color: {colors[i]}; font-weight: bold; font-size: 16px; background-color: #f0f0f0; padding: 5px; border-radius: 5px;")
            self.lbl_weights.append(lbl)
            weight_layout.addWidget(lbl)
        left_layout.addLayout(weight_layout)

        # 实时曲线
        pg.setConfigOption('background', 'w')
        pg.setConfigOption('foreground', 'k')
        self.plot_widget = pg.PlotWidget(title="实时重量曲线 (g)")
        self.plot_widget.addLegend()
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.curves = []
        for i in range(4):
            curve = self.plot_widget.plot(pen=colors[i], name=f"通道 {i + 1}")
            self.curves.append(curve)
        left_layout.addWidget(self.plot_widget)

        # --- 右侧：参数控制面板 ---
        self.tabs = QTabWidget()
        self.tabs.addTab(self.create_tab_system(), "系统与通讯")
        self.tabs.addTab(self.create_tab_control(), "称重控制")
        self.tabs.addTab(self.create_tab_calibration(), "标定校准")

        splitter.addWidget(left_widget)
        splitter.addWidget(self.tabs)
        splitter.setSizes([700, 500])
        main_layout.addWidget(splitter)

    def create_tab_system(self):
        widget = QWidget()
        layout = QGridLayout(widget)

        # 设备ID
        layout.addWidget(QLabel("设备ID (1-255):"), 0, 0)
        self.sys_id_spin = QSpinBox()
        self.sys_id_spin.setRange(1, 255)
        layout.addWidget(self.sys_id_spin, 0, 1)
        btn_set_id = QPushButton("设置ID (需重启)")
        btn_set_id.clicked.connect(lambda: self.write_single_register(0x0032, self.sys_id_spin.value()))
        layout.addWidget(btn_set_id, 0, 2)

        # 波特率
        layout.addWidget(QLabel("模块波特率:"), 1, 0)
        self.sys_baud_combo = QComboBox()
        self.sys_baud_combo.addItems(["4800", "9600", "14400", "19200", "38400", "56000", "57600", "115200"])
        self.sys_baud_combo.setCurrentIndex(1)
        layout.addWidget(self.sys_baud_combo, 1, 1)
        btn_set_baud = QPushButton("设置波特率 (需重启)")
        btn_set_baud.clicked.connect(lambda: self.write_single_register(0x0033, self.sys_baud_combo.currentIndex()))
        layout.addWidget(btn_set_baud, 1, 2)

        # 奇偶校验
        layout.addWidget(QLabel("奇偶校验:"), 2, 0)
        self.sys_parity_combo = QComboBox()
        self.sys_parity_combo.addItems(["无校验", "奇校验", "偶校验"])
        layout.addWidget(self.sys_parity_combo, 2, 1)
        btn_set_parity = QPushButton("设置校验 (需重启)")
        btn_set_parity.clicked.connect(lambda: self.write_single_register(0x003D, self.sys_parity_combo.currentIndex()))
        layout.addWidget(btn_set_parity, 2, 2)

        layout.setRowStretch(3, 1)
        layout.addWidget(QLabel("⚠️ 注意：修改系统通讯参数后，必须对设备断电重新上电才能生效！",
                                styleSheet="color: red; font-weight: bold;"), 4, 0, 1, 3)
        return widget

    def create_tab_control(self):
        widget = QWidget()
        layout = QGridLayout(widget)

        layout.addWidget(QLabel("<b>快捷操作</b>"), 0, 0, 1, 4)
        for i in range(4):
            btn_tare = QPushButton(f"通道{i + 1} 去皮")
            btn_tare.clicked.connect(lambda checked, ch=i + 1: self.write_single_register(0x0034, ch))
            layout.addWidget(btn_tare, 1, i)

            btn_zero = QPushButton(f"通道{i + 1} 零点校准")
            btn_zero.clicked.connect(lambda checked, ch=i + 1: self.write_single_register(0x0035, ch))
            layout.addWidget(btn_zero, 2, i)

        layout.addWidget(QLabel("<b>追零范围 (0~100)</b>"), 3, 0, 1, 4)
        self.spin_tare_range = []
        for i in range(4):
            spin = QSpinBox()
            spin.setRange(0, 100)
            self.spin_tare_range.append(spin)
            layout.addWidget(QLabel(f"通道{i + 1}:"), 4, i * 2)
            layout.addWidget(spin, 4, i * 2 + 1)
        btn_set_tare_range = QPushButton("下发追零范围")
        btn_set_tare_range.clicked.connect(self.set_all_tare_ranges)
        layout.addWidget(btn_set_tare_range, 5, 0, 1, 4)

        layout.addWidget(QLabel("<b>采集速率</b>"), 6, 0, 1, 4)
        self.combo_rate = []
        for i in range(4):
            combo = QComboBox()
            combo.addItems(["10Hz (1)", "40Hz (2)"])
            self.combo_rate.append(combo)
            layout.addWidget(QLabel(f"通道{i + 1}:"), 7, i * 2)
            layout.addWidget(combo, 7, i * 2 + 1)
        btn_set_rate = QPushButton("下发采集速率")
        btn_set_rate.clicked.connect(self.set_all_rates)
        layout.addWidget(btn_set_rate, 8, 0, 1, 4)

        layout.setRowStretch(9, 1)
        return widget

    def create_tab_calibration(self):
        widget = QWidget()
        layout = QGridLayout(widget)

        layout.addWidget(QLabel("⚠️ 标定前，请确保修正系数为1:1（或恢复出厂设置），并重新上电。"), 0, 0, 1, 3,
                         Qt.AlignmentFlag.AlignCenter)

        self.calib_ch_combo = QComboBox()
        self.calib_ch_combo.addItems(["通道1", "通道2", "通道3", "通道4"])
        layout.addWidget(QLabel("选择通道:"), 1, 0)
        layout.addWidget(self.calib_ch_combo, 1, 1)

        self.lbl_current_ad = QLabel("当前AD值: 未知")
        self.lbl_current_ad.setStyleSheet("font-weight: bold; color: blue;")
        layout.addWidget(self.lbl_current_ad, 2, 0, 1, 2)
        btn_read_ad = QPushButton("读取当前AD值")
        btn_read_ad.clicked.connect(self.read_current_ad)
        layout.addWidget(btn_read_ad, 2, 2)

        layout.addWidget(QLabel("标准砝码重量(g):"), 3, 0)
        self.input_weight = QLineEdit("2000")
        layout.addWidget(self.input_weight, 3, 1, 1, 2)

        btn_calc_write = QPushButton("计算并写入修正系数 (需重启)")
        btn_calc_write.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 10px;")
        btn_calc_write.clicked.connect(self.calc_and_write_coeff)
        layout.addWidget(btn_calc_write, 4, 0, 1, 3)

        layout.setRowStretch(5, 1)
        return widget

    def init_timer(self):
        self.timer = QTimer()
        self.timer.timeout.connect(self.read_data)

    def refresh_ports(self):
        self.port_combo.clear()
        ports = serial.tools.list_ports.comports()
        for port in ports:
            self.port_combo.addItem(port.device)

    def toggle_connection(self):
        if not self.is_connected:
            port = self.port_combo.currentText()
            baud = int(self.baud_combo.currentText())
            self.slave_id = self.slave_spin.value()

            self.client = ModbusSerialClient(port=port, baudrate=baud, parity='N', stopbits=1, bytesize=8, timeout=1)
            if self.client.connect():
                self.is_connected = True
                self.btn_connect.setText("断开连接")
                self.btn_connect.setStyleSheet("background-color: #f44336; color: white;")
                self.timer.start(100)
            else:
                QMessageBox.critical(self, "错误", "串口连接失败，请检查端口和接线!")
        else:
            self.timer.stop()
            self.client.close()
            self.is_connected = False
            self.btn_connect.setText("连接设备")
            self.btn_connect.setStyleSheet("")

    def read_data(self):
        if not self.is_connected:
            return
        try:
            # 新版 pymodbus 使用 device_id 替代 slave
            result = self.client.read_holding_registers(address=0x0000, count=8, device_id=self.slave_id)
            if not result.isError():
                # 使用新 API 解码 32 位有符号整型 (INT32)
                # 注意：如果解析出的数据异常(如乱码或超大值)，请将 word_order="big" 改为 "little"
                weights = self.client.convert_from_registers(
                    registers=result.registers,
                    data_type=self.client.DATATYPE.INT32,
                    word_order="big"
                )

                self.time_step += 1
                self.time_buffer.append(self.time_step)

                for i in range(4):
                    self.data_buffers[i].append(weights[i])
                    self.lbl_weights[i].setText(f"通道{i + 1}: {weights[i]} g")
                    self.curves[i].setData(self.time_buffer, self.data_buffers[i])
        except Exception as e:
            pass  # 忽略单次读取超时或异常，保持界面流畅

    def write_single_register(self, address, value):
        if not self.is_connected:
            QMessageBox.warning(self, "警告", "请先连接串口!")
            return
        try:
            result = self.client.write_register(address=address, value=value, device_id=self.slave_id)
            if not result.isError():
                QMessageBox.information(self, "成功", "指令下发成功!")
            else:
                QMessageBox.critical(self, "失败", "写入失败，请检查地址和设备状态!")
        except Exception as e:
            QMessageBox.critical(self, "错误", str(e))

    def set_all_tare_ranges(self):
        if not self.is_connected: return
        base_addr = 0x0036
        for i in range(4):
            self.client.write_register(address=base_addr + i, value=self.spin_tare_range[i].value(),
                                       device_id=self.slave_id)
        QMessageBox.information(self, "成功", "追零范围设置已下发!")

    def set_all_rates(self):
        if not self.is_connected: return
        base_addr = 0x0043
        for i in range(4):
            val = self.combo_rate[i].currentIndex() + 1
            self.client.write_register(address=base_addr + i, value=val, device_id=self.slave_id)
        QMessageBox.information(self, "成功", "采集速率设置已下发!")

    def read_current_ad(self):
        if not self.is_connected:
            QMessageBox.warning(self, "警告", "请先连接串口!")
            return
        ch = self.calib_ch_combo.currentIndex()
        try:
            # 从UI标签中安全提取当前重量数值作为AD值
            text = self.lbl_weights[ch].text()
            weight_str = text.split(":")[1].replace("g", "").strip()
            ad_val = abs(int(weight_str))
            self.lbl_current_ad.setText(f"当前AD值: {ad_val}")
        except Exception:
            QMessageBox.warning(self, "警告", "读取AD值失败，请确保已连接并获取到数据!")

    def calc_and_write_coeff(self):
        if not self.is_connected:
            QMessageBox.warning(self, "警告", "请先连接串口!")
            return

        try:
            ch = self.calib_ch_combo.currentIndex()
            target_weight = float(self.input_weight.text())
            ad_text = self.lbl_current_ad.text()
            if "未知" in ad_text:
                QMessageBox.warning(self, "警告", "请先读取当前AD值!")
                return

            ad_value = float(ad_text.split(":")[1].strip())
            if ad_value == 0:
                QMessageBox.critical(self, "错误", "AD值不能为0，请确保传感器已受力且系数为1:1!")
                return

            coeff = target_weight / ad_value
            base_addr = 0x0064 + ch * 2

            # 使用新 API 将浮点数编码为 Modbus 寄存器列表
            registers = self.client.convert_to_registers(
                value=coeff,
                data_type=self.client.DATATYPE.FLOAT32,
                word_order="big"  # 如果设备要求小端，改为 "little"
            )

            result = self.client.write_registers(address=base_addr, values=registers, device_id=self.slave_id)
            if not result.isError():
                QMessageBox.information(self, "成功",
                                        f"通道{ch + 1}修正系数({coeff:.6f})写入成功!\n⚠️ 请断电重新上电使参数生效！")
            else:
                QMessageBox.critical(self, "失败", "写入失败!")
        except ValueError:
            QMessageBox.critical(self, "错误", "请输入有效的砝码重量数值!")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = WeightTransmitterApp()
    window.show()
    sys.exit(app.exec())