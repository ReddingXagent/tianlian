// ESLint flat config — Expo 官方推荐 (eslint-config-expo/flat)
// 2026-07-31 lint 门控建立: 此前仓库零lint门控, tsc之外无静态检查
const { defineConfig } = require('eslint/config');
const expoConfig = require('eslint-config-expo/flat');

module.exports = defineConfig([
  expoConfig,
  {
    // 生成物与构建配置不走lint
    ignores: ['dist/**', 'web-build/**', '*.config.js'],
  },
  {
    // 分诊降级: screens的数据加载模式(effect内loadData→setState)是有意为之,
    // 5个screen无测试覆盖, 重构风险高 → 降warn跟踪(F18), 待screen测试补齐后逐处修复
    rules: {
      'react-hooks/set-state-in-effect': 'warn',
    },
  },
  {
    // 测试文件放开 jest 全局 + jest惯用法豁免
    files: ['**/__tests__/**', '**/*.test.{ts,tsx}'],
    rules: {
      // mock组件(箭头函数)无需displayName
      'react/display-name': 'off',
      // jest.mock会被babel提升到imports之前, import写在mock之后是jest惯用法
      'import/first': 'off',
      // jest.mock 工厂函数内 require() 是 RN 测试标准模式
      '@typescript-eslint/no-require-imports': 'off',
      // axios mock通过默认导入访问.create是测试惯用法
      'import/no-named-as-default-member': 'off',
    },
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
