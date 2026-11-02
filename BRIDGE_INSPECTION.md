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

## Confirmed Game singleton accessor; clean private no-coin test

The user-provided IL2CPP metadata shows:

- \`SYBO.Subway.Game\` contains \`private static Game instance\`
- \`SYBO.Subway.Game$$get_Instance\` returns a \`Game*\` (\`ii\` WASM signature)
- \`SYBO.Subway.Game$$Die\` accepts \`Game*\` plus method metadata (\`vii\`)
- The \`Coin.Pickup\` method was confirmed to execute on player coin pickup
  using the crash diagnostic.

The new \`tools/try_nocoin_gameover.py\` generates an **isolated** game
page that replaces \`Coin.Pickup\` with these calls:

\`\`\`text
Game* game = Game.get_Instance(null);
Game.Die(game, null);
\`\`\`

These are conceptual pseudocode; the script actually emits WebAssembly
\`call\` instructions and verifies method names and signatures from the
existing \`script.json\`. Unlike the first experiment, this calls
\`Die\` with an actual Game instance instead of relying on the
\`Game.CoinManager_OnCoinCollected\` event handler.

### Test procedure

From the repository root on the experiment branch:

\`\`\`powershell
git pull
py -m unittest discover -s tools -p "test_*.py"
py tools/try_nocoin_gameover.py
py tools/try_nocoin_gameover.py --write
py -m http.server 8000
\`\`\`

Open **http://localhost:8000/nocoin-gameover.html?inspect=1** in a new
private/incognito window. Start a run and collect a coin. The desired
result is the game's normal death/game-over flow rather than a WASM
\`unreachable\` error. If it freezes or continues normally, use browser
DevTools Console to capture the error and report what happened.

The unique test page, config and WASM asset are ignored by git. The
original \`index.html\`, original Unity JSON and original compiled asset
are untouched. The code was unit-tested on synthetic data, **not**
validated during a live run of this commercial game.

The commercial build's redistribution rights have not been established.
Do not publish or upload any modified game files to a public website
without appropriate authorization.

## WASD controls (normal and No-Coin pages)

\`tools/wasd-controls.js\` has been loaded from \`index.html\`, which is
also the template for \`nocoin-gameover.html\`. It converts WASD to
synthetic arrow-key keyboard events with the values expected by Unity's
Emscripten keyboard callback.

| WASD | Existing action |
| --- | --- |
| W | Up arrow / jump |
| A | Left arrow / move left |
| S | Down arrow / roll |
| D | Right arrow / move right |

The original arrow keys still work. Input remapping is ignored while
typing in text fields or while Ctrl/Alt/Meta shortcuts are active. When
the window loses focus, held translated arrows are released.

Update the experiment branch and **regenerate your existing working
No-Coin game test page** so that it includes the new script:

\`\`\`powershell
git pull
py tools/try_nocoin_gameover.py --write
py -m http.server 8000
\`\`\`

Then open \`http://localhost:8000/nocoin-gameover.html?inspect=1\`
in a fresh browser window and test W, A, S, and D. The code is
also loaded by the original \`index.html\`.

The JS mapping was verified with a local mocked-keyboard test. If Node
is installed, you can run the same test:

\`\`\`powershell
node tools/test_wasd_controls.cjs
\`\`\`

The synthetic keyboard events have not been verified in the live browser
on this specific Unity build; confirm their behavior locally. This
addition modifies only HTML/JavaScript, not the previously tested
coin-triggered \`Game.Die\` WebAssembly patch. Keep generated commercial
game files private.

## Run timer: starts on run, freezes at death or coin-triggered game-over

\`tools/run-timer.js\` adds a visible, non-clickable stopwatch at the top
center of both the normal game page and the regenerated No-Coin page.

It listens for the Unity build's **existing** Poki SDK run lifecycle
calls (confirmed by previous bridge logs):

- \`PokiSDK.gameplayStart\` or \`PokiSDK.roundStart('run')\`: start at zero
- \`PokiSDK.gameplayStop\` or \`PokiSDK.roundEnd('run')\`: stop and freeze
- the next run-start resets the clock to \`00:00.00\`
- duplicate start and stop events do not reset or double-stop a run

The display reads \`NO-COIN TIMER\` while waiting, \`RUN TIME\` during
play, and \`FINAL TIME\` after game-over. It shows minutes, seconds and
hundredths (\`MM:SS.hh\`). It uses \`performance.now()\` and
\`requestAnimationFrame\` for smooth monotonic elapsed time.

This is a browser overlay, **not** a change to the WebAssembly coin
patch. The existing, locally tested coin -> \`Game.Die\` behavior stays
unchanged. In the actual browser the clock stops on the game's own
reported run-end event, so there may be a delay if Unity signals
\`gameplayStop\`/ \`roundEnd\` after a death animation rather than at
the first collision frame.

The diagnostic bridge inspector now subscribes to the timer's
\`runner-sdk-lifecycle\` event instead of wrapping these four SDK methods
separately; that avoids recursive wrapper stacking when \`?inspect=1\`.

**Update and regenerate the No-Coin game page**, which is produced from
the repository's \`index.html\`:

\`\`\`powershell
git switch experiment/webgl-bridge-inspector
git pull
py tools/try_nocoin_gameover.py --write
py -m http.server 8000
\`\`\`

Open **http://localhost:8000/nocoin-gameover.html?inspect=1** in a
fresh private/incognito window, start a run, and collect a coin or
naturally die to verify the final elapsed time freezes.

Standalone synthetic JavaScript lifecycle test (when Node.js is
installed):

\`\`\`powershell
node tools/test_run_timer.cjs
\`\`\`

The mocked runtime tests have been checked; **the overlay still needs
a user-side test in the live Unity game** to confirm the precise timing
of its SDK game-over event.

## Fullscreen landing page, personal-best time and scrollable sections

The root \`index.html\` is now a simple extensible challenge website:

- **Full-viewport game** at the top (\`#challenge-stage\`) with a native
  browser Fullscreen button.
- **Scrollable personal-records section** (\`#records\`) immediately
  underneath, including best time, last completed time, run count and
  recent run history.
- \`#future-features\` / \`#challenge-modules\` placeholders for
  future modules; placeholders are visibly labeled as future work.
- The diagnostics overlay is gone: the HTML no longer loads
  \`tools/bridge-inspector.js\`. The diagnostic source remains in
  \`tools/\` for isolated future investigations, but there is no log on
  the game page, even if \`?inspect=1\` is present.

The commercial Unity loader hardcodes \`html, body {overflow:hidden}\`
and absolutely positions its \`#game-container\` using viewport-sized
negative margins. \`tools/challenge-site.css\` overrides this, and
\`tools/challenge-site.js\` moves the injected Unity loader and game
nodes into \`#challenge-game\` via \`MutationObserver\`. The actual
Unity binary remains the same as the previously working No-Coin test.

The timer publishes \`runner-timer-state\` on run start/finish.
\`tools/challenge-site.js\` saves completed **survival time** to the
browser's \`localStorage\` under \`no-coin-challenge.records.v1\`.
This is **not the original game's distance/points score**.
Only \`data-run-mode="no-coin"\` pages contribute to the record.
The generator now applies that marker **only** to
\`nocoin-gameover.html\`; unmodified \`index.html\` gameplay does not
add misleading times to the challenge scoreboard.

Personal records are local to a browser/profile/origin, can be cleared
alongside site data, and do not synchronize across devices. Private
windows can erase their local storage on exit. Only runs completed
since this addition can be recorded; old times were never saved.

From the experiment branch:

\`\`\`powershell
git pull
py tools/try_nocoin_gameover.py --write
py -m http.server 8000
\`\`\`

Open **http://localhost:8000/nocoin-gameover.html**, play to game over,
then scroll or select "YOUR BEST SCORE" to see your statistics.

Optional automated JavaScript checks with Node.js:

\`\`\`powershell
node tools/test_challenge_site.cjs
node tools/test_run_timer.cjs
node tools/test_wasd_controls.cjs
\`\`\`

The challenge-site JavaScript and run-timer integration were also
checked together using synthetic browser events. The visual
Unity-loader reparenting and native fullscreen layout still require
a browser test with the user's local game build.

The generated alternative game assets remain ignored by Git. Do not
commit or publicly deploy them without redistribution rights.

## Fullscreen clean view (hide branding, records prompt, exit control on hover)

The Unity game section's native browser fullscreen mode now hides the
\`NO-COIN CHALLENGE\` page branding and the \`YOUR BEST SCORE\` arrow/link.
It also removes the header gradient. The game and stopwatch remain visible.

The \`Exit fullscreen\` button remains in the top-right corner as an
invisible hit target and appears only when you hover over that button,
or focus it with keyboard navigation. The browser's \`Esc\` key also
exits fullscreen. This uses CSS fullscreen selectors and **does not**
modify the game's rendering or WASD controls.

Test the CSS contract (Node.js optional):

\`\`\`powershell
node tools/test_fullscreen_ui.cjs
\`\`\`

## Unlockables and inventory investigation (not yet patched)

The user also requested all character skins unlocked and **1,000,000,000**
of the game's boards/hoverboards, score boosters, headstarts, and blue
keys. These are stored in game-specific IL2CPP data, not in the
challenge website's local best-time storage. Browser overlay changes
alone cannot alter genuine Unity ownership/item counts.

The local read-only \`tools/inspect_unlocks.py\` script searches the
Il2CppDumper \`script.json\` and \`dump.cs\` for relevant ownership,
consumable and currency methods and fields:

\`\`\`powershell
git pull
py tools/inspect_unlocks.py --category skins --category boards --category boosters --category headstarts
py tools/inspect_unlocks.py --category currency --category storage
\`\`\`

These commands list candidate method names/signatures and field
details. **They do not unlock or add anything yet.** Examining that
output is necessary to avoid inventing ownership methods or damaging
local save data. Any future patch should apply only to the user's
private local build, with a save backup and no deployment of
unauthorized commercial assets.

## 2026-11-02 inventory report findings and targeted next checks

The user's uploaded text report from \`inspect_unlocks.py\` confirms these
**metadata declarations** (not yet validated runtime behavior):

- \`Data.Save.InventorySave\`: \`SetKeys\` (\`vii\`), \`IncreaseAmount\`
  (\`viii\`), \`GetAmount\` (\`iii\`), \`keys { get; set; }\`.
- \`Data.Managers.BoardManager\`: \`IsBoardOwned\`, \`IsBoardUnlocked\`
  (\`iii\` each). These are board ownership checks, not consumable
  hoverboard quantities.
- \`Info.SellableConsumable\`: \`headstart\`, \`scorebooster\`,
  \`hoverboard\` static descriptors.
- None of those class/method names alone identifies the
  \`UpgradeType\` enum numeric values, item quantity arguments, or
  **character unlock/save** method. Guessing would risk changing
  unrelated player progress.

The targeted read-only inspector prints **full C# declarations**,
particularly parameter types and enum numeric values:

\`\`\`powershell
git pull
py -m unittest discover -s tools -p "test_inventory_details.py"
py tools/inspect_inventory_details.py > local-analysis/inventory-details.txt
\`\`\`

The generic WASM method inspector now accepts repeatable \`--name\`
arguments, for signature/table verification of relevant methods
(the output is also read-only):

\`\`\`powershell
py tools/show_resolved_wasm_bodies.py local-analysis/game.wasm local-analysis/dump/script.json --max-bytes 48 --name 'Data.Save.InventorySave$$SetKeys' --name 'Data.Save.InventorySave$$IncreaseAmount' --name 'Data.Save.InventorySave$$GetAmount' --name 'Data.Managers.BoardManager$$IsBoardOwned' > local-analysis/inventory-wasm.txt
\`\`\`

**PowerShell note:** Keep the single quotes around arguments containing
\`$$\` to prevent PowerShell from expanding them.

Inspect the two output text files before implementing local item
grants. Save backups, confirm the game uses local rather than
cloud-authoritative ownership, and do not commit modified commercial
game binaries or publish them without authorization.

## Experimental private local inventory-grant No-Coin build

The uploaded detailed IL2CPP report shows these exact declarations:

- \`InventorySave.SetKeys(int newAmount)\` and \`InventorySave.get_keys()\`
- \`InventorySave.GetAmount(UpgradeType)\` and \`IncreaseAmount(UpgradeType, int)\`
- \`CharacterManager.UnlockCharacter(Characters.CharacterId)\` and
  \`IsCharacterOwned(Characters.CharacterId)\`
- \`BoardManager.UnlockBoard(Boards.BoardId)\` and
  \`IsBoardOwned(Boards.BoardId)\`
- \`UpgradeType.hoverboard = 1\`
- \`UpgradeType.headstart2000 = 3\`
- \`UpgradeType.scorebooster = 15\`

\`tools/try_nocoin_unlocks.py\` is an independent, reversible **local-only
test generator**. It verifies method signatures and the enums in the
local dump before generating any build. The generated
\`nocoin-unlocks.html\` keeps the previously verified
\`Coin.Pickup -> Game.Die(Game.Instance)\` behavior.

The test prepends a grant routine to \`SYBO.Subway.Game.StartNewGame\`,
which should execute when a new run begins **after** loading the save.
This assumption and the inventory effects are **not yet tested in the
real game**. No item grants occur merely from opening the page if that
method has not yet executed.

The routine checks the existing balance/ownership before changing it:

- keys: raise to 1,000,000,000 using \`SetKeys\` only if below the target
- consumable hoverboards, headstarts and score boosters: use
  \`GetAmount\` and \`IncreaseAmount(type, target-current)\` if
  \`0 <= current < 1,000,000,000\`, to avoid overflowing on repeated runs
- characters and boards: if not owned, use \`UnlockCharacter(id)\` or
  \`UnlockBoard(id)\` for IDs parsed from \`dump.cs\` enum constants
- **alternate outfits not yet unlocked** because the source report does
  not establish valid outfit indices per character

For the first test, use an **isolated private/incognito browser
session** to avoid altering any important existing local game save.
Even though the generated WASM stays local, the game's save may
persist changes within the current browser profile.

\`\`\`powershell
git switch experiment/webgl-bridge-inspector
git pull
py -m unittest discover -s tools -p "test_nocoin_unlocks.py"
py tools/try_nocoin_unlocks.py --items-only
py tools/try_nocoin_unlocks.py --items-only --write
py -m http.server 8000
\`\`\`

Then open **http://localhost:8000/nocoin-unlocks.html** and start a run
to trigger the grant routine. Check in-game keys and consumable amounts.

If the initial items-only version works, stop the server, run
\`py tools/try_nocoin_unlocks.py --max-characters 5 --max-boards 5 --write\`
as a small character/board test, and then
\`py tools/try_nocoin_unlocks.py --write\` for all enum IDs. Restart
the local server or refresh the page after each change.

The old known-working \`nocoin-gameover.html\` is unaffected, and the
original Unity assets are never overwritten. The generated test
WASM files are ignored by Git. All of the above is experimental,
and must not be publicly deployed without the commercial game's
distribution rights.

## Full character/board unlock page + clean header

The user confirmed that the \`--items-only\` build successfully gave
1,000,000,000 keys, consumable hoverboards, headstarts, and score
boosters. This did **not** unlock characters or board models because
\`--items-only\` deliberately omitted the corresponding game methods.

Generate the **full** version by leaving off \`--items-only\`:

\`\`\`powershell
git switch experiment/webgl-bridge-inspector
git pull
py -m unittest discover -s tools -p "test_nocoin_unlocks.py"
py tools/try_nocoin_unlocks.py
py tools/try_nocoin_unlocks.py --write
py -m http.server 8000
\`\`\`

Open **http://localhost:8000/nocoin-unlocks-full.html** in a fresh
private/incognito tab. This is a separate URL from the proven items-only
\`nocoin-unlocks.html\` page, so it cannot accidentally load that old
page's cached HTML/configuration.

Start one run so \`Game.StartNewGame\` executes. Return to the menu,
open the character and board selection screens, and check the new
ownership. The full build calls these existing game methods on all
nonnegative enumerated CharacterId/BoardId values, guarded by checks:

- \`CharacterManager.IsCharacterOwned\` → \`UnlockCharacter\`
- \`BoardManager.IsBoardOwned\` → \`UnlockBoard\`

This remains **an untested modification to the live collection
screens**; it is not proof that every content ID has usable assets.
For a smaller first test, use
\`py tools/try_nocoin_unlocks.py --max-characters 5 --max-boards 5 --write\`
and open the same full-unlock URL. Regenerate without limits if that
works.

The alternate outfits of each base character are not yet covered; the
valid outfit indices for each character remain unknown. Do not guess
outfit indices or modify existing cloud-linked saves without a backup.

In the website UI, the No-Coin logo/branding (symbol plus text) is
**removed from index.html entirely**, so it does not appear in regular
or fullscreen gameplay. The fullscreen button stays in the top-right
corner, and its exit appearance remains hover/focus-only in fullscreen.
The run timer, WASD controls and scrollable records remain.

## Blank global namespace fix for character/board enum lookup

The first full-unlock dry run successfully verified all 12 relevant
WASM method targets and printed the matching C# method declarations,
but failed before writing an asset:

\`\`\`text
RuntimeError: Expected one IL2CPP type Characters.CharacterId; found 0
\`\`\`

The cause was a bug in \`find_records\`: it called \`strip()\` on each
\`dump.cs\` line, but recognized namespace comments only if the resulting
string began \`// Namespace: \` (with a trailing space). An empty/global
namespace entry thus became \`// Namespace:\`, which was not recognized.
This caused a type like \`Characters.CharacterId\` to inherit the last
nonempty namespace.

The parser now recognizes \`// Namespace:\` whether or not text follows
the colon and resets to \`""\` for global types. Regression tests cover
both \`Characters.CharacterId\` and \`Boards.BoardId\` under blank
namespace markers, following a nonempty namespace.

Retry from the experiment branch, with a read-only dry run **first**:

\`\`\`powershell
git pull
py -m unittest discover -s tools -p "test_nocoin_unlocks.py"
py tools/try_nocoin_unlocks.py
\`\`\`

After a successful dry run, \`py tools/try_nocoin_unlocks.py --write\`
creates the separate \`nocoin-unlocks-full.html\` local test page.
This remains experimental: game ownership and visual unlock UI need
to be confirmed in an isolated profile. No assets were produced by
the failed dry run.

## Optional coin rule and hoverboard-invalidated timers (private local build)

The user requested a scroll-down switch between:

1. **Coin = game over** (the previously confirmed normal \`Game.Die\`
   patch).
2. **Coin = timer stops only** (the original \`Coin.Pickup\` method runs,
   so collecting the coin should not cause a forced game-over, but
   the browser stops the stopwatch immediately).

A new **CHALLENGE SETTINGS** section below the game links the two
locally-generated pages and reloads the WebGL build when changed:

- **http://localhost:8000/nocoin-unlocks-full.html** — normal
  coin-death challenge with working full inventory unlocks.
- **http://localhost:8000/nocoin-unlocks-timer.html** — new
  coin-stops-timer-only experiment with the same inventory unlocks.
- With \`--items-only\`, the pair is
  \`nocoin-unlocks.html\` and \`nocoin-unlocks-items-timer.html\`.

Both pages share the same browser-local personal best and run history.
The timer freezes on the first coin/hoverboard signal; another event or
subsequent in-game death cannot change that recorded time. A new run
resets it. After freezing, **Unity gameplay continues** in the
timer-only coin mode.

### How the event bridge works

\`tools/challenge_wasm_bridge.py\` resolves the pre-existing Unity
Emscripten import \`env._JS_Eval_EvalJS(i32)\`, verifies its type, and
emits a reserved marker on coin pickup. The original import handler in
\`4399.z.js\` is intentionally blank. Only a **generated ignored copy**
(\`4399.challenge.<hash>.js\`) receives a handler that dispatches a
\`runner-game-event\` for either coin or hoverboard marker values.

The timer's \`tools/run-timer.js\` listens for that browser event, emits
\`runner-timer-state\` at the exact frozen time, and the existing
personal-best recorder saves it. This bridge requires no hard-coded
WASM memory address and does not touch tracked commercial binaries.

The hoverboard stop is implemented best-effort via a **verified**
method from this build:

- Prefer exactly one named \`ActivateHoverboard\`/\`UseHoverboard\`
  style \`void\` method in \`script.json\`.
- Otherwise, watch
  \`InventorySave.DecreaseAmount(UpgradeType.hoverboard=1, amount)\`
  if present with the expected signature.
- Otherwise, watch
  \`InventorySave.IncreaseAmount(UpgradeType.hoverboard=1, delta<0)\`,
  which some games use to consume a board.

This avoids the unreliable alternative of stopping on any Space
keypress. The hoverboard hook is installed in **both** coin modes.
Because the exact activation/consumption behavior is not yet verified
in the real game, **a real browser test is required**. If the timer
does not stop on board use, inspect the candidate method names printed
during the dry run.

### Update/test

\`\`\`powershell
git switch experiment/webgl-bridge-inspector
git pull
py -m unittest discover -s tools -p "test_challenge_wasm_bridge.py"
py -m unittest discover -s tools -p "test_nocoin_unlocks.py"
py tools/try_nocoin_unlocks.py
py tools/try_nocoin_unlocks.py --write
py -m http.server 8000
\`\`\`

Open the full-unlock page above, scroll down to **Challenge settings**,
then select **Coin = stop timer only**. This switches to the
independent timer-only page. Start a run, collect a coin, and confirm
the runner continues while the clock and saved time freeze. Try
activating a hoverboard during another run and confirm the same
stopwatch behavior.

If the build generator cannot resolve the JS import or the hook's
signature, it will stop before writing new assets, preserving the
previous locally generated working versions. Share the terminal
error if that happens.

Do not commit or publicly redistribute generated commercial assets.


## Hoverboard stop fix and optional Blitz speed (experiment)

The negative InventorySave.IncreaseAmount inventory hook did not fire
when the user activated a hoverboard. The website now loads a fallback
in tools/hoverboard-input.js: during an active timed No-Coin run, Space
or double-click/double-tap on the game invokes the hoverboard timer-stop
event. The runner keeps going and the final time is saved. This
detects an activation attempt rather than verifying that Unity accepted
it: pressing Space during a cooldown can stop the timer. We need the
real hoverboard activation method for perfect accuracy; inspect
tools/inspect_run_mechanics.py for candidate method names.

The --blitz option adds two experimental game variants, both using
the same billion-item inventory and character/board unlocks. It
injects UnityEngine.Time.set_timeScale(2.25f) at Game.StartNewGame
to make the game initially play much faster. The generator verifies
the real WASM function signature before generating Blitz pages; if
the stripped build lacks the method, no Blitz output is written.

After updating the experiment branch, use these commands:

    git pull
    py -m unittest discover -s tools -p "test_nocoin_unlocks.py"
    py -m unittest discover -s tools -p "test_challenge_wasm_bridge.py"
    node tools/test_hoverboard_input.cjs
    py tools/try_nocoin_unlocks.py --blitz
    py tools/try_nocoin_unlocks.py --blitz --write
    py -m http.server 8000

If native timeScale is verified, the pages generated are:
- nocoin-unlocks-full.html (normal speed, coin = death)
- nocoin-unlocks-timer.html (normal speed, coin = timer only)
- nocoin-blitz.html (2.25x Unity timeScale, coin = death)
- nocoin-blitz-timer.html (2.25x Unity timeScale, coin = timer only)

The scroll-down Challenge Settings controls select these two
independent options while retaining the other option.

If --blitz fails to find UnityEngine.Time.set_timeScale, run:

    py tools/inspect_run_mechanics.py > local-analysis/run-mechanics.txt

The report is read-only; supply its relevant candidate lines to
investigate a game-specific speed and hoverboard activation hook.

Both the effect of Unity timeScale and the input fallback need live
browser verification. No generated commercial assets are committed
or meant for public redistribution.

Blitz personal bests are saved separately in browser localStorage under
no-coin-challenge.records.blitz.v1. The original normal-speed personal
best stays under no-coin-challenge.records.v1, untouched.
