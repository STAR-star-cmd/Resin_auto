import sys
import time
import serial.tools.list_ports
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QPushButton, QComboBox, QMessageBox)
from PyQt6.QtCore import Qt, QThread, QObject, pyqtSignal, pyqtSlot, QTimer
from PyQt6.QtGui import QFont, QColor

from hardware.weight_module import WeighingModule


class ScaleWorker(QObject):
    """后台工作器：运行在独立线程，负责硬件轮询与控制"""
    data_updated = pyqtSignal(dict)
    error_msg = pyqtSignal(str)
    status_changed = pyqtSignal(bool, str)  # (是否连接, 端口名)

    # 修复 Bug: 新增异常断开与连接失败信号，防止线程残留导致 UI 死锁
    connection_lost = pyqtSignal(str)
    connection_failed = pyqtSignal(str)

    def __init__(self, port):
        super().__init__()
        self.port = port
        # 优化: 显式指定波特率 115200 (您提到的 15200 大概率为 115200 笔误)
        self.module = WeighingModule(port, baudrate=115200)
        self.timer = None

    @pyqtSlot()
    def start(self):
        self.timer = QTimer()
        self.timer.timeout.connect(self._poll)

        if self.module.connect():
            # 优化: 115200 高波特率下，将轮询间隔从 100ms 缩短至 50ms (20Hz) 提升实时性
            self.timer.start(50)
            self.status_changed.emit(True, self.port)
        else:
            self.error_msg.emit(f"无法打开串口 {self.port}")
            self.connection_failed.emit(f"无法打开串口 {self.port}")

    @pyqtSlot()
    def stop(self):
        if self.timer is not None:
            self.timer.stop()
        self.module.close()
        self.status_changed.emit(False, "")

    @pyqtSlot()
    def do_tare(self):
        try:
            self.module.tare()
        except Exception as e:
            self.error_msg.emit(f"清零失败: {e}")

    def _poll(self):
        try:
            data = self.module.read_weight()
            self.data_updated.emit(data)
        except ConnectionError as e:
            self.error_msg.emit(f"硬件断开: {e}")
            self.stop()
            self.connection_lost.emit(str(e))
        except Exception as e:
            self.error_msg.emit(f"读取异常: {e}")


