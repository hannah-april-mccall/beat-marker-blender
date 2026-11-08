# Changelog

## 0.4.0

- Bundle an offline background analysis engine with platform-specific Mac, Windows and Linux releases.
- Include the Beat This! model, private Python runtime, FFmpeg and FFprobe.
- Remove the dependency on an installed Premiere/CEP version of Beat Marker.
- Store saved analyses outside the extension installation directory.
- Handle ZIP installers that discard executable permissions using an extension user-data copy.
- Add reproducible build scripts, generated-audio engine checks and platform release automation.

## 0.3.0

- Add beat-number checkboxes based on the detected beats per bar.
- Preserve the selected beat combination when saving a Blender project.
- Apply the same selected beats to marker updates and clip alignment.

## 0.2.1

- Show live clip-alignment previews and per-clip explanations.

## 0.2.0

- Add clip alignment, source anchors, optional ripple and whole-operation Undo.

## 0.1.0

- Analyse selected music and create refreshable numbered timeline markers.
