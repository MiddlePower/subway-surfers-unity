#!/usr/bin/env python3
"""Read-only: correlate Il2CppDumper script.json addresses with WASM table entries.

Usage:
  py tools/resolve_wasm_methods.py local-analysis/game.wasm local-analysis/dump/script.json

Only prints locations and signatures. Does not patch or execute game code.
"""
import argparse
import json
from pathlib import Path

TARGETS = (
    'SYBO.Subway.Game$$CoinManager_OnCoinCollected',
    'SYBO.Subway.Coins.CoinManager$$RaiseOnCoinCollected',
    'SYBO.Subway.Coins.CoinManager$$PickupCoin',
    'SYBO.Subway.Coins.Coin$$Pickup',
    'SYBO.Subway.Game$$Die',
    'UIScreenController$$GameOverTriggered',
)
TYPES = {0x7F: 'i', 0x7E: 'j', 0x7D: 'f', 0x7C: 'd', 0x7B: 'V'}


class Reader:
    def __init__(self, data, start=0, end=None):
        self.data = data
        self.pos = start
        self.end = len(data) if end is None else end

    def byte(self):
        if self.pos >= self.end:
            raise ValueError('Unexpected end of WASM section')
        result = self.data[self.pos]
        self.pos += 1
        return result

    def uint(self):
        result = 0
        for i in range(10):
            byte = self.byte()
            result |= (byte & 0x7f) << (7 * i)
            if byte < 0x80:
                return result
        raise ValueError('Invalid LEB128 integer')

    def sint(self, bits=32):
        value = 0
        shift = 0
        while True:
            b = self.byte()
            value |= (b & 0x7f) << shift
            shift += 7
            if not b & 0x80:
                break
            if shift >= 64:
                raise ValueError('Invalid signed LEB128')
        if shift < bits and b & 0x40:
            value |= -(1 << shift)
        return value

    def read(self, size):
        if size < 0 or self.pos + size > self.end:
            raise ValueError('Invalid WASM data length')
        start = self.pos
        self.pos += size
        return self.data[start:self.pos]

    def name(self):
        return self.read(self.uint()).decode('utf8', 'replace')


def limits(reader):
    flags = reader.uint()
    reader.uint()
    if flags & 1:
        reader.uint()


def expression(reader, globals_by_index):
    op = reader.byte()
    if op == 0x41:  # i32.const
        value = reader.sint()
    elif op == 0x23:  # global.get (may refer to an imported tableBase)
        index = reader.uint()
        value = globals_by_index[index] if index < len(globals_by_index) else None
    elif op == 0x42:  # i64.const
        reader.sint(64)
        value = None
    elif op == 0x43:  # f32.const
        reader.read(4)
        value = None
    elif op == 0x44:  # f64.const
        reader.read(8)
        value = None
    else:
        raise ValueError(f'Unsupported constant-expression opcode: 0x{op:X}')
    if reader.byte() != 0x0B:
        raise ValueError('Unexpected WASM constant expression')
    return value


def vector(reader):
    return [reader.uint() for _ in range(reader.uint())]


