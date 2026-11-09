# Installation

Use Blender 5.2 or newer. Download the named ZIP for your operating system from the [Releases page](https://github.com/hannah-april-mccall/beat-marker-blender/releases/tag/v0.4.0). Keep the ZIP intact for Blender's installer. GitHub's automatic Source code archives do not include the analysis engine.

| Computer | Package |
| --- | --- |
| Apple Silicon Mac | `beat-marker-blender-0.4.0-macos-arm64.zip` |
| Intel or AMD Windows x64 PC | `beat-marker-blender-0.4.0-windows-x64.zip` |
| Intel or AMD Linux x64, glibc 2.35+ | `beat-marker-blender-0.4.0-linux-x64.zip` |

1. Open **Blender → Preferences → Get Extensions**.
2. Open the menu and choose **Install from Disk**.
3. Select the downloaded ZIP and enable **Beat Marker**.
4. In the Video Sequencer, press **N** and open the **Beat Marker** tab.
5. Save a project copy, select a music sound strip and click **Analyse selected music**.

The engine, trained model, private Python runtime, FFmpeg and FFprobe are included. No separate Python, FFmpeg or Premiere installation is needed. Analysis works offline.

## Mac security warnings

The bundled native helper programs have no Apple Developer ID signature or notarisation. If macOS blocks a named Beat Marker helper as an unidentified developer or because Apple cannot check it for malicious software, open **System Settings → Privacy & Security**, find the notice for the component you just tried to run and use **Open Anyway** if available. Confirm the specific component and retry the analysis in Blender. Only approve components from this repository's release package. See [Apple's instructions](https://support.apple.com/en-gb/102445).

If the approval option is unavailable, or the message specifically reports malware or a damaged file, stop and check the exact message. A managed Mac may require IT approval. Do not turn off Gatekeeper or remove security protections globally.

## Windows security warnings

The native engine and helper programs have no Windows publisher signatures. If Windows offers **Windows protected your PC → More info → Run anyway** for a component from the release you downloaded, check its identity and source before choosing to run it. Windows Smart App Control or an organisation's policy may block unsigned helpers without offering an override; ask IT for an approved installation method in that case. A specific malware alert is different from an unrecognised-publisher warning. See [Microsoft's SmartScreen explanation](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation).

## Linux

Use the x64 package on a glibc 2.35+ system. The add-on can prepare a runnable copy in its user-data directory if installation loses executable permissions. A system that forbids running software from user directories may need an administrator-approved installation method. ARM and musl-based Linux distributions are not included.

## Update and removal

Use Blender's extension controls to remove or replace the add-on, then install the newer matching ZIP. Save a project copy before testing an update. Analysis data is stored in Blender's extension user-data directory, separately from the installed code. No packages are installed into Blender's Python environment.

Read the README for marker refresh and alignment limits, and TESTING.md for the checks performed on each platform. Support is best-effort; use the repository's bug-report template and remove personal information from any logs or screenshots.
