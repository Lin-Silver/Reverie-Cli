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
