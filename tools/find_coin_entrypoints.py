#!/usr/bin/env python3
"""Inspect method names and call signatures in an existing Il2CppDumper script.json.

This is read-only. It does not edit or patch the Unity WebGL game.

Example:
  py tools/find_coin_entrypoints.py local-analysis/dump/script.json
"""
import argparse
import json
from pathlib import Path

COIN_MARKERS = (
    'CoinManager$$PickupCoin',
    'CoinManager$$RaiseOnCoinCollected',
    'Game$$CoinManager_OnCoinCollected',
    'Coin$$Pickup',
    'GameStats$$',
)
END_MARKERS = ('$$OnCriticalHit', '$$EndGame', '$$GameOver', '$$OnGameOver', '$$Kill', '$$Die')


def rank_method(name):
    if 'CoinManager_OnCoinCollected' in name:
        return 0
    if 'RaiseOnCoinCollected' in name:
        return 1
    if 'PickupCoin' in name:
        return 2
    if '$$Pickup' in name and 'Coin' in name:
        return 3
    return 4


def show(title, items, maximum):
    print(f'\n{title}: {len(items)} candidate(s), displaying up to {maximum}')
    for item in items[:maximum]:
        addr = item.get('Address')
        if isinstance(addr, int):
            value = f'0x{addr:X} ({addr})'
        else:
            value = str(addr)
        print('  ' + item.get('Name', '<unnamed>'))
        print('    Dumper address: ' + value)
        print('    Type signature: ' + str(item.get('TypeSignature', '<unknown>')))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('script_json', type=Path)
    p.add_argument('--limit', type=int, default=35)
    args = p.parse_args()
    if not 1 <= args.limit <= 200:
        p.error('--limit must be between 1 and 200')
    doc = json.loads(args.script_json.read_text(encoding='utf-8-sig'))
    all_methods = doc.get('ScriptMethod', [])
    if not isinstance(all_methods, list):
        raise ValueError('Il2CppDumper script.json has no ScriptMethod list')
    coins = [item for item in all_methods if any(
        marker.lower() in item.get('Name', '').lower() for marker in COIN_MARKERS)]
    coins.sort(key=lambda item: (rank_method(item.get('Name', '')), item.get('Name', '')))
    ends = [item for item in all_methods if any(
        marker.lower() in item.get('Name', '').lower() for marker in END_MARKERS)]
    ends.sort(key=lambda item: item.get('Name', ''))
    print(f'Loaded {len(all_methods):,} Il2CppDumper script method records')
    show('Coin / pickup event methods', coins, args.limit)
    show('Possible end-of-run handlers (names only, unverified)', ends, args.limit)
    print('\nImportant: these numeric values are not necessarily file offsets or WASM')
    print('function indices. No code has been modified by this inspection.')


if __name__ == '__main__':
    main()
