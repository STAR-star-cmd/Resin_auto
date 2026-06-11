import serial

class DeviceController:
    def __init__(self, port, baudrate=115200):
        """初始化串口并等待Arduino就绪"""
        self.ser = serial.Serial(port, baudrate, timeout=2)
        # 阻塞等待Arduino重启并发送就绪标志，避免发令丢失
        while True:
            line = self.ser.readline().decode('utf-8', errors='ignore').strip()
            if "系统就绪" in line:
                break

    def _send(self, cmd):
        """底层发送方法，自动追加换行符以触发Arduino的帧结束判定"""
        self.ser.write((cmd + '\n').encode('utf-8'))

    def x(self, speed, seconds=None):
        """控制X轴电机. speed: -255~255, seconds: 可选运行秒数"""
        cmd = f"X{speed}"
        if seconds is not None:
            cmd += f" {seconds}"
        self._send(cmd)

    def y(self, speed, seconds=None):
        """控制Y轴电机. speed: -255~255, seconds: 可选运行秒数"""
        cmd = f"Y{speed}"
        if seconds is not None:
            cmd += f" {seconds}"
        self._send(cmd)

    def u(self, state):
        """控制超声/形变模块. state: 'ON', 'OFF' 或 整数秒数"""
        self._send(f"U {state}")

    def close(self):
        """关闭串口释放资源"""
        self.ser.close()

if __name__ == "__main__":
    ctrl = DeviceController('COM17')

    try:
        # 1. 电机控制验证
        ctrl.x(100)  # 发送 "X150\n" -> X轴正转，持续运行
        ctrl.y(-100, 5)  # 发送 "Y-200 5\n" -> Y轴反转，5秒后Arduino自动停止
        ctrl.x(0)  # 发送 "X0\n" -> 立即刹车停止X轴

    finally:
        ctrl.close()