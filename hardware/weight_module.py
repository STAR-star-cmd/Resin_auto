from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException

"""
粉末区域称重模块
默认参数: 115200, 8N1, 站号 0x01
"""

class WeighingModule:
    def __init__(self, port: str, baudrate: int = 115200, slave_id: int = 1):
        self.client = ModbusSerialClient(
            port=port, baudrate=baudrate,
            bytesize=8, parity='N', stopbits=1, timeout=1
        )
        self.slave_id = slave_id

    def connect(self) -> bool:
        return self.client.connect()

    def close(self):
        self.client.close()

    def read_weight(self) -> dict:

        r = self.client.read_holding_registers(
            address=0x0000, count=4, device_id=self.slave_id
        )
        if r.isError():
            raise ModbusException(f"读取失败: {r}")

        regs = r.registers
        # 高 16 位在 regs[0], 低 16 位在 regs[1], 有符号
        raw = (regs[0] << 16) | regs[1]
        if raw >= 0x80000000:
            raw -= 0x100000000

        precision = regs[2]        # 0~3 对应小数位数
        status = regs[3]

        return {
            'weight':     raw / (10 ** precision),
            'raw':        raw,
            'precision':  precision,
            'stable':     bool(status & 0x01),  # bit0
            'zero':       bool(status & 0x02),  # bit1
            'overweight': bool(status & 0x04),  # bit2
            'valid':      bool(status & 0x20),  # bit5
            'status':     status,
        }

    def tare(self):
        """清零 (功能码 06, 地址 0x0004 写 1)"""
        r = self.client.write_register(
            address=0x0004, value=1, device_id=self.slave_id
        )
        if r.isError():
            raise ModbusException(f"清零失败: {r}")
        return True


if __name__ == '__main__':
    PORT = 'COM20'
    m = WeighingModule(PORT, baudrate=115200, slave_id=1)

    if not m.connect():
        raise SystemExit("串口打开失败")

    try:
        d = m.read_weight()
        print(f"重量={d['weight']}  稳定={d['stable']}  "
              f"零点={d['zero']}  超重={d['overweight']}  有效={d['valid']}")
    finally:
        m.close()