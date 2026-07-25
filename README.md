# mib3-dl

Convert virtually **any** video into an MP4 that VW **MIB3, MOI3** infotainment
units will actually play — or download straight from **Yle Areena** and convert
in one step — all from a friendly terminal UI.

---

## Table of contents

- [Why this exists](#why-this-exists)
- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
  - [Interactive (the normal way)](#interactive-the-normal-way)
  - [Downloading from Yle Areena](#downloading-from-yle-areena)
  - [Converting a local file directly](#converting-a-local-file-directly)
  - [All command-line options](#all-command-line-options)
- [Encoding profiles](#encoding-profiles)
- [The output format (technical target)](#the-output-format-technical-target)
- [How it works](#how-it-works)
- [Tips for the car](#tips-for-the-car)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Why this exists

VW MIB3 / MOI3 media players accept only a narrow slice of what "video files"
can be. Community testing shows the usual reasons a file refuses to play (it
appears greyed-out and unselectable) are:

- a codec/container the unit doesn't support,
- a **frame rate above ~30 fps**, or
- **multichannel / 5.1 audio**.

`mib3-dl` removes the guesswork by always producing an **MP4 / H.264 /
stereo AAC** file with a capped frame rate, a safe resolution, and a fast-start
`moov` atom, so the unit sees exactly what it expects.

## Features

- **Full-screen file browser** — navigate the whole filesystem with the arrow
  keys: open folders, go up with `../` (or `Ctrl+U`), or type a path like
  `/media/usb` to jump anywhere. Works no matter where your file lives.
- **Choose the output folder** — after picking the source, pick where the
  result goes (e.g. straight onto a mounted USB stick).
- **Fuzzy file search** — start typing to filter the current folder; `dh`
  finds `Die Hard.mkv`.
- **Yle Areena downloads built in** — paste a programme address and it
  downloads (via the bundled `yle-dl`) and converts automatically.
- **Known-good MIB3/MOI3 target** — H.264 MP4 + stereo AAC, capped fps,
  faststart.
- **Fast** — a quick x264 preset by default, and if a file already meets the
  MIB3 spec it's **remuxed instead of re-encoded** (near-instant).
- **Profiles** — `safe` (default), `strict`, and `compat` for stubborn units.
- **Live progress bar** during encoding.
- **Safe by default** — never overwrites the input, cleans up partial files
  on cancel, and removes temporary downloads when done.

## Requirements

- **Python 3.9+**
- **[`ffmpeg`](https://ffmpeg.org/)** and **`ffprobe`** on your `PATH`
  - Debian/Ubuntu: `sudo apt install ffmpeg`
  - macOS: `brew install ffmpeg`
  - Windows: install ffmpeg and add it to `PATH`
- **Yle Areena downloads work out of the box** — the
  [`yle-dl`](https://aajanki.github.io/yle-dl/) tool is a bundled dependency and
  is installed automatically. Nothing extra to install.

## Installation

Install with [pipx](https://pipx.pypa.io/) (recommended — it keeps the tool and
all its dependencies isolated):

```bash
pipx install .
```

For development from a checkout:

```bash
pipx install --editable .
```

This installs the **`mib3-dl`** command along with everything it needs,
including `yle-dl`.

## Usage

### Interactive (the normal way)

Just run it:

```bash
mib3-dl
```

You'll first be asked where the video comes from:

```
 Where is the video?
 ╭──────────────────────────────────────────╮
 │ > Yle Areena  (download by address)       │
 │   Local file  (browse this computer)      │
 ╰──────────────────────────────────────────╯
```

- **↑ / ↓** move, **Enter** selects, **Esc** cancels.

Choose **Local file** and you get a full-screen filesystem browser:

- **↑ / ↓** move, **Enter** opens a folder or picks a file.
- **`../`** (top of the list) or **`Ctrl+U`** goes up to the parent folder.
- **Type** to fuzzy-filter the current folder.
- **Type a path** (e.g. `/media/usb` or `~/Videos`) and press **Enter** to jump
  straight there — so you can reach a file anywhere, not just under the current
  directory.

Once you've picked the file, a second screen asks **where to save the result**:

```
 Select the output folder
 /media/usb
 ╭──────────────────────────────────────────╮
 │ > Use this folder                         │
 │   ../  (parent folder)                    │
 │   movies/                                 │
 ╰──────────────────────────────────────────╯
```

Navigate the same way (arrows, `../`, `Ctrl+U`, or type a path), then pick
**Use this folder** to save there — handy for writing straight to a mounted
USB stick. The file is named `<source name>_mib3.mp4`.

Output names are automatically made **FAT32/exFAT-safe**: characters those
filesystems reject (`: " * ? < > | \ /`) are replaced, so titles like
`Tuuri: Vauvakisa: 2026-06-27T08:14` become
`Tuuri-Vauvakisa-2026-06-27T08-14_mib3.mp4` and can be written straight to a
USB stick. (An explicit `-o` path is used exactly as you give it.)

### Downloading from Yle Areena

Choose **Yle Areena** and you'll be asked for the address:

```
? Paste the Yle Areena video address: https://areena.yle.fi/1-72801351
```

You're then asked for the **output folder** (the same chooser as above). After
that it's fully automatic — it downloads the programme and converts it to a
MIB3-ready MP4 **with no further questions**, so you can walk away. The finished
file is written to the folder you chose as `<programme title>_mib3.mp4`, and the
temporary download is cleaned up afterwards.

> The folder is requested *before* the download starts, precisely so the
> download and conversion can run unattended.

> Note: much of Yle Areena is only available inside Finland. If a download
> fails, the tool shows `yle-dl`'s error with a hint.

### Converting a local file directly

Skip the menu entirely by naming a file (and optionally the output):

```bash
mib3-dl movie.mkv
mib3-dl movie.mkv -o /media/usb/movie.mp4
```

Point the local picker at a specific folder instead of the current directory:

```bash
mib3-dl --path ~/Downloads
```

Pick a profile:

```bash
mib3-dl --profile smooth big_movie.avi
mib3-dl --list-profiles
```

### All command-line options

```
mib3-dl [input]

positional:
  input                 Input video file. If omitted, the source menu opens.

options:
  -o, --output FILE     Output file (default: <input>_mib3.mp4 next to input,
                        or ./<title>_mib3.mp4 for Yle downloads).
  -p, --profile NAME    Encoding profile: safe | strict | compat
                        (default: safe).
  --preset NAME         x264 speed/quality preset, overriding the profile
                        (ultrafast … veryslow; faster = quicker, larger files).
  --path DIR            Folder the local file browser starts in
                        (default: current directory).
  --list-profiles       Show the available profiles and exit.
  -y, --yes             Overwrite the output file without asking.
  --version             Show the version and exit.
  -h, --help            Show help and exit.
```

## Encoding profiles

| Profile  | H.264        | Resolution | Frame rate           | When to use                                        |
| -------- | ------------ | ---------- | -------------------- | -------------------------------------------------- |
| `safe`   | Baseline L3.1 | ≤ 1280×720 | forced 23.976 fps    | **Default.** The most broadly compatible config.   |
| `smooth` | Baseline L3.1 | ≤ 1280×720 | keeps source, ≤30fps | If 23.976 makes 25/30fps content look juddery.     |
| `compat` | Baseline L3.0 | ≤ 854×480  | forced 23.976 fps    | Oldest / pickiest units.                           |

All profiles output MP4 / **H.264 Baseline** (no B-frames / no CABAC) /
`yuv420p` / **stereo** AAC (192k, 48 kHz) with `+faststart`. Aspect ratio is
always preserved and the video is never upscaled.

> **Why Baseline?** MIB3 / MOI3 units reliably decode only H.264 **Baseline**
> profile. High- or Main-profile files typically play the audio but show a
> black/absent picture. This is the single most common cause of "sound but no
> video" — see [Compatibility notes](#compatibility-notes).

## The output format (technical target)

Regardless of profile, every output is:

- **Container:** MP4, with the `moov` atom moved to the front (`+faststart`)
- **Video:** H.264 (`libx264`), **Baseline profile** (no B-frames, no CABAC),
  Level 3.1 (3.0 for `compat`), `yuv420p`
- **Resolution:** scaled to fit the profile's box, aspect-preserving, even
  dimensions, never upscaled (≤ 1280×720)
- **Frame rate:** forced to 23.976 fps (or capped at 30 for `smooth`)
- **Audio:** AAC-LC, **stereo** (5.1 is downmixed), 48 kHz
- **Subtitles:** dropped (they can prevent playback on some units)

## How it works

1. **Source selection** — a Textual menu (Yle Areena vs. local file).
2. **Acquire** — either `yle-dl` downloads the programme into a temp folder, or
   you pick a local file via the fuzzy picker.
3. **Probe** — `ffprobe` reads the source's codecs, resolution, frame rate,
   pixel format, H.264 profile/level, and audio channels.
4. **Plan** — each stream that already meets the MIB3 target is **stream-copied**
   (remuxed) instead of re-encoded. A file that's already compatible finishes in
   seconds; only what actually needs changing gets re-encoded.
5. **Transcode** — `ffmpeg` produces the MP4, streaming a live progress bar
   (partial output is deleted if you cancel).
6. **Done** — you get a ready-to-play MP4; temporary downloads are removed.

### A note on speed

Re-encoding video is inherently CPU-heavy. Two things keep it quick:

- **Remux when possible.** If the source is already H.264 / yuv420p within the
  target resolution and frame rate (and its audio is already stereo AAC), the
  data is copied as-is — no quality loss and near-instant.
- **A fast preset by default.** Profiles use the `veryfast` x264 preset. Want
  smaller files and don't mind waiting? Add `--preset slow` (or `medium`).

> The Yle Areena flow is download **then** convert — `yle-dl` fetches Yle's
> original stream, which is then run through the same plan/transcode step. It is
> not downloaded pre-formatted for MIB3.

## Tips for the car

- Format the USB stick as **FAT32** or **exFAT**.
- If a file still won't play, try `--profile compat`.
- Some units limit how many files a folder may contain — keep folders tidy.

## Troubleshooting

| Symptom                                   | Fix                                                        |
| ----------------------------------------- | --------------------------------------------------------- |
| `ffmpeg not found`                        | Install ffmpeg (see [Requirements](#requirements)).       |
| **Audio plays but no picture / black**    | The source was High-profile H.264. The default `safe` profile now re-encodes to Baseline — reconvert with the current version. Still failing? Try `--profile compat`. |
| File greys out / won't select             | Try `--profile compat` (smaller, Level 3.0).              |
| `Error opening output … Invalid argument` | The name contained characters FAT32 rejects. Auto-generated names are now sanitised; if you passed `-o`, remove `: " * ? < > \| \` from it. |
| Yle download fails                        | Content may be Finland-only; check the address & network. |
| Picker shows no files                     | Browse to the folder, or type its path in the picker.     |

## Compatibility notes

The encoding target is based on the official **VW/Audi Self-Study Program 970893,
"Third-generation modular infotainment matrix"** (the MIB3 platform SSP, 2021),
plus corroborating owner reports:

- The SSP lists H.264 (`.mp4 .m4v .mov .avi`) as supported, with a general
  ceiling of **1920×1080 @ 30 fps, 15 Mbit/s**, and panels of 1280×720 or
  1540×720 — but it does **not** restrict the H.264 profile.
- In practice, MIB3 / MOI3 decoders reliably handle only H.264 **Baseline**
  profile. High/Main-profile streams commonly result in **audio with no
  picture** — the single most-reported MIB3 video problem. Every confirmed
  working community config uses Baseline (typically Level 3.0/3.1, ≤720p,
  23.976 fps, stereo AAC). `mib3-dl` targets exactly that.
- Frame rates at/above 30 fps and 5.1 audio are known to make files rejected or
  greyed-out, so output is 23.976 fps and stereo by default.

Behaviour still varies by firmware/region; `smooth` and `compat` exist for the
cases the default doesn't cover.

## License

**Proprietary — All Rights Reserved.** This project is **not** open source.
No part of it may be copied, modified, distributed, or used without the prior
explicit written permission of the author. See [`LICENSE`](LICENSE) for the full
terms. To request permission, contact the author via
[github.com/jugih-official](https://github.com/jugih-official).
