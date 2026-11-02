#!/usr/bin/env python3
"""Experimental LOCAL inventory + No-Coin build generator.

Read-only dry run:
    py tools/try_nocoin_unlocks.py
Create independent local test page:
    py tools/try_nocoin_unlocks.py --write
Lower-risk first test (currencies + consumables, without board/character unlocks):
    py tools/try_nocoin_unlocks.py --items-only --write

Test in a NEW private/incognito browser profile at:
    http://localhost:8000/nocoin-unlocks.html

This does NOT overwrite any original Unity game assets, index.html, or the
previous working nocoin-gameover.html. BUT playing this experimental build
may modify the browser profile's Unity save. Use an isolated browser profile
and back up important game progress; do not distribute commercial game assets.

Method metadata and signatures are verified against the local Il2CppDumper
outputs. Runtime inventory behavior remains unverified until tested.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

from patch_no_coin_local import encode_with_original_compression, replace_function_body, uleb
from probe_coin_hook import DEFAULT_ASSET, DEFAULT_CONFIG, ORIGINAL_WASM, PAGE_TEMPLATE, source_asset
from resolve_wasm_methods import Reader, analyze, signature
from show_resolved_wasm_bodies import map_target
from try_nocoin_gameover import build_die_via_game_instance, COIN_PICKUP, GAME_DIE, GAME_INSTANCE
from challenge_wasm_bridge import (
    COIN_MARKER, HOVERBOARD_MARKER, bridge_import, marker_instruction,
    runtime_output, enumerate_hoverboard_candidates,
)

MAX_ITEMS = 1_000_000_000
SCRIPT = Path("local-analysis/dump/script.json")
DUMP = Path("local-analysis/dump/dump.cs")
# Keep the successful items-only experiment available as a fallback.
# The full character + board unlock experiment gets a separate page so
# browser/loader caches cannot silently show the items-only version.
OUTPUT_PAGE_ITEMS = Path("nocoin-unlocks.html")
OUTPUT_PAGE_FULL = Path("nocoin-unlocks-full.html")
OUTPUT_PAGE_TIMER = Path("nocoin-unlocks-timer.html")
OUTPUT_PAGE_ITEMS_TIMER = Path("nocoin-unlocks-items-timer.html")


def output_page_for(items_only):
    return OUTPUT_PAGE_ITEMS if items_only else OUTPUT_PAGE_FULL


def timer_page_for(items_only):
    return OUTPUT_PAGE_ITEMS_TIMER if items_only else OUTPUT_PAGE_TIMER


# UpgradeType enum values are checked against dump.cs, not assumed to match
# some other Subway Surfers build.
UPGRADES = {
    "hoverboard": 1,
    "headstart2000": 3,
    "scorebooster": 15,
}

# Runtime call signatures include one hidden IL2CPP MethodInfo* argument.
METHODS = {
    "start": ("SYBO.Subway.Game$$StartNewGame", "vii", ()),
    "keys_get": ("Data.Save.InventorySave$$get_keys", "ii", ()),
    "keys_set": ("Data.Save.InventorySave$$SetKeys", "vii", ("int",)),
    "amount_get": ("Data.Save.InventorySave$$GetAmount", "iii", ("UpgradeType",)),
    "amount_add": ("Data.Save.InventorySave$$IncreaseAmount", "viii", ("UpgradeType", "int")),
    "character_owned": ("Data.Managers.CharacterManager$$IsCharacterOwned", "iii", ("Characters.CharacterId",)),
    "character_unlock": ("Data.Managers.CharacterManager$$UnlockCharacter", "vii", ("Characters.CharacterId",)),
    "board_owned": ("Data.Managers.BoardManager$$IsBoardOwned", "iii", ("Boards.BoardId",)),
    "board_unlock": ("Data.Managers.BoardManager$$UnlockBoard", "vii", ("Boards.BoardId",)),
}


def signed_leb(value):
    """Return the i32.const signed LEB128 representation of a signed integer."""
    if not -(1 << 31) <= value <= (1 << 31) - 1:
        raise ValueError("Value does not fit in signed i32")
    out = bytearray()
    while True:
        byte = value & 0x7f
        value >>= 7
        done = ((value == 0 and (byte & 0x40) == 0)
                or (value == -1 and (byte & 0x40) != 0))
        out.append(byte if done else byte | 0x80)
        if done:
            return bytes(out)


def const(value):
    return b"\x41" + signed_leb(value)


def call(index):
    return b"\x10" + uleb(index)


def get_local(index):
    return b"\x20" + uleb(index)


def set_local(index):
    return b"\x21" + uleb(index)


def conditional(test, action):
    return test + b"\x04\x40" + action + b"\x0b"


def find_records(text):
    """Return (type name, kind, declarations) from Il2CppDumper's dump.cs."""
    namespace = ""
    current = None
    records = []
    for line in text.splitlines():
        stripped = line.strip()
        # Blank global namespaces are written as "// Namespace: " in
        # dump.cs, but strip() removes the trailing space. The earlier
        # parser failed to reset namespace on "// Namespace:" and thus
        # mislabeled global types like Characters.CharacterId as belonging
        # to the last nonempty namespace.
        if stripped.startswith("// Namespace:"):
            namespace = stripped[len("// Namespace:"):].strip()
            continue
        if "// TypeDefIndex:" in stripped:
            # Capture the entire C# type token, including compiler-generated
            # nested names such as Game.<WaitForSecond>d__123 and Game.<>c.
            # The old regex stopped at "<", mistakenly identifying every
            # Game.<...> nested type as another SYBO.Subway.Game.
            m = re.search(r"\b(class|struct|enum|interface)\s+([^\s:{]+)", stripped)
            current = None
            if m:
                kind, simple = m.groups()
                # Nested metadata declarations may already carry the
                # namespace prefix (avoid e.g. Boards.Boards.BoardId).
                fullname = (simple if not namespace or simple.startswith(namespace + ".")
                            else namespace + "." + simple)
                current = {"name": fullname, "simple": simple,
                           "kind": kind, "lines": []}
                records.append(current)
            continue
        if current is not None:
            current["lines"].append(stripped)
    return records


