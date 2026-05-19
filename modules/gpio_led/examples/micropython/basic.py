from modules.gpio_led.drivers.micropython import Driver


led = Driver(pin=2, active_high=True)
led.blink(times=3, delay_ms=250)
