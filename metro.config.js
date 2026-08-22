/**
 * metro.config.js — Metro 解析器对齐 tsconfig paths (F1995)
 *
 * 背景: F1446 接入 @tianlian/shared-ui 后, tsc/jest 经 paths/moduleNameMapper 解析,
 * 但 metro (expo export / expo start) 不认 tsconfig paths, 依赖 node_modules 符号链接,
 * 符号链接为本地手工产物不入 git, CI 上 expo export 必挂。
 *
 * 方案: resolver.extraNodeModules 映射 @tianlian/* 到 shared 真实源码目录 +
 * watchFolders 纳入监听 + resolver.nodeModulesPaths 显式指定 projectRoot/node_modules。
 *
 * 根因(F1995 破解): shared-ui/src 经 babel-preset-expo 变换生成的 @babel/runtime/helpers/*
 * 是相对 shared 源文件解析的缺 module-root 裸依赖。metro 默认 hierarchical lookup 沿 sharedRoot
 * 向上爬只得到 tianlian-shared/../../node_modules(CI 上不存在), 找不到项目自己的
 * node_modules/@babel/runtime。显式指定 projectRoot/node_modules 后 runtime helper 从
 * 本仓自己 node_modules 解析, 彻底摆脱对 tianlian-shared/node_modules 软链的巧合依赖。
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

// nodeModulesPaths: 显式把 projectRoot 自己的 node_modules 加入裸依赖解析路径
config.resolver.nodeModulesPaths = [
  path.resolve(projectRoot, 'node_modules'),
];

module.exports = config;