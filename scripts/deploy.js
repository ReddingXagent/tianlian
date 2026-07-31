#!/usr/bin/env node
/**
 * 微信小程序部署门控脚本 (miniprogram-ci 上传体验版)
 * 流程: 结构门控 → appid校验 → 上传密钥校验 → 上传(--check 在上传前止步)
 * 用法:
 *   node scripts/deploy.js --check                 # 仅验证部署管线就绪(不上传)
 *   node scripts/deploy.js                         # 正式上传(需真appid + 密钥)
 *   node scripts/deploy.js --version=1.2.0 --robot=2 --desc="修复X"
 * 密钥: private-key/<appid>.key (小程序后台→开发设置→生成并下载代码上传密钥), 或 env MP_KEY_PATH
 * 退出码: 0=成功/就绪 1=门控失败或运行错误 2=appid占位(待丁哥) 3=缺上传密钥
 */
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const ROOT = path.resolve(__dirname, '..');
const PLACEHOLDER_APPID = 'wx0000000000000000';

function parseArgs(argv) {
  const args = { check: false, version: null, desc: null, robot: 1 };
  for (const a of argv.slice(2)) {
    if (a === '--check') args.check = true;
    else if (a.startsWith('--version=')) args.version = a.slice(10);
    else if (a.startsWith('--desc=')) args.desc = a.slice(7);
    else if (a.startsWith('--robot=')) args.robot = Number(a.slice(8)) || 1;
    else {
      console.error(`未知参数: ${a}`);
      process.exit(1);
    }
  }
  return args;
}

function runStructureGate() {
  console.log('▶ 步骤1/4 结构门控...');
  const r = spawnSync(process.execPath, [path.join(__dirname, 'check-mp-structure.js')], {
    stdio: 'inherit',
  });
  if (r.status !== 0) {
    console.error('✗ 结构门控未通过, 部署中止');
    process.exit(1);
  }
}

function loadAppid() {
  const proj = JSON.parse(fs.readFileSync(path.join(ROOT, 'project.config.json'), 'utf8'));
  return proj.appid;
}

function gitDesc() {
  try {
    const branch = spawnSync('git', ['rev-parse', '--abbrev-ref', 'HEAD'], { cwd: ROOT }).stdout.toString().trim();
    const sha = spawnSync('git', ['rev-parse', '--short', 'HEAD'], { cwd: ROOT }).stdout.toString().trim();
    if (branch && sha) return `${branch}@${sha} ${new Date().toISOString()}`;
  } catch { /* 非git环境降级 */ }
  return new Date().toISOString();
}

async function main() {
  const args = parseArgs(process.argv);

  runStructureGate();

  console.log('▶ 步骤2/4 appid校验...');
  const appid = loadAppid();
  if (!appid || appid === PLACEHOLDER_APPID) {
    console.error('✗ appid 为占位符 wx0000000000000000, 无法上传');
    console.error('  → 需丁哥在微信公众平台注册小程序并提供真 appid, 替换 project.config.json');
    process.exit(2);
  }
  console.log(`  appid: ${appid}`);

  console.log('▶ 步骤3/4 上传密钥校验...');
  const keyPath = process.env.MP_KEY_PATH || path.join(ROOT, 'private-key', `${appid}.key`);
  if (!fs.existsSync(keyPath)) {
    console.error(`✗ 上传密钥缺失: ${path.relative(ROOT, keyPath)}`);
    console.error('  → 小程序后台 → 开发设置 → 小程序代码上传: 生成密钥并下载, 放置到上述路径(已gitignore)');
    process.exit(3);
  }
  console.log(`  密钥: ${path.relative(ROOT, keyPath)}`);

  if (args.check) {
    console.log('✔ 部署管线就绪 (--check 模式, 未上传)');
    process.exit(0);
  }

  console.log('▶ 步骤4/4 miniprogram-ci 上传...');
  let ci;
  try {
    ci = require('miniprogram-ci');
  } catch {
    console.error('✗ 未安装 miniprogram-ci: npm install --save-dev miniprogram-ci');
    process.exit(1);
  }
  const pkg = JSON.parse(fs.readFileSync(path.join(ROOT, 'package.json'), 'utf8'));
  const version = args.version || pkg.version;
  const desc = args.desc || gitDesc();
  const project = new ci.Project({
    projectPath: ROOT,
    appid,
    privateKeyPath: keyPath,
    ignores: ['node_modules/**/*', 'coverage/**/*', 'scripts/**/*'],
  });
  await ci.upload({
    project,
    version,
    desc,
    robot: args.robot,
    setting: { es6: true, es7: true, minify: true, minifyWXML: true, minifyWXSS: true },
  });
  console.log(`✔ 上传完成: v${version} robot#${args.robot}`);
  console.log(`  描述: ${desc}`);
  console.log('  → 微信公众平台 → 版本管理 → 选体验版/提交审核');
}

main().catch((e) => {
  console.error(`✗ 部署失败: ${e.message}`);
  process.exit(1);
});
