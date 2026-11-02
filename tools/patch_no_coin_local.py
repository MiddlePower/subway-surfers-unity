#!/usr/bin/env python3
"""Experimental, reversible LOCAL no-coin patch for an existing Unity WASM build.

No binary is uploaded or committed. Run without --write to verify targets.
Run with --write to generate an alternative local .unityweb asset. Does NOT
replace the existing asset automatically, and is NOT for public redistribution.

Run:
  py tools/patch_no_coin_local.py
  py tools/patch_no_coin_local.py --write
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

from resolve_wasm_methods import Reader, analyze, signature
from prepare_il2cpp_analysis import decode_blob

MAGIC = b'\0asm\x01\0\0\0'
COIN_HANDLER = 'SYBO.Subway.Game$$CoinManager_OnCoinCollected'
DIE_HANDLER = 'SYBO.Subway.Game$$Die'


def uleb(value):
    if value < 0:
        raise ValueError('Cannot encode negative LEB128 integer')
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def replace_function_body(wasm, function_index, imported_count, new_body):
    """Replace exactly one code body; recalculate binary section/body sizes."""
    if not wasm.startswith(MAGIC):
        raise ValueError('Not a raw WASM v1 module')
    body_number = function_index - imported_count
    if body_number < 0:
        raise ValueError('Cannot replace an imported function')
    r = Reader(wasm, 8)
    while r.pos < len(wasm):
        section_start = r.pos
        kind = r.byte()
        payload_size = r.uint()
        payload_start = r.pos
        payload_end = payload_start + payload_size
        if payload_end > len(wasm):
            raise ValueError('Truncated WASM section')
        if kind == 10:
            code = Reader(wasm, payload_start, payload_end)
            count = code.uint()
            if body_number >= count:
                raise ValueError(f'Function {function_index} has no code body')
            result_parts = [uleb(count)]
            original_body = None
            for i in range(count):
                size = code.uint()
                raw = code.read(size)
                if i == body_number:
                    original_body = raw
                    raw = new_body
                result_parts.extend((uleb(len(raw)), raw))
            if code.pos != payload_end:
                raise ValueError('Trailing data in WASM code section')
            new_payload = b''.join(result_parts)
            rewritten = (
                wasm[:section_start] + b'\x0a' + uleb(len(new_payload))
                + new_payload + wasm[payload_end:]
            )
            return rewritten, original_body
        r.pos = payload_end
    raise ValueError('No WASM code section found')


def build_call_die_body(die_function_index):
    # Game.Die: void (Game this, MethodInfo* method)
    # Game.CoinManager_OnCoinCollected: void (Game this, sender, args, MethodInfo*)
    # New handler: Die(this, null), keeping the function's original signature.
    return (b'\x00'
            b'\x20\x00'       # local.get 0: Game this
            b'\x41\x00'       # i32.const 0: null MethodInfo
            b'\x10' + uleb(die_function_index)
            + b'\x0b')


def encode_with_original_compression(raw, compression):
    if compression == 'raw':
        return raw
    if compression == 'gzip':
        return gzip.compress(raw, mtime=0)
    if compression == 'brotli':
        import brotli
        return brotli.compress(raw)
    raise ValueError('Unsupported compression: ' + compression)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--write', action='store_true', help='Generate a local patched asset')
    p.add_argument('--wasm', type=Path, default=Path('local-analysis/game.wasm'))
    p.add_argument('--script', type=Path, default=Path('local-analysis/dump/script.json'))
    p.add_argument('--source', type=Path,
                   default=Path('Build/SanFrancisco/SanFrancisco.wasm.code.unityweb'))
    p.add_argument('--output', type=Path,
                   default=Path('local-analysis/nocoin/SanFrancisco.wasm.code.unityweb'))
    args = p.parse_args()
    from show_resolved_wasm_bodies import map_target

    wasm = args.wasm.read_bytes()
    script = json.loads(args.script.read_text(encoding='utf-8-sig'))
    types, func_types, imports, table, bodies, diagnostics = analyze(wasm)
    mapping_args = (types, func_types, imports, table, bodies, diagnostics['exports'])
    coin_index, coin_error = map_target(wasm, script, COIN_HANDLER, *mapping_args)
    die_index, die_error = map_target(wasm, script, DIE_HANDLER, *mapping_args)
    if coin_error or die_error:
        raise RuntimeError(f'Mapping not verified: coin={coin_error}, die={die_error}')
    coin_sig = signature(types[func_types[coin_index]])
    die_sig = signature(types[func_types[die_index]])
    print(f'Coin event handler: WASM function {coin_index}; signature {coin_sig}')
    print(f'Game.Die: WASM function {die_index}; signature {die_sig}')
    if coin_sig != 'viiii' or die_sig != 'vii':
        raise ValueError('Unexpected signatures; refusing to generate patch')

    original_packed = args.source.read_bytes()
    source_wasm, compression = decode_blob(original_packed, MAGIC)
    if hashlib.sha256(source_wasm).digest() != hashlib.sha256(wasm).digest():
        raise ValueError('Original WebGL binary differs from local-analysis/game.wasm')
    patch_body = build_call_die_body(die_index)
    rewritten, original_body = replace_function_body(wasm, coin_index, imports, patch_body)
    if original_body is None or len(original_body) < 2:
        raise ValueError('Original coin handler body not found')
    # Re-parse sections to catch incorrect code-section size accounting.
    after = analyze(rewritten)
    if after[1] != func_types or after[2] != imports or len(after[4]) != len(bodies):
        raise RuntimeError('Verification failed; WASM function layout changed')
    new_packed = encode_with_original_compression(rewritten, compression)

    print(f'Original handler: {len(original_body)} bytes, patched: {len(patch_body)} bytes')
    print('Original asset compression:', compression)
    print('Generated WASM size:', len(rewritten))
    print('Hypothesis: coin collection triggers Game.Die(this, null).')
    print('UNTESTED against this game; it could crash or not end the run.')
    if not args.write:
        print('Dry run only: add --write to create the local output asset.')
        return
    if args.source.resolve() == args.output.resolve():
        raise ValueError('Output would overwrite source; aborting')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(new_packed)
    print('Created:', args.output)
    print('Original game build asset remains unchanged.')


if __name__ == '__main__':
    main()
