from modules.rgb_led.drivers.micropython import Driver


led = Driver(red=12, green=13, blue=14, common_type="common_cathode")
led.set_color("magenta")
