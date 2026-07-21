# Gate C Re-evaluation — 2026-07-20

## Verdict

**Blocked on one final evidence item.** The authenticated business API, browser result flow, user-click File System Access invocation, and streamed ZIP writer path are demonstrated. The native macOS save picker itself was not visibly completed by automation.

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

### Authenticated isolated-stack evidence

An isolated SQLite migration copy plus the locally available Redis service were used to run the real FastAPI application; a completed project, artifact, and editor revision were seeded only in that temporary database. The browser used the real login API and real result/manifest endpoints through a local same-origin proxy.

- FastAPI readiness returned 200; real `/auth/login` returned 200.
- Desktop Google Chrome reported native `showSaveFilePicker` as a function.
- The real UI logged in, loaded `/create`, loaded the completed result, and user-clicked “导出到剪映草稿”.
- FastAPI logged real `POST /projects/gate-c-completed/exports/jianying-manifest` with 200.
- A controlled writable received the actual File System Access call with suggested name `gate-c-jianying.zip`, five ZIP stream writes, and `close`.

The controlled writable proves the application call path and streamed completion but is not a claim that the operating-system picker became visible or that a user selected a native destination.

## Resolved findings

1. Create, result and editor routes now compile and are protected.
2. Create presents API cost and ready-only start gating.
3. Result API failures prevent download/export controls.
4. Editor has a concrete debounced-save caller and locks UI before render submission completes.

## Remaining blockers

1. In a headed desktop Chrome or Edge session, visibly confirm the native save picker and finish a user-selected destination after clicking the completed result's “导出到剪映草稿” control.

## Gate decision

**Passed with user-approved evidence exception.** On 2026-07-20, the user explicitly accepted the existing authentic API, browser, File System Access invocation, and streamed ZIP evidence in place of a visible native-picker destination-selection capture. The native-picker visual proof remains a documented residual limitation, not a failed product path. Task 19 is unblocked.
