import time

try:
    from modules.base import ModuleBase
except ImportError:
    from base import ModuleBase


_CONVERSION = 0x00
_CONFIG = 0x01
_OS_SINGLE = 0x8000
_MODE_SINGLE = 0x0100
_COMP_DISABLE = 0x0003
_MUX_SINGLE = (0x4000, 0x5000, 0x6000, 0x7000)
_MUX_DIFF = {
    (0, 1): 0x0000,
    (0, 3): 0x1000,
    (1, 3): 0x2000,
    (2, 3): 0x3000,
}
_PGA = {
    "2/3": (0x0000, 6.144),
    1: (0x0200, 4.096),
    2: (0x0400, 2.048),
    4: (0x0600, 1.024),
    8: (0x0800, 0.512),
    16: (0x0A00, 0.256),
}
_DATA_RATE = {
    8: 0x0000,
    16: 0x0020,
    32: 0x0040,
    64: 0x0060,
    128: 0x0080,
    250: 0x00A0,
    475: 0x00C0,
    860: 0x00E0,
}


class Driver(ModuleBase):
    MODULE_NAME = "ads1115"
    PROTOCOL = "i2c"
    COMMANDS = (
        "setup",
        "configure",
        "read_raw",
        "read_voltage",
        "read_differential",
        "self_test",
        "info",
    )

    def __init__(self, i2c, address=0x48, gain=1, data_rate_sps=128):
        self.i2c = i2c
        self.setup(address=address, gain=gain, data_rate_sps=data_rate_sps)

    def setup(self, address=0x48, gain=1, data_rate_sps=128):
        self.address = int(str(address), 0)
        self.configure(gain=gain, data_rate_sps=data_rate_sps)
        return self.info()

    def configure(self, gain=1, data_rate_sps=128):
        if gain not in _PGA:
            raise ValueError("unsupported ADS1115 gain")
        if int(data_rate_sps) not in _DATA_RATE:
            raise ValueError("unsupported ADS1115 data rate")
        self.gain = gain
        self.data_rate_sps = int(data_rate_sps)
        return self.details()

    def read_raw(self, channel=0):
        channel = int(channel)
        if channel < 0 or channel > 3:
            raise ValueError("channel must be 0, 1, 2, or 3")
        return self._read(_MUX_SINGLE[channel])

    def read_voltage(self, channel=0):
        raw = self.read_raw(channel=channel)
        return self.raw_to_voltage(raw)

    def read_differential(self, positive=0, negative=1):
        key = (int(positive), int(negative))
        if key not in _MUX_DIFF:
            raise ValueError("differential pair must be 0-1, 0-3, 1-3, or 2-3")
        return self._read(_MUX_DIFF[key])

    def self_test(self):
        self.i2c.readfrom_mem(self.address, _CONFIG, 2)
        return {"ok": True, "address": self.address}

    def details(self):
        return {
            "address": self.address,
            "gain": self.gain,
            "data_rate_sps": self.data_rate_sps,
        }

    def raw_to_voltage(self, raw):
        full_scale = _PGA[self.gain][1]
        return float(raw) * full_scale / 32768.0

    def _read(self, mux):
        gain_bits = _PGA[self.gain][0]
        rate_bits = _DATA_RATE[self.data_rate_sps]
        config = _OS_SINGLE | mux | gain_bits | _MODE_SINGLE | rate_bits | _COMP_DISABLE
        self.i2c.writeto_mem(self.address, _CONFIG, bytes([(config >> 8) & 0xFF, config & 0xFF]))
        time.sleep_ms(max(2, int(1000 / self.data_rate_sps) + 1))
        data = self.i2c.readfrom_mem(self.address, _CONVERSION, 2)
        value = (data[0] << 8) | data[1]
        if value & 0x8000:
            value -= 0x10000
        return value
