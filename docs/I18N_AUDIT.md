# i18n DOM Audit

`scripts\build.bat` runs `node --check` on `scripts\i18n_dom_audit.mjs` so the audit tool is covered by CI syntax checks.

Install the isolated Playwright runtime:

```bat
cmd /c npm install --prefix tools\i18n-audit
```

To run the full DOM audit, start the source server first:

```bat
scripts\i18n_dom_audit.bat http://127.0.0.1:18080 zh-TW
```

To audit routed workspaces instead of only the initial page, pass a comma-separated page list. Each target can be scoped to `cnn` or `rnn` so the script switches the training mode before clicking the page navigation item:

```bat
scripts\i18n_dom_audit.bat http://127.0.0.1:18080 zh-TW --pages cnn:dataset,cnn:training,cnn:model-compare,cnn:inference,cnn:auto-labeling,rnn:sequence-dataset,rnn:training,rnn:model-compare,rnn:sequence-test,rnn:export --fail-on-issues
```

If CI already provides a shared Playwright install, set `PLAYWRIGHT_NODE_MODULES=C:\path\to\node_modules` to override the local fallback.

The scanner checks visible text, placeholders, titles, `aria-label`, `alt`, and common tooltip attributes. Use the output as a page-level cleanup queue for untranslated or mixed-language UI text.
