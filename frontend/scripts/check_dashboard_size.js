const fs = require('fs');
const path = require('path');

const FILES = [
  'src/pages/Dashboard.js',
  'src/pages/Landing.js',
  'src/pages/Login.js',
  'src/pages/Register.js',
  'src/App.js',
];

const DASHBOARD_LINE_LIMIT = 800;

console.log('=== Frontend File Line Counts ===\n');

FILES.forEach((file) => {
  const fullPath = path.resolve(__dirname, '..', file);
  if (!fs.existsSync(fullPath)) {
    console.log(`  ${file}: FILE NOT FOUND`);
    return;
  }
  const lines = fs.readFileSync(fullPath, 'utf8').split('\n').length;
  console.log(`  ${file}: ${lines} lines`);
});

// Dashboard size warning
const dashboardPath = path.resolve(__dirname, '..', 'src/pages/Dashboard.js');
if (fs.existsSync(dashboardPath)) {
  const dashboardLines = fs.readFileSync(dashboardPath, 'utf8').split('\n').length;
  console.log('');
  if (dashboardLines > DASHBOARD_LINE_LIMIT) {
    console.warn(
      `WARNING: Dashboard.js has ${dashboardLines} lines (limit: ${DASHBOARD_LINE_LIMIT})`
    );
    process.exitCode = 1;
  } else {
    console.log(
      `OK: Dashboard.js is within the ${DASHBOARD_LINE_LIMIT}-line limit (${dashboardLines} lines)`
    );
  }
}
