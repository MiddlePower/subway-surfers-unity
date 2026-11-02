#!/usr/bin/env python3
"""Generate a reversible, cache-busted LOCAL No-Coin game-over test page.

This is a private, experimental modification of a compiled Unity WebGL build.
It changes Coin.Pickup to get SYBO.Subway.Game.Instance and call Game.Die.
It does NOT modify the original build files or automatically publish anything.

From the repository root:
  py tools/try_nocoin_gameover.py
  py tools/try_nocoin_gameover.py --write
  py -m http.server 8000

Open http://localhost:8000/nocoin-gameover.html?inspect=1 in a private window.
"""
import argparse
import hashlib
import json
from pathlib import Path

from patch_no_coin_local import (
    encode_with_original_compression, replace_function_body, uleb,
)
from probe_coin_hook import (
    ORIGINAL_WASM, DEFAULT_ASSET, DEFAULT_CONFIG, PAGE_TEMPLATE, source_asset,
)
from resolve_wasm_methods import analyze, signature
from show_resolved_wasm_bodies import map_target

COIN_PICKUP = 'SYBO.Subway.Coins.Coin$$Pickup'
GAME_INSTANCE = 'SYBO.Subway.Game$$get_Instance'
GAME_DIE = 'SYBO.Subway.Game$$Die'
OUTPUT_PAGE = Path('nocoin-gameover.html')


def build_die_via_game_instance(getter_func, die_func):
    """WebAssembly code for: Game.Die(Game.get_Instance(null), null).

    Coin.Pickup has signature void(Coin* this, MethodInfo*), but this
    replacement intentionally does not consume those arguments:
      00                 zero local declaration groups
      41 00              i32.const 0 (MethodInfo* for get_Instance)
      10 <func>          call Game.get_Instance -> i32 Game*
      41 00              i32.const 0 (MethodInfo* for Die)
      10 <func>          call Game.Die
      0b                 end
    """
    return (b'\x00\x41\x00\x10' + uleb(getter_func)
            + b'\x41\x00\x10' + uleb(die_func) + b'\x0b')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true',
                        help='Create alternate local page, JSON config and WASM file')
    args = parser.parse_args()

    original = ORIGINAL_WASM.read_bytes()
    script = json.loads(Path('local-analysis/dump/script.json').read_text(encoding='utf-8-sig'))
    types, type_ids, imported, table, bodies, diag = analyze(original)

    expected = ((COIN_PICKUP, 'viii'),
                (GAME_INSTANCE, 'ii'),
                (GAME_DIE, 'vii'))
    resolved = {}
    for name, wanted_sig in expected:
        idx, err = map_target(original, script, name, types, type_ids,
                              imported, table, bodies, diag['exports'])
        if err:
            raise RuntimeError(f'Method cannot be resolved: {name}: {err}')
        actual_sig = signature(types[type_ids[idx]])
        if actual_sig != wanted_sig:
            raise ValueError(f'Unexpected signature for {name}: {actual_sig}, expected {wanted_sig}')
        resolved[name] = idx
        print(f'Verified {name} -> WASM function {idx} ({actual_sig})')

    # Avoid patching if code-generation unexpectedly coalesced methods.
    if len(set(resolved.values())) != 3:
        raise ValueError('Multiple target method names map to the same WASM function')
    packed_source_path, compression = source_asset(original)
    new_body = build_die_via_game_instance(resolved[GAME_INSTANCE], resolved[GAME_DIE])
    patched, old_body = replace_function_body(original, resolved[COIN_PICKUP], imported, new_body)
    if old_body is None or len(old_body) < 2:
        raise ValueError('Original coin pickup body was not found')
    after = analyze(patched)
    if (len(after[4]) != len(bodies) or
        after[1] != type_ids or after[2] != imported or
        after[3] != table):
        raise RuntimeError('WASM structure verification failed')

    suffix = hashlib.sha256(patched).hexdigest()[:12]
    filename = f'SanFrancisco.nocoin.gameover.{suffix}.wasm.code.unityweb'
    config_filename = f'SanFrancisco.nocoin.gameover.{suffix}.json'
    asset_path = DEFAULT_ASSET.with_name(filename)
    config_path = DEFAULT_CONFIG.with_name(config_filename)

    base_config = json.loads(DEFAULT_CONFIG.read_text(encoding='utf-8'))
    if base_config.get('wasmCodeUrl') != DEFAULT_ASSET.name:
        raise ValueError('Unexpected WASM asset in the original Unity JSON config')
    base_config['wasmCodeUrl'] = filename
    original_page = PAGE_TEMPLATE.read_text(encoding='utf-8')
    if original_page.count('SanFrancisco.json') != 1:
        raise ValueError('Expected one SanFrancisco.json reference in root index.html')
    page = original_page.replace('SanFrancisco.json', config_filename)

    print(f'\nCoin.Pickup original WASM body: {len(old_body)} bytes; replacement: {len(new_body)} bytes')
    print('Test action: Game.Die(Game.Instance, null) immediately upon Coin.Pickup')
    print('Original input:', packed_source_path)
    print('Unmodified original build and index.html will remain untouched.')
    print('Unverified gameplay outcome: may end run, freeze, crash or be ignored.')

    if not args.write:
        print('\nDry run completed; use --write to create private local test files.')
        return

    asset_path.write_bytes(encode_with_original_compression(patched, compression))
    config_path.write_text(json.dumps(base_config, indent=2), encoding='utf-8')
    OUTPUT_PAGE.write_text(page, encoding='utf-8')
    print('\nCreated local test asset:', asset_path)
    print('Created local config:', config_path)
    print('Created local page:', OUTPUT_PAGE)
    print('Start: py -m http.server 8000')
    print('Open: http://localhost:8000/nocoin-gameover.html?inspect=1')
    print('If it fails, copy any JavaScript Console error and describe what happened.')
    print('Do not commit or publicly redistribute these modified commercial game files.')


if __name__ == '__main__':
    main()
