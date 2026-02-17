#!/usr/bin/env node
/**
 * Validate Dashboard Section Files
 * 
 * Quick smoke test to ensure all section files:
 * - Have balanced braces
 * - Export a component
 * - Don't have obvious syntax errors
 */

const fs = require('fs');
const path = require('path');

const sectionsDir = path.join(__dirname, '../src/pages/dashboard/sections');
const sections = [
  'LiveTradesSection.js',
  'FetchAISection.js',
  'FlokxSection.js',
  'SystemModeSection.js',
  'ApiSetupSection.js',
  'OverviewSection.js',
  'WelcomeSection.js',
  'ProfileSection.js',
  'AdminPanelSection.js',
  'BotManagementSection.js',
  'ProfitsSection.js',
  'CountdownSection.js',
  'WalletHubSection.js',
  'MetricsWithTabsSection.js',
  'FlokxAlertsSection.js'
];

let errors = 0;

console.log('🔍 Validating Dashboard Section Files...\n');

sections.forEach(section => {
  const filePath = path.join(sectionsDir, section);
  
  if (!fs.existsSync(filePath)) {
    console.log(`❌ ${section} - File not found`);
    errors++;
    return;
  }
  
  const content = fs.readFileSync(filePath, 'utf8');
  
  // Check for balanced braces
  const openBraces = (content.match(/{/g) || []).length;
  const closeBraces = (content.match(/}/g) || []).length;
  
  if (openBraces !== closeBraces) {
    console.log(`❌ ${section} - Unbalanced braces (${openBraces} open, ${closeBraces} close)`);
    errors++;
    return;
  }
  
  // Check for export
  if (!content.includes('export default')) {
    console.log(`❌ ${section} - Missing export default`);
    errors++;
    return;
  }
  
  // Check for React import
  if (!content.includes("import React")) {
    console.log(`⚠️  ${section} - Missing React import (may be okay)`);
  }
  
  console.log(`✅ ${section}`);
});

console.log(`\n${'='.repeat(60)}`);
if (errors === 0) {
  console.log('✅ All section files validated successfully!');
  process.exit(0);
} else {
  console.log(`❌ ${errors} section file(s) had validation errors`);
  process.exit(1);
}
