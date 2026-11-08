# Beat Marker for Blender

Analyse music locally, create numbered beat markers, and align video edits to the music in Blender's Video Sequencer.

Beat Marker detects beats and bar starts using **Beat This!**, then maps the results to the music strip's source trim and timeline position. Select the beats you want to mark—for example, beats **1 and 3**—and fit your video clips between them.

## Install

1. Open **[Releases](../../releases)** and download the ZIP for your computer. Use the named Beat Marker package rather than GitHub's automatic **Source code** ZIP.
2. In Blender, open **Preferences → Get Extensions → menu → Install from Disk**.
3. Select the downloaded ZIP and enable **Beat Marker**.
4. In the Video Sequencer, press **N** and open the **Beat Marker** tab.

The release packages include the background analysis engine, trained model, private Python runtime, FFmpeg and FFprobe. **You do not need Premiere Pro, a separate Python installation or an internet connection to analyse music.** Your audio stays on your computer.

Blender **5.2 or newer** is required. Platform-specific packages are built for Apple silicon Macs, Windows x64 and Linux x64. Blender 5.2 has no official Intel Mac distribution, so an Intel Mac package is not included. The build workflow runs the frozen-engine and background Blender checks on each platform. See [building and compatibility](docs/BUILDING.md).

## Create beat markers

1. Select one music sound strip.
2. Choose **Timing** and click **Analyse selected music**.
3. Choose the beat-number checkboxes you want, then click **Update marker times**.
4. If you move or trim music, click **Update marker times** again. Saved beat timestamps are reused; no new analysis is needed.

The tool preserves manually added markers. **Remove from Selected** removes only its own markers for the selected music. Multiple analysed music strips can coexist in one scene. Beat numbers and the music-strip name distinguish songs in Blender's shared marker row.

**Timing** offers automatic sparse-intro recovery, original model detections, or a steady beat grid. Beat and bar positions are estimates and can require a listening review. The detected beats per bar do not establish the written note value of a time signature.

## Align video edits

1. Analyse the music and choose the beat numbers you want to use.
2. Select video clips, or choose a video channel in **Clips**.
3. Choose **Extend / reduce**, **Extend only** or **Reduce only**.
4. Choose a **Source anchor**: start, midpoint or end of the currently used source range.
5. Set a threshold in frames and optionally enable **Ripple following clips**.
6. Click **Preview alignment** to see proposed edges and the result for each clip.
7. Click **Apply alignment**. Blender's normal **Undo** reverses the whole operation.

Clips can move on the timeline as their source trims change. Matching connected audio follows the video. Preview does not modify the clips. Applying alignment also refreshes the tool's music-marker positions.

## Current limits

- Music must be a normal-speed, unpacked sound file in the top level of the Sequencer. Render retimed or nested music to a normal audio file first.
- Clip alignment supports forward, normal-speed movie strips and matching connected sound strips. Rate stretch is not included.
- Retimed/reversed clips, locked strips, meta strips, animated strips and transition/effect inputs are skipped with an explanation.
- Generated markers are timeline markers. Use **Update marker times** after moving music.
- Linux packages target x64 systems with glibc 2.35 or newer, such as Ubuntu 22.04+. Other Linux architectures and musl-based systems are not included.

## Development

The add-on is in `beat_marker/`; the background worker and musical recovery code are in `engine/`. Python and native build instructions are in [BUILDING.md](docs/BUILDING.md). The source checkout intentionally excludes models, installed Python environments, caches, test songs and stock footage.

Bug reports should include the Beat Marker version, Blender version, operating system and the smallest reproducible example. Do not upload music or footage you do not have permission to share.

## Credits and licence

Beat Marker source: **MIT**, copyright Hannah McCall. Beat detection: [Beat This!](https://github.com/CPJKU/beat_this), MIT, Institute of Computational Perception, JKU Linz. Bundled Python packages retain their original licences. The FFmpeg build is LGPL and includes its corresponding source and build configuration. See [third-party notices](THIRD_PARTY_NOTICES.md).

This GitHub release is independent of Blender's official Extensions Platform.
