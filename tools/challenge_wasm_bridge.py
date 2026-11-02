"""Local-only WebAssembly -> page lifecycle bridge for the No-Coin challenge.

The original Unity WebGL Emscripten runtime contains a no-op imported function:
    env._JS_Eval_EvalJS(ptr)  (signature void(i32))
We reserve two non-pointer positive i32 marker values. The generated local
runtime JS recognizes ONLY those markers and dispatches runner-game-event;
every other invocation remains a no-op as in the original runtime.

Neither the original 4399.z.js nor the original WASM file is overwritten.
"""
import hashlib
from pathlib import Path

from patch_no_coin_local import uleb
from resolve_wasm_methods import Reader, signature

COIN_MARKER = 0x4E434F49   # "NCOI"
HOVERBOARD_MARKER = 0x4E484F56  # "NHOV"
JS_BRIDGE_NAME = "_JS_Eval_EvalJS"
RUNTIME_SOURCE = Path("4399.z.js")
RUNTIME_PREFIX = "4399.challenge."

# Match precisely the intentionally blank Emscripten callback. Refuse to
# modify a runtime that already supplies real behavior at this hook.
JS_ORIGINAL = "function _JS_Eval_EvalJS(ptr) {\n\n        }"


def uleb_i32(value):
    """Signed LEB for positive marker i32 constants (< 2^31)."""
    if not 0 <= value < (1 << 31):
        raise ValueError("Marker out of range")
    result = bytearray()
    while True:
        b = value & 0x7f
        value >>= 7
        if (value == 0 and (b & 0x40) == 0):
            result.append(b)
            return bytes(result)
        result.append(b | 0x80)


def bridge_import(wasm, types, type_ids, imported_count):
    """Resolve a named WASM import by iterating the binary's import section."""
    reader = Reader(wasm, 8)
    imported_index = 0
    found = []
    while reader.pos < reader.end:
        section_id = reader.byte()
        size = reader.uint()
        section = Reader(wasm, reader.pos, reader.pos + size)
        reader.pos = section.end
        if section_id != 2:
            continue
        for _ in range(section.uint()):
            module, name, kind = section.name(), section.name(), section.byte()
            if kind == 0:
                if name == JS_BRIDGE_NAME:
                    found.append((module, imported_index, section.uint()))
                else:
                    section.uint()
                imported_index += 1
            elif kind == 1:
                section.byte()
                limit_flag = section.uint()
                section.uint()
                if limit_flag & 1:
                    section.uint()
            elif kind == 2:
                limit_flag = section.uint()
                section.uint()
                if limit_flag & 1:
                    section.uint()
            elif kind == 3:
                section.byte()
                section.byte()
            else:
                raise RuntimeError("Unsupported WASM imported item kind")
        break

    if imported_index != imported_count:
        raise RuntimeError(
            f"Imported function count mismatch: {imported_index} vs {imported_count}")
    if len(found) != 1:
        raise RuntimeError(
            f"Expected one imported {JS_BRIDGE_NAME}; found {len(found)}")
    module, index, type_index = found[0]
    if module != "env":
        raise RuntimeError(f"Unexpected bridge import module: {module}")
    if signature(types[type_index]) != "vi" or signature(types[type_ids[index]]) != "vi":
        raise RuntimeError(
            f"Bridge import must have signature vi, got {signature(types[type_index])}")
    return index


def marker_instruction(import_index, marker):
    """Emit i32.const MARKER; call imported no-op JS callback."""
    return b"\x41" + uleb_i32(marker) + b"\x10" + uleb(import_index)


def runtime_bridge(source):
    if source.count(JS_ORIGINAL) != 1:
        raise RuntimeError(
            "Expected exactly one blank _JS_Eval_EvalJS function in 4399.z.js")
    replacement = (
        "function _JS_Eval_EvalJS(ptr) {\n"
        "            // Reserved markers from local private No-Coin experiment.\n"
        f"            var kind = ptr === {COIN_MARKER} ? 'coin' : "
        f"(ptr === {HOVERBOARD_MARKER} ? 'hoverboard' : null);\n"
        "            if (kind && typeof window !== 'undefined') {\n"
        "                window.dispatchEvent(new CustomEvent('runner-game-event', "
        "{ detail: { kind: kind } }));\n"
        "            }\n"
        "        }"
    )
    return source.replace(JS_ORIGINAL, replacement)


def runtime_output():
    js = runtime_bridge(RUNTIME_SOURCE.read_text(encoding="utf-8"))
    name = RUNTIME_PREFIX + hashlib.sha256(js.encode("utf-8")).hexdigest()[:12] + ".js"
    return Path(name), js


def enumerate_hoverboard_candidates(script):
    """Provide a diagnostic shortlist without choosing unverified activation methods."""
    matches = []
    for method in script.get("ScriptMethod", []):
        name = method.get("Name", "")
        if "$$" not in name:
            continue
        owner, action = name.split("$$", 1)
        lower = action.lower()
        if (
            ("hoverboard" in owner.lower() and
             any(t in lower for t in ("activate", "start", "enable", "use", "run")))
            or ("hoverboard" in lower and
                any(t in lower for t in ("activate", "use", "start", "enable")))
            or (owner == "Data.Save.InventorySave" and
                any(t in lower for t in ("decreaseamount", "consume", "removeamount")))
        ):
            matches.append(method)
    return matches[:80]
