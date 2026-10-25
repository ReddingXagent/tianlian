// ESLint flat config — Expo 官方推荐 (eslint-config-expo/flat)
// 2026-07-31 lint 门控建立: 此前仓库零lint门控(F19/F45), 模板源自 station-app/ops-app
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
    // F241续打: 日期格式单一源守卫 — 新增日期显示点禁止内联toLocale*(设备locale漂移/参数双源),
    // 渲染侧一律走src/utils/format.ts(locale钉zh-CN); format.ts自身与测试豁免(预防式门控F220: 基线零违规)
    files: ['src/**/*.{ts,tsx}'],
    ignores: ['src/utils/format.ts', '**/__tests__/**', '**/*.test.{ts,tsx}'],
    rules: {
      'no-restricted-syntax': [
        'error',
        {
          selector:
            "CallExpression[callee.property.name=/^toLocale(String|DateString|TimeString)$/]",
          message:
            '日期显示一律走src/utils/format.ts(locale钉zh-CN), 禁止内联toLocale*(F241单一源守卫)',
        },
        {
          selector:
            "BinaryExpression[operator='/'] > MemberExpression[property.name='distance']",
          message:
            '距离显示一律走src/utils/format.ts的formatDistance, 禁止内联distance/1000(F253单一源守卫)',
        },
        {
          selector:
            "CallExpression[callee.property.name='toFixed'][callee.object.property.name=/^(amount|balance|pricePerKwh|serviceFee|paidAmount|value|couponDiscount)$/]",
          message:
            '金额显示一律走src/utils/format.ts的formatMoney, 禁止内联金额类属性.toFixed(2)(F259单一源守卫)',
        },
        {
          selector:
            "CallExpression[callee.property.name='toFixed'][callee.object.property.name=/^(energy|totalEnergy)$/]",
          message:
            '电量显示一律走src/utils/format.ts的formatEnergy, 禁止内联energy/totalEnergy.toFixed(F265单一源守卫)',
        },
      ],
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
    // 测试文件放开 jest 全局 + jest惯用法豁免
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
    rules: {
      // mock组件(箭头函数)无需displayName
      'react/display-name': 'off',
      // jest.mock会被babel提升到imports之前, import写在mock之后是jest惯用法
      'import/first': 'off',
      // jest.mock工厂函数内 require() 是 RN 测试标准模式
      '@typescript-eslint/no-require-imports': 'off',
      // axios mock通过默认导入访问.create是测试惯用法
      'import/no-named-as-default-member': 'off',
    },
  },
]);
