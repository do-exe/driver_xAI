import time
from machine import Pin, PWM

try:
    from modules.base import ModuleBase
except ImportError:
    from base import ModuleBase


COLORS = {
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "white": (255, 255, 255),
    "yellow": (255, 255, 0),
    "cyan": (0, 255, 255),
    "magenta": (255, 0, 255),
    "off": (0, 0, 0),
}


class Driver(ModuleBase):
    MODULE_NAME = "rgb_led"
    INTERFACE = "gpio"
    COMMANDS = (
        "setup",
        "set_rgb",
        "set_color",
        "off",
        "blink",
        "self_test",
        "info",
    )

    def __init__(
        self,
        red,
        green,
        blue,
        common_type="common_cathode",
        pwm_frequency_hz=1000,
        max_value=255,
    ):
        self.setup(
            red=red,
            green=green,
            blue=blue,
            common_type=common_type,
            pwm_frequency_hz=pwm_frequency_hz,
            max_value=max_value,
        )

    def setup(
        self,
        red,
        green,
        blue,
        common_type="common_cathode",
        pwm_frequency_hz=1000,
        max_value=255,
    ):
        self.max_value = int(max_value)
        self.invert = common_type == "common_anode"
        self.red = PWM(Pin(int(red), Pin.OUT), freq=int(pwm_frequency_hz))
        self.green = PWM(Pin(int(green), Pin.OUT), freq=int(pwm_frequency_hz))
        self.blue = PWM(Pin(int(blue), Pin.OUT), freq=int(pwm_frequency_hz))
        self.off()
        return self.info()

    def set_rgb(self, red=0, green=0, blue=0):
        self._write(self.red, red)
        self._write(self.green, green)
        self._write(self.blue, blue)
        return {"red": int(red), "green": int(green), "blue": int(blue)}

    def set_color(self, name):
        if name not in COLORS:
            raise ValueError("unknown color: %s" % name)
        red, green, blue = COLORS[name]
        return self.set_rgb(red, green, blue)

    def off(self):
        return self.set_rgb(0, 0, 0)

    def blink(self, red=255, green=255, blue=255, times=3, delay_ms=250):
        for _ in range(int(times)):
            self.set_rgb(red, green, blue)
            time.sleep_ms(int(delay_ms))
            self.off()
            time.sleep_ms(int(delay_ms))
        return {"ok": True}

    def self_test(self):
        self.set_rgb(255, 0, 0)
        time.sleep_ms(150)
        self.set_rgb(0, 255, 0)
        time.sleep_ms(150)
        self.set_rgb(0, 0, 255)
        time.sleep_ms(150)
        self.off()
        return {"ok": True}

    def details(self):
        return {
            "max_value": self.max_value,
            "inverted": self.invert,
        }

    def _write(self, pwm, value):
        value = max(0, min(self.max_value, int(value)))
        if self.invert:
            value = self.max_value - value
        duty = int(value * 65535 / self.max_value)
        if hasattr(pwm, "duty_u16"):
            pwm.duty_u16(duty)
        else:
            pwm.duty(int(value * 1023 / self.max_value))
