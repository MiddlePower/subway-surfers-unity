#!/usr/bin/env python3
"""Prepare a local Unity WebGL IL2CPP build for read-only offline analysis.

Usage:
  py tools/prepare_il2cpp_analysis.py
  py tools/prepare_il2cpp_analysis.py --output local-analysis

Outputs only to local-analysis/ (ignored by git).
"""
import argparse
import gzip
import struct
from pathlib import Path

MAGIC = b'UnityWebData1.0\x00'
WASM_MAGIC = b'\x00asm'


def decode_blob(blob: bytes, expected_magic: bytes) -> tuple[bytes, str]:
    if blob.startswith(expected_magic):
        return blob, 'raw'
    if blob.startswith(b'\x1f\x8b'):
        out = gzip.decompress(blob)
        mode = 'gzip'
    else:
        try:
            import brotli
        except ImportError as exc:
            raise RuntimeError('Unknown compression; try: py -m pip install brotli') from exc
        try:
            out = brotli.decompress(blob)
            mode = 'brotli'
        except Exception as exc:
            raise ValueError('Unrecognized format or compression') from exc
    if not out.startswith(expected_magic):
        raise ValueError('Decompression succeeded, but signature is unexpected')
    return out, mode


def extract_archive_file(blob: bytes, target: str) -> bytes:
    if not blob.startswith(MAGIC) or len(blob) < 20:
        raise ValueError('Invalid UnityWebData archive')
    start = struct.unpack_from('<I', blob, 16)[0]
    if not 20 <= start <= len(blob):
        raise ValueError('Invalid UnityWebData file table bounds')
    cursor = 20
    while cursor < start:
        if cursor + 12 > start:
            raise ValueError('Truncated archive record')
        offset, size, length = struct.unpack_from('<III', blob, cursor)
        cursor += 12
        if length > 16384 or cursor + length > start or offset < start or offset + size > len(blob):
            raise ValueError('Invalid archive file record')
        filename = blob[cursor:cursor+length].decode('utf-8', 'replace')
        cursor += length
        if filename == target:
            return blob[offset:offset+size]
    raise FileNotFoundError(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('.'), help='Repository root')
    parser.add_argument('--output', type=Path, default=Path('local-analysis'), help='Local output folder')
    args = parser.parse_args()
    datafile = args.root / 'Build/SanFrancisco/SanFrancisco.data.unityweb'
    wasmfile = args.root / 'Build/SanFrancisco/SanFrancisco.wasm.code.unityweb'
    for path in (datafile, wasmfile):
        if not path.is_file():
            parser.error(f'Missing build input: {path}')
    archive, data_compression = decode_blob(datafile.read_bytes(), MAGIC)
    meta = extract_archive_file(archive, 'Il2CppData/Metadata/global-metadata.dat')
    if len(meta) < 8 or struct.unpack_from('<I', meta, 0)[0] != 0xFAB11BAF:
        raise ValueError('Invalid IL2CPP metadata header')
    wasm, wasm_compression = decode_blob(wasmfile.read_bytes(), WASM_MAGIC)
    if len(wasm) < 8 or struct.unpack_from('<I', wasm, 4)[0] != 1:
        raise ValueError('Unexpected WASM binary version')
    args.output.mkdir(parents=True, exist_ok=True)
    out_meta = args.output / 'global-metadata.dat'
    out_wasm = args.output / 'game.wasm'
    out_meta.write_bytes(meta)
    out_wasm.write_bytes(wasm)
    print(f'IL2CPP metadata: {out_meta} ({len(meta):,} bytes; v{struct.unpack_from("<I", meta, 4)[0]})')
    print(f'WebAssembly: {out_wasm} ({len(wasm):,} bytes; format: {wasm_compression})')
    print(f'Unity data archive format: {data_compression}')
    print('These files are for private, local analysis only. Do not add them to git.')
    print('Both files are inputs for a compatible IL2CPP analysis tool such as Il2CppDumper.')


if __name__ == '__main__':
    main()
