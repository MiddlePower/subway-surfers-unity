# Unity WebGL inspection experiment

This is an **experimental, read-only browser bridge probe** for a WebGL
build that does not include its original Unity editor project or C# code.

It does **not** implement a no-coin challenge, patch WebAssembly, change
compiled gameplay, or bypass any access control.

## Run locally

Serve the repository from a local HTTP server (do not open index.html with
file://). For example, with Python installed:

```sh
python -m http.server 8000
```

Then open `http://localhost:8000/?inspect=1`.

A small panel displays whether `window.unityGame` and its standard
`SendMessage` method are present. It also lists browser-visible calls to
selected Poki SDK methods.

To investigate: start a new run, copy the log before collecting a coin,
collect **one coin**, and copy the log afterward. Compare which events, if
any, appear at that moment. The inspector reports **SDK calls only**;
there is no reason to assume the coin counter is exposed through them.
If there is no coin-specific event, this approach alone cannot enforce
the challenge.

Remove `?inspect=1` to disable the probe entirely. Events are logged
locally in memory and may be copied from the panel. No new requests are
sent by the inspector.

## Confirmed build facts

- `index.html` boots a Unity 2019.4.18f1 WebGL game.
- `unity.js` creates `window.unityGame` via
  `UnityLoader.instantiate(...)`.
- The Unity loader exposes `window.unityGame.SendMessage`. This can
  call **existing** methods on **existing** Unity GameObjects, but it does
  not reveal their names or automatically expose coins.
- `Build/SanFrancisco/SanFrancisco.json` identifies the product as
  **Subway Surfers** by **Kiloo Games**.
- The build contains compiled `.wasm.code.unityweb` and
  `.data.unityweb` files, but no editable C# source.

## Possible next investigations

1. Check whether the bridge emits coin-specific events during gameplay.
2. If there are no suitable events, examine the compiled Unity data and
   metadata *where permitted* to determine whether the coin pickup code
   can be identified. This can be much harder than editing a Unity source
   project and has not been demonstrated here.
3. If a callable in-game method exists, prototype a locally enforced
   fail-state after coin pickup. Otherwise, use an original source-code
   project for the challenge.

## Rights

This fork contains a built version of a commercial game with **no
permission grant located in the repository**. Owning or forking the GitHub
repository does not grant rights to modify or publicly redistribute the
underlying game. Do not publish or host the compiled assets without the
appropriate authorization.

## After the initial bridge experiment: inspect the data archive

The original Poki SDK test did **not** show per-coin events. The next
read-only experiment examines the Unity WebGL asset archive itself.

On Windows, from the checked-out experiment branch, run:

```powershell
py -m pip install brotli
py tools/inspect_unityweb.py Build/SanFrancisco/SanFrancisco.data.unityweb
```

This prints the files contained in the decompressed WebGL data archive,
marks likely metadata files, and counts occurrences of terms such as
`Coin` and `Collect`. No Unity assets are changed or extracted. To
save the output to a small text file:

```powershell
py tools/inspect_unityweb.py Build/SanFrancisco/SanFrancisco.data.unityweb > inspection-report.txt
```

**Send back the text output**, not the compiled game files. The report
helps determine whether the next feasible step is metadata analysis
or whether the only editable options are outside the game.

**Important:** Metadata inspection is not the same as modifying the
compiled WebAssembly. We have not found or patched the coin handler yet.

## IL2CPP class/method name scan

The archive listing confirmed that `global-metadata.dat` exists and has
coin-related strings. To distinguish actual **class and method names** from
arbitrary text matches, run:

```powershell
git pull
py tools/inspect_coin_symbols.py Build/SanFrancisco/SanFrancisco.data.unityweb --limit 100
```

The scanner reads the already confirmed metadata archive and tries to list
qualified class names with coin/pickup/collection/scoring methods. It also
prints matching strings if the metadata records do not match the expected
Unity 2019 IL2CPP version-24 structure. It **does not patch** the game.

Copy the printed text output into the conversation to evaluate which
candidate names are relevant. Do not upload commercial game binaries.

## Confirmed game-specific symbols

The IL2CPP symbol output provided from the locally extracted metadata
identified these likely coin-related handlers:

- `SYBO.Subway.Coins.Coin.Pickup`
- `SYBO.Subway.Coins.CoinManager.PickupCoin`
- `SYBO.Subway.Coins.CoinManager.RaiseOnCoinCollected`
- `SYBO.Subway.Game.CoinManager_OnCoinCollected`
- `GameStats.add_OnCoinsIncreased`

These are **names from metadata**. They are not JavaScript events,
callable browser APIs, or recovered C# implementations.

### Next: correlate with compiled WebAssembly

The metadata alone cannot locate or change the executable handler. A
compatible IL2CPP utility needs both metadata and the compiled WebAssembly
module. To prepare them **locally** without modifying the original files:

```powershell
git pull
py -m pip install brotli
py tools/prepare_il2cpp_analysis.py
```

This creates:

- `local-analysis/global-metadata.dat`
- `local-analysis/game.wasm`

The output directory is ignored by git. Do not upload or commit these
extracted commercial game files. The script does not patch game behavior.

A possible next analysis tool is
[Perfare/Il2CppDumper](https://github.com/Perfare/Il2CppDumper),
which documents WebAssembly and metadata support. Its success on this
specific build is not verified. If it supports the build, the command-line
form is:

```powershell
Il2CppDumper.exe local-analysis/game.wasm local-analysis/global-metadata.dat local-analysis/dump
```

Then inspect the generated `dump.cs` for
`CoinManager_OnCoinCollected` and `RaiseOnCoinCollected`.

Please share **a short text excerpt of the method signatures / addresses
or an error message**, not the game's binaries. Even with a successful
dump, identifying and altering a method in Unity WebGL can require
additional analysis, and permission is needed to publish a modified
commercial build.

## Follow-up: confirm method signatures after a successful Il2CppDumper run

The local `dump.cs` showed:

- `SYBO.Subway.Game.CoinManager_OnCoinCollected(object, EventArgs)`, shown with `RVA 0x2D0`
- `SYBO.Subway.Coins.CoinManager.RaiseOnCoinCollected()`, shown with `RVA 0x1989`

**These RVAs are not reliable raw byte offsets in a WebAssembly module.**
Do not modify `game.wasm` at these offsets.

Il2CppDumper additionally writes a `script.json` with its method
names and type signatures, suitable for later Ghidra correlation. Run:

```powershell
git pull
py tools/find_coin_entrypoints.py local-analysis/dump/script.json
```

This prints the signatures and dumper addresses of likely coin-event and
game-over methods. It performs **no** modifications.

For deeper authorized offline analysis, Il2CppDumper also generates
`ghidra_wasm.py`; its README documents use with
[nneonneo/ghidra-wasm-plugin](https://github.com/nneonneo/ghidra-wasm-plugin).
Import `local-analysis/game.wasm` into a compatible Ghidra/WebAssembly
environment, then inspect named handlers. This analysis has not yet been
completed, so no working game modification is claimed.

## Verify the WASM function-table mapping

The user-provided Il2CppDumper output showed:

- `SYBO.Subway.Game$$CoinManager_OnCoinCollected` at dumper address `0x2D0`, signature `viiii`
- `SYBO.Subway.Coins.CoinManager$$RaiseOnCoinCollected` at `0x1989`, signature `vii`
- `SYBO.Subway.Coins.CoinManager$$PickupCoin` at `0xC48`, signature `viii`
- `SYBO.Subway.Game$$Die` at `0x182E`, signature `vii`

Il2CppDumper's `ghidra_wasm.py` resolves its methods via symbols
such as `func_viiii_720` within the WebAssembly `dynCall` namespace.
The dumper address is **not** a safe raw file offset.

An optional local read-only function table analyzer:

```powershell
git pull
py tools/resolve_wasm_methods.py local-analysis/game.wasm local-analysis/dump/script.json
```

It attempts to correlate the dumper addresses with the WebAssembly
element-section function table, function signatures, and body locations.
It supports the older, simple active element segments typically emitted
by Unity 2019/Emscripten; newer element encodings may require a different
parser. The parser was tested on synthetic WASM but not yet on the
commercial game's build.

**Never patch at a dumper RVA or raw byte offset solely on the basis of
this report.** No binary edit or runtime mod is included.

## Table mapping follow-up: zero initialized slots

A first run of `resolve_wasm_methods.py` showed 72,441 functions,
481 imports and **zero resolved table entries** for the named coin
handlers. That result does not establish that the methods are absent.

The Unity/Emscripten JavaScript bootstrap creates the indirect function
table and sets `env.tableBase = 0`. The earlier analyzer silently
ignored element sections with `global.get` offset expressions, even
when they referenced that imported base.

The updated analyzer interprets the confirmed `env.tableBase` import
and prints counts for total and unresolved element segments plus global
import names, to make remaining unsupported layouts explicit.

```powershell
git pull
py tools/resolve_wasm_methods.py local-analysis/game.wasm local-analysis/dump/script.json
```

If the result remains zero, include the new `Element section present`
and `Imported globals` lines in the output. Do not infer any executable
file offset directly from the Il2CppDumper addresses.

## Corrected mapping: Emscripten dynCall signature groups

The direct table mapping found 125,739 entries, but method signatures
did **not** match. This is expected when Emscripten allocates groups of
function-table slots by call signature and `dynCall_*` wrappers apply an
offset and bitmask. The Ghidra WASM plugin's
[`analyze_dyncalls.py`](https://github.com/nneonneo/ghidra-wasm-plugin/blob/master/ghidra_scripts/analyze_dyncalls.py)
documents this behavior.

The next local read-only command searches WASM exports for the relevant
`dynCall_*` wrappers, derives candidate masks and offsets from their
short `call_indirect` sequences, and checks the actual resolved function
type before reporting any verified method:

```powershell
git pull
py tools/resolve_dyncall_methods.py local-analysis/game.wasm local-analysis/dump/script.json
```

If the wrapper instruction pattern differs from the expected Emscripten
sequence, the tool prints a short diagnostic and recommends Ghidra
instead of inventing a mapping. **Nothing is patched automatically.**

## dynCall parser fix from real 2026-11-02 output

The diagnostic output included a `dynCall_viiii` body ending in
`local.get 0; i32.const mask; i32.and; i32.const base; i32.add; call_indirect`.
The scanner previously stopped at `i32.add` instead of advancing to
`call_indirect`. This is corrected on the experiment branch.

The supplied wrapper bytes decode as:

- `dynCall_viiii`: `mask = 0x1FFF`, `base = 113449`
- `dynCall_vii`: `mask = 0x3FFF`, `base = 80275`
- `dynCall_viii`: `mask = 0x3FFF`, `base = 96918`

These are **table lookup parameters**, not locations to edit in the
commercial game's binary. The fact that the exported `dynCall_viiii`
has the type `viiiii` is expected: the exported wrapper accepts an
extra function-pointer index parameter.

Run the tests on the provided diagnostic bytes and then repeat the
read-only mapping:

```powershell
git pull
py -m unittest discover -s tools -p "test_*.py"
py tools/resolve_dyncall_methods.py local-analysis/game.wasm local-analysis/dump/script.json
```

A `VERIFIED signature match` would confirm a signature-consistent
candidate mapping only; it does **not** confirm the method semantics
or implement coin-triggered game-over.

## Experimental local-only no-coin patch

The provided runtime output successfully identified:

- \`SYBO.Subway.Game$$CoinManager_OnCoinCollected\` -> WASM function \`44591\` (\`viiii\`)
- \`SYBO.Subway.Game$$Die\` -> WASM function \`44566\` (\`vii\`)

The reversible script \`tools/patch_no_coin_local.py\` uses these *verified
mappings* (it recalculates them from \`script.json\`, rather than relying on
fixed indices). It generates a copy of the compiled WebAssembly with the
coin-collected callback replaced by a call to \`Game.Die(this, null)\`.
This is a hypothesis: it might fail in the actual game.

Run from the **experiment branch** on your own machine:

\`\`\`powershell
git pull
py -m unittest discover -s tools -p "test_*.py"
py tools/patch_no_coin_local.py
py tools/patch_no_coin_local.py --write
\`\`\`

The first patcher call is a dry run, and the second creates
\`local-analysis/nocoin/SanFrancisco.wasm.code.unityweb\`.
It does **not** overwrite the original asset.

For a **private local test only**, back up the original file, then replace
your local build's asset:

\`\`\`powershell
Copy-Item Build/SanFrancisco/SanFrancisco.wasm.code.unityweb local-analysis/original.wasm.code.unityweb
Copy-Item local-analysis/nocoin/SanFrancisco.wasm.code.unityweb Build/SanFrancisco/SanFrancisco.wasm.code.unityweb -Force
py -m http.server 8000
\`\`\`

Open \`http://localhost:8000/?inspect=1\` in a fresh private browser window
to avoid cached WebGL files. Start a run and collect exactly one coin.
Check whether gameplay immediately ends, crashes, or behaves normally.

Restore the unmodified source file afterward:

\`\`\`powershell
Copy-Item local-analysis/original.wasm.code.unityweb Build/SanFrancisco/SanFrancisco.wasm.code.unityweb -Force
\`\`\`

If the original file was not backed up, and it was originally unchanged
in your repository, \`git restore -- Build/SanFrancisco/SanFrancisco.wasm.code.unityweb\`
can restore it instead.

**Important:** This is an experimental modification of a commercial build
whose repository does not grant redistribution rights. Do not publish,
commit, share or host the modified assets; a public no-coin website
would require an authorized game build or an independently created,
properly licensed runner.

## If the no-coin game patch appears to have no effect

The earlier experimental patch changed
\`SYBO.Subway.Game$$CoinManager_OnCoinCollected\`. If picking up coins still
works normally, there are at least two possibilities:

- The Unity loader is still using a cached WASM asset.
- The \`Game.CoinManager_OnCoinCollected\` handler is not actually being
  executed in the normal pickup path.

The diagnostic \`tools/probe_coin_hook.py\` distinguishes these cases
without touching the existing \`index.html\`, Unity config, or WASM asset.
It creates a uniquely named \`nocoin-probe.html\` entry point, unique JSON
config, and unique compiled WASM asset. The unique URLs avoid reusing the
previously cached build files.

\`\`\`powershell
git pull
py tools/probe_coin_hook.py --status
py tools/probe_coin_hook.py --hook coin-pickup
py -m http.server 8000
\`\`\`

Open **http://localhost:8000/nocoin-probe.html?inspect=1** in a fresh
private browser session. During gameplay, deliberately pick up one coin.

**Expected diagnostic behavior:** if \`Coin.Pickup\` executes, the
modified WASM intentionally throws an \`unreachable\` error and the
game will probably freeze/stop. This is *only a test*, not a finished
end-of-run implementation.

- If it freezes **only upon coin collection**, the pickup path is
  verified. That would suggest the earlier handler is unused or the
  direct \`Game.Die\` call did not work.
- If it runs normally, press F12 → **Network**, reload the probe page
  (Ctrl+Shift+R), and check whether the requested filename begins with
  \`SanFrancisco.probe.coin-pickup.\`. Check for a 200 response and
  share browser Console errors.
- If the unique WASM loads but the coin still has no effect, try
  \`--hook coin-manager-pickup\` or \`--hook coin-event\` and retest.

The output page and probe assets are ignored by git; do not commit or
redistribute any of these commercial game files. Open normal
\`http://localhost:8000/\` to play without the diagnostic probe page.

## Result: coin pickup trap executed during gameplay

The user confirmed that the \`--hook coin-pickup\` diagnostic
**froze/crashed immediately upon collecting a coin**. This establishes
that \`SYBO.Subway.Coins.Coin.Pickup\` is an active gameplay path in
this build, and that the cache-busted local build loaded the diagnostic.

The previous no-coin experiment patched
\`Game.CoinManager_OnCoinCollected\`, and normal gameplay continued.
That does not prove whether it was unused or whether its attempted
\`Game.Die\` call failed.

To implement a *clean* run-ending action at \`Coin.Pickup\`, the patched
code would need the **live \`SYBO.Subway.Game\` instance**; passing the
\`Coin\` object as the Game instance would be incorrect. Before writing
another game patch, inspect the recovered Game fields, properties and
singleton accessors:

\`\`\`powershell
git pull
py tools/inspect_game_instance.py local-analysis/dump/dump.cs local-analysis/dump/script.json
\`\`\`

Share the text output (not compiled commercial game files). This is a
read-only scanner. Until the Game instance can be reliably obtained and
a clean game-over path tested, the diagnostic trap is **not a playable
No-Coin Challenge**.
