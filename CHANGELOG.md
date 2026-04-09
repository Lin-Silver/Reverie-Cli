# Changelog

All notable changes to this project will be documented in this file.

## 2.1.24 - 2026-04-09

- Fixed the `/web model` and other TUI selectors so they render in a stable live view without duplicating panels while navigating in Windows terminals.
- Bumped the canonical Reverie CLI version to `2.1.24`.
- Fixed the Windows build flow so `build.bat` no longer passes the invalid `--specpath` option when building from `reverie.spec`.
- Kept build output, PyInstaller work files, caches, and runtime temp data inside the project root instead of spilling into the system temp directory on `C:`.
- Ensured `build.bat` pauses on both success and failure so the build window does not close immediately when launched by double-clicking.
