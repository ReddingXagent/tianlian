#!/usr/bin/env node
/**
 * CI lint 门控 — 猴王自驱 lint 加固轮 (2026-08-03)
 * 统一入口: eslint + 结构检查
 * 用法: node scripts/lint-ci.js  (有错误退1)
 */
const { execSync } = require('child_process');

const steps = [
  { name: 'eslint', cmd: 'npm run lint' },
  { name: 'structure', cmd: 'node scripts/check-mp-structure.js' },
];

let failed = false;
for (const step of steps) {
  console.log(`\n▶ ${step.name} ...`);
  try {
    execSync(step.cmd, { stdio: 'inherit', cwd: process.cwd() });
    console.log(`✅ ${step.name} passed`);
  } catch {
    console.error(`❌ ${step.name} failed`);
    failed = true;
  }
}

if (failed) {
  console.error('\n🚫 Lint CI failed');
  process.exit(1);
}
console.log('\n🎉 All lint checks passed');