class MainWindow(QMainWindow):
    stop_worker_signal = pyqtSignal()
    tare_worker_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("自动化称重控制台")
        self.resize(400, 300)

        self.worker = None
        self.thread = None

        self._init_ui()
        self._scan_ports()

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # 1. 顶部：串口配置区
        top_layout = QHBoxLayout()
        self.combo_port = QComboBox()
        self.btn_connect = QPushButton("连接")
        self.btn_connect.clicked.connect(self.toggle_connection)
        top_layout.addWidget(QLabel("串口:"))
        top_layout.addWidget(self.combo_port, 1)
        top_layout.addWidget(self.btn_connect)
        layout.addLayout(top_layout)

        # 2. 中间：数据显示区
        self.lbl_weight = QLabel("--")
        self.lbl_weight.setFont(QFont("Arial", 48, QFont.Weight.Bold))
        self.lbl_weight.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_status = QLabel("状态: 未连接")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setStyleSheet("color: gray; font-size: 16px;")

        layout.addWidget(self.lbl_weight, 2)
        layout.addWidget(self.lbl_status, 1)

        # 3. 底部：操作区
        self.btn_tare = QPushButton("清零 (Tare)")
        self.btn_tare.setFont(QFont("Arial", 16))
        self.btn_tare.setEnabled(False)
        self.btn_tare.clicked.connect(self.handle_tare)
        layout.addWidget(self.btn_tare)

    def _scan_ports(self):
        """扫描可用串口"""
        self.combo_port.clear()
        ports = serial.tools.list_ports.comports()
        for p in ports:
            desc = f"{p.device} ({p.description})"
            self.combo_port.addItem(desc, p.device)
        if not ports:
            self.combo_port.addItem("未检测到串口")

    def toggle_connection(self):
        """连接/断开 切换"""
        if self.thread and self.thread.isRunning():
            # 断开
            self.stop_worker_signal.emit()
            self.thread.quit()

            # 修复 Bug: 增加超时机制，防止串口 close() 阻塞导致 UI 卡死
            if not self.thread.wait(2000):
                self.thread.terminate()

            # 修复 Bug: 移除 .disconnect() 调用。
            # PyQt 会在 worker 对象被销毁时自动解除信号绑定，手动 disconnect 极易引发 TypeError 崩溃。
            self.thread = None
            self.worker = None

            self.btn_connect.setText("连接")
            self.btn_tare.setEnabled(False)
            self.combo_port.setEnabled(True)
            self.lbl_status.setText("状态: 未连接")
            self.lbl_status.setStyleSheet("color: gray;")
        else:
            # 连接
            port = self.combo_port.currentData()
            if not port:
                QMessageBox.warning(self, "错误", "请选择有效的串口")
                return

            self.worker = ScaleWorker(port)
            self.thread = QThread()
            self.worker.moveToThread(self.thread)

            # 信号绑定
            self.thread.started.connect(self.worker.start)
            self.stop_worker_signal.connect(self.worker.stop)
            self.tare_worker_signal.connect(self.worker.do_tare)

            self.worker.status_changed.connect(self.on_status_changed)
            self.worker.data_updated.connect(self.on_data_updated)
            self.worker.error_msg.connect(self.on_error)

            # 绑定异常处理信号
            self.worker.connection_lost.connect(self.handle_connection_lost)
            self.worker.connection_failed.connect(self.handle_connection_failed)

            self.thread.start()
            self.btn_connect.setText("断开")
            self.combo_port.setEnabled(False)

    @pyqtSlot(bool, str)
    def on_status_changed(self, connected, port):
        if connected:
            self.btn_tare.setEnabled(True)
            self.lbl_status.setText(f"状态: 已连接 ({port})")
            self.lbl_status.setStyleSheet("color: green;")
        else:
            self.btn_tare.setEnabled(False)
            self.lbl_status.setText("状态: 未连接")
            self.lbl_status.setStyleSheet("color: gray;")

    @pyqtSlot(dict)
    def on_data_updated(self, data):
        """更新 UI 数据"""
        weight = data['weight']
        self.lbl_weight.setText(f"{weight:.{data['precision']}f}")

        status_text = []
        color = "black"

        if not data['valid']:
            status_text.append("无效")
            color = "red"
        elif data['overweight']:
            status_text.append("超重!")
            color = "red"
        else:
            if data['stable']:
                status_text.append("稳定")
                color = "green"
            else:
                status_text.append("跳动中")
                color = "orange"

            if data['zero']:
                status_text.append("零点")

        self.lbl_status.setText(f"状态: {' | '.join(status_text)}")
        self.lbl_weight.setStyleSheet(f"color: {color};")

    @pyqtSlot(str)
    def on_error(self, msg):
        """异常处理"""
        print(f"[硬件异常] {msg}")
        self.lbl_status.setText(f"错误: {msg}")
        self.lbl_status.setStyleSheet("color: red;")

    @pyqtSlot(str)
    def handle_connection_lost(self, msg):
        """处理运行中物理断开"""
        QMessageBox.critical(self, "连接断开", f"硬件连接已意外断开:\n{msg}")
        self._cleanup_thread()

    @pyqtSlot(str)
    def handle_connection_failed(self, msg):
        """处理初始连接失败"""
        QMessageBox.critical(self, "连接失败", msg)
        self._cleanup_thread()

    def _cleanup_thread(self):
        """统一清理线程与重置 UI"""
        if self.thread and self.thread.isRunning():
            self.thread.quit()
            if not self.thread.wait(2000):
                self.thread.terminate()

        self.thread = None
        self.worker = None
        self.btn_connect.setText("连接")
        self.btn_tare.setEnabled(False)
        self.combo_port.setEnabled(True)
        self.lbl_status.setText("状态: 未连接")
        self.lbl_status.setStyleSheet("color: gray;")

    def handle_tare(self):
        if self.worker:
            self.tare_worker_signal.emit()

    def closeEvent(self, event):
        """窗口关闭时安全清理线程"""
        if self.thread and self.thread.isRunning():
            self.stop_worker_signal.emit()
            self.thread.quit()
            if not self.thread.wait(2000):
                self.thread.terminate()
        event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())