def exact_record(records, fullname):
    # Il2CppDumper's nested type name already contains its outer class.
    matches = [r for r in records if r["name"] == fullname]
    if len(matches) != 1:
        # Show declaration names (not only 0 matches), making it possible
        # to diagnose a genuinely different enum/type layout in the dump.
        type_token = fullname.rsplit(".", 1)[-1]
        nearby = sorted({
            r["name"] + " [" + r["kind"] + "]"
            for r in records
            if r["name"].endswith("." + type_token)
            or r["simple"] == fullname
            or r["simple"].endswith("." + type_token)
        })
        preview = ", ".join(nearby[:15]) if nearby else "none"
        raise RuntimeError(
            f"Expected one IL2CPP type {fullname}; found {len(matches)}. "
            f"Nearby declared types: {preview}. "
            "No IDs will be guessed from unrelated types.")
    return matches[0]


def enum_ids(records, fullname):
    enum = exact_record(records, fullname)
    if enum["kind"] != "enum":
        raise ValueError(f"{fullname} is not an enum")
    values = {}
    pattern = re.compile(r"\bconst\s+\S+\s+([A-Za-z_]\w*)\s*=\s*(-?\d+)\s*;")
    for line in enum["lines"]:
        match = pattern.search(line)
        if match:
            name, value = match.groups()
            number = int(value)
            if 0 <= number <= 65535 and not name.startswith("_"):
                values[name] = number
    ids = sorted(set(values.values()))
    if not ids:
        raise RuntimeError(f"Could not find numeric enum values for {fullname}")
    return ids


def verify_upgrade_ids(records):
    enum = exact_record(records, "Info.UpgradeType")
    if enum["kind"] != "enum":
        raise ValueError("UpgradeType metadata is not an enum")
    for name, expected in UPGRADES.items():
        pattern = r"\bconst\s+UpgradeType\s+" + re.escape(name) + r"\s*=\s*" + str(expected) + r"\s*;"
        if not any(re.search(pattern, line) for line in enum["lines"]):
            raise RuntimeError(f"UpgradeType.{name}={expected} missing/mismatched")


def verify_parameter_types(records, full_method, expected, expect_static=True):
    owner, method_name = full_method.split("$$", 1)
    record = exact_record(records, owner)
    declarations = []
    for line in record["lines"]:
        if not re.search(r"\b" + re.escape(method_name) + r"\s*\(", line):
            continue
        static = " static " in (" " + line + " ")
        if static != expect_static:
            continue
        if not line.endswith("{ }"):
            continue
        match = re.search(r"\b" + re.escape(method_name) + r"\s*\((.*)\)\s*\{\s*\}", line)
        if match:
            declarations.append((line, match.group(1)))
    if len(declarations) != 1:
        raise RuntimeError(
            f"Expected one {'static' if expect_static else 'instance'} "
            f"method declaration for {full_method}; got {len(declarations)}")
    declaration, arguments = declarations[0]
    actual = []
    if arguments.strip():
        for part in arguments.split(","):
            arg = part.split("=")[0].strip()
            tokens = arg.split()
            if len(tokens) < 2:
                raise RuntimeError("Unexpected C# argument syntax: " + declaration)
            actual.append(tokens[-2])
    if tuple(actual) != expected:
        raise RuntimeError(f"C# parameter mismatch for {full_method}: expected {expected}, got {actual} in {declaration}")
    return declaration


