<div align="center">

<h1 align="center">CloseOreUI — iOS IPA Patcher</h1>

<p>Patch a Minecraft Bedrock <code>.ipa</code> so it drops OreUI and falls back to the<br>
classic JSON-UI — by rewriting one function in <code>minecraftpe</code> to <code>return 0</code>.</p>

<p>
<b>English</b> · <a href="./README.zh-CN.md">中文</a>
</p>

</div>

<br/>

> [!IMPORTANT]
> **Your IPA must be re-signed before it will install.**
> This tool outputs an **unsigned / ad-hoc** IPA. iOS will not install it as-is.
> You need your own signing identity via Sideloadly, AltStore, ESign, Feather, or TrollStore.

> [!WARNING]
> **The "inject dylibs" option produces an ad-hoc-signed IPA.**
> Ad-hoc signatures only work on **jailbroken devices** or via **TrollStore**.
> A normal (non-jailbroken, no TrollStore) device cannot install that output.
> If you just want to remove OreUI, leave the checkbox **unchecked**.

## What this does

Minecraft Bedrock decides whether to draw its new OreUI interface or the legacy JSON-UI
by consulting a screen-tech-stack function inside `minecraftpe`. This tool:

1. Opens the IPA and locates `Payload/<App>.app/minecraftpe`.
2. Finds that function by reading the ARM64 Mach-O directly — no disassembler, no external SDK.
3. Overwrites its prologue with `movz w0, #0` + `ret`, so it always reports "no tech stack".
4. Repacks the IPA, preserving every other entry byte-for-byte.

The patch is **8 bytes**, in-place, and never grows the binary:

```
00 00 80 52    movz w0, #0
C0 03 5F D6    ret
```

Nothing else is modified. Assets, resources, and the rest of the app bundle are copied through untouched.

## How it finds the function

Two independent strategies, tried in order. This is what lets it survive game updates
without a hard-coded offset.

**1. Named registration (preferred)**

Minecraft registers its screen tech stacks under string keys. The patcher looks for these
anchors in the binary:

```
getTechStackForScreen
vanilla.screenTechStack
```

For each hit it walks the string cross-references, expands nearby branch targets, and scores
every candidate function. A hit here adds a large bonus, so an anchored match wins outright
unless the structural scan is far more confident.

**2. Structural fingerprint (fallback)**

If the anchors are gone (renamed, inlined, or stripped), it scans `LC_FUNCTION_STARTS` and
scores every function by shape:

| Signal | What it looks for |
|---|---|
| Known prologue | The 16-byte ARM64 prologue Minecraft has used across versions |
| Return | Any `ret` in the body |
| Compare-to-1 | `cmp wN, #1` |
| Move-1 / Move-0 | `movz wN, #1` / `movz wN, #0` |
| Conditional select | `csel` targeting `w0` |
| Field loads | `ldr xN, [x0, #0x30]`, `ldr wN, [xM, #0x18]` |
| Call density | Number of `bl` instructions, resolved through thunks |

A function only qualifies if the score clears the threshold **and** it wins by a clear margin
over the runner-up. If nothing qualifies, the tool writes a diagnostic file instead of
guessing.

**Already patched?** Detected — it reports `state=patched` and does nothing.

## Download and run

There is **no installer and no release download** — this is a script plus a few data files,
so you grab the whole repository.

**1. Download the repository**

Click the green **Code** button → **Download ZIP**, then extract it anywhere.
(Or clone it: `git clone https://github.com/yinghuajimew/CloseOreUI-iOS-IPA-Patcher.git`)

**2. Install Python**

Python **3.11 or newer** is required — <https://www.python.org/downloads/>.
On Windows, tick **"Add python.exe to PATH"** during installation, otherwise the commands
below will not be found.

**3. Install the one dependency**

Open a terminal **in the extracted folder** (the one containing `main.py`) and run:

```bash
pip install -r requirements.txt
```

This installs `tkinterdnd2`, which enables drag-and-drop. It is optional — if you skip this
step the program still runs, it just tells you to install it and you use **Add Files** instead.

**4. Run it**

```bash
python main.py
```

On Windows you can also double-click `main.py` if Python is associated with `.py` files,
but running it from a terminal is better because errors stay visible.

**5. Keep the folder intact**

The program loads files relative to its own location. Do **not** move `main.py` out of the
folder on its own. These files must stay next to it:

| Required | Why |
|---|---|
| `lang/*.json` | UI text. Without these, the interface shows raw key names instead of words. |
| `HyniSign.dylib`<br>`libhynisloader.dylib`<br>`HyniSwizzleFPS.dylib` | Only read when **inject dylibs** is checked. Missing them makes injection fail with an error — removal-only mode is unaffected. |
| `zsign.exe` | Only used for injection. Same rule. |

In other words: **removing OreUI works with `main.py` + `lang/` alone**, but download
everything so the optional features work too.

## Requirements

- Python **3.11+**
- Windows is the primary target (it remembers your language in `HKCU\Software\iosoreuipatcher`).
  On macOS/Linux it runs too, but the language choice is not saved — it falls back to your
  system locale each launch.
- Optional: `tkinterdnd2` for drag-and-drop

```bash
pip install -r requirements.txt
```

## Usage

1. Run `python main.py`.
2. Add one or more `.ipa` files (drag them in, or click **Add Files**).
3. Leave **inject dylibs** unchecked unless you specifically want the optional tweaks (see below).
4. Optionally pick an output folder.
5. Click **Start** and watch the log.

Output naming:

| Mode | Suffix | Also injects |
|---|---|---|
| OreUI removal only | `_No_oreui.ipa` | — |
| OreUI removal + dylibs | `_No_oreui_all.ipa` | the three dylibs |

