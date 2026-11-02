#!/usr/bin/env python3
"""Inspect local IL2CPP for *real* hoverboard activation and speed hooks.

    py tools/inspect_run_mechanics.py
    py tools/inspect_run_mechanics.py --max 60

Read-only: no changes to WASM, Unity save or player inventory. Print this
report if automatic hook discovery cannot confirm an activation/speed method.
"""
import argparse
import json
from pathlib import Path

SCRIPT = Path("local-analysis/dump/script.json")

def candidates(methods, target):
    results = []
    for m in methods:
        name = m.get("Name", "")
        if "$$" not in name:
            continue
        owner, action = name.split("$$", 1)
        owner_l, action_l = owner.lower(), action.lower()
        if target == "hoverboard":
            if not any(x in owner_l + "." + action_l for x in ("hoverboard", "boardactive", "boardactivation", "onboard")):
                continue
            score = 0
            if any(x in action_l for x in ("activate", "activated", "start", "startuse", "enable", "spawn", "begin", "equip", "trigger")): score += 30
            if any(x in action_l for x in ("update", "lateupdate", "move", "get_", "set_", "refresh", "is", "check")): score -= 20
            if "hoverboard" in owner_l: score += 8
            if any(x in owner_l for x in ("game", "player", "character", "runner")): score += 5
            if m.get("TypeSignature", "").startswith("v"): score += 10
        else:
            if not any(x in owner_l + "." + action_l for x in ("speed", "timescale", "velocity", "accelerat", "gameplaytime")):
                continue
            score = 0
            if action_l in ("set_timescale", "set_timeScale".lower()): score += 60
            if any(x in action_l for x in ("set_", "increase", "boost", "start", "set")): score += 20
            if "speed" in action_l: score += 15
            if "time" in owner_l: score += 6
            if any(x in action_l for x in ("get_", "maxspeed", "getmax")): score -= 10
            if m.get("TypeSignature", "") in ("vfi", "vfii"): score += 10
        if score > 0: results.append((score, name, m.get("TypeSignature","?")))
    return sorted(results, key=lambda row: (-row[0], row[1]))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--script",type=Path,default=SCRIPT)
    p.add_argument("--max",type=int,default=45)
    args=p.parse_args()
    if not 1 <= args.max <= 300: p.error("--max must be 1..300")
    methods=json.loads(args.script.read_text(encoding="utf-8-sig")).get("ScriptMethod",[])
    for category in ("hoverboard", "speed"):
        found=candidates(methods,category)
        print("\n=== "+category.upper()+" METHOD CANDIDATES (score/name/signature) ===")
        for score,name,sig in found[:args.max]:
            print(f"{score:>3} {name} | {sig}")
        print(f"Found {len(found)} candidates, showing {min(len(found),args.max)}")
    print("\nThis report is READ-ONLY. Names do not prove a method is called on activation.")
if __name__=="__main__":
    main()
