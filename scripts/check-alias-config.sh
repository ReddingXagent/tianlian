#!/usr/bin/env bash
# 路径别名双源漂移守卫 (F231)
# tsconfig.compilerOptions.paths 与 package.json jest.moduleNameMapper 是同一语义的双源:
#   - tsconfig.paths 是 tsc/typecheck 的解析源
#   - jest.moduleNameMapper 是测试侧的解析源
# 只改一侧 → tsc 与 jest 解析分叉: 一侧通过一侧报错, 或解析到不同目录
# (metro 打包侧由 Expo tsconfigPaths 默认支持; 本守卫守住静态检查+测试两侧一致)
# 本守卫断言两侧别名集合与目标目录一致; 增删别名时两处同步修改
set -euo pipefail

cd "$(dirname "$0")/.."

node <<'EOF'
const fs = require('fs');

const ts = JSON.parse(fs.readFileSync('tsconfig.json', 'utf8'));
const pkg = JSON.parse(fs.readFileSync('package.json', 'utf8'));

const tsPaths = (ts.compilerOptions && ts.compilerOptions.paths) || {};
const jestMap = (pkg.jest && pkg.jest.moduleNameMapper) || {};

// 归一化 tsconfig paths: "@/*" -> { prefix: "@/", dir: "src/" }
const tsAliases = {};
for (const [alias, targets] of Object.entries(tsPaths)) {
  if (!Array.isArray(targets) || targets.length === 0) continue;
  if (!alias.endsWith('*')) continue; // 精确别名不在 jest 正则映射覆盖范围, 此处不处理
  tsAliases[alias.slice(0, -1)] = String(targets[0]).replace(/\*$/, '');
}

// 归一化 jest moduleNameMapper: "^@/(.*)$" -> { prefix: "@/", dir: "src/" }
const jestAliases = {};
for (const [pattern, target] of Object.entries(jestMap)) {
  const m = pattern.match(/^\^(.*?)\(\.\*\)\$$/);
  if (!m) continue;
  jestAliases[m[1]] = String(target).replace(/^<rootDir>\//, '').replace(/\$1$/, '');
}

const errs = [];
for (const [prefix, dir] of Object.entries(tsAliases)) {
  if (!(prefix in jestAliases)) {
    errs.push(`别名 ${prefix}* 仅 tsconfig.paths 声明, jest.moduleNameMapper 缺失`);
  } else if (jestAliases[prefix] !== dir) {
    errs.push(`别名 ${prefix}* 目标漂移: tsconfig=${dir} vs jest=${jestAliases[prefix]}`);
  }
}
for (const prefix of Object.keys(jestAliases)) {
  if (!(prefix in tsAliases)) {
    errs.push(`别名 ${prefix}* 仅 jest.moduleNameMapper 声明, tsconfig.paths 缺失`);
  }
}

if (errs.length > 0) {
  console.error('❌ 路径别名双源漂移:');
  for (const e of errs) console.error('   - ' + e);
  console.error('   tsconfig.paths 与 jest.moduleNameMapper 必须同步修改');
  process.exit(1);
}

const names = Object.keys(tsAliases).map((p) => p + '*');
console.log(`✅ 路径别名双源一致 (${names.length}项): ${names.join(', ') || '(无)'}`);
EOF