def resolve_methods(wasm, script, metadata, collection):
    types, type_ids, imports, table, bodies, diagnostics = metadata
    exports = diagnostics["exports"]
    wanted = {
        "coin": (COIN_PICKUP, "viii"),
        "game_instance": (GAME_INSTANCE, "ii"),
        "die": (GAME_DIE, "vii"),
    }
    for key, (name, sig, params) in METHODS.items():
        if not collection and key in ("character_owned", "character_unlock", "board_owned", "board_unlock"):
            continue
        wanted[key] = (name, sig)

    indices = {}
    for key, (name, expected_sig) in wanted.items():
        index, error = map_target(wasm, script, name, types, type_ids, imports, table, bodies, exports)
        if error:
            raise RuntimeError(f"{name}: {error}")
        actual = signature(types[type_ids[index]])
        if actual != expected_sig:
            raise ValueError(f"{name}: signature {actual} != {expected_sig}")
        if index < imports:
            raise ValueError(f"{name}: method unexpectedly points to an import")
        indices[key] = index
        print(f"{key}: WASM function {index}, verified {actual}")

    if len(set(indices.values())) != len(indices):
        raise RuntimeError("Some target names map to the same WASM function; aborting")
    return indices


def build_inventory_preamble(methods, local_index, character_ids, board_ids):
    instructions = bytearray()

    # keys = max(currentKeys, 1 billion) (do not reduce an existing balance).
    instructions.extend(const(0) + call(methods["keys_get"]) + set_local(local_index))
    check = get_local(local_index) + const(MAX_ITEMS) + b"\x48"  # i32.lt_s
    action = const(MAX_ITEMS) + const(0) + call(methods["keys_set"])
    instructions.extend(conditional(check, action))

    # These three upgrade IDs represent CONSUMABLE item quantities,
    # not different hoverboard character models. Refresh up to exactly
    # MAX_ITEMS, never simply add a billion every new run (integer overflow).
    for upgrade_id in UPGRADES.values():
        instructions.extend(const(upgrade_id) + const(0) +
                            call(methods["amount_get"]) + set_local(local_index))
        # Only grant if 0 <= current < MAX_ITEMS.
        check = (get_local(local_index) + const(0) + b"\x4e" +
                 get_local(local_index) + const(MAX_ITEMS) + b"\x48" +
                 b"\x71")
        grant = (const(upgrade_id) + const(MAX_ITEMS) +
                 get_local(local_index) + b"\x6b" +
                 const(0) + call(methods["amount_add"]))
        instructions.extend(conditional(check, grant))

    if character_ids or board_ids:
        # Query ownership before unlocking each ID, so repeated runs do
        # not unnecessarily re-trigger every unlock event.
        for character in character_ids:
            test = (const(character) + const(0) +
                    call(methods["character_owned"]) + b"\x45")
            unlock = const(character) + const(0) + call(methods["character_unlock"])
            instructions.extend(conditional(test, unlock))
        for board in board_ids:
            test = (const(board) + const(0) +
                    call(methods["board_owned"]) + b"\x45")
            unlock = const(board) + const(0) + call(methods["board_unlock"])
            instructions.extend(conditional(test, unlock))

    return bytes(instructions)


def prepend_to_existing_body(existing, preamble, parameter_count):
    """Insert preamble after WASM local declarations, adding scratch i32."""
    reader = Reader(existing)
    groups = reader.uint()
    total_locals = 0
    for _ in range(groups):
        total_locals += reader.uint()
        reader.byte()
    scratch_index = parameter_count + total_locals
    # Validate body is terminated by the end opcode, so original execution
    # remains reachable after the preamble (no bare return inserted).
    if existing[-1:] != b"\x0b":
        raise ValueError("Original method body is missing its terminal END")
    header = uleb(groups + 1) + existing[len(uleb(groups)):reader.pos] + b"\x01\x7f"
    return header + preamble(scratch_index) + existing[reader.pos:]