def analyze(binary):
    if binary[:8] != b'\0asm\x01\0\0\0':
        raise ValueError('Expected uncompressed WASM 1 binary from prepare_il2cpp_analysis.py')
    reader = Reader(binary, 8)
    types, func_type_indices, imported_count, tables, bodies = [], [], 0, {}, []
    local_types = []
    exports = {}
    globals_by_index = []
    global_imports = []
    segments = 0
    unresolved_segments = 0
    element_section_present = False
    while reader.pos < reader.end:
        section_id = reader.byte()
        section_size = reader.uint()
        section = Reader(binary, reader.pos, reader.pos + section_size)
        if section.end > len(binary):
            raise ValueError('Invalid WASM section bounds')
        reader.pos = section.end
        if section_id == 1:  # type section
            for _ in range(section.uint()):
                if section.byte() != 0x60:
                    raise ValueError('Unsupported WASM function type')
                params = section.read(section.uint())
                results = section.read(section.uint())
                types.append((params, results))
        elif section_id == 2:  # imports
            for _ in range(section.uint()):
                module = section.name()
                name = section.name()
                kind = section.byte()
                if kind == 0:
                    func_type_indices.append(section.uint())
                    imported_count += 1
                elif kind == 1:
                    section.byte()  # elem type
                    limits(section)
                elif kind == 2:
                    limits(section)
                elif kind == 3:
                    value_type = section.byte()
                    section.byte()  # mutable bit
                    # Confirmed in the Unity Emscripten JS loader:
                    # env["tableBase"] = 0.
                    is_table_base = module == 'env' and name == 'tableBase' and value_type == 0x7F
                    globals_by_index.append(0 if is_table_base else None)
                    global_imports.append(f'{module}.{name}' + (' = 0' if is_table_base else ' = unknown'))
                else:
                    raise ValueError(f'Unsupported WASM import kind {kind}')
        elif section_id == 3:  # functions
            local_types = vector(section)
        elif section_id == 7:  # exported functions (including dynCall_ wrappers)
            for _ in range(section.uint()):
                export_name = section.name()
                kind = section.byte()
                index = section.uint()
                if kind == 0:
                    exports[export_name] = index
        elif section_id == 6:  # defined globals, evaluated when constant
            for _ in range(section.uint()):
                value_type = section.byte()
                section.byte()  # mutable bit
                const = expression(section, globals_by_index)
                globals_by_index.append(const if value_type == 0x7F else None)
        elif section_id == 9:  # function table initialization
            element_section_present = True
            for _ in range(section.uint()):
                segments += 1
                flag = section.uint()
                if flag == 0:
                    table = 0
                    base = expression(section, globals_by_index)
                    elements = vector(section)
                elif flag == 2:
                    table = section.uint()
                    base = expression(section, globals_by_index)
                    section.byte()  # elem kind
                    elements = vector(section)
                elif flag in (1, 3):  # passive or declarative
                    section.byte()  # elem kind
                    vector(section)
                    continue
                else:
                    raise ValueError(f'Unsupported newer WASM element segment flag: {flag}')
                if base is None:
                    unresolved_segments += 1
                    continue
                for n, fidx in enumerate(elements):
                    tables[(table, base + n)] = fidx
        elif section_id == 10:  # code bodies
            for _ in range(section.uint()):
                size = section.uint()
                start = section.pos
                if start + size > section.end:
                    raise ValueError('Invalid WASM function body')
                bodies.append((start, size))
                section.pos += size
    func_type_indices.extend(local_types)
    if bodies and len(bodies) != len(local_types):
        raise ValueError('WASM function count does not match code bodies')
    diagnostics = {'element_section_present': element_section_present,
                   'segments': segments, 'unresolved_segments': unresolved_segments,
                   'imported_globals': global_imports, 'exports': exports}
    return types, func_type_indices, imported_count, tables, bodies, diagnostics


def signature(sig):
    params, result = sig
    result_char = TYPES.get(result[0], '?') if result else 'v'
    return result_char + ''.join(TYPES.get(t, '?') for t in params)


def report(wasm, script):
    types, func_types, imports, tables, bodies, diagnostics = analyze(wasm)
    print(f'WASM: {len(func_types):,} functions ({imports:,} imported), {len(tables):,} initialized table slots')
    print('Element section present:', diagnostics['element_section_present'],
          '| segments:', diagnostics['segments'],
          '| unresolved offset segments:', diagnostics['unresolved_segments'])
    if diagnostics['imported_globals']:
        print('Imported globals:', ', '.join(diagnostics['imported_globals'][:20]))
    if not tables:
        print('No resolved table slots. Table offsets might depend on runtime globals or dynamic initialization.')
    methods = script.get('ScriptMethod', [])
    for needle in TARGETS:
        found = [m for m in methods if m.get('Name') == needle]
        for m in found:
            index = m['Address']
            func_id = tables.get((0, index))
            print(f'\n{needle}:')
            print(f'  Dumper value = 0x{index:X} ({index}); type = {m.get("TypeSignature")}')
            if func_id is None:
                print('  No static entry in table 0 at this index; inspect the dynamic-call table in Ghidra.')
                continue
            print(f'  WebAssembly table[0][{index}] => function index {func_id}')
            if func_id >= len(func_types):
                print('  ERROR: element points outside declared function range')
                continue
            type_idx = func_types[func_id]
            if type_idx >= len(types):
                print('  ERROR: invalid function type index')
                continue
            wasmsig = signature(types[type_idx])
            print('  WASM signature:', wasmsig, '| dumper signature:', m.get('TypeSignature'))
            if wasmsig != m.get('TypeSignature'):
                print('  WARNING: signature differs; mapping may be incorrect or table uses a wrapper.')
            if func_id < imports:
                print('  Function is imported; body not stored in this WASM module')
            else:
                body_idx = func_id - imports
                if body_idx < len(bodies):
                    start, size = bodies[body_idx]
                    print(f'  WASM body at file offset 0x{start:X}, length {size:,} bytes (read-only finding)')
    print('\nThis report identifies candidate code bodies only; do not patch by raw offset without disassembly and verification.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wasm', type=Path)
    parser.add_argument('script', type=Path)
    args = parser.parse_args()
    report(args.wasm.read_bytes(), json.loads(args.script.read_text(encoding='utf-8-sig')))


if __name__ == '__main__':
    main()
