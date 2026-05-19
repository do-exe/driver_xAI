from modules.pwm_led.drivers.micropython import Driver


led = Driver(pin=2, active_high=True, pwm_frequency_hz=1000, max_value=255)
led.fade(cycles=1, step=16, delay_ms=25)
