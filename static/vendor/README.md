# Vendored Frontend Assets

This folder contains local copies of frontend runtime assets so Vision Training Studio can render in offline or CDN-blocked environments.

## Assets

- `chartjs/chart.umd.min.js`
  - Source: Chart.js `4.4.9`
  - Original CDN: `https://cdn.jsdelivr.net/npm/chart.js@4.4.9/dist/chart.umd.min.js`
- `dropzone/dropzone.min.js`
  - Source: Dropzone `5.9.3`
  - Original CDN: `https://cdnjs.cloudflare.com/ajax/libs/dropzone/5.9.3/min/dropzone.min.js`
- `fontawesome/`
  - Source: Font Awesome Free `6.4.0`
  - Original CDN: `https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/`
  - Includes CSS plus `.woff2` and `.ttf` webfont fallbacks.
- `fonts/inter/`
  - Source: Google Fonts Inter CSS and WOFF2 files
  - Original CSS: `https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap`

## Policy

Do not point production UI directly at CDN assets. Add or update local files here, then reference them from `static/index.html`.
