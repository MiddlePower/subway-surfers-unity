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
