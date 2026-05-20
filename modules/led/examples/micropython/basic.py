from modules.led.drivers.micropython import Driver


led = Driver(
    channels={"red": 44, "green": 43, "blue": 2},
    common_type="common_cathode",
)
led.set_color("white")
