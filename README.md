# mib3convert

Convert virtually **any** video (`.mkv`, `.avi`, `.wmv`, `.mov`, …) into an MP4
that VW **MIB3 / MOI3** infotainment units will actually play — with an
interactive terminal file picker.

Car head units are picky: they silently *grey out* files that use the wrong
codec, an unusual frame rate, or multichannel audio. `mib3convert` re-encodes to
a known-good target: **H.264 (MP4) + stereo AAC**, sane resolution, capped frame
rate, and a fast-start `moov` atom.

## Requirements

- Python 3.9+
- [`ffmpeg`](https://ffmpeg.org/) and `ffprobe` on your `PATH`
  - Debian/Ubuntu: `sudo apt install ffmpeg`
  - macOS: `brew install ffmpeg`
- Downloading from Yle Areena works out of the box —
  [`yle-dl`](https://aajanki.github.io/yle-dl/) is bundled as a dependency and
  installed automatically.

## Install

```bash
pipx install .
# or, from a checkout during development:
pipx install --editable .
```

This installs the `mib3convert` command together with everything it needs,
including `yle-dl` for Yle Areena downloads.

## Usage

Just run it — you'll be asked where the video comes from:

```bash
mib3convert
```

```
 Where is the video?
 ╭──────────────────────────────────────────╮
 │ > Yle Areena  (download by address)       │
 │   Local file  (browse this computer)      │
 ╰──────────────────────────────────────────╯
```

- **Yle Areena** — paste the programme address (e.g.
  `https://areena.yle.fi/1-72801351`); it downloads with `yle-dl` and converts
  automatically, no further questions. The MP4 lands in the current directory.
- **Local file** — opens a full-screen, arrow-navigable picker (type to
  fuzzy-search, ↑/↓ to move, Enter to pick).

Skip the menu by naming a local file directly (also lets you choose the output):

```bash
mib3convert movie.mkv -o /media/usb/movie.mp4
```

Point the local picker at a specific folder:

```bash
mib3convert --path ~/Downloads
```

Pick an encoding profile:

```bash
mib3convert --profile strict big_movie.avi
mib3convert --list-profiles
```

## Profiles

| Profile  | Target                                                                 |
| -------- | ---------------------------------------------------------------------- |
| `safe`   | 1280×720, keeps source fps up to 30, 192k stereo AAC. **Default.**     |
| `strict` | 1280×720, forces 23.976 fps, 320k stereo AAC. Use if `safe` greys out. |
| `compat` | 854×480, 23.976 fps, H.264 Main, 192k stereo AAC. Oldest units.        |

The output is always MP4 / H.264 / yuv420p / stereo AAC with `+faststart`.

## Tips for the car

- Format the USB stick as **FAT32** or **exFAT**.
- If a file still greys out, try `--profile strict`, then `--profile compat`.
- Some units limit the number of files per folder — keep it tidy.

## Compatibility notes

Targets are based on community testing of MIB3 media playback (frame rates above
~30 fps and 5.1 audio are the usual culprits for rejected files). Behaviour
varies by firmware/region; the `strict` and `compat` profiles exist for stubborn
units.

## License

MIT
