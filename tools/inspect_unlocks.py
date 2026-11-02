#!/usr/bin/env python3
"""Read-only survey of IL2CPP skin, board, booster and currency methods.

From the repository root run:
  py tools/inspect_unlocks.py
  py tools/inspect_unlocks.py --category skins --category currency

Reads only local-analysis/dump/script.json and dump.cs, never patches binaries.
"""
import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

CATEGORIES = {
    'skins': ('character', 'skin', 'outfit', 'costume', 'wardrobe', 'avatar'),
    'boards': ('hoverboard', 'board'),
    'boosters': ('scorebooster', 'booster', 'powerup', 'multiplier', 'consumable'),
    'headstarts': ('headstart', 'head_start'),
    'currency': ('currency', 'wallet', 'keymanager', 'keydata', 'playerinfo', 'playerdata', 'balance', 'inventory', 'economy'),
    'storage': ('playerprefs', 'savedata', 'savegame', 'profile', 'inventory', 'userdata', 'progress', 'persistence', 'owned'),
}
ACTIONS = ('unlock', 'owned', 'acquire', 'purchase', 'buy', 'give', 'grant', 'add', 'get', 'set', 'amount', 'count', 'balance', 'save', 'load', 'equip', 'spend', 'consume', 'has', 'initialize')
EXCLUDED = ('System.', 'UnityEngine.', 'Unity.', 'Mono.', 'Google.', 'Firebase.', 'TMPro.', 'DG.', 'Newtonsoft.', 'Microsoft.', 'PlayFab.')


def rank(name, words, methods):
    short = name.split('.')[-1].lower()
    matched = [word for word in words if word in short]
    if not matched:
        return -999
    value = sum(30 + min(len(word), 12) for word in matched)
    value += 4 * sum(any(word in m['Name'].split('$$')[-1].lower() for word in ACTIONS) for m in methods)
    value -= 28 * sum(bad in short for bad in ('popup', 'screen', 'widget', 'button', 'animation', 'view', 'tutorial', 'localization'))
    value += 7 if any(good in short for good in ('data', 'manager')) else 0
    return value


def fields_in_dump(path, owner_names):
    """Read only likely field/property lines from requested named types."""
    wanted = set(owner_names)
    found = defaultdict(list)
    namespace, current_type, area = '', '', ''
    for line in path.read_text(encoding='utf-8-sig', errors='replace').splitlines():
        label = line.strip()
        if label.startswith('// Namespace: '):
            namespace = label[len('// Namespace: '):]
            current_type = ''
            area = ''
        elif '// TypeDefIndex:' in label:
            matches = re.findall(r'\b(?:class|struct|interface)\s+([A-Za-z_]\w*)', label)
            typename = matches[-1] if matches else ''
            current_type = ((namespace + '.') if namespace else '') + typename
            area = ''
        elif label in ('// Fields', '// Properties', '// Methods'):
            area = label
        elif (current_type in wanted and area in ('// Fields', '// Properties')
              and label and not label.startswith('//') and len(found[current_type]) < 10):
            if any(word in label.lower() for word in ('key', 'coin', 'board', 'item', 'count', 'owned', 'character', 'unlock', 'boost', 'headstart', 'balance', 'currency', 'inventory', 'amount', 'save')):
                found[current_type].append(label[:150])
    return found


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--script', type=Path, default=Path('local-analysis/dump/script.json'))
    p.add_argument('--dump', type=Path, default=Path('local-analysis/dump/dump.cs'))
    p.add_argument('--category', choices=sorted(CATEGORIES), action='append')
    p.add_argument('--max-classes', type=int, default=6)
    p.add_argument('--max-methods', type=int, default=8)
    a = p.parse_args()
    if not 1 <= a.max_classes <= 30 or not 1 <= a.max_methods <= 30:
        p.error('max-classes and max-methods must be 1 to 30')

    script = json.loads(a.script.read_text(encoding='utf-8-sig'))
    by_owner = defaultdict(list)
    for m in script.get('ScriptMethod', []):
        name = m.get('Name', '')
        if '$$' not in name:
            continue
        owner = name.split('$$', 1)[0]
        if not owner.startswith(EXCLUDED):
            by_owner[owner].append(m)

    selected = {}
    for category in a.category or CATEGORIES:
        candidates = [(rank(owner, CATEGORIES[category], methods), owner, methods)
                      for owner, methods in by_owner.items()]
        selected[category] = sorted((row for row in candidates if row[0] > 0),
                                    key=lambda row: (-row[0], row[1]))[:a.max_classes]

    fields = fields_in_dump(a.dump, {owner for rows in selected.values() for _, owner, _ in rows})
    for category, rows in selected.items():
        print('\n' + '=' * 14 + ' ' + category.upper() + ' ' + '=' * 14)
        print('Candidate types (ownership and item behavior NOT YET VERIFIED):')
        for score, owner, methods in rows:
            print('\n' + owner + ' (ranking ' + str(score) + ')')
            relevant = [m for m in methods if any(word in m['Name'].split('$$', 1)[-1].lower()
                                                   for word in ACTIONS)]
            relevant.sort(key=lambda m: (not any(word in m['Name'].lower() for word in ('unlock', 'owned', 'give', 'grant', 'get', 'set', 'add', 'save')), m['Name']))
            for m in relevant[:a.max_methods]:
                print('  {}  [{}] pointer={}'.format(m['Name'].split('$$')[-1], m.get('TypeSignature'), m.get('Address')))
            if not relevant:
                print('  (no likely ownership methods)')
            for field in fields.get(owner, [])[:5]:
                print('  FIELD/PROPERTY: ' + field)

    print('\nRead-only method survey complete. No items or skins changed.')


if __name__ == '__main__':
    main()
