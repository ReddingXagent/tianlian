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
      // 基础安全规则
      'no-redeclare': 'error',
      'no-dupe-keys': 'error',
      'no-debugger': 'error',
      'no-duplicate-case': 'error',
      // 安全防护规则 (F113, 2026-08-03 lint加固轮)
      'no-eval': 'error',
      'no-implied-eval': 'error',
      'no-prototype-builtins': 'error',
      'no-self-assign': 'error',
      'no-self-compare': 'error',
      'no-shadow-restricted-names': 'error',
      'no-sparse-arrays': 'error',
      'no-unreachable': 'error',
      'no-useless-escape': 'error',
      'no-inner-declarations': 'error',
      'no-misleading-character-class': 'error',
      'no-async-promise-executor': 'error',
      'no-class-assign': 'error',
      'no-const-assign': 'error',
      'no-this-before-super': 'error',
      'require-yield': 'error',
      // 代码质量防回归规则 (2026-08-03 猴王自驱lint轮, 加入时全仓0违规)
      'eqeqeq': 'error',                // 强制===, 防类型隐式转换bug
      'no-var': 'error',                // 禁var, 统一let/const作用域
      'prefer-const': 'error',          // 未重赋值变量用const
      'no-fallthrough': 'error',        // 防switch穿透
      'guard-for-in': 'error',          // for-in需hasOwnProperty防原型链污染
      'radix': 'error',                 // parseInt必须带进制参数
      'no-return-assign': 'error',      // 防return中误写=为==
      'no-useless-return': 'error',     // 禁无意义return
      // 代码质量防回归规则第二批 (2026-08-04 猴王自驱lint轮, 加入时全仓0违规)
      'no-implicit-coercion': 'error',  // 禁''+x等隐式转换, 用String()/Number() (util.js padZero已顺手修复)
      'no-empty-function': 'error',     // 禁空函数, 防静默吞错 (fire-and-forget需显式disable+注释)
      'no-unneeded-ternary': 'error',   // 禁cond?true:false冗余三元
      'no-lonely-if': 'error',          // else中单独if应写else-if
      'prefer-object-spread': 'error',  // Object.assign({},x)→{...x}
      'no-useless-computed-key': 'error', // 禁无意义计算属性键
      'no-dupe-else-if': 'error',       // 防if/else-if重复条件
      'default-case': 'error',          // switch必须有default
      'no-alert': 'error',              // 禁alert/confirm/prompt(小程序环境本无, 防误用)
      'no-multi-str': 'error',          // 禁反斜杠多行字符串
      'yoda': 'error',                  // 禁尤达条件(1===x)
      // 代码质量防回归规则第三批 (2026-08-04 猴王自驱lint轮, 加入时全仓0违规)
      'no-template-curly-in-string': 'error',   // 普通字符串里写${}必是笔误
      'no-unmodified-loop-condition': 'error',  // 循环条件永不变更=死循环隐患
      'array-callback-return': 'error',         // map/filter/reduce回调必须有return
      'no-useless-call': 'error',               // 无意义call/apply
      'no-useless-concat': 'error',             // 禁字面量' '+'b'拼接
      'no-else-return': 'error',                // return后的else冗余
      'no-promise-executor-return': 'error',    // executor返回值无意义, 防误以为resolve
      'no-unsafe-optional-chaining': 'error',   // 防(undefined)?.x()类型错误
      'no-case-declarations': 'error',          // switch case内声明需块级作用域
      'no-sequences': 'error',                  // 防逗号表达式歧义
      'no-new-wrappers': 'error',               // 禁new String/Number/Boolean包装对象
      'prefer-regex-literals': 'error',         // new RegExp('字面量')→正则字面量
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
