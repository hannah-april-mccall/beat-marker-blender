# Verification and compatibility

Release 0.4.0 was built on native GitHub-hosted runners on 8 November 2026. All three platform jobs and the release job completed successfully. Tests used generated media and isolated Blender preferences, not private projects or downloaded songs.

| Check | Apple Silicon Mac | Windows x64 | Linux x64 |
| --- | --- | --- | --- |
| Frozen engine analyses generated audio offline | Passed, 49 beats | Passed, 49 beats | Passed, 49 beats |
| Source offsets, beat-number selection, marker ownership and persistence in background Blender | Passed | Passed | Passed |
| Background Blender alignment matrix | Passed, 589 checks / 18 cases | Passed, 589 checks / 18 cases | Passed, 589 checks / 18 cases |
| Bundled-engine analysis and marker refresh in background Blender | Passed, 20 markers | Passed, 20 markers | Passed, 20 markers |
| Interactive editing UI | Checked on Mac | Not separately checked | Not separately checked |

The native jobs used Blender 5.2.3 LTS. The manifest requires Blender 5.2 or newer. Mac builds target Apple Silicon; Intel Macs are not included. Windows and Linux builds target Intel/AMD x64. Linux requires glibc 2.35 or newer, such as Ubuntu 22.04. Minimum-version operating systems and every later Blender version have not been separately tested.

Background tests verify the editing and analysis logic but do not establish interactive UI behaviour on every machine. The runtime checks relocate the engine, run it with a restricted environment, verify its model and check cache reuse.

The engine and native helper programs have no paid OS publisher signatures or Apple notarisation. Installation from a quarantined browser download on a clean machine has not been separately verified on every platform. See INSTALLATION.md for warning and policy limits.

Known limits are listed in the README. Beat and bar estimates need listening review. Save a project copy before applying alignment, especially with linked audio or ripple enabled. Blender's native Undo reverses an applied operation.
