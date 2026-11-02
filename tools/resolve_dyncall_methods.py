#!/usr/bin/env python3
"""Read-only: resolve IL2CPP method pointers through Emscripten dynCall_* groups.

Usage:
  py tools/resolve_dyncall_methods.py local-analysis/game.wasm local-analysis/dump/script.json

Unlike a direct WASM table lookup, Emscripten's dynCall_* exports may apply
a signature-specific offset and bitmask before calling the function table.
This script verifies the actual target's WebAssembly type. It does not patch.
"""
import argparse
import json
from pathlib import Path

from resolve_wasm_methods import TARGETS, Reader, analyze, signature


def get_body(wasm, function_id, imports, bodies):
    if function_id < imports:
        return None
    idx = function_id - imports
    if idx >= len(bodies):
        return None
    start, size = bodies[idx]
    r = Reader(wasm, start, start + size)
    # WASM function bodies begin with local-variable declaration groups.
    for _ in range(r.uint()):
        r.uint()
        r.byte()
    return r.pos, r.end


def candidate_dyncall_indirections(wasm, function_id, imports, bodies):
    """Find short dynCall instruction sequences ending with call_indirect.

    Typical Emscripten sequence:
      local.get 0; i32.const mask; i32.and;
      i32.const offset; i32.add; call_indirect <type> <table>
    Or with mask/add omitted.
    """
    bounds = get_body(wasm, function_id, imports, bodies)
    if not bounds:
        return []
    start, end = bounds
    found = []
    for pos in range(start, end):
        if wasm[pos] != 0x20:  # local.get
            continue
        r = Reader(wasm, pos, end)
        try:
            if r.byte() != 0x20 or r.uint() != 0:
                continue
            mask = 0xFFFFFFFF
            offset = 0
            op = r.byte()
            if op == 0x41:  # i32.const
                first = r.sint()
                op = r.byte()
                if op == 0x71:  # i32.and
                    mask = first & 0xFFFFFFFF
                    op = r.byte()
                    if op == 0x41:  # optional offset after the mask
                        offset = r.sint()
                        op = r.byte()
                        if op != 0x6A:  # i32.add
                            continue
                        op = r.byte()  # advance past i32.add to call_indirect
                    elif op != 0x11:
                        continue
                elif op == 0x6A:  # i32.add (no mask)
                    offset = first
                    op = r.byte()
                else:
                    continue
            if op != 0x11:  # call_indirect
                continue
            type_idx = r.uint()
            table_idx = r.uint()
            found.append((mask, offset, table_idx, type_idx, pos))
        except (ValueError, IndexError):
            continue
    return list(dict.fromkeys(found))


def show_report(wasm, doc):
    types, type_for_function, imported, table, bodies, diagnostics = analyze(wasm)
    exports = diagnostics['exports']
    named_methods = doc.get('ScriptMethod', [])
    print(f'WASM exported dynCall functions: {sum(name.startswith("dynCall_") for name in exports):,}')
    print(f'Initialized table slots: {len(table):,}; entries from {diagnostics["segments"]} element segment(s)')
    for exact_name in TARGETS:
        methods = [x for x in named_methods if x.get('Name') == exact_name]
        for method in methods:
            addr = method['Address']
            expected = method.get('TypeSignature')
            dyn_name = 'dynCall_' + str(expected)
            export_func = exports.get(dyn_name)
            print(f'\n{exact_name}:')
            print(f'  Il2CppDumper pointer: {addr} (0x{addr:X}); expected signature: {expected}')
            if export_func is None:
                print(f'  {dyn_name} not exported by this build; cannot resolve automatically.')
                continue
            print(f'  Export {dyn_name} is WASM function {export_func}')
            if export_func >= len(type_for_function):
                print('  ERROR: export refers to an unknown function index')
                continue
            export_sig = signature(types[type_for_function[export_func]])
            print(f'  Export signature: {export_sig}')
            patterns = candidate_dyncall_indirections(wasm, export_func, imported, bodies)
            if not patterns:
                print('  Could not decode dynCall table offset/mask automatically.')
                bounds = get_body(wasm, export_func, imported, bodies)
                if bounds:
                    begin, end = bounds
                    print('  DynCall instruction bytes (up to first 64):', wasm[begin:min(end, begin + 64)].hex(' '))
                print('  Use Ghidra + ghidra-wasm-plugin analyze_dyncalls.py to resolve this wrapper.')
                continue
            matched = False
            for mask, base, table_idx, call_type, _ in patterns:
                call_sig = signature(types[call_type]) if call_type < len(types) else '<unknown>'
                slot = base + (addr & mask)
                idx = table.get((table_idx, slot))
                if idx is None or idx >= len(type_for_function):
                    print(f'  Candidate slot {slot} not initialized in table {table_idx}; indirect sig {call_sig}')
                    continue
                actual_sig = signature(types[type_for_function[idx]])
                print(f'  dynCall maps (index & 0x{mask:X}) + {base} -> table[{table_idx}][{slot}] -> function {idx}')
                print(f'  Indirect-call signature: {call_sig}; target function signature: {actual_sig}')
                if actual_sig != expected or call_sig != expected:
                    print('  MISMATCH: not verified; do not use this function for modifications.')
                    continue
                matched = True
                target_body = get_body(wasm, idx, imported, bodies)
                if target_body:
                    start, end = target_body
                    print(f'  VERIFIED signature match; WASM function body at 0x{start:X} ({end-start:,} bytes)')
                else:
                    print('  VERIFIED signature match; target is an imported function')
            if not matched:
                print('  No verified matching method body located.')
    print('\nRead-only metadata mapping only. No actual run-ending behavior has been implemented.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('wasm', type=Path)
    p.add_argument('script_json', type=Path)
    args = p.parse_args()
    raw = args.wasm.read_bytes()
    script = json.loads(args.script_json.read_text(encoding='utf-8-sig'))
    show_report(raw, script)


if __name__ == '__main__':
    main()
