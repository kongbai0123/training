@echo off
setlocal
cd /d "%~dp0\.."
node scripts\i18n_dom_audit.mjs %*
