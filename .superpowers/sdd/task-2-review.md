# Task 2 Review：Shared Accessible Language Switcher

## Review scope

- Reviewed `.superpowers/sdd/task-2-brief.md`, `.superpowers/sdd/task-2-report.md`, and `.superpowers/sdd/task-2-review.diff`.
- Inspected the resulting Task 2 source plus the Task 1 `I18nProvider`/locale contract needed to validate integration.
- Per instruction, did **not** rerun the reported build or test commands. Test status below is based on the supplied report and review diff.

## Verdicts

### Spec compliance：✅

The implementation satisfies the Task 2 brief and the global constraints:

- Defines exactly the three required locales: `zh-CN`, `en`, and `ja`, with the requested short names and self-names.
- Exposes the requested `LanguageSwitcher` props with matching defaults.
- Mounts the desktop switcher immediately before `.login-button` and the inline mobile switcher immediately before `.mobile-menu__login`.
- Keeps locale switching in application state/local storage; the switcher itself performs no navigation and the supplied browser verification asserts the pathname remains `/`.
- Implements native-button keyboard interaction, including menu opening, looping `ArrowUp`/`ArrowDown`, `Home`, `End`, `Escape`, and focus restoration.
- Implements outside-pointer dismissal and the requested ARIA surface: `menu`, `menuitem`, `aria-current`, `aria-haspopup`, `aria-expanded`, and the test id.
- Translates the requested public-header navigation, feedback, menu labels, accessible names, and login copy for all three locale resources.
- Provides minimum 44px switcher targets, visible focus rings, selected-check alignment, popover stacking, a three-column inline mobile layout, and hides the desktop switcher below 768px.
- Adds `verify:i18n` and covers browser-locale initialization, locale persistence, unchanged URL, keyboard traversal, Escape/focus restore, outside click, and the 390px mobile entries.
- Uses the existing in-house i18n context only; no third-party i18n package was introduced.
- Introduces no screenshot, base64, bitmap, canvas, or image-based UI reconstruction in the Task 2 changes.

### Code quality：Approved

The component is focused and maintainable: locale metadata is centralized, desktop and inline modes share selection state, event listeners are scoped to the open lifecycle and cleaned up, menu queries are confined to the component ref, and preview/browser cleanup is protected by `finally`. The verification script also avoids a fixed port and terminates the detached preview process group.

## Findings

### Critical

None.

### Important

None.

### Minor

None blocking or actionable within the Task 2 brief.

## Test and report assessment

- Supplied RED evidence is credible and matches the required initial failure: the browser assertion timed out because `language-switcher-trigger` did not exist.
- Supplied GREEN evidence reports successful build, 4/4 locale tests, successful Playwright verification, and two consecutive cleanup-sensitive verification runs.
- `git diff --check` is reported clean.
- The report explicitly identifies the existing bundle-size warning and dirty workspace without misclassifying either as a Task 2 regression.

## Final conclusion

Task 2 is ready for integration as reviewed. No source change request is required.
