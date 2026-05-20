from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent
MODULES_DIR = ROOT_DIR / "modules"
INTERFACES_DIR = ROOT_DIR / "interfaces"
PROTOCOLS_DIR = ROOT_DIR / "protocols"


def help() -> dict[str, str]:
    return {
        "search": "search(module_id_or_module_name) -> fast module discovery from registries",
        "registry": "registry(type, name=None) -> protocol/interface registry lookup",
        "info": "info(module_id) -> read module identity from info.json",
        "inspect": "inspect(module_id, has_variant=False, variant_name=None) -> available files, keys, and commands",
        "get": "get(module_id, has_variant, variant_name, source, file_type, key) -> read module data",
        "set": "set(module_id, has_variant, variant_name, source, file_type, key, value) -> update parameters.custom",
        "make_mini": "make_mini(modules, output_dir, parameters=None) -> create a small Driver xAI folder with selected modules",
        "execute": "execute(module_id, has_variant, variant_name, command, parameters=None) -> return executable command plan",
    }


def search(module_id_or_module_name: str) -> list[dict[str, Any]]:
    query = module_id_or_module_name.strip().lower()
    matches: list[dict[str, Any]] = []
    for registry_data in _all_registries():
        for module_ref in registry_data.get("modules", []):
            module_id = module_ref.get("id", "")
            module_name = module_ref.get("name", "")
            module_info = info(module_id)
            command_names = " ".join(inspect(module_id)["commands"]).lower()
            searchable = " ".join([
                module_id.lower(),
                module_name.lower(),
                str(module_info.get("summary", "")).lower(),
                command_names,
            ])
            if query in searchable:
                matches.append({
                    "module_id": module_id,
                    "module_name": module_name,
                    "source_type": registry_data["type"],
                    "source_id": registry_data["id"],
                    "summary": module_info.get("summary", ""),
                    "verified": module_info.get("verified", False),
                })
    return matches


def registry(type: str, name: str | None = None) -> list[dict[str, Any]] | dict[str, Any]:
    registry_type = _normalize_registry_type(type)
    root = PROTOCOLS_DIR if registry_type == "protocol" else INTERFACES_DIR
    if name is None:
        return [_read_registry(path) for path in sorted(root.glob("*/registry.json"))]
    return _read_registry(root / name / "registry.json")


def info(module_id: str) -> dict[str, Any]:
    data = _read_json(_module_dir(module_id) / "info.json")
    _validate_module_identity(module_id, data)
    return data


def inspect(module_id: str, has_variant: bool = False, variant_name: str | None = None) -> dict[str, Any]:
    module_dir = _module_variant_dir(module_id, has_variant, variant_name)
    sources = sorted(path.name for path in module_dir.iterdir() if path.is_file())
    drivers_dir = module_dir / "drivers"
    drivers = sorted(path.name for path in drivers_dir.iterdir()) if drivers_dir.exists() else []
    parameters = _read_json(module_dir / "parameters.json")
    commands = _read_json(module_dir / "commands.json").get("commands", [])
    return {
        "module_id": module_id,
        "sources": sources,
        "drivers": drivers,
        "get_keys": {
            "info": sorted(info(module_id).keys()),
            "parameters": sorted(parameters.keys()),
            "commands": [command["name"] for command in commands],
        },
        "set_keys": sorted(parameters.get("custom", {}).keys()),
        "commands": [command["name"] for command in commands],
    }


def get(
    module_id: str,
    has_variant: bool,
    variant_name: str | None,
    source: str,
    file_type: str,
    key: str = "all",
) -> Any:
    module_dir = _module_variant_dir(module_id, has_variant, variant_name)
    if file_type == "json":
        source_path = module_dir / _json_source_name(source)
        data = _read_json(source_path)
        return data if key == "all" else data[key]
    if file_type == "driver":
        source_path = module_dir / "drivers" / source
        if not source_path.exists():
            raise FileNotFoundError(source_path)
        return source_path.read_text(encoding="utf-8")
    raise ValueError("file_type must be json or driver")


def set(
    module_id: str,
    has_variant: bool,
    variant_name: str | None,
    source: str,
    file_type: str,
    key: str,
    value: Any,
) -> dict[str, Any]:
    if source != "parameters" or file_type != "json":
        raise ValueError("set() only supports source='parameters' and file_type='json'")
    parameters_path = _module_variant_dir(module_id, has_variant, variant_name) / "parameters.json"
    data = _read_json(parameters_path)
    custom = data.setdefault("custom", {})
    custom[key] = value
    parameters_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "module_id": module_id, "source": "parameters", "key": key, "value": value}


