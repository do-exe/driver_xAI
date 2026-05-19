from machine import I2C, Pin

from modules.ads1115.drivers.micropython import Driver


i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=400000)
adc = Driver(i2c, address=0x48, gain=1, data_rate_sps=128)

print(adc.read_voltage(channel=0))
