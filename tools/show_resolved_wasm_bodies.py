#!/usr/bin/env python3
"""Read-only dump of WASM bytecode for resolved IL2CPP methods.

Run:
  py tools/show_resolved_wasm_bodies.py local-analysis/game.wasm local-analysis/dump/script.json

Prints hexadecimal bytes only. Does not edit the game.
"""
import argparse
import json
from pathlib import Path

from resolve_wasm_methods import TARGETS, analyze, signature
from resolve_dyncall_methods import candidate_dyncall_indirections, get_body


def map_target(wasm, script, name, types, function_types, imports, table, bodies, exports):
    method = next((m for m in script.get('ScriptMethod', []) if m.get('Name') == name), None)
    if not method:
        return None, 'Method is absent from script.json'
    expected = method['TypeSignature']
    dyn = exports.get('dynCall_' + expected)
    if dyn is None:
        return None, 'dynCall wrapper is not exported'
    for mask, base, table_index, call_type, _ in candidate_dyncall_indirections(wasm, dyn, imports, bodies):
        slot = base + (int(method['Address']) & mask)
        function_index = table.get((table_index, slot))
        if function_index is None or function_index >= len(function_types):
            continue
        if call_type >= len(types) or signature(types[call_type]) != expected:
            continue
        if signature(types[function_types[function_index]]) != expected:
            continue
        return function_index, None
    return None, 'No verified dynCall table mapping'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('wasm', type=Path)
    p.add_argument('script_json', type=Path)
    p.add_argument('--max-bytes', type=int, default=160,
                   help='Maximum bytecode bytes to print per function')
    p.add_argument('--name', action='append', default=[],
                   help='Inspect one exact script.json method name (repeatable); '
                        'otherwise inspect the default coin/death targets')
    args = p.parse_args()
    if not 8 <= args.max_bytes <= 2000:
        p.error('--max-bytes must be between 8 and 2000')
    wasm = args.wasm.read_bytes()
    script = json.loads(args.script_json.read_text(encoding='utf-8-sig'))
    types, func_types, imported, table, bodies, diagnostics = analyze(wasm)

    for name in (args.name or TARGETS):
        print('\n=== ' + name + ' ===')
        idx, problem = map_target(
            wasm, script, name, types, func_types,
            imported, table, bodies, diagnostics['exports'])
        if problem:
            print('NOT VERIFIED: ' + problem)
            continue
        bounds = get_body(wasm, idx, imported, bodies)
        if bounds is None:
            print('No local WASM function body found')
            continue
        start, end = bounds
        print(f'WASM function #{idx}, bytecode file offset 0x{start:X}, length {end - start:,} bytes')
        print('Bytecode (hex, after local declarations):')
        data = wasm[start:min(end, start + args.max_bytes)]
        for offset in range(0, len(data), 16):
            print(f'  +0x{offset:04X}: {data[offset:offset + 16].hex(" ")}')
        if len(data) < end - start:
            print(f'  ... {end - start - len(data):,} further bytes omitted')
    print('\nRead-only inspection. No commercial game files modified.')


if __name__ == '__main__':
    main()
