// ESLint flat config — Expo 官方推荐 (eslint-config-expo/flat)
// 2026-07-31 猴王自驱lint轮建立: 此前仓库零lint门控(F19), 模板源自 ops-app
const { defineConfig } = require('eslint/config');
const expoConfig = require('eslint-config-expo/flat');

module.exports = defineConfig([
  expoConfig,
  {
    // 生成物与构建配置不走lint
    ignores: ['dist/**', 'web-build/**', '*.config.js'],
  },
  {
    // 分诊降级: 各screen数据加载模式(effect内fetch→setState)是有意为之,
    // 10处同构, 重构风险高 → 降warn跟踪(F28), 待screen测试补齐后逐处评估
    rules: {
      'react-hooks/set-state-in-effect': 'warn',
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
