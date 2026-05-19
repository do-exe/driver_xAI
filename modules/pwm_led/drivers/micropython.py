import time
from machine import Pin, PWM

try:
    from modules.base import ModuleBase
except ImportError:
    from base import ModuleBase


class Driver(ModuleBase):
    MODULE_NAME = "pwm_led"
    INTERFACE = "gpio"
    COMMANDS = (
        "setup",
        "set_brightness",
        "on",
        "off",
        "blink",
        "fade",
        "self_test",
        "info",
    )

    def __init__(self, pin, active_high=True, pwm_frequency_hz=1000, max_value=255):
        self.setup(
            pin=pin,
            active_high=active_high,
            pwm_frequency_hz=pwm_frequency_hz,
            max_value=max_value,
        )

    def setup(self, pin, active_high=True, pwm_frequency_hz=1000, max_value=255):
        self.pin_number = int(pin)
        self.active_high = bool(active_high)
        self.frequency_hz = int(pwm_frequency_hz)
        self.max_value = int(max_value)
        self.pwm = PWM(Pin(self.pin_number, Pin.OUT), freq=self.frequency_hz)
        self.off()
        return self.info()

    def set_brightness(self, value=0):
        value = max(0, min(self.max_value, int(value)))
        duty_value = value if self.active_high else self.max_value - value
        duty = int(duty_value * 65535 / self.max_value)
        if hasattr(self.pwm, "duty_u16"):
            self.pwm.duty_u16(duty)
        else:
            self.pwm.duty(int(duty_value * 1023 / self.max_value))
        return {"pin": self.pin_number, "brightness": value}

    def on(self):
        return self.set_brightness(self.max_value)

    def off(self):
        return self.set_brightness(0)

    def blink(self, times=3, delay_ms=250, value=None):
        brightness = self.max_value if value is None else int(value)
        for _ in range(int(times)):
            self.set_brightness(brightness)
            time.sleep_ms(int(delay_ms))
            self.off()
            time.sleep_ms(int(delay_ms))
        return {"ok": True, "pin": self.pin_number}

    def fade(self, cycles=1, step=16, delay_ms=25):
        step = max(1, int(step))
        levels = list(range(0, self.max_value + 1, step))
        if not levels or levels[-1] != self.max_value:
            levels.append(self.max_value)
        for _ in range(int(cycles)):
            for level in levels:
                self.set_brightness(level)
                time.sleep_ms(int(delay_ms))
            for level in reversed(levels):
                self.set_brightness(level)
                time.sleep_ms(int(delay_ms))
        self.off()
        return {"ok": True, "pin": self.pin_number}

    def self_test(self):
        return self.fade(cycles=1, step=max(1, self.max_value // 8), delay_ms=35)

    def details(self):
        return {
            "pin": self.pin_number,
            "active_high": self.active_high,
            "pwm_frequency_hz": self.frequency_hz,
            "max_value": self.max_value,
        }