def make_mini(
    modules: list[str],
    output_dir: str,
    parameters: dict[str, dict[str, Any]] | None = None,
    include_examples: bool = False,
    include_tests: bool = False,
    include_all_drivers: bool = False,
    clean: bool = True,
) -> dict[str, Any]:
    """
    Create a mini Driver xAI folder with the same catalog shape as the full repo.

    The generated folder uses driver_xai.py instead of main.py so it does not
    clash with a user's MicroPython application entrypoint.
    """
    if not modules:
        raise ValueError("modules is required")

    selected = [_normalize_module_id(module_id) for module_id in modules]
    unknown = [module_id for module_id in selected if not _module_dir(module_id).is_dir()]
    if unknown:
        raise FileNotFoundError(f"unknown modules: {', '.join(unknown)}")

    output_root = Path(output_dir).expanduser().resolve()
    if output_root.exists() and clean:
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    parameter_overrides = parameters or {}
    written: list[str] = []
    lock_modules: dict[str, Any] = {}
    config_modules: dict[str, Any] = {}

    _copy_file(ROOT_DIR / "modules" / "__init__.py", output_root / "modules" / "__init__.py", written)
    _copy_file(ROOT_DIR / "modules" / "base.py", output_root / "modules" / "base.py", written)

    selected_set = {module_id for module_id in selected}
    for module_id in selected:
        module_root = _module_dir(module_id)
        target_root = output_root / "modules" / module_id
        module_info = info(module_id)
        module_parameters = _merge_parameters(
            _read_json(module_root / "parameters.json"),
            parameter_overrides.get(module_id, {}),
        )

        _copy_file(module_root / "__init__.py", target_root / "__init__.py", written)
        _copy_file(module_root / "info.json", target_root / "info.json", written)
        _write_json(target_root / "parameters.json", module_parameters, written)
        _copy_file(module_root / "commands.json", target_root / "commands.json", written)

        source_drivers = module_root / "drivers"
        target_drivers = target_root / "drivers"
        _copy_file(source_drivers / "__init__.py", target_drivers / "__init__.py", written)
        driver_names = _driver_names(source_drivers, include_all_drivers)
        for driver_name in driver_names:
            _copy_file(source_drivers / driver_name, target_drivers / driver_name, written)

        if include_examples:
            _copy_tree_files(module_root / "examples", target_root / "examples", written)
        if include_tests:
            _copy_tree_files(module_root / "tests", target_root / "tests", written)

        config_modules[module_id] = parameter_overrides.get(module_id, {})
        lock_modules[module_id] = {
            "module_id": module_id,
            "module_name": module_info["module_name"],
            "version": module_info.get("version"),
            "interface": module_info.get("interface"),
            "protocol": module_info.get("protocol"),
            "drivers": driver_names,
            "source": f"modules/{module_id}",
        }

    registries = _write_filtered_registries(output_root, selected_set, written)
    _copy_tree_files(ROOT_DIR / "schemas", output_root / "schemas", written)
    _write_text(output_root / "driver_xai.py", _driver_xai_runner_source(), written)
    _write_json(
        output_root / "driver_xai_config.json",
        {
            "schema_version": "1.0",
            "modules": config_modules,
        },
        written,
    )
    _write_json(
        output_root / "driver_xai.lock.json",
        {
            "schema_version": "1.0",
            "source": str(ROOT_DIR),
            "modules": lock_modules,
            "registries": registries,
        },
        written,
    )

    return {
        "ok": True,
        "output_dir": str(output_root),
        "modules": selected,
        "registries": registries,
        "files": written,
        "entrypoint": "driver_xai.py",
        "note": "Generated mini Driver xAI folder preserves catalog shape and does not create main.py.",
    }


