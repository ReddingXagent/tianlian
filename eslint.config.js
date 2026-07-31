// ESLint flat config — Expo 官方推荐 (eslint-config-expo/flat)
// 2026-07-31 猴王自驱lint轮建立: 此前仓库零lint门控(F19/F45), 模板源自 station-app/ops-app
const { defineConfig } = require('eslint/config');
const expoConfig = require('eslint-config-expo/flat');

module.exports = defineConfig([
  expoConfig,
  {
    // 生成物与构建配置不走lint
    ignores: ['dist/**', 'web-build/**', 'coverage/**', '*.config.js'],
  },
  {
    // 分诊降级: 各screen数据加载模式(effect内fetch→setState)是有意为之,
    // 7处同构(同station F18/F28), 重构风险高 → 降warn跟踪, 待screen测试补齐后逐处评估
    rules: {
      'react-hooks/set-state-in-effect': 'warn',
    },
  },
  {
    // Node脚本(部署门控等)放开node全局
    files: ['scripts/**/*.js'],
    languageOptions: {
      globals: {
        require: 'readonly',
        module: 'writable',
        process: 'readonly',
        console: 'readonly',
        __dirname: 'readonly',
        Buffer: 'readonly',
      },
    },
  },
  {
    // 测试文件放开 jest 全局
    files: ['**/__tests__/**', '**/*.test.{ts,tsx}'],
    languageOptions: {
      globals: {
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
]);
