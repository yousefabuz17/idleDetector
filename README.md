# IdleDetector

`IdleDetector` is a macOS-focused monitoring library that tracks user inactivity and broadcasts rich desktop notifications for important idle milestones. It combines Quartz-powered idle metrics, `pmset` log introspection, and terminal-notifier automation to give you a reliable, asynchronous way to respond to screensaver, display-off, and wake transitions.

## Table of contents
- [Features](#features)
- [How it works](#how-it-works)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [License](#license)

## Features
- **Real-time idle stage detection** – Classifies activity into granular stages (active, idle, pre-screensaver, screensaver, display-off, wake) so you can tailor responses to each transition.
- **Asynchronous architecture** – The main `idleDetector` loop runs on `asyncio`, avoiding blocking while it polls system state and dispatches alerts.
- **macOS-aware system model** – Uses a `MacOS` helper to safely access Quartz APIs, `pmset` power settings, and screensaver state with graceful fallbacks.
- **Contextual notifications** – Automatically builds stage-specific messages ("Sleep time", "Wake up", etc.) and optionally groups them to prevent duplicate alerts.
- **Terminal Notifier integration** – Wraps the `terminal-notifier` binary, verifies its version, and injects rich media from the bundled assets.
- **Extensible data models** – Serializable dataclasses and namespaces keep stage metadata, timers, and notification configuration easy to introspect or persist.

## How it works
IdleDetector revolves around three cooperating components:

1. **`MacOS` machine adapter** – Validates that the host is running a supported macOS version, then exposes async helpers that fetch idle time, display sleep, and screensaver configuration.
2. **`StageManager`** – Evaluates the machine metrics, determines which idle stages apply, and tracks reference timers (screensaver/display-off). It manages wake transitions and respects custom idle thresholds when system settings are missing.
3. **`idleNotifier` / `TerminalNotifier`** – Builds human-friendly notification text based on the current stage and dispatches alerts through the `terminal-notifier` CLI, including per-stage images.

These pieces are orchestrated by the asynchronous `idleDetector` controller, which runs until it receives SIGINT/SIGTERM. Whenever the current stage indicates an alert-worthy transition, the detector triggers the notifier to surface a desktop notification.

## Requirements
- macOS 10.10 (Yosemite) or later.
- Python 3.13 or newer.
- [`terminal-notifier`](https://github.com/julienXX/terminal-notifier) available on your `PATH` (e.g., `brew install terminal-notifier`).
- Access to macOS command-line tools such as `pmset`, `defaults`, and `osascript` (present by default on macOS).

> **Note:** IdleDetector relies on macOS-only APIs (Quartz, Core Graphics). It will refuse to run on non-macOS platforms.

## Installation
...

## Configuration
Key options available on `idleDetector`:

| Parameter | Description |
|-----------|-------------|
| `ignoreDnD` | Send notifications even when Do Not Disturb is active (default: `True`). |
| `compact_timestamp` | Use shortened time strings in notifications (default: `False`). |
| `idle_interval_if_no_modes_are_set` | Fallback idle duration when no screensaver or display-off timers exist (seconds). |
| `consider_screensaver_as_off` | Treat an active screensaver as equivalent to the display turning off. |
| `group_notifications` | Group alerts by stage to avoid duplicates. |


## License
This project is licensed under the Apache License 2.0. See the [LICENSE](LICENSE) file for details.