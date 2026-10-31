# CI follow-up for 2.5.3

The GitHub Actions runs for `211c577` exposed two independent failures:

- [Desktop job](https://github.com/Lin-Silver/Reverie-Cli/actions/runs/41191440392/job/124508871753): Git 2.56 returns `gitfile does not point to a valid repository` for the real invalid-gitfile fixture. Workspace discovery previously recognized only `not a git repository`. Handle both as unavailable workspaces, while retaining unrelated errors such as dubious ownership. A regression test reproduces the exact new error and failed before the fix; the real Git repository/branch integration tests remain enabled.
- [Linux package job](https://github.com/Lin-Silver/Reverie-Cli/actions/runs/41191440500/job/124508871971): `dist:linux` passes `--output release`, but the package path guard accepted only descendants. Accept the allowed directories themselves as well; retain sibling-prefix and normalized traversal rejection. Run the package helper tests in the standard desktop CI job as well as the existing package verification workflow.

Local Windows verification:

- `npm test -- electron/git-workspace-errors.test.ts electron/git-workspace.test.ts`: 6 passed, including real Git branch creation, switching, dirty status and remote tracking.
- `npm test`: 452 passed, 1 skipped.
- `npm run typecheck`: passed.
- `npm run build`: passed, version 2.5.3. Existing bundle-size warning remains.
- `node --test scripts/package-validation.node-test.mjs`: 3 passed, 3 Linux-only tests skipped on Windows. Native Linux package execution requires the new GitHub runner result; Windows checks alone do not validate Linux artifacts.

This follow-up changes Git discovery and packaging validation, with no further visual changes or version bump. Existing local packages and the unrelated deleted upstream playbook are preserved.

## Cloud verification and Python portability follow-up

For `52016e1`, the [desktop job](https://github.com/Lin-Silver/Reverie-Cli/actions/runs/41191796738/job/124509940467) passed with Git 2.56: 452 desktop tests passed, 1 skipped; all 6 Linux package helper tests, types and build passed. The [Linux package job](https://github.com/Lin-Silver/Reverie-Cli/actions/runs/41191796717/job/124509969921) and [macOS Apple Silicon package job](https://github.com/Lin-Silver/Reverie-Cli/actions/runs/41191796717/job/124509969753) also completed successfully.

Later Python jobs revealed additional portability problems:

- Git normalized three unmodified Elaya upstream files to LF, while their provenance manifest checksums cover CRLF bytes. Preserve exact imported bytes and original whitespace via path-scoped Git attributes. All three staged blobs match their existing SHA-256 entries; no manifest checksum or upstream content is redefined.
- The native Pyglet symbol test requested the EGL headless backend on macOS, which has no EGL library. Use that backend only on Linux; keep native constants/assertions on macOS and Windows.
- Linux used the runner's unrelated Chromium build, which both failed sandbox launch and crashed in a native iframe fixture. Install the browser matching the pinned Playwright driver, prefer that installed binary in both DOM fixtures, and enable sandboxing in both. Follow [Playwright CI setup](https://playwright.dev/python/docs/ci) and the [Chromium path-scoped AppArmor profile](https://chromium.googlesource.com/chromium/src/+/main/docs/security/apparmor-userns-restrictions.md); do not disable Chromium sandboxing or globally change the user-namespace policy.
- Running the previously skipped browser fixtures locally also exposed three task JSON reads using the Windows default encoding. Read those UTF-8 fixtures explicitly. The provenance, Engine window and native calibration subset then passed 77/77 on Windows with a real browser.

The workflow YAML parses and the CI setup script passes Bash syntax validation. Linux/macOS follow-up behavior still needs the subsequent cloud run; local Windows results cannot establish it. Synthetic DOM fixtures remain zero formal model-quality samples.
