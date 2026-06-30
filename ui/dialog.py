from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QLabel, QPushButton,
    QDialog, QSpinBox, QDoubleSpinBox, QDialogButtonBox, QFormLayout, QScrollArea, QTabWidget, QHBoxLayout, QComboBox,
    QPlainTextEdit, QGridLayout)
from PyQt6.QtCore import Qt

# ================= 温度设置对话框 =================
class TemperatureDialog(QDialog):
    """弹出对话框用于修改设定温度"""

    def __init__(self, parent=None, channel=""):
        super().__init__(parent)
        self.setWindowTitle(f"Set Temperature - {channel}")
        self.setMinimumWidth(250)

        layout = QFormLayout(self)

        self.spin_box = QSpinBox(self)
        self.spin_box.setRange(0, 500)
        self.spin_box.setValue(25)
        self.spin_box.setSuffix(" °C")
        layout.addRow("Target Temperature:", self.spin_box)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addRow(self.button_box)


# ================= 系统设置对话框 =================
class SystemSettingsDialog(QDialog):
    """系统设置对话框：包含重量和时间设置"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("System Settings")
        self.setMinimumWidth(500)
        self.setMinimumHeight(600)

        main_layout = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        layout = QVBoxLayout(scroll_widget)

        # 1. 单体重量 (4种)
        mono_group = QGroupBox("Monomers Weight")
        mono_form = QFormLayout()
        self.mono_spins = []
        for i in range(1, 5):
            spin = QDoubleSpinBox()
            spin.setRange(0.0, 9999.0)
            spin.setSuffix(" g")
            mono_form.addRow(f"Monomer {i}:", spin)
            self.mono_spins.append(spin)
        mono_group.setLayout(mono_form)
        layout.addWidget(mono_group)

        # 2. 低聚物重量 (2种)
        oligo_group = QGroupBox("Oligomers Weight")
        oligo_form = QFormLayout()
        self.oligo_spins = []
        for i in range(1, 3):
            spin = QDoubleSpinBox()
            spin.setRange(0.0, 9999.0)
            spin.setSuffix(" g")
            oligo_form.addRow(f"Oligomer {i}:", spin)
            self.oligo_spins.append(spin)
        oligo_group.setLayout(oligo_form)
        layout.addWidget(oligo_group)

        # 3. 粉末添加物重量 (3种)
        powder_group = QGroupBox("Powder Additives Weight")
        powder_form = QFormLayout()
        self.powder_spins = []
        for i in range(1, 4):
            spin = QDoubleSpinBox()
            spin.setRange(0.0, 9999.0)
            spin.setSuffix(" g")
            powder_form.addRow(f"Powder Type {i}:", spin)
            self.powder_spins.append(spin)
        powder_group.setLayout(powder_form)
        layout.addWidget(powder_group)

        # 4. 工艺时间设置 (搅拌x2、超声x1、UVx1)
        time_group = QGroupBox("Process Time Settings")
        time_form = QFormLayout()
        self.time_spins = {}

        for i in range(1, 3):
            spin = QSpinBox()
            spin.setRange(0, 9999)
            spin.setSuffix(" s")
            time_form.addRow(f"Stirring {i} Time:", spin)
            self.time_spins[f"stir_{i}"] = spin

        spin_us = QSpinBox()
        spin_us.setRange(0, 9999)
        spin_us.setSuffix(" s")
        time_form.addRow("Ultrasonic Time:", spin_us)
        self.time_spins["ultrasonic"] = spin_us

        spin_uv = QSpinBox()
        spin_uv.setRange(0, 9999)
        spin_uv.setSuffix(" s")
        time_form.addRow("UV Light Time:", spin_uv)
        self.time_spins["uv"] = spin_uv

        time_group.setLayout(time_form)
        layout.addWidget(time_group)

        layout.addStretch()
        scroll.setWidget(scroll_widget)
        main_layout.addWidget(scroll)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        main_layout.addWidget(btn_box)


# ================= 系统状态对话框 =================
class SystemStatusDialog(QDialog):
    """系统状态对话框：显示各个模块的实时参数"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("System Status Monitor")
        self.setMinimumSize(600, 500)

        main_layout = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        modules = [
            ("Temperature Module", ["CH1 Heater", "CH2 Heater", "CH3 Heater", "CH4 Heater"]),
            ("Weight Module", ["Scale 1 Connection", "Scale 2 Connection", "Auto-Tare Status"]),
            ("Mechanical Module", ["Force Sensor", "Motor Controller", "Sampling Rate"]),
            ("Process Actuators", ["Stirrer 1 RPM", "Stirrer 2 RPM", "Ultrasonic Power", "UV Light Intensity"])
        ]

        self.status_labels = {}

        for mod_name, params in modules:
            group = QGroupBox(mod_name)
            form = QFormLayout()
            for p in params:
                lbl = QLabel("Normal / Standby")
                lbl.setStyleSheet("color: green; font-weight: bold;")
                form.addRow(f"{p}:", lbl)
                self.status_labels[f"{mod_name}-{p}"] = lbl
            group.setLayout(form)
            scroll_layout.addWidget(group)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        main_layout.addWidget(scroll)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        main_layout.addWidget(btn_close)

    def update_status(self, key, value, color="green"):
        if key in self.status_labels:
            self.status_labels[key].setText(str(value))
            self.status_labels[key].setStyleSheet(f"color: {color}; font-weight: bold;")


