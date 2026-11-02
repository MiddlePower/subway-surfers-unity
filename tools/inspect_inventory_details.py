#!/usr/bin/env python3
"""Read-only IL2CPP ownership/inventory detail report.

Focuses on C# method declarations (to recover PARAMETER TYPES), relevant
enums (to recover item IDs), and saved-data structures. This is a follow-up
to inspect_unlocks.py, not an item or currency patch.

From the repo root:
  py tools/inspect_inventory_details.py > local-analysis/inventory-details.txt

No compiled commercial files, cloud saves or in-game balances are modified.
"""
import argparse
import re
from pathlib import Path

EXACT_TYPES = {
    'Data.Save.InventorySave',
    'Data.Managers.BoardManager',
    'CharacterNameEventManager',
    'Info.SellableConsumable',
}
ENUM_NAMES = {
    'UpgradeType', 'BoardId', 'CharacterId', 'CharacterType', 'CharacterName',
    'ItemType', 'ConsumableType', 'InventoryType', 'CurrencyType',
}
OWNER_TOKENS = (
    'charactersave', 'characterdata', 'charactermanager',
    'boardsave', 'boarddata', 'boardmanager', 'unlocks',
    'ownership', 'ownedsave', 'inventorysave',
    'powerupsave', 'upgradesave', 'consumablesave',
    'currency', 'iteminventory', 'boardid', 'characterid',
)
METHOD_ACTIONS = (
    'unlock', 'own', 'grant', 'give', 'set', 'get', 'add',
    'buy', 'purchase', 'save', 'load', 'getamount',
    'increase', 'has', 'equip', 'spend', 'consume',
)
IGNORE_OWNERS = ('System.', 'UnityEngine.', 'Unity.', 'Mono.', 'TMPro.',
                 'Google.', 'Firebase.', 'Kiloo.GameCenter.')
TYPE_DECL = re.compile(r'\b(class|struct|enum|interface)\s+([A-Za-z_][A-Za-z0-9_]*)(?:<[^{}]+>)?')
SAVED_FIELD = re.compile(r'\b(?:enum|const)\b|(?:=|;|{ get)', re.IGNORECASE)


def parse_dump(path):
    namespace = ''
    records = []
    current = None
    with path.open('r', encoding='utf-8-sig', errors='replace') as handle:
        for line in handle:
            stripped = line.strip()
            if stripped.startswith('// Namespace: '):
                namespace = stripped[len('// Namespace: '):]
                continue
            if '// TypeDefIndex:' in stripped:
                match = TYPE_DECL.search(stripped)
                if match:
                    typename = match.group(2)
                    fq = namespace + '.' + typename if namespace else typename
                    current = {'name': fq, 'kind': match.group(1),
                               'declaration': stripped, 'lines': []}
                    records.append(current)
                else:
                    current = None
                continue
            if current is not None:
                current['lines'].append(stripped)
    return records


def is_relevant(record):
    fq = record['name']
    short = fq.rsplit('.', 1)[-1].lower()
    if fq.startswith(IGNORE_OWNERS):
        return False
    if fq in EXACT_TYPES or short in (enum.lower() for enum in ENUM_NAMES):
        return True
    if any(token in short for token in OWNER_TOKENS):
        return True
    if ('save' in fq.lower() and any(word in short for word in
                                    ('character', 'board', 'inventory',
                                     'upgrade', 'key', 'coin', 'item'))):
        return True
    return False


def priority(rec):
    short = rec['name'].rsplit('.', 1)[-1].lower()
    if rec['name'] in EXACT_TYPES:
        return -100
    if short in (enum.lower() for enum in ENUM_NAMES):
        return -90
    score = 0
    if 'save' in rec['name'].lower():
        score -= 20
    if 'data' in short:
        score -= 12
    if 'manager' in short:
        score -= 8
    if 'unlock' in short or 'own' in short:
        score -= 25
    if 'popup' in short or 'ui' in short or 'screen' in short:
        score += 40
    return score


def show_record(record, max_methods, max_fields, full=False):
    print('\n' + '=' * 78)
    print(record['name'] + '  [' + record['kind'] + ']')
    print(record['declaration'][:190])
    section = ''
    fields = []
    methods = []
    for line in record['lines']:
        if line in ('// Fields', '// Properties', '// Methods'):
            section = line
            continue
        if not line or line.startswith('//'):
            continue
        if section in ('// Fields', '// Properties'):
            if (full or record['kind'] == 'enum' or
                any(token in line.lower() for token in
                    ('key', 'coin', 'board', 'headstart', 'boost',
                     'consumable', 'character', 'unlock', 'owned',
                     'upgrade', 'currency', 'amount', 'inventory', 'save',
                     'item', 'reward', 'skin'))):
                fields.append(line)
        elif section == '// Methods':
            if '(' in line and (full or any(a in line.lower().split('(')[0]
                                            for a in METHOD_ACTIONS)):
                methods.append(line)

    print('Fields/properties (' + str(len(fields)) + ' matches):')
    for line in fields[:max_fields]:
        print('  ' + line[:210])
    if len(fields) > max_fields:
        print('  ... ' + str(len(fields) - max_fields) + ' additional fields omitted')
    print('Method declarations (' + str(len(methods)) + ' matches):')
    for line in methods[:max_methods]:
        print('  ' + line[:250])
    if len(methods) > max_methods:
        print('  ... ' + str(len(methods) - max_methods) + ' additional methods omitted')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dump', type=Path,
                        default=Path('local-analysis/dump/dump.cs'))
    parser.add_argument('--max-types', type=int, default=32,
                        help='Number of non-core matching types to print')
    parser.add_argument('--max-methods', type=int, default=25)
    parser.add_argument('--max-fields', type=int, default=48)
    args = parser.parse_args()
    if not 1 <= args.max_types <= 150 or not 1 <= args.max_methods <= 150:
        parser.error('max-types and max-methods must be 1..150')
    print('IL2CPP OWNERSHIP / CURRENCY PARAMETER REPORT — READ ONLY')
    print('Metadata declares names and signatures only, not actual behavior.')
    entries = [rec for rec in parse_dump(args.dump) if is_relevant(rec)]
    entries.sort(key=lambda rec: (priority(rec), rec['name']))
    important = [rec for rec in entries if priority(rec) <= -90]
    supplementary = [rec for rec in entries if priority(rec) > -90][:args.max_types]
    print('Total candidate types:', len(entries))
    print('Showing', len(important), 'core types and',
          len(supplementary), 'additional ownership/save types')
    for rec in important + supplementary:
        show_record(rec, args.max_methods, args.max_fields,
                    full=rec['name'] in EXACT_TYPES or
                    rec['kind'] == 'enum')
    print('\nNo inventory or character unlock changes were made.')
    print('These names must be cross-checked against actual game behavior.')


if __name__ == '__main__':
    main()
