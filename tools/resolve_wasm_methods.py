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


def expression(reader):
    op = reader.byte()
    if op == 0x41:  # i32.const
        value = reader.sint()
    elif op == 0x23:  # global.get; runtime address unknown
        reader.uint()
        value = None
    else:
        raise ValueError(f'Unsupported element offset opcode: 0x{op:X}')
    if reader.byte() != 0x0B:
        raise ValueError('Unexpected WASM element offset expression')
    return value


def vector(reader):
    return [reader.uint() for _ in range(reader.uint())]


def analyze(binary):
    if binary[:8] != b'\0asm\x01\0\0\0':
        raise ValueError('Expected uncompressed WASM 1 binary from prepare_il2cpp_analysis.py')
    reader = Reader(binary, 8)
    types, func_type_indices, imported_count, tables, bodies = [], [], 0, {}, []
    local_types = []
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
                section.name()
                section.name()
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
                    section.byte()  # value type
                    section.byte()  # mutable bit
                else:
                    raise ValueError(f'Unsupported WASM import kind {kind}')
        elif section_id == 3:  # functions
            local_types = vector(section)
        elif section_id == 9:  # function table initialization
            for _ in range(section.uint()):
                flag = section.uint()
                if flag == 0:
                    table = 0
                    base = expression(section)
                    elements = vector(section)
                elif flag == 2:
                    table = section.uint()
                    base = expression(section)
                    section.byte()  # elem kind
                    elements = vector(section)
                elif flag in (1, 3):  # passive or declarative
                    section.byte()  # elem kind
                    vector(section)
                    continue
                else:
                    raise ValueError(f'Unsupported newer WASM element segment flag: {flag}')
                if base is None:
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
    return types, func_type_indices, imported_count, tables, bodies


def signature(sig):
    params, result = sig
    result_char = TYPES.get(result[0], '?') if result else 'v'
    return result_char + ''.join(TYPES.get(t, '?') for t in params)


def report(wasm, script):
    types, func_types, imports, tables, bodies = analyze(wasm)
    print(f'WASM: {len(func_types):,} functions ({imports:,} imported), {len(tables):,} initialized table slots')
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