def execute(
    module_id: str,
    has_variant: bool,
    variant_name: str | None,
    command: str,
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    module_dir = _module_variant_dir(module_id, has_variant, variant_name)
    commands = _read_json(module_dir / "commands.json").get("commands", [])
    command_data = next((item for item in commands if item.get("name") == command), None)
    if command_data is None:
        raise ValueError(f"unsupported command for {module_id}: {command}")
    return {
        "status": "ready",
        "module_id": module_id,
        "command": command,
        "parameters": parameters or {},
        "driver": str(module_dir / "drivers" / "micropython.py"),
        "command_spec": command_data,
        "log": "Command resolved. Runtime execution should be performed by the host/device backend.",
    }


def _normalize_module_id(module_id: str) -> str:
    value = str(module_id).strip()
    if not value:
        raise ValueError("module_id is required")
    return value


def _module_dir(module_id: str) -> Path:
    path = MODULES_DIR / module_id
    if not path.is_dir():
        raise FileNotFoundError(path)
    return path


def _module_variant_dir(module_id: str, has_variant: bool, variant_name: str | None) -> Path:
    module_dir = _module_dir(module_id)
    if not has_variant:
        return module_dir
    if not variant_name:
        raise ValueError("variant_name is required when has_variant is true")
    variant_dir = module_dir / "variants" / variant_name
    if not variant_dir.is_dir():
        raise FileNotFoundError(variant_dir)
    return variant_dir


def _all_registries() -> list[dict[str, Any]]:
    registries: list[dict[str, Any]] = []
    registries.extend(registry("protocol"))
    registries.extend(registry("interface"))
    return registries


def _read_registry(path: Path) -> dict[str, Any]:
    data = _read_json(path)
    if data.get("id") != path.parent.name or data.get("name") != path.parent.name:
        raise ValueError(f"registry id/name must match folder name: {path}")
    if data.get("type") not in {"protocol", "interface"}:
        raise ValueError(f"registry type must be protocol or interface: {path}")
    for module_ref in data.get("modules", []):
        if module_ref.get("id") != module_ref.get("name"):
            raise ValueError(f"registry module id/name mismatch: {path}")
        module_info = info(module_ref["id"])
        if module_info["module_id"] != module_ref["id"]:
            raise ValueError(f"registry references mismatched module: {path}")
    return data


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _json_source_name(source: str) -> str:
    return source if source.endswith(".json") else f"{source}.json"


def _normalize_registry_type(type: str) -> str:
    value = type.strip().lower()
    if value not in {"protocol", "interface"}:
        raise ValueError("type must be protocol or interface")
    return value


def _validate_module_identity(module_id: str, data: dict[str, Any]) -> None:
    if data.get("module_id") != module_id or data.get("module_name") != module_id:
        raise ValueError("folder name, module_id, and module_name must be the same")


def _merge_parameters(template: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    data = json.loads(json.dumps(template))
    if not override:
        return data

    for section_name in ("pins", "options", "config", "bus", "custom"):
        section = data.get(section_name)
        if not isinstance(section, dict):
            continue
        nested_override = override.get(section_name)
        if isinstance(nested_override, dict):
            for key, value in nested_override.items():
                _assign_parameter(section, key, value)
        for key in list(section.keys()):
            if key in override:
                _assign_parameter(section, key, override[key])

    custom = data.setdefault("custom", {})
    if isinstance(custom, dict):
        for key, value in override.items():
            if key not in {"pins", "options", "config", "bus", "custom"} and not _parameter_key_exists(data, key):
                custom[key] = value

    return data


def _assign_parameter(section: dict[str, Any], key: str, value: Any) -> None:
    current = section.get(key)
    if isinstance(current, dict) and "default" in current:
        current["default"] = value
        return
    section[key] = value


def _parameter_key_exists(data: dict[str, Any], key: str) -> bool:
    for section_name in ("pins", "options", "config", "bus"):
        section = data.get(section_name)
        if isinstance(section, dict) and key in section:
            return True
    return False


def _driver_names(source_drivers: Path, include_all_drivers: bool) -> list[str]:
    if include_all_drivers:
        return sorted(path.name for path in source_drivers.iterdir() if path.is_file() and path.name != "__init__.py")
    return ["micropython.py"]


def _write_filtered_registries(output_root: Path, selected_modules: set[str], written: list[str]) -> list[str]:
    registries: list[str] = []
    for source_root, target_root_name in ((PROTOCOLS_DIR, "protocols"), (INTERFACES_DIR, "interfaces")):
        for source_registry in sorted(source_root.glob("*/registry.json")):
            registry_data = _read_json(source_registry)
            filtered_modules = [
                module_ref
                for module_ref in registry_data.get("modules", [])
                if module_ref.get("id") in selected_modules
            ]
            if not filtered_modules:
                continue
            registry_data["modules"] = filtered_modules
            target_registry = output_root / target_root_name / source_registry.parent.name / "registry.json"
            _write_json(target_registry, registry_data, written)
            registries.append(f"{registry_data['type']}:{registry_data['id']}")
    return registries


def _copy_tree_files(source_root: Path, target_root: Path, written: list[str]) -> None:
    if not source_root.is_dir():
        return
    for source in sorted(path for path in source_root.rglob("*") if path.is_file()):
        if "__pycache__" in source.parts or source.suffix in {".pyc", ".pyo"}:
            continue
        _copy_file(source, target_root / source.relative_to(source_root), written)


def _copy_file(source: Path, target: Path, written: list[str]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    written.append(str(target))


def _write_json(path: Path, data: dict[str, Any], written: list[str]) -> None:
    _write_text(path, json.dumps(data, indent=2, sort_keys=True) + "\n", written)


def _write_text(path: Path, text: str, written: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    written.append(str(path))


def _driver_xai_runner_source() -> str:
    return '''try:
    import ujson as json
except ImportError:
    import json
import sys


try:
    ROOT_DIR = __file__.rsplit("/", 1)[0] if "/" in __file__ else ""
except NameError:
    ROOT_DIR = ""

_instances = {}


def _path(path):
    return ("%s/%s" % (ROOT_DIR, path)) if ROOT_DIR else path


def _read_json(path):
    with open(_path(path), "r") as handle:
        return json.loads(handle.read())


def _ok(action, module_id=None, command=None, result=None):
    return {
        "ok": True,
        "action": action,
        "module_id": module_id,
        "command": command,
        "result": result,
        "error": None,
    }


def _error(code, message, module_id=None, command=None, details=None):
    return {
        "ok": False,
        "action": None,
        "module_id": module_id,
        "command": command,
        "result": None,
        "error": {
            "code": code,
            "message": message,
            "details": details,
        },
    }


def config():
    return _read_json("driver_xai_config.json")


def lock():
    return _read_json("driver_xai.lock.json")


def list_modules():
    return _ok("list_modules", result=sorted(lock().get("modules", {}).keys()))


def info(module_id):
    return _read_json("modules/%s/info.json" % module_id)


def parameters(module_id):
    return _read_json("modules/%s/parameters.json" % module_id)


def commands(module_id):
    return _read_json("modules/%s/commands.json" % module_id)["commands"]


def describe(module_id):
    data = {
        "info": info(module_id),
        "parameters": parameters(module_id),
        "commands": commands(module_id),
        "lock": lock().get("modules", {}).get(module_id, {}),
    }
    return _ok("describe", module_id=module_id, result=data)


def describe_command(module_id, command):
    command_data = _command_spec(module_id, command)
    if command_data is None:
        return _error("UNKNOWN_COMMAND", "unknown command", module_id, command)
    return _ok("describe_command", module_id=module_id, command=command, result=command_data)


def setup_from_parameters(module_id):
    data = parameters(module_id)
    setup = {}
    for section_name in ("pins", "config"):
        section = data.get(section_name, {})
        for key, value in section.items():
            setup[key] = value
    for key, value in data.get("options", {}).items():
        if isinstance(value, dict) and "default" in value:
            setup[key] = value["default"]
        else:
            setup[key] = value
    return setup


def _bus_setup(module_id, setup):
    module_info = info(module_id)
    if module_info.get("protocol") != "i2c" or "i2c" in setup:
        return setup
    bus = parameters(module_id).get("bus", {})
    sda = bus.get("sda")
    scl = bus.get("scl")
    if sda is None or scl is None:
        return setup
    try:
        from machine import I2C, Pin
        name = str(bus.get("name", "i2c0"))
        bus_id = int(name.replace("i2c", "") or 0)
        frequency = int(bus.get("frequency_hz", 400000))
        setup["i2c"] = I2C(bus_id, scl=Pin(int(scl)), sda=Pin(int(sda)), freq=frequency)
    except Exception:
        pass
    return setup


def load_driver(module_id):
    if ROOT_DIR and ROOT_DIR not in sys.path:
        sys.path.insert(0, ROOT_DIR)
    elif "" not in sys.path:
        sys.path.insert(0, "")
    module = __import__("modules.%s.drivers.micropython" % module_id, None, None, ("Driver",))
    return module.Driver


def create(module_id, setup=None, refresh=False):
    if setup is None:
        setup = setup_from_parameters(module_id)
    setup = _bus_setup(module_id, setup)
    if refresh or module_id not in _instances:
        Driver = load_driver(module_id)
        _instances[module_id] = Driver(**setup)
    return _instances[module_id]


def reset(module_id=None):
    targets = [module_id] if module_id else list(_instances.keys())
    for target in targets:
        driver = _instances.get(target)
        if driver is not None and hasattr(driver, "off"):
            try:
                driver.off()
            except Exception:
                pass
        if target in _instances:
            del _instances[target]
    return _ok("reset", module_id=module_id, result={"modules": targets})


def state(module_id):
    try:
        driver = create(module_id)
        if hasattr(driver, "state"):
            result = driver.state()
        elif hasattr(driver, "details"):
            result = driver.details()
        else:
            result = {}
        return _ok("state", module_id=module_id, result=result)
    except Exception as exc:
        return _error("STATE_ERROR", str(exc), module_id)


def validate(module_id, command, runtime=None):
    command_data = _command_spec(module_id, command)
    if command_data is None:
        return _error("UNKNOWN_COMMAND", "unknown command", module_id, command)
    if runtime is None:
        runtime = {}
    if not isinstance(runtime, dict):
        return _error("INVALID_RUNTIME", "runtime must be an object", module_id, command)

    inputs = command_data.get("inputs", {})
    if isinstance(inputs, list):
        normalized = {}
        for name in inputs:
            normalized[name] = {"required": False}
        inputs = normalized
    if not isinstance(inputs, dict):
        return _error("INVALID_COMMAND_SPEC", "command inputs must be an object", module_id, command)

    errors = []
    allow_extra = bool(command_data.get("allow_extra", False))
    for key in runtime:
        if key not in inputs and not allow_extra:
            errors.append({"field": key, "message": "unknown input"})
    for name, rule in inputs.items():
        if rule is None:
            rule = {}
        if rule.get("required", False) and name not in runtime:
            errors.append({"field": name, "message": "required input missing"})
            continue
        if name not in runtime:
            continue
        error = _validate_value(name, runtime[name], rule)
        if error:
            errors.append(error)

    combinations = command_data.get("allowed_combinations")
    if combinations and not _matches_combination(runtime, inputs, combinations):
        errors.append({
            "field": "allowed_combinations",
            "message": "input combination is not supported",
            "allowed": combinations,
        })

    if errors:
        return _error("VALIDATION_ERROR", "runtime failed validation", module_id, command, errors)
    return _ok("validate", module_id=module_id, command=command, result={"runtime": runtime})


def execute(module_id, command=None, runtime=None, setup=None, refresh=False):
    if command is None:
        return _error("MISSING_COMMAND", "command is required", module_id)
    validation = validate(module_id, command, runtime)
    if not validation.get("ok"):
        return validation
    try:
        command_data = _command_spec(module_id, command)
        method_name = command_data.get("driver_method", command)
        driver = create(module_id, setup=setup, refresh=refresh)
        method = getattr(driver, method_name)
        result = method(**(runtime or {}))
        return _ok("execute", module_id=module_id, command=command, result=result)
    except Exception as exc:
        return _error("EXECUTION_ERROR", str(exc), module_id, command)


def _command_spec(module_id, command):
    for command_data in commands(module_id):
        if command_data.get("name") == command:
            return command_data
    return None


def _validate_value(name, value, rule):
    if value is None:
        if rule.get("nullable", False):
            return None
        return {"field": name, "message": "null is not allowed"}

    expected_type = rule.get("type")
    if expected_type and not _matches_type(value, expected_type):
        return {"field": name, "message": "expected %s" % expected_type}

    if "allowed" in rule and value not in rule.get("allowed", []):
        return {"field": name, "message": "value is not allowed", "allowed": rule.get("allowed", [])}

    if isinstance(value, (int, float)):
        if "min" in rule and value < rule["min"]:
            return {"field": name, "message": "value below minimum", "min": rule["min"]}
        if "max" in rule and value > rule["max"]:
            return {"field": name, "message": "value above maximum", "max": rule["max"]}
    return None


def _matches_combination(runtime, inputs, combinations):
    for combination in combinations:
        matched = True
        for name, expected in combination.items():
            value = runtime[name] if name in runtime else inputs.get(name, {}).get("default")
            if value != expected:
                matched = False
                break
        if matched:
            return True
    return False


def _matches_type(value, expected_type):
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    return True
'''
