import time
from machine import Pin

try:
    from modules.base import ModuleBase
except ImportError:
    from base import ModuleBase


class Driver(ModuleBase):
    MODULE_NAME = "gpio_led"
    INTERFACE = "gpio"
    COMMANDS = (
        "setup",
        "on",
        "off",
        "on_for",
        "blink",
        "self_test",
        "info",
    )

    def __init__(self, pin, active_high=True):
        self.setup(pin=pin, active_high=active_high)

    def setup(self, pin, active_high=True):
        self.pin_number = int(pin)
        self.active_high = bool(active_high)
        self.led = Pin(self.pin_number, Pin.OUT)
        self.off()
        return self.info()

    def on(self):
        self._write(True)
        return {"pin": self.pin_number, "state": "on"}

    def off(self):
        self._write(False)
        return {"pin": self.pin_number, "state": "off"}

    def on_for(self, seconds=1):
        self.on()
        time.sleep(float(seconds))
        return self.off()

    def blink(self, times=3, delay_ms=250):
        for _ in range(int(times)):
            self.on()
            time.sleep_ms(int(delay_ms))
            self.off()
            time.sleep_ms(int(delay_ms))
        return {"ok": True, "pin": self.pin_number}

    def self_test(self):
        return self.blink(times=2, delay_ms=150)

    def details(self):
        return {
            "pin": self.pin_number,
            "active_high": self.active_high,
        }

    def _write(self, state):
        value = 1 if bool(state) == self.active_high else 0
        self.led.value(value)