# ================= 新增：系统调试对话框 =================
class DebugDialog(QDialog):
    """调试对话框：包含5个硬件模块的Tab页"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("系统调试面板 (System Debug)")
        self.resize(800, 600)

        main_layout = QVBoxLayout(self)
        self.tabs = QTabWidget()

        # 定义5个Tab页及其预设占位内容
        tabs_info = [
            ("液体材料模块", "Liquid Material Module - 调试参数与日志区域"),
            ("固体材料模块", "Solid Material Module - 调试参数与日志区域"),
            ("混匀模块", "Mixing Module - 调试参数与日志区域"),
            ("机械臂模块", "Robotic Arm Module - 调试参数与日志区域"),
            ("拉伸试样模块", "Tensile Specimen Module - 调试参数与日志区域")
        ]

        for name, text in tabs_info:
            tab = QWidget()
            tab_layout = QVBoxLayout(tab)

            # 预设空白占位
            label = QLabel(text)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("font-size: 16px; color: #888888; border: 2px dashed #cccccc; padding: 50px;")
            tab_layout.addWidget(label)
            tab_layout.addStretch()

            self.tabs.addTab(tab, name)

        main_layout.addWidget(self.tabs)

        # 底部关闭按钮
        btn_close = QPushButton("关闭 (Close)")
        btn_close.setMinimumHeight(40)
        btn_close.clicked.connect(self.accept)
        main_layout.addWidget(btn_close)

# ================= 启动配置对话框 =================
class StartConfigDialog(QDialog):
    """点击 Start Config 后弹出的控制入口对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Start Configuration")
        self.setMinimumWidth(300)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        # 定义6个控制按钮
        buttons_text = [
            "Overall",
            "Module1",
            "Module2",
            "Module3",
            "Module4",
            "Module5"
        ]

        self.buttons = []
        for text in buttons_text:
            btn = QPushButton(text)
            btn.setMinimumHeight(45)
            layout.addWidget(btn)
            self.buttons.append(btn)

        # 底部关闭按钮
        btn_close = QPushButton("取消 / Close")
        btn_close.setStyleSheet("background-color: #6c757d; margin-top: 10px;")
        btn_close.clicked.connect(self.reject)
        layout.addWidget(btn_close)


