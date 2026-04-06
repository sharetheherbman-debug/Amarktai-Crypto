#!/usr/bin/env node
/**
 * verify-build.js
 *
 * Asserts that all JS/CSS asset references embedded in the built index.html
 * point to files that actually exist in the build directory.
 *
 * Usage:
 *   node verify-build.js [build_dir]
 *   build_dir defaults to ./build (relative to cwd)
 *
 * Exit 0 = all referenced assets exist
 * Exit 1 = one or more referenced assets are missing
 */

'use strict';

const fs = require('fs');
const path = require('path');

const buildDir = process.argv[2]
  ? path.resolve(process.argv[2])
  : path.resolve(process.cwd(), 'build');

const indexPath = path.join(buildDir, 'index.html');

if (!fs.existsSync(indexPath)) {
  console.error(`ERROR: index.html not found at ${indexPath}`);
  process.exit(1);
}

const html = fs.readFileSync(indexPath, 'utf8');

// Extract all /static/... and ./static/... references from script src, link href, and img src
// Matches both double-quoted and single-quoted attribute values.
const refPattern = /(?:src|href)=["']([^"']*\/static\/[^"']*)["']/g;
const refs = new Set();
let match;
while ((match = refPattern.exec(html)) !== null) {
  refs.add(match[1]);
}

if (refs.size === 0) {
  console.warn('WARN: No /static/ asset references found in index.html');
  console.log('Build verification: PASS (no static refs to verify)');
  process.exit(0);
}

let missing = 0;
for (const ref of refs) {
  // Normalize: remove leading / or ./
  const normalized = ref.replace(/^\.?\//, '');
  const filePath = path.join(buildDir, normalized);

  if (!fs.existsSync(filePath)) {
    console.error(`MISSING: ${ref}`);
    console.error(`         expected at: ${filePath}`);
    missing++;
  } else {
    console.log(`OK: ${ref}`);
  }
}

if (missing > 0) {
  console.error(`\nFAIL: ${missing} asset(s) referenced in index.html are missing from the build directory.`);
  process.exit(1);
} else {
  console.log(`\nPASS: All ${refs.size} referenced asset(s) exist in ${buildDir}`);
  process.exit(0);
}
