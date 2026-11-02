#!/usr/bin/env python3
"""Find supported ways to obtain the live Game instance from IL2CPP dumps.

Read-only. Does not touch the commercial build or create any modified WASM.

Usage:
  py tools/inspect_game_instance.py local-analysis/dump/dump.cs local-analysis/dump/script.json
"""
import argparse
import json
import re
from pathlib import Path


def find_class(lines, namespace, typename):
    ns = '// Namespace: ' + namespace
    for start, line in enumerate(lines):
        if line.strip() != ns:
            continue
        end = start + 1
        while end < len(lines) and not lines[end].startswith('// Namespace:'):
            end += 1
        for idx in range(start + 1, min(start + 24, end)):
            if re.search(r'\bclass\s+' + re.escape(typename) + r'\b', lines[idx]):
                return start, end, idx
    return None


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('dump', type=Path)
    p.add_argument('script', type=Path)
    args = p.parse_args()

    lines = args.dump.read_text(encoding='utf-8-sig', errors='replace').splitlines()
    scripts = json.loads(args.script.read_text(encoding='utf-8-sig'))
    methods = scripts.get('ScriptMethod', [])

    print('=== Game class: fields and properties ===')
    region = find_class(lines, 'SYBO.Subway', 'Game')
    if region:
        start, end, cls = region
        print('Class declaration:', lines[cls].strip())
        field_lines = []
        for line in lines[cls+1:end]:
            label = line.strip()
            if label == '// Methods':
                break
            if any(x in label.lower() for x in ('static ', 'instance', 'singleton', ' game;', 'game {', 'game <', 'game _', 'game m_')):
                if len(label) > 160:
                    label = label[:160] + '...'
                if label and not label.startswith('//'):
                    field_lines.append(label)
        for line in field_lines[:55]:
            print(' ', line)
        if not field_lines:
            print('No obvious singleton fields or properties in Game.')
    else:
        print('Could not locate the precise Game class block; method list below is still useful.')

    print('\n=== Relevant Game methods ===')
    names = [item for item in methods if item.get('Name','').startswith('SYBO.Subway.Game$$')]
    patterns = ['instance', 'singleton', 'current', 'game', 'state', 'die', 'death', 'end', 'over', 'manager', 'player', 'character']
    matching = [item for item in names if any(
        term in item.get('Name', '').split('$$', 1)[-1].lower() for term in patterns)]
    for item in matching[:80]:
        print(' ', item.get('Name'), '|', item.get('TypeSignature'), '| address:', item.get('Address'))
    print(f'{len(names)} Game methods total; {len(matching)} relevant name matches.')

    print('\n=== Other singleton/game accessor candidates ===')
    candidates = []
    for item in methods:
        name = item.get('Name','')
        if '$$' not in name:
            continue
        owner, meth = name.split('$$',1)
        if owner.startswith('System.') or owner.startswith('UnityEngine.'):
            continue
        if (
            ('Game' in owner or owner.endswith('Manager') or owner.endswith('Controller'))
            and (meth.startswith(('get_Instance', 'get_instance', 'get_Game', 'get_Current',
                                 'get_Active', 'get_Main', 'get_Singleton')))
        ):
            candidates.append(item)
    for item in candidates[:75]:
        print(' ', item.get('Name'), '|', item.get('TypeSignature'), '| address:', item.get('Address'))
    print(f'{len(candidates)} total candidate accessors.')

    print('\n=== Coin class references to the game ===')
    for namespace, typ in [('SYBO.Subway.Coins', 'Coin'), ('SYBO.Subway.Coins', 'CoinManager')]:
        region = find_class(lines, namespace, typ)
        if not region:
            continue
        start, end, cls = region
        print(typ + ':')
        for line in lines[cls+1:end]:
            label = line.strip()
            if label == '// Methods':
                break
            if ('Game' in label or 'manager' in label.lower() or 'instance' in label.lower()):
                if len(label) < 180 and label and not label.startswith('//'):
                    print(' ', label)
    print('\nThis is read-only inspection; recovered names are not executable code.')


if __name__ == '__main__':
    main()
