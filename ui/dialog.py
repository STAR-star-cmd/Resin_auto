from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QLabel, QPushButton,
    QDialog, QSpinBox, QDoubleSpinBox, QDialogButtonBox, QFormLayout, QScrollArea, QTabWidget, QHBoxLayout, QComboBox)
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
        self.setMinimumWidth(400)

        main_layout = QVBoxLayout(self)

        # === 基础动作区 ===
        action_group = QGroupBox("Basic Actions")
        action_layout = QFormLayout()

        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setRange(0.0, 9999.0)
        self.amount_spin.setValue(10.0)
        self.amount_spin.setSuffix(" steps")
        action_layout.addRow("Amount:", self.amount_spin)

        btn_layout = QHBoxLayout()
        self.btn_deliver = QPushButton("Deliver (输送)")
        self.btn_retract = QPushButton("Retract (回抽)")
        self.btn_stop = QPushButton("STOP (急停)")
        self.btn_stop.setStyleSheet("background-color: #dc3545; color: white;")
        for btn in (self.btn_deliver, self.btn_retract, self.btn_stop):
            btn.setMinimumHeight(35)
            btn_layout.addWidget(btn)
        action_layout.addRow(btn_layout)

        btn_extra_layout = QHBoxLayout()
        self.btn_home = QPushButton("HOME (归零)")
        self.btn_test = QPushButton("TEST (测试电机)")
        self.btn_deliver_seq = QPushButton("DELIVER Sequence")
        for btn in (self.btn_home, self.btn_test, self.btn_deliver_seq):
            btn.setMinimumHeight(35)
            btn_extra_layout.addWidget(btn)
        action_layout.addRow(btn_extra_layout)

        action_group.setLayout(action_layout)
        main_layout.addWidget(action_group)

        # === 参数设置区 ===
        param_group = QGroupBox("Parameter Setting")
        param_layout = QFormLayout()

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

        param_row = QHBoxLayout()
        param_row.addWidget(self.param_key_combo)
        param_row.addWidget(self.param_value_spin)
        param_row.addWidget(self.btn_set_param)
        param_layout.addRow("Key / Value:", param_row)

        param_group.setLayout(param_layout)
        main_layout.addWidget(param_group)

        # === 查询区 ===
        query_layout = QHBoxLayout()
        self.btn_status = QPushButton("Get STATUS")
        self.btn_config = QPushButton("Get CONFIG")
        for btn in (self.btn_status, self.btn_config):
            btn.setMinimumHeight(35)
            query_layout.addWidget(btn)
        main_layout.addLayout(query_layout)

        # === 底部关闭按钮 ===
        btn_close = QPushButton("Close")
        btn_close.setMinimumHeight(40)
        btn_close.setStyleSheet("background-color: #6c757d; margin-top: 10px;")
        btn_close.clicked.connect(self.accept)
        main_layout.addWidget(btn_close)