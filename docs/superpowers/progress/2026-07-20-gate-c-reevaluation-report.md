# Gate C Re-evaluation — 2026-07-20

## Verdict

**Blocked.** The recovered Task 17 route and module evidence is green, but an authenticated browser/API session and a real Chrome/Edge user-gesture File System Access export have not been demonstrated.

## Direct verification evidence

From `docs/web/homepage-prototype`:

- `node scripts/verify-api-auth.mjs` — PASS.
- `node scripts/verify-api-project-flow.mjs` — PASS (6 checks).
- `node scripts/verify-create-route-flow.mjs` — PASS.
- `node scripts/verify-project-result-route.mjs` — PASS (3 checks).
- `node scripts/verify-project-editor-route.mjs` — PASS (3 checks).
- `node scripts/verify-jianying-export.mjs` — PASS (4 checks).
- `npm run build` — PASS; existing >500 kB output-chunk advisory remains.
- `git diff --check` — PASS.

## Browser evidence

Playwright opened the local Vite application at `http://127.0.0.1:5174`.

- `/create` redirected unauthenticated users to `/login` and rendered the login form.
- `/projects/demo/result` redirected unauthenticated users to `/login`.
- `/projects/demo/editor` redirected unauthenticated users to `/login`.

This proves protected-route behavior, but cannot prove the authenticated Create → result → export loop because no locally runnable authenticated API session/data fixture was available. It also cannot prove `showSaveFilePicker` because the completed-result export button requires that authenticated completion-state flow and a real user gesture.

## Resolved findings

1. Create, result and editor routes now compile and are protected.
2. Create presents API cost and ready-only start gating.
3. Result API failures prevent download/export controls.
4. Editor has a concrete debounced-save caller and locks UI before render submission completes.

## Remaining blockers

1. Run a local authenticated API stack with a ready project and completed project fixture in a desktop Chrome or Edge session.
2. Click the completed result's “导出到剪映草稿” control and confirm the File System Access save picker plus streamed ZIP completion under a user gesture.

## Gate decision

Gate C remains blocked pending those two browser-level acceptance proofs. Task 19 must not start.
