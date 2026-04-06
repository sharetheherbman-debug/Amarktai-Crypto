# Frontend Build Proof

## Environment
- Node: v24.13.0
- npm: 11.6.2

## Commands

### `npm ci`
```
npm warn ERESOLVE overriding peer dependency
...
added 1500 packages, and audited 1501 packages in 16s

13 vulnerabilities (3 low, 4 moderate, 6 high)
```

### `npm run build`
```
> frontend@0.1.0 build
> npm run check:assets && craco build

✅ All asset references are valid!
Creating an optimized production build...
Compiled successfully.

File sizes after gzip:
  230.06 kB  build/static/js/main.77cf4fbd.js
  16.59 kB   build/static/css/main.da8e3f36.css
```
