/**
 * metro.config.js — Metro 解析器对齐 tsconfig paths (F1972)
 *
 * 背景: F1446 接入 @tianlian/shared-ui 后, tsc/jest 经 paths/moduleNameMapper 解析,
 * 但 metro (expo export / expo start) 不认 tsconfig paths, 依赖 node_modules 符号链接,
 * 符号链接为本地手工产物不入 git, CI 上 expo export 必挂。
 *
 * 方案:metro resolver.extraNodeModules 映射 + watchFolders 把 tianlian-shared 纳入监听,
 * 摆脱符号链接依赖; expo export 按此解析出包。
 */
const { getDefaultConfig } = require('expo/metro-config');
const path = require('path');

const projectRoot = __dirname;
const sharedRoot = path.resolve(projectRoot, '../tianlian-shared');

const config = getDefaultConfig(projectRoot);

// watchFolders: 让 metro 能解析项目根外的 shared 包(符号链接与 CI 均可解析)
config.watchFolders = [...(config.watchFolders || []), sharedRoot];

// extraNodeModules: 显式映射 @tianlian/* 包名到真实目录, 不依赖 node_modules 符号链接
config.resolver.extraNodeModules = {
  ...(config.resolver.extraNodeModules || {}),
  '@tianlian/shared-ui': path.resolve(sharedRoot, 'shared-ui/src'),
  '@tianlian/shared-types': path.resolve(sharedRoot, 'shared-types/src'),
};

module.exports = config;
