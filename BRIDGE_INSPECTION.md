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
