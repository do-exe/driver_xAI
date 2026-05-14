# Future Modules

These module folders were removed for now and kept as future candidates:

- bme280
- ssd1306

## Future Protocols

These protocol folders were removed for now. Add them back only when a real module needs them:

- ble
- can
- ethernet
- i2s
- lora
- nfc_rfid
- onewire
- rs485_modbus
- spi
- uart
- usb
- wifi
- zigbee

## Active Interfaces

- gpio

## Future Tooling

Add a module generator so new drivers are easier to create.

Target command:

```bash
python tools/create_module.py --name bh1750 --protocol i2c
```

The generator should create:

- `modules/<name>/base.json`
- `modules/<name>/commands.json`
- `modules/<name>/setup.template.json`
- `modules/<name>/driver.py`

It should also update the matching protocol/interface registry and run validation.

## Future Capabilities

The active design does not use capabilities. Module API descriptions are the main way AI understands what each module can do.

Capabilities can be added later if the codebase becomes large enough that search/filtering needs broad categories.

Possible future use:

- find all measurement modules
- find all output modules
- find all display modules
- filter modules by broad purpose

If added later, capabilities should be controlled by the project, not invented freely by contributors.
