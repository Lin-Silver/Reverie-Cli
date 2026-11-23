# Native workspace commands

The public name, aliases, arguments, noninteractive execution, project audit log, script checks and toolchain environment follow the final Python `command_exec.py` at repository commit `070fa25b07692c90c56a6b00a9a969ff2abb7804`. That file and this Rust implementation belong to this repository under its MIT license. The Python source remains frozen on `Reverie-Cli-py`.

The process implementation is native Rust and Tokio. Windows uses `windows-sys` Job Objects with `KILL_ON_JOB_CLOSE`; Unix uses a dedicated process group. The Win32 signatures were checked against the installed `windows-sys 0.61.2` source. Tokio `1.54.1` supplies process creation, asynchronous pipes and cancellation integration. No first-party command runner calls a Python helper.

Rust additionally validates each PowerShell pipeline stage, rejects dynamic PowerShell execution and option-attached traversal, drains bounded output from both pipes, and records whether delivery did not start, occurred or is uncertain. Normal exit also closes remaining descendants. UTF-8 fragments are decoded across pipe reads; the PowerShell wrapper explicitly selects UTF-8 output.

Script inspection is a heuristic policy and does not establish operating-system sandbox containment. Commands may invoke installed third-party runtimes. Real service behavior, escaping child processes, platform-specific legacy encodings and failed Job Object assignment require the extended acceptance recorded in `tasks/rust-3.0/UNVERIFIED.md`.
