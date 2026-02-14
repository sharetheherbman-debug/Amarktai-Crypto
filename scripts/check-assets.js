#!/usr/bin/env node
/**
 * Asset Reference Validator
 * 
 * Scans frontend code for /assets/... references and validates
 * that all referenced assets exist in public/assets/
 * 
 * Fails CI/build if referenced assets are missing.
 */

const fs = require('fs');
const path = require('path');
const { exec } = require('child_process');
const { promisify } = require('util');

const execAsync = promisify(exec);

const FRONTEND_DIR = path.join(__dirname, '..', 'frontend');
const PUBLIC_ASSETS_DIR = path.join(FRONTEND_DIR, 'public', 'assets');
const SRC_DIR = path.join(FRONTEND_DIR, 'src');
const PUBLIC_DIR = path.join(FRONTEND_DIR, 'public');

// Asset reference patterns
const ASSET_PATTERNS = [
  /["'`]\/assets\/([^"'`\s]+)["'`]/g,  // "/assets/file.ext"
  /src=["']\/assets\/([^"']+)["']/g,   // src="/assets/file.ext"
  /href=["']\/assets\/([^"']+)["']/g,  // href="/assets/file.ext"
  /url\(['"]?\/assets\/([^'")\s]+)['"]?\)/g  // url('/assets/file.ext')
];

async function findAssetReferences() {
  const references = new Set();
  
  try {
    // Search in src/ directory
    const { stdout: srcResults } = await execAsync(
      `grep -r "/assets/" --include="*.js" --include="*.jsx" --include="*.css" "${SRC_DIR}" || true`
    );
    
    // Search in public/index.html
    const { stdout: publicResults } = await execAsync(
      `grep "/assets/" "${PUBLIC_DIR}/index.html" || true`
    );
    
    const allResults = srcResults + '\n' + publicResults;
    
    // Extract asset paths using patterns
    for (const pattern of ASSET_PATTERNS) {
      let match;
      while ((match = pattern.exec(allResults)) !== null) {
        if (match[1]) {
          references.add(match[1]);
        }
      }
    }
  } catch (error) {
    // grep returns non-zero if no matches, which is fine
    if (error.code !== 1) {
      console.error('Error searching for asset references:', error.message);
    }
  }
  
  return Array.from(references).sort();
}

function getExistingAssets() {
  const assets = [];
  
  try {
    if (!fs.existsSync(PUBLIC_ASSETS_DIR)) {
      console.warn(`⚠️  Warning: ${PUBLIC_ASSETS_DIR} does not exist`);
      return assets;
    }

    const walkDir = (dir) => {
      const entries = fs.readdirSync(dir, { withFileTypes: true });
      for (const entry of entries) {
        const entryPath = path.join(dir, entry.name);
        if (entry.isDirectory()) {
          walkDir(entryPath);
        } else if (entry.isFile() && entry.name !== '.gitkeep' && entry.name !== 'README_ASSETS.txt') {
          const stat = fs.statSync(entryPath);
          assets.push({
            name: entry.name,
            size: stat.size,
            path: entryPath,
            relativePath: path.relative(PUBLIC_ASSETS_DIR, entryPath)
          });
        }
      }
    };

    walkDir(PUBLIC_ASSETS_DIR);
  } catch (error) {
    console.error('Error reading assets directory:', error.message);
  }
  
  return assets;
}

async function validateAssets() {
  console.log('🔍 Scanning frontend code for asset references...\n');
  
  const references = await findAssetReferences();
  const existingAssets = getExistingAssets();
  const existingAssetNames = existingAssets.map(a => a.name);
  
  console.log(`Found ${references.length} asset references in code:`);
  references.forEach(ref => console.log(`  - /assets/${ref}`));
  console.log();
  
  console.log(`Found ${existingAssets.length} assets in public/assets/:`);
  existingAssets.forEach(asset => {
    const sizeKB = (asset.size / 1024).toFixed(2);
    const status = asset.size === 0 ? '⚠️  EMPTY' : '✅';
    const assetLabel = asset.relativePath || asset.name;
    console.log(`  ${status} ${assetLabel} (${sizeKB} KB)`);
  });
  console.log();
  
  // Check for missing assets
  const missingAssets = [];
  const emptyAssets = [];
  
  for (const ref of references) {
    const fileName = path.basename(ref);
    const asset = existingAssets.find(a => a.name === fileName);
    
    if (!asset) {
      missingAssets.push(ref);
    } else if (asset.size === 0) {
      emptyAssets.push(ref);
    }
  }
  
  // Check for unused assets
  const unusedAssets = existingAssets.filter(asset => {
    return !references.some(ref => path.basename(ref) === asset.name);
  });
  
  // Report results
  let hasErrors = false;
  
  if (missingAssets.length > 0) {
    console.error('❌ MISSING ASSETS (referenced in code but not found):');
    missingAssets.forEach(asset => console.error(`   - /assets/${asset}`));
    console.error();
    hasErrors = true;
  }
  
  if (emptyAssets.length > 0) {
    console.warn('⚠️  EMPTY ASSETS (0 bytes - likely placeholders):');
    emptyAssets.forEach(asset => console.warn(`   - /assets/${asset}`));
    console.warn();
    hasErrors = true;
  }
  
  if (unusedAssets.length > 0) {
    console.log('ℹ️  Unused assets (in public/assets/ but not referenced):');
    unusedAssets.forEach(asset => console.log(`   - ${asset.relativePath || asset.name}`));
    console.log();
  }
  
  if (!hasErrors) {
    console.log('✅ All asset references are valid!\n');
    return 0;
  } else {
    console.error('❌ Asset validation failed!\n');
    console.error('To fix:');
    console.error('  1. Copy missing assets to frontend/public/assets/');
    console.error('  2. Replace empty placeholder files with real assets');
    console.error('  3. Remove references to assets that should not exist\n');
    return 1;
  }
}

// Run validation
validateAssets()
  .then(exitCode => process.exit(exitCode))
  .catch(error => {
    console.error('Fatal error:', error);
    process.exit(1);
  });