def select_hoverboard_hook(script, wasm, metadata, records, explicit=None):
    """Choose an activation-specific method, or verified inventory consumption.

    Never guess an arbitrary Hoverboard method. If the compiled game's
    names are ambiguous, generate the coin toggle but print candidates.
    """
    suggestions = enumerate_hoverboard_candidates(script)
    if explicit:
        matches = [m for m in script.get("ScriptMethod", [])
                   if m.get("Name") == explicit]
        if len(matches) != 1:
            raise ValueError("Requested hoverboard hook not found in script.json: " + explicit)
        candidate = matches[0]
        route = "explicit"
    else:
        preferred_names = {
            "ActivateHoverboard", "UseHoverboard", "StartHoverboard",
            "ActivateBoard", "UseBoard", "OnHoverboardActivated",
        }
        direct = [m for m in suggestions
                  if m["Name"].rsplit("$$", 1)[-1] in preferred_names]
        if len(direct) == 1:
            candidate, route = direct[0], "direct"
        else:
            spends = [m for m in suggestions
                      if m.get("Name") == "Data.Save.InventorySave$$DecreaseAmount"]
            if len(spends) == 1:
                candidate, route = spends[0], "consumption"
            else:
                print("WARNING: No unambiguous hoverboard activation/consumption hook.")
                print("Potential names in your build (for follow-up analysis):")
                for method in suggestions[:25]:
                    print(" -", method.get("Name"), method.get("TypeSignature"))
                print("Hoverboard-specific automatic timer stop NOT YET ACTIVE.")
                return None

    name = candidate["Name"]
    expected_sig = candidate.get("TypeSignature")
    types, type_ids, imports, table, bodies, diag = metadata
    index, err = map_target(wasm, script, name, types, type_ids, imports,
                            table, bodies, diag["exports"])
    if err:
        raise RuntimeError("Hoverboard method cannot be verified: " + err)
    actual = signature(types[type_ids[index]])
    if actual != expected_sig or index < imports or not actual.startswith("v"):
        raise RuntimeError(
            f"Hoverboard hook signature mismatch: {name}: {actual}/{expected_sig}")
    if route == "consumption":
        # Only stop for UpgradeType.hoverboard == 1, never for unrelated
        # powerups bought/consumed via the same method.
        verify_parameter_types(records, name, ("UpgradeType", "int"))
        if actual != "viii":
            raise RuntimeError("Expected DecreaseAmount(UpgradeType,int) -> viii")
    print("Hoverboard event source:", name, "(route:", route, "signature:", actual + ")")
    return index, len(types[type_ids[index]][0]), route


