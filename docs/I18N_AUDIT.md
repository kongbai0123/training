# i18n DOM Audit

`scripts\build.bat` runs `node --check` on `scripts\i18n_dom_audit.mjs` so the audit tool is covered by CI syntax checks.

To run the full DOM audit, start the source server first and provide a Playwright runtime:

```bat
set PLAYWRIGHT_NODE_MODULES=C:\path\to\node_modules
scripts\i18n_dom_audit.bat http://127.0.0.1:18080 zh-TW
```

The scanner checks visible text, placeholders, titles, `aria-label`, `alt`, and common tooltip attributes. Use the output as a page-level cleanup queue for untranslated or mixed-language UI text.
