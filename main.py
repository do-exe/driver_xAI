from __future__ import annotations

import json
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
        "execute": "execute(module_id, has_variant, variant_name, command, parameters=None) -> return executable command plan",
    }


def search(module_id_or_module_name: str) -> list[dict[str, Any]]:
    query = module_id_or_module_name.strip().lower()
    matches: list[dict[str, Any]] = []
    for registry_data in _all_registries():
        for module_ref in registry_data.get("modules", []):
            module_id = module_ref.get("id", "")
            module_name = module_ref.get("name", "")
            if query in {module_id.lower(), module_name.lower()}:
                module_info = info(module_id)
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