def patch_hoverboard_event(wasm, hook, import_index, imports):
    if not hook:
        return wasm
    func_index, parameters, route = hook
    if route == "consumption":
        # InventorySave.DecreaseAmount(UpgradeType type, int amount):
        # send the event only for type==hoverboard (1).
        event = (b"\x20\x00" + b"\x41\x01\x46" +
                 b"\x04\x40" +
                 marker_instruction(import_index, HOVERBOARD_MARKER) +
                 b"\x0b")
    else:
        event = marker_instruction(import_index, HOVERBOARD_MARKER)
    start, size = analyze(wasm)[4][func_index-imports]
    original = wasm[start:start+size]
    replacement = prepend_to_existing_body(
        original, lambda unused: event, parameter_count=parameters)
    patched, old = replace_function_body(wasm, func_index, imports, replacement)
    if old != original:
        raise RuntimeError("Hoverboard function body changed unexpectedly")
    return patched


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true",
                        help="Generate local page and asset (no overwrites of original build)")
    parser.add_argument("--items-only", action="store_true",
                        help="Skip character/board model unlocks; test currencies and consumables first")
    parser.add_argument("--hoverboard-hook",
                        help="Exact verified IL2CPP method name to signal hoverboard use")
    parser.add_argument("--max-characters", type=int, default=0,
                        help="Limit initial test to N character IDs (0 means all)")
    parser.add_argument("--max-boards", type=int, default=0,
                        help="Limit initial test to N board IDs (0 means all)")
    args = parser.parse_args()
    if args.max_characters < 0 or args.max_boards < 0:
        parser.error("Maximum counts cannot be negative")

    game_bytes = ORIGINAL_WASM.read_bytes()
    dump = DUMP.read_text(encoding="utf-8-sig", errors="replace")
    records = find_records(dump)
    verify_upgrade_ids(records)
    script = json.loads(SCRIPT.read_text(encoding="utf-8-sig"))
    metadata = analyze(game_bytes)
    funcs = resolve_methods(game_bytes, script, metadata, not args.items_only)

    for key, (_, _, types) in METHODS.items():
        if key in funcs:
            print("Declaration:", verify_parameter_types(
                records, METHODS[key][0], types, expect_static=(key != "start")))

    characters = [] if args.items_only else enum_ids(records, "Characters.CharacterId")
    boards = [] if args.items_only else enum_ids(records, "Boards.BoardId")
    if not args.items_only and (not characters or not boards):
        raise RuntimeError("Full unlock test requires verified character and board IDs")
    output_page = output_page_for(args.items_only)
    timer_page = timer_page_for(args.items_only)
    if args.max_characters:
        characters = characters[:args.max_characters]
    if args.max_boards:
        boards = boards[:args.max_boards]
    print(f"Requested grants: keys={MAX_ITEMS}, "
          f"hoverboard/headstart/scorebooster={MAX_ITEMS} each, "
          f"character IDs={len(characters)}, board IDs={len(boards)}")
    if not args.items_only:
        print("Character ID sample:", characters[:12])
        print("Board ID sample:", boards[:12])
        print("Character/board grants activate when you START A RUN. "
              "Check the character and board selection menus AFTER returning to the menu.")
    print("Note: Alternate character outfits are NOT yet unlocked; "
          "valid per-character outfit counts have not been verified.")

    _, _, imports, _, bodies, _ = metadata
    packed_source, compression = source_asset(game_bytes)
    coin_body = build_die_via_game_instance(funcs["game_instance"], funcs["die"])
    patched, original_coin = replace_function_body(
        game_bytes, funcs["coin"], imports, coin_body)
    original_start = bodies[funcs["start"] - imports]
    original_start_body = game_bytes[original_start[0]:
                                     original_start[0] + original_start[1]]

    # Game.StartNewGame signature 'vii' = 2 params (Game this, MethodInfo*).
    start_body = prepend_to_existing_body(
        original_start_body,
        lambda scratch: build_inventory_preamble(funcs, scratch, characters, boards),
        parameter_count=2,
    )
    patched, old_start = replace_function_body(
        patched, funcs["start"], imports, start_body)
    if old_start != original_start_body or original_coin is None:
        raise RuntimeError("Target bodies changed between patches; aborting")

    new_metadata = analyze(patched)
    if (new_metadata[1] != metadata[1] or new_metadata[2] != metadata[2]
            or new_metadata[3] != metadata[3] or len(new_metadata[4]) != len(bodies)):
        raise RuntimeError("WASM section structure failed verification")

    checksum = hashlib.sha256(patched).hexdigest()[:12]
    asset_file = DEFAULT_ASSET.with_name(f"SanFrancisco.nocoin.unlocks.{checksum}.wasm.code.unityweb")
    config_file = DEFAULT_CONFIG.with_name(f"SanFrancisco.nocoin.unlocks.{checksum}.json")
    original_config = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
    if original_config.get("wasmCodeUrl") != DEFAULT_ASSET.name:
        raise ValueError("Unexpected original JSON WASM asset")
    original_config["wasmCodeUrl"] = asset_file.name

    template = PAGE_TEMPLATE.read_text(encoding="utf-8")
    if (template.count("SanFrancisco.json") != 1 or
            template.count('data-run-mode="standard"') != 1):
        raise ValueError("Unexpected root page template; refusing to generate test")
    page = template.replace("SanFrancisco.json", config_file.name)
    page = page.replace('data-run-mode="standard"',
                        'data-run-mode="no-coin"')

    print("Local original source:", packed_source)
    print("Original WASM unchanged; compiled private test will be separate.")
    print("IMPORTANT: Inventory runs only when Game.StartNewGame executes, "
          "not necessarily at initial main menu.")
    print("This is UNTESTED in the real game; back up your browser save.")
    if not args.write:
        print("Dry-run complete; add --write for experimental local files.")
        return

    asset_file.write_bytes(encode_with_original_compression(patched, compression))
    config_file.write_text(json.dumps(original_config, indent=2), encoding="utf-8")
    output_page.write_text(page, encoding="utf-8")
    print("Created:", asset_file)
    print("Created:", config_file)
    print("Created:", output_page)
    print(f"Open http://localhost:8000/{output_page.name} in an isolated browser profile.")
    print("Do not commit/redistribute these commercial game assets.")


if __name__ == "__main__":
    main()
