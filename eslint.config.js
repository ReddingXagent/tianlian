// ESLint flat config — 微信小程序原生(纯JS+CommonJS)
// 2026-07-31 猴王自驱lint轮建立: 此前仓库零lint门控(F19), 模板思路源自 station-app/ops-app
const js = require('@eslint/js');

// 微信小程序全局
const wxGlobals = {
  wx: 'readonly',
  App: 'readonly',
  Page: 'readonly',
  Component: 'readonly',
  Behavior: 'readonly',
  getApp: 'readonly',
  getCurrentPages: 'readonly',
  requirePlugin: 'readonly',
};

module.exports = [
  js.configs.recommended,
  {
    // 依赖与生成物不走lint
    ignores: ['node_modules/**', 'miniprogram_npm/**', 'coverage/**'],
  },
  {
    files: ['**/*.js'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'commonjs',
      globals: {
        ...wxGlobals,
        console: 'readonly',
        setTimeout: 'readonly',
        clearTimeout: 'readonly',
        setInterval: 'readonly',
        clearInterval: 'readonly',
        Promise: 'readonly',
        URL: 'readonly',
      },
    },
    rules: {
      // F19路线: warn→error 收窄 (2026-08-03 猴王自驱lint轮)
      // no-unused-vars: 0违规→升级error
      'no-unused-vars': ['error', { argsIgnorePattern: '^_', caughtErrors: 'none' }],
      'no-undef': 'error',
      'no-constant-condition': ['error', { checkLoops: false }],
      // 新增安全规则
      'no-redeclare': 'error',
      'no-dupe-keys': 'error',
      'no-debugger': 'error',
      'no-duplicate-case': 'error',
    },
  },
  {
    // 测试文件放开 jest 全局
    files: ['**/__tests__/**', '**/*.test.js'],
    languageOptions: {
      globals: {
        // jest 跑在 node 环境
        __dirname: 'readonly',
        require: 'readonly',
        module: 'writable',
        process: 'readonly',
        Buffer: 'readonly',
        describe: 'readonly',
        it: 'readonly',
        test: 'readonly',
        expect: 'readonly',
        jest: 'readonly',
        beforeEach: 'readonly',
        afterEach: 'readonly',
        beforeAll: 'readonly',
        afterAll: 'readonly',
      },
    },
  },
  {
    // scripts 目录跑在 node 下
    files: ['scripts/**/*.js'],
    languageOptions: {
      globals: {
        process: 'readonly',
        require: 'readonly',
        module: 'writable',
        __dirname: 'readonly',
      },
    },
  },
];
