#!/usr/bin/env python3
"""Generate an isolated, cache-busted LOCAL test page for a selected coin hook.

This diagnostic deliberately triggers a WASM 'unreachable' exception when its
selected function is called. It DOES NOT implement the no-coin challenge.
Neither index.html nor the original Unity build assets are modified.

Usage:
  py tools/probe_coin_hook.py --hook coin-pickup
  py tools/probe_coin_hook.py --hook game-callback
  py tools/probe_coin_hook.py --status
  py -m http.server 8000

Visit http://localhost:8000/nocoin-probe.html?inspect=1 (fresh/private tab).
"""
import argparse
import hashlib
import json
from pathlib import Path

from patch_no_coin_local import encode_with_original_compression, replace_function_body
from prepare_il2cpp_analysis import decode_blob
from resolve_wasm_methods import analyze
from show_resolved_wasm_bodies import map_target

ORIGINAL_WASM = Path('local-analysis/game.wasm')
DEFAULT_ASSET = Path('Build/SanFrancisco/SanFrancisco.wasm.code.unityweb')
BACKUP_ASSET = Path('local-analysis/original.wasm.code.unityweb')
DEFAULT_CONFIG = Path('Build/SanFrancisco/SanFrancisco.json')
PAGE_TEMPLATE = Path('index.html')
OUTPUT_PAGE = Path('nocoin-probe.html')
WASM_MAGIC = b'\0asm\x01\0\0\0'
HOOKS = {
    'coin-pickup': 'SYBO.Subway.Coins.Coin$$Pickup',
    'coin-manager-pickup': 'SYBO.Subway.Coins.CoinManager$$PickupCoin',
    'coin-event': 'SYBO.Subway.Coins.CoinManager$$RaiseOnCoinCollected',
    'game-callback': 'SYBO.Subway.Game$$CoinManager_OnCoinCollected',
}


def fingerprint(data):
    return hashlib.sha256(data).hexdigest()[:12]


def source_asset(original_wasm):
    for candidate in (BACKUP_ASSET, DEFAULT_ASSET):
        if not candidate.exists():
            continue
        packed = candidate.read_bytes()
        unpacked, compression = decode_blob(packed, WASM_MAGIC)
        if unpacked == original_wasm:
            return candidate, compression
    raise ValueError(
        'No original Unity asset matches local-analysis/game.wasm. '
        'Restore the original asset from git, or ensure the backup '
        'local-analysis/original.wasm.code.unityweb exists.')


def status():
    if not ORIGINAL_WASM.exists():
        print('Missing original local-analysis/game.wasm; run prepare_il2cpp_analysis.py')
        return
    original = ORIGINAL_WASM.read_bytes()
    print('Original uncompressed WASM SHA256:', hashlib.sha256(original).hexdigest())
    for path in (BACKUP_ASSET, DEFAULT_ASSET):
        if not path.is_file():
            print(path, ': not found')
            continue
        try:
            raw, compression = decode_blob(path.read_bytes(), WASM_MAGIC)
            print(f'{path}: compression={compression}, matches original={raw == original}, '
                  f'sha256={hashlib.sha256(raw).hexdigest()}')
        except Exception as exc:
            print(path, ': cannot inspect:', exc)
    if DEFAULT_CONFIG.exists():
        data = json.loads(DEFAULT_CONFIG.read_text(encoding='utf-8'))
        print('Original config wasmCodeUrl:', data.get('wasmCodeUrl'))


def build_probe(hook_name):
    if not ORIGINAL_WASM.is_file():
        raise FileNotFoundError('Run: py tools/prepare_il2cpp_analysis.py')
    original_wasm = ORIGINAL_WASM.read_bytes()
    source_path, compression = source_asset(original_wasm)
    script_path = Path('local-analysis/dump/script.json')
    script = json.loads(script_path.read_text(encoding='utf-8-sig'))
    types, function_types, imports, table, bodies, diagnostics = analyze(original_wasm)
    target = HOOKS[hook_name]
    func, error = map_target(
        original_wasm, script, target, types, function_types,
        imports, table, bodies, diagnostics['exports'])
    if error:
        raise RuntimeError('Target not verified: ' + error)
    # Local declaration count: 0, unreachable opcode: 0x00, end: 0x0B
    # This intentionally traps if the function is actually called.
    patched, old_body = replace_function_body(original_wasm, func, imports, b'\x00\x00\x0b')
    if len(analyze(patched)[4]) != len(bodies):
        raise ValueError('WASM function count changed unexpectedly')
    token = fingerprint(patched)
    asset_name = f'SanFrancisco.probe.{hook_name}.{token}.wasm.code.unityweb'
    config_name = f'SanFrancisco.probe.{hook_name}.{token}.json'
    output_asset = DEFAULT_ASSET.with_name(asset_name)
    output_config = DEFAULT_CONFIG.with_name(config_name)
    config = json.loads(DEFAULT_CONFIG.read_text(encoding='utf-8'))
    if config.get('wasmCodeUrl') != DEFAULT_ASSET.name:
        raise ValueError('Original JSON config points to unexpected WASM asset; refusing')
    config['wasmCodeUrl'] = asset_name

    html = PAGE_TEMPLATE.read_text(encoding='utf-8')
    if 'SanFrancisco.json' not in html:
        raise ValueError('HTML entrypoint lacks expected Unity config reference')
    html = html.replace('SanFrancisco.json', config_name)
    if html == PAGE_TEMPLATE.read_text(encoding='utf-8'):
        raise ValueError('No HTML changes made')

    output_asset.write_bytes(encode_with_original_compression(patched, compression))
    output_config.write_text(json.dumps(config, indent=2), encoding='utf-8')
    OUTPUT_PAGE.write_text(html, encoding='utf-8')
    print('Hook:', hook_name, '-', target)
    print('Verified WASM function:', func, '| original body:', len(old_body), 'bytes')
    print('Probe body: unreachable (intentional diagnostic crash)')
    print('Original asset:', source_path, '(unchanged)')
    print('Unique test WASM:', output_asset)
    print('Unique test JSON:', output_config)
    print('Unique test HTML:', OUTPUT_PAGE)
    print('Open: http://localhost:8000/nocoin-probe.html?inspect=1')
    print('Start a run, then collect ONE coin. A freeze/exception means the selected hook ran.')
    print('If the game runs normally, inspect the browser Console and Network tabs.')
    print('Do NOT publish this commercial build or its modified probe files.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--hook', choices=HOOKS, default='coin-pickup')
    p.add_argument('--status', action='store_true')
    args = p.parse_args()
    if args.status:
        status()
    else:
        build_probe(args.hook)


if __name__ == '__main__':
    main()