class MonomerControlDialog(QDialog):
    """Module1 专用：单体模块完整控制面板"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Module1 - Monomer Control")
        self.setMinimumWidth(650)
        self.setMinimumHeight(750)

        main_layout = QVBoxLayout(self)

        # 使用滚动区域防止内容过多
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        layout = QVBoxLayout(scroll_widget)

        # === 1. 基础动作与序列区 ===
        action_group = QGroupBox("Sequence & Global Actions")
        action_layout = QVBoxLayout()

        btn_layout1 = QHBoxLayout()
        self.btn_deliver_seq = QPushButton("DELIVER Sequence (全序列)")
        self.btn_home = QPushButton("HOME (主电机归零)")
        self.btn_test = QPushButton("TEST (测试电机)")
        self.btn_stop = QPushButton("STOP (急停)")
        self.btn_stop.setStyleSheet("background-color: #dc3545; color: white;")
        for btn in (self.btn_deliver_seq, self.btn_home, self.btn_test, self.btn_stop):
            btn.setMinimumHeight(35)
            btn_layout1.addWidget(btn)
        action_layout.addLayout(btn_layout1)

        # 兼容旧版的 Deliver/Retract (通过E0)
        btn_layout2 = QHBoxLayout()
        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setRange(0.0, 9999.0)
        self.amount_spin.setValue(10.0)
        self.amount_spin.setSuffix(" steps")
        btn_layout2.addWidget(QLabel("E0 Steps:"))
        btn_layout2.addWidget(self.amount_spin)

        self.btn_deliver = QPushButton("Deliver E0 (输送)")
        self.btn_retract = QPushButton("Retract E0 (回抽)")
        for btn in (self.btn_deliver, self.btn_retract):
            btn.setMinimumHeight(35)
            btn_layout2.addWidget(btn)
        action_layout.addLayout(btn_layout2)

        action_group.setLayout(action_layout)
        layout.addWidget(action_group)

        # === 2. 单次工位给料 (FEED) ===
        feed_group = QGroupBox("Single Station Feed (FEED 0-5)")
        feed_layout = QHBoxLayout()
        self.feed_station_spin = QSpinBox()
        self.feed_station_spin.setRange(0, 5)
        self.feed_station_spin.setValue(0)
        self.btn_feed = QPushButton("FEED Station")
        self.btn_feed.setMinimumHeight(35)
        self.btn_feed.setStyleSheet("background-color: #17a2b8; color: white;")
        feed_layout.addWidget(QLabel("Station ID (0-3:Extruder, 4:P1, 5:P2):"))
        feed_layout.addWidget(self.feed_station_spin)
        feed_layout.addWidget(self.btn_feed)
        feed_group.setLayout(feed_layout)
        layout.addWidget(feed_group)

        # === 3. 独立电机与气泵控制 ===
        motor_group = QGroupBox("Direct Motor & Pump Control")
        motor_layout = QGridLayout()

        # 挤出机 E0-E3
        self.ext_spins = []
        for i in range(4):
            lbl = QLabel(f"E{i} Steps:")
            spin = QSpinBox()
            spin.setRange(-99999, 99999)
            spin.setValue(0)
            btn = QPushButton(f"Move E{i}")
            btn.setMinimumHeight(30)
            motor_layout.addWidget(lbl, i, 0)
            motor_layout.addWidget(spin, i, 1)
            motor_layout.addWidget(btn, i, 2)
            self.ext_spins.append((spin, btn))

        # 主电机 M
        self.main_spin = QSpinBox()
        self.main_spin.setRange(-99999, 99999)
        self.main_spin.setValue(0)
        self.btn_move_main = QPushButton("Move Main (M)")
        self.btn_move_main.setMinimumHeight(30)
        motor_layout.addWidget(QLabel("Main Steps:"), 4, 0)
        motor_layout.addWidget(self.main_spin, 4, 1)
        motor_layout.addWidget(self.btn_move_main, 4, 2)

        # 气泵 P1/P2
        self.pump_spin = QSpinBox()
        self.pump_spin.setRange(0, 99999)
        self.pump_spin.setValue(1000)
        self.pump_spin.setSuffix(" ms")
        self.btn_pump1 = QPushButton("Trigger P1")
        self.btn_pump2 = QPushButton("Trigger P2")
        for btn in (self.btn_pump1, self.btn_pump2):
            btn.setMinimumHeight(30)
        motor_layout.addWidget(QLabel("Pump Duration:"), 5, 0)
        motor_layout.addWidget(self.pump_spin, 5, 1)
        pump_btn_layout = QHBoxLayout()
        pump_btn_layout.addWidget(self.btn_pump1)
        pump_btn_layout.addWidget(self.btn_pump2)
        motor_layout.addLayout(pump_btn_layout, 5, 2)

        motor_group.setLayout(motor_layout)
        layout.addWidget(motor_group)

        # === 4. 参数设置与查询 ===
        param_group = QGroupBox("Parameter & Query")
        param_layout = QVBoxLayout()

        set_layout = QHBoxLayout()
        self.param_key_combo = QComboBox()
        self.param_key_combo.addItems([
            "EXT0", "EXT1", "EXT2", "EXT3",
            "RET0", "RET1", "RET2", "RET3",
            "PUMP1", "PUMP2",
            "POS0", "POS1", "POS2", "POS3"
        ])
        self.param_value_spin = QSpinBox()
        self.param_value_spin.setRange(-99999, 99999)
        self.btn_set_param = QPushButton("SET Param")
        self.btn_set_param.setMinimumHeight(35)
        set_layout.addWidget(self.param_key_combo)
        set_layout.addWidget(self.param_value_spin)
        set_layout.addWidget(self.btn_set_param)
        param_layout.addLayout(set_layout)

        query_layout = QHBoxLayout()
        self.btn_status = QPushButton("Get STATUS")
        self.btn_config = QPushButton("Get CONFIG")
        self.btn_help = QPushButton("Get HELP")
        for btn in (self.btn_status, self.btn_config, self.btn_help):
            btn.setMinimumHeight(35)
            query_layout.addWidget(btn)
        param_layout.addLayout(query_layout)

        param_group.setLayout(param_layout)
        layout.addWidget(param_group)

        # === 5. 响应控制台 (黑底绿字终端风格) ===
        console_group = QGroupBox("Response Console (Async)")
        console_layout = QVBoxLayout()
        self.response_text = QPlainTextEdit()
        self.response_text.setReadOnly(True)
        self.response_text.setMaximumHeight(150)
        self.response_text.setStyleSheet("background-color: #1e1e1e; color: #00ff00; font-family: Consolas, monospace;")
        console_layout.addWidget(self.response_text)
        console_group.setLayout(console_layout)
        layout.addWidget(console_group)

        layout.addStretch()
        scroll.setWidget(scroll_widget)
        main_layout.addWidget(scroll)

        # === 底部关闭按钮 ===
        btn_close = QPushButton("Close")
        btn_close.setMinimumHeight(40)
        btn_close.setStyleSheet("background-color: #6c757d; margin-top: 10px;")
        btn_close.clicked.connect(self.accept)
        main_layout.addWidget(btn_close)


class PowderControlDialog(QDialog):
    """Module2 专用：粉末模块完整控制面板 (支持3个送料装置)"""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Module2 - Powder Control")
        self.setMinimumWidth(500)

        main_layout = QVBoxLayout(self)

        # 使用 TabWidget 区分3个送料装置
        self.tabs = QTabWidget()
        self.feeders = []

        for i in range(1, 4):
            tab = QWidget()
            tab_layout = QVBoxLayout(tab)

            group = QGroupBox(f"Feeder {i} Control")
            form = QFormLayout()

            # 投料重量
            amount_spin = QDoubleSpinBox()
            amount_spin.setRange(0.0, 9999.0)
            amount_spin.setValue(10.0)
            amount_spin.setSuffix(" g")
            form.addRow("Target Amount:", amount_spin)

            # 投料按钮
            btn_dispense = QPushButton("Dispense (投料)")
            btn_dispense.setMinimumHeight(35)
            btn_dispense.setStyleSheet("background-color: #28a745; color: white;")
            form.addRow(btn_dispense)

            # 步数设置
            steps_spin = QSpinBox()
            steps_spin.setRange(0, 99999)
            steps_spin.setValue(1000)
            btn_set_steps = QPushButton("Set Steps (设置步数)")
            btn_set_steps.setMinimumHeight(30)

            steps_layout = QHBoxLayout()
            steps_layout.addWidget(steps_spin)
            steps_layout.addWidget(btn_set_steps)
            form.addRow("Feeder Steps:", steps_layout)

            group.setLayout(form)
            tab_layout.addWidget(group)
            tab_layout.addStretch()

            self.tabs.addTab(tab, f"Feeder {i}")

            # 保存组件引用以便后续绑定信号
            self.feeders.append({
                'id': i,
                'amount_spin': amount_spin,
                'btn_dispense': btn_dispense,
                'steps_spin': steps_spin,
                'btn_set_steps': btn_set_steps,
            })

        main_layout.addWidget(self.tabs)

        # === 全局控制区 ===
        global_group = QGroupBox("Global Actions")
        global_layout = QHBoxLayout()
        self.btn_home = QPushButton("Home (回位)")
        self.btn_stop = QPushButton("STOP (急停)")
        self.btn_stop.setStyleSheet("background-color: #dc3545; color: white;")
        self.btn_reset = QPushButton("Reset E-Stop (复位)")
        self.btn_status = QPushButton("Get Status (状态)")

        for btn in (self.btn_stop, self.btn_reset, self.btn_status, self.btn_home):
            btn.setMinimumHeight(40)
            global_layout.addWidget(btn)

        global_group.setLayout(global_layout)
        main_layout.addWidget(global_group)

        # === 底部关闭按钮 ===
        btn_close = QPushButton("Close")
        btn_close.setMinimumHeight(40)
        btn_close.setStyleSheet("background-color: #6c757d; margin-top: 10px;")
        btn_close.clicked.connect(self.accept)
        main_layout.addWidget(btn_close)


# ================= 混匀模块(Module3)控制对话框 =================
class MixingControlDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Module3 - Mixing & Ultrasonic Control")
        self.setMinimumWidth(450)

        main_layout = QVBoxLayout(self)

        # 1. 超声控制
        ultra_group = QGroupBox("Ultrasonic (超声)")
        ultra_layout = QFormLayout()
        self.ultra_time_spin = QSpinBox()
        self.ultra_time_spin.setRange(1, 999)
        self.ultra_time_spin.setValue(5)
        self.ultra_time_spin.setSuffix(" s")
        self.btn_ultra_start = QPushButton("Start Ultrasonic")
        self.btn_ultra_start.setStyleSheet("background-color: #17a2b8; color: white;")
        self.btn_ultra_start.setMinimumHeight(35)
        ultra_layout.addRow("Time:", self.ultra_time_spin)
        ultra_layout.addRow(self.btn_ultra_start)
        ultra_group.setLayout(ultra_layout)
        main_layout.addWidget(ultra_group)

        # 2. 磁力搅拌 1 (对应 X轴)
        stir1_group = QGroupBox("Magnetic Stirrer 1 (X-axis)")
        stir1_layout = QFormLayout()
        self.stir1_speed_spin = QSpinBox()
        self.stir1_speed_spin.setRange(-255, 255)
        self.stir1_speed_spin.setValue(100)
        self.stir1_time_spin = QSpinBox()
        self.stir1_time_spin.setRange(1, 999)
        self.stir1_time_spin.setValue(5)
        self.stir1_time_spin.setSuffix(" s")
        self.btn_stir1_start = QPushButton("Start Stirrer 1")
        self.btn_stir1_start.setStyleSheet("background-color: #28a745; color: white;")
        self.btn_stir1_start.setMinimumHeight(35)

        stir1_layout.addRow("Speed (-255~255):", self.stir1_speed_spin)
        stir1_layout.addRow("Time:", self.stir1_time_spin)
        stir1_layout.addRow(self.btn_stir1_start)
        stir1_group.setLayout(stir1_layout)
        main_layout.addWidget(stir1_group)

        # 3. 磁力搅拌 2 (对应 Y轴)
        stir2_group = QGroupBox("Magnetic Stirrer 2 (Y-axis)")
        stir2_layout = QFormLayout()
        self.stir2_speed_spin = QSpinBox()
        self.stir2_speed_spin.setRange(-255, 255)
        self.stir2_speed_spin.setValue(100)
        self.stir2_time_spin = QSpinBox()
        self.stir2_time_spin.setRange(1, 999)
        self.stir2_time_spin.setValue(5)
        self.stir2_time_spin.setSuffix(" s")
        self.btn_stir2_start = QPushButton("Start Stirrer 2")
        self.btn_stir2_start.setStyleSheet("background-color: #28a745; color: white;")
        self.btn_stir2_start.setMinimumHeight(35)

        stir2_layout.addRow("Speed (-255~255):", self.stir2_speed_spin)
        stir2_layout.addRow("Time:", self.stir2_time_spin)
        stir2_layout.addRow(self.btn_stir2_start)
        stir2_group.setLayout(stir2_layout)
        main_layout.addWidget(stir2_group)

        # 全局急停按钮
        self.btn_stop_all = QPushButton("STOP ALL (急停)")
        self.btn_stop_all.setMinimumHeight(45)
        self.btn_stop_all.setStyleSheet("background-color: #dc3545; color: white; font-weight: bold; font-size: 16px;")
        main_layout.addWidget(self.btn_stop_all)

        # 底部关闭按钮
        btn_close = QPushButton("Close")
        btn_close.setMinimumHeight(40)
        btn_close.setStyleSheet("background-color: #6c757d; margin-top: 10px;")
        btn_close.clicked.connect(self.accept)
        main_layout.addWidget(btn_close)