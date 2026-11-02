#!/usr/bin/env python3
"""Read-only IL2CPP metadata symbol scanner for a Unity WebGL data archive.

Run: py tools/inspect_coin_symbols.py Build/SanFrancisco/SanFrancisco.data.unityweb
Requires the sibling inspect_unityweb.py; Brotli needs py -m pip install brotli.
"""
import argparse
import struct
from pathlib import Path

from inspect_unityweb import MAGIC, decode_container

TERMS = ('coin', 'pickup', 'collect', 'currency', 'score', 'magnet')


def u32(data, offset):
    return struct.unpack_from('<I', data, offset)[0]


def archive_file(data, name):
    if not data.startswith(MAGIC):
        raise ValueError('Expected UnityWebData1.0 archive')
    start = u32(data, 16)
    if not (20 <= start <= len(data)):
        raise ValueError('Invalid UnityWebData file table')
    pos = 20
    while pos < start:
        if pos + 12 > start:
            raise ValueError('Truncated archive entry')
        off, size, namelen = struct.unpack_from('<III', data, pos)
        pos += 12
        if namelen > 65536 or pos + namelen > start or off + size > len(data) or off < start:
            raise ValueError('Invalid archive entry')
        filename = data[pos:pos + namelen].decode('utf8', errors='replace')
        pos += namelen
        if filename == name:
            return data[off:off + size]
    raise FileNotFoundError(name)


def il2cpp_symbols(meta):
    if len(meta) < 176 or u32(meta, 0) != 0xFAB11BAF:
        raise ValueError('Not an IL2CPP global-metadata.dat file')
    version = u32(meta, 4)
    if version != 24:
        raise ValueError(f'IL2CPP metadata version {version}; this scanner supports version 24 only')

    def section(offset):
        ptr, size = struct.unpack_from('<II', meta, offset)
        if ptr > len(meta) or size > len(meta) - ptr:
            raise ValueError(f'Bad IL2CPP section at header offset {offset}')
        return ptr, size

    strings_off, strings_size = section(24)
    method_off, method_size = section(48)
    type_off, type_size = section(160)
    pool = meta[strings_off:strings_off + strings_size]
    cache = {}

    def name(index):
        if index in cache:
            return cache[index]
        if index >= len(pool):
            return ''
        stop = pool.find(b'\0', index)
        if stop == -1:
            return ''
        value = pool[index:stop].decode('utf8', errors='replace')
        cache[index] = value
        return value

    matches = []
    cursor = 0
    while cursor < len(pool):
        stop = pool.find(b'\0', cursor)
        if stop == -1:
            break
        label = name(cursor)
        if any(term in label.lower() for term in TERMS) and len(label) <= 140:
            matches.append(label)
        cursor = stop + 1
    matches = sorted(set(matches), key=lambda s: (0 if 'coin' in s.lower() else 1, s.lower()))

    # Metadata v24.2+ typically uses 32-byte method and 92-byte type records.
    # Unknown sub-versions fall back to strings rather than guessing owners.
    candidates = []
    if method_size % 32 == 0 and type_size % 92 == 0:
        total_methods = method_size // 32
        total_types = type_size // 92
        methods = [name(u32(meta, method_off + i * 32)) for i in range(total_methods)]
        checked = min(total_methods, 1000)
        valid_names = sum(bool(m and len(m) < 200) for m in methods[:checked])
        if valid_names >= checked * 0.75:
            for i in range(total_types):
                off = type_off + i * 92
                type_name = name(u32(meta, off))
                namespace = name(u32(meta, off + 4))
                method_start = u32(meta, off + 40)
                count = struct.unpack_from('<H', meta, off + 68)[0]
                if not type_name or method_start + count > total_methods:
                    continue
                relevant = [m for m in methods[method_start:method_start + count]
                            if any(term in m.lower() for term in TERMS)]
                if relevant or any(term in type_name.lower() for term in TERMS):
                    owner = (namespace + '.' if namespace else '') + type_name
                    candidates.append((owner, relevant))

    candidates.sort(key=lambda pair: (
        0 if 'coin' in pair[0].lower() or any('coin' in m.lower() for m in pair[1]) else 1,
        0 if 'pickup' in pair[0].lower() or any('pickup' in m.lower() for m in pair[1]) else 1,
        pair[0].lower()
    ))
    return {'version': version, 'pool_size': len(pool),
            'methods': method_size // 32 if method_size % 32 == 0 else None,
            'types': type_size // 92 if type_size % 92 == 0 else None,
            'strings': matches, 'candidate_types': candidates}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--limit', type=int, default=90)
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000:
        parser.error('--limit must be from 1 to 1000')
    raw, compression = decode_container(args.archive.read_bytes())
    metadata = archive_file(raw, 'Il2CppData/Metadata/global-metadata.dat')
    result = il2cpp_symbols(metadata)
    print(f"Metadata v{result['version']} | {len(metadata):,} bytes | {compression}")
    print(f"Name pool: {result['pool_size']:,} bytes | Method records: {result['methods']} | Type records: {result['types']}")
    if result['candidate_types']:
        print(f"\nCandidate types ({len(result['candidate_types'])}; showing up to {args.limit}):")
        for owner, methods in result['candidate_types'][:args.limit]:
            print(f' - {owner}' + (': ' + ', '.join(methods[:12]) if methods else ''))
    else:
        print('\nNo validated class/method mapping found; displaying names only.')
    print(f"\nMatching symbol strings ({len(result['strings'])}; showing up to {args.limit}):")
    for symbol in result['strings'][:args.limit]:
        print(' - ' + symbol)
    print('\nNames are not proof of a callable method, code address, or legal permission to redistribute.')


if __name__ == '__main__':
    main()
