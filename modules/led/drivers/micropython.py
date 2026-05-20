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
    MODULE_NAME = "led"
    INTERFACE = "gpio"
    COMMANDS = (
        "setup",
        "set",
        "set_channel",
        "set_all",
        "set_rgb",
        "set_color",
        "on",
        "off",
        "blink",
        "fade",
        "self_test",
        "info",
    )

    def __init__(
        self,
        channels=None,
        pin=None,
        mode="pwm",
        active_high=True,
        common_type="common_cathode",
        pwm_frequency_hz=1000,
        max_value=255,
    ):
        self.setup(
            channels=channels,
            pin=pin,
            mode=mode,
            active_high=active_high,
            common_type=common_type,
            pwm_frequency_hz=pwm_frequency_hz,
            max_value=max_value,
        )

    def setup(
        self,
        channels=None,
        pin=None,
        mode="pwm",
        active_high=True,
        common_type="common_cathode",
        pwm_frequency_hz=1000,
        max_value=255,
    ):
        if channels is None:
            if pin is None:
                raise ValueError("channels or pin is required")
            channels = {"led": pin}
        if not channels:
            raise ValueError("channels cannot be empty")

        self.mode = str(mode)
        self.max_value = int(max_value)
        self.frequency_hz = int(pwm_frequency_hz)
        self.active_high = self._resolve_active_high(active_high, common_type)
        self.outputs = {}
        self.channel_pins = {}
        self.values = {}

        for name, channel_pin in channels.items():
            channel_name = str(name)
            pin_number = int(channel_pin)
            self.channel_pins[channel_name] = pin_number
            if self.mode == "digital":
                self.outputs[channel_name] = Pin(pin_number, Pin.OUT)
            else:
                self.outputs[channel_name] = PWM(Pin(pin_number, Pin.OUT), freq=self.frequency_hz)
            self.values[channel_name] = 0

        self.off()
        return self.info()

    def set(self, values=None, **kwargs):
        values = self._merged_values(values, kwargs)
        for name, value in values.items():
            self.set_channel(name, value)
        return self.state()

    def set_channel(self, name, value=0):
        channel = str(name)
        if channel not in self.outputs:
            raise ValueError("unknown LED channel: %s" % channel)
        self._write(channel, value)
        return {channel: int(value)}

    def set_all(self, value=0):
        for name in self.outputs:
            self._write(name, value)
        return self.state()

    def set_rgb(self, red=0, green=0, blue=0):
        values = {}
        for name in self.outputs:
            group = self._rgb_group(name)
            if group == "red":
                values[name] = red
            elif group == "green":
                values[name] = green
            elif group == "blue":
                values[name] = blue
        if not values:
            raise ValueError("no RGB-like channels are configured")
        return self.set(values)

    def set_color(self, name):
        color = str(name)
        if color not in COLORS:
            raise ValueError("unknown color: %s" % color)
        red, green, blue = COLORS[color]
        return self.set_rgb(red=red, green=green, blue=blue)

    def on(self, value=None):
        return self.set_all(self.max_value if value is None else value)

    def off(self):
        return self.set_all(0)

    def blink(self, values=None, times=3, delay_ms=250):
        on_values = values if values is not None else self._all_values(self.max_value)
        for _ in range(int(times)):
            self.set(on_values)
            time.sleep_ms(int(delay_ms))
            self.off()
            time.sleep_ms(int(delay_ms))
        return {"ok": True, "channels": list(self.outputs.keys())}

    def fade(self, channel=None, cycles=1, step=16, delay_ms=25):
        step = max(1, int(step))
        levels = list(range(0, self.max_value + 1, step))
        if not levels or levels[-1] != self.max_value:
            levels.append(self.max_value)
        channels = [str(channel)] if channel else list(self.outputs.keys())
        for _ in range(int(cycles)):
            for level in levels:
                self.set({name: level for name in channels})
                time.sleep_ms(int(delay_ms))
            for level in reversed(levels):
                self.set({name: level for name in channels})
                time.sleep_ms(int(delay_ms))
        self.off()
        return {"ok": True, "channels": channels}

    def self_test(self):
        for name in self.outputs:
            self.off()
            self.set_channel(name, self.max_value)
            time.sleep_ms(150)
        self.off()
        return {"ok": True, "channels": list(self.outputs.keys())}

    def state(self):
        return {name: int(self.values.get(name, 0)) for name in self.outputs}

    def details(self):
        return {
            "channels": self.channel_pins,
            "mode": self.mode,
            "active_high": self.active_high,
            "pwm_frequency_hz": self.frequency_hz,
            "max_value": self.max_value,
        }

    def _write(self, name, value):
        output = self.outputs[name]
        value = max(0, min(self.max_value, int(value)))
        if self.mode == "digital":
            output.value(1 if (value > 0) == self.active_high else 0)
            self.values[name] = self.max_value if value > 0 else 0
            return

        duty_value = value if self.active_high else self.max_value - value
        duty = int(duty_value * 65535 / self.max_value)
        if hasattr(output, "duty_u16"):
            output.duty_u16(duty)
        else:
            output.duty(int(duty_value * 1023 / self.max_value))
        self.values[name] = value

    def _resolve_active_high(self, active_high, common_type):
        if common_type == "common_anode":
            return False
        if common_type == "common_cathode":
            return True
        return bool(active_high)

    def _rgb_group(self, name):
        text = str(name).lower()
        if text.startswith("red") or text.startswith("r"):
            return "red"
        if text.startswith("green") or text.startswith("g"):
            return "green"
        if text.startswith("blue") or text.startswith("b"):
            return "blue"
        return ""

    def _merged_values(self, values, kwargs):
        merged = {}
        if isinstance(values, dict):
            merged.update(values)
        elif values is not None:
            raise ValueError("values must be a dict")
        merged.update(kwargs)
        return merged

    def _all_values(self, value):
        return {name: value for name in self.outputs}