The original IPA is **never** overwritten. If a name already exists, a `_2`, `_3`, … is appended.

Two diagnostic files are written next to the source IPA:

- `*_OreUI_v6_result.txt` — what was chosen, its score, offset, and before/after bytes.
- `*_OreUI_v6_diagnostic.txt` — only when no target was found; lists every candidate considered.

Include these when reporting a patch failure — they contain no game data, only offsets.

## Optional dylib injection

> [!NOTE]
> **These three dylibs have nothing to do with removing OreUI.**
> OreUI removal is the pure-Python binary patch described above and works with all three
> dylibs deleted. They are unrelated extras that got bundled into the same tool.

When **inject dylibs** is checked, the tool calls `zsign -a` to inject three dylibs into the
repacked IPA. Each one solves a different, unrelated problem:

### `HyniSign.dylib` — fixes Xbox sign-in

Re-signed Minecraft can't write its Xbox Live device-identity key into the Keychain, because
the original Mojang `kSecAttrAccessGroup` no longer matches your signing identity.
`SecKeyCreateRandomKey` then fails with **`-34018` (`errSecMissingEntitlement`)**, and sign-in
breaks.

This dylib rebinds the Keychain functions (`SecItemAdd`, `SecItemCopyMatching`,
`SecItemUpdate`, `SecItemDelete`, `SecKeyCreateRandomKey`, `SecKeyGeneratePair`) through
`fishhook` and strips the access group from the query before the real call.

**Use it if:** you re-signed the IPA yourself and Xbox sign-in fails.

### `libhynisloader.dylib` — loads a full `renderer` folder from resource packs

Normally Minecraft loads renderer files only from the ones shipped inside the app. This dylib
hooks `fopen` and redirects requests so the game loads a complete `renderer` folder from your
resource packs instead — the same idea as Draco Injector on Android.

**Use it if:** you want custom RenderDragon shaders or renderer overrides via resource packs.
**Ignore it if:** you just want OreUI gone.

### `HyniSwizzleFPS.dylib` — lifts the 60 FPS cap

Swizzles `CADisplayLink` so ProMotion iPhones/iPads render above 60 FPS instead of being
clamped.

**Use it if:** you have a ProMotion display and the game feels capped.

### Summary

| File | Solves | Needed for OreUI removal? |
|---|---|---|
| `HyniSign.dylib` | Xbox sign-in `-34018` after re-signing | **No** |
| `libhynisloader.dylib` | Custom renderer/shader loading | **No** |
| `HyniSwizzleFPS.dylib` | 60 FPS cap | **No** |

**Note on `libhynisloader.dylib`:** the file in this repo is **not** an unmodified upstream
build. It is a locally combined build containing both the `fopen` hook from HynisLoader and
the `HyniSignCopyStripped` helper from HyniSign. Upstream ships these separately.

> [!WARNING]
> Because injection uses `zsign -a` (ad-hoc), the resulting `_No_oreui_all.ipa` only installs
> on a **jailbroken device** or via **TrollStore**. If that is not your situation, leave the
> checkbox off and use `_No_oreui.ipa` with your own signing tool instead.

## Third-party components and licensing

This project bundles third-party binaries. Their licenses and attribution are recorded here
rather than in the repository `LICENSE` file.

**zsign** — bundled as `zsign.exe`.
MIT License, Copyright (c) 2026 zhlynn — <https://github.com/zhlynn/zsign>

```
MIT License

Copyright (c) 2026 zhlynn

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

**libhynisloader.dylib** — derived from [HynisDev/HynisLoader](https://github.com/HynisDev/HynisLoader),
which is **GPL-3.0**. Distributing a binary built from it means this repository is subject to
GPL-3.0 with respect to that component.

**[HyniSign](https://github.com/vanhoof/HyniSign)** and **[HyniSwizzleFPS](https://github.com/vanhoof/HyniSwizzleFPS)** — upstream repositories publish **no license file**.
Absence of a license means the author reserves all rights; these binaries are redistributed
here for user convenience by the original packager, not with a verified license grant. If you
are the rights holder and want them removed, open an issue.

**fishhook** — used by both HyniSign and HynisLoader. BSD-3-Clause,
Copyright (c) 2013 Facebook, Inc. — <https://github.com/facebook/fishhook>

If you intend to redistribute this project, verify these terms yourself. The core OreUI
patching logic in `main.py` is independent of all of the above.

## Known limitations

- **iOS only, arm64 only.** The patcher decodes AArch64 instruction encodings; it will not work on 32-bit builds.
- **The output must be re-signed.** See the warning at the top.
- **`_No_oreui_all.ipa` needs TrollStore or a jailbreak** because it is ad-hoc signed.
- **A future game update may break the structural scan.** When that happens you get a
  diagnostic file rather than a silently wrong patch — send it in.
- **Not every screen is covered.** OreUI removal affects the in-game UI entry point the patch
  targets; it does not rewrite any assets.
- **Windows-oriented.** The GUI stores its language preference in the Windows registry; on other
  platforms it falls back to the system locale without persisting.

## Credits

- Project author: **xiaoli**
- Reverse-engineering and patch approach: **奕帆雨顺**
- Testing and feedback: **xiaoli**, **奕帆雨顺**
- Repository hosting: **樱花祭喵**
- Debug build and adaptation opportunities: **银果集团**

Third-party projects are credited in the licensing section above.

## Disclaimer

This tool modifies a game you own, for personal use. It is not affiliated with Mojang or
Microsoft. Redistributing a patched build, or using it commercially, is not endorsed here.
