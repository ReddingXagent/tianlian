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
      // 注: recommended已error的规则(22条)不再重复声明(F189配置卫生轮去重), 仅保留带选项覆盖的
      'no-unused-vars': ['error', { argsIgnorePattern: '^_', caughtErrors: 'none' }],
      'no-constant-condition': ['error', { checkLoops: false }],
      // 安全防护规则 (F113, 2026-08-03 lint加固轮; recommended未含部分)
      'no-eval': 'error',
      'no-implied-eval': 'error',
      'no-self-compare': 'error',
      'no-inner-declarations': 'error',
      // 代码质量防回归规则 (2026-08-03 猴王自驱lint轮, 加入时全仓0违规)
      'eqeqeq': 'error',                // 强制===, 防类型隐式转换bug
      'no-var': 'error',                // 禁var, 统一let/const作用域
      'prefer-const': 'error',          // 未重赋值变量用const
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
      'no-sequences': 'error',                  // 防逗号表达式歧义
      'no-new-wrappers': 'error',               // 禁new String/Number/Boolean包装对象
      'prefer-regex-literals': 'error',         // new RegExp('字面量')→正则字面量
      // 代码质量防回归规则第四批 (2026-08-04 猴王自驱lint轮, 加入时全仓0违规)
      'no-throw-literal': 'error',              // throw必须是Error对象, 禁throw字符串/字面量
      'no-unreachable-loop': 'error',           // 循环体最多执行一次=死循环/逻辑错误
      'no-unused-expressions': 'error',         // 禁无副作用孤立表达式, 防漏写调用
      'require-await': 'error',                 // async函数必须含await, 防无意义异步包装
      'no-multi-assign': 'error',               // 禁a=b=c链式赋值, 防作用域意外
      'no-extra-bind': 'error',                 // 禁无this引用的多余.bind()
      'no-useless-rename': 'error',             // 禁解构/import同名无意义重命名
      'no-array-constructor': 'error',          // 禁new Array()歧义构造, 用字面量
      'prefer-numeric-literals': 'error',       // parseInt('0x1a')等→数值字面量
      'no-proto': 'error',                      // 禁__proto__(原型链污染风险), 用Object.getPrototypeOf
      'no-new-func': 'error',                   // 禁new Function()动态构造(等同eval)
      // 代码质量防回归规则第五批 (2026-08-04 猴王自驱lint轮, 候选池24条扫描实测, 0违规20条全收)
      'no-labels': 'error',                 // 禁label语句, 防goto式控制流
      'no-div-regex': 'error',              // 禁/=开头正则歧义, 用[=]
      'accessor-pairs': 'error',            // setter须配套getter
      'no-nested-ternary': 'error',         // 禁嵌套三元, 可读性
      'no-new-require': 'error',            // 禁new require()歧义写法
      'no-octal-escape': 'error',           // 禁八进制转义序列
      'no-void': 'error',                   // 禁void运算符
      'no-iterator': 'error',               // 禁__iterator__属性
      'prefer-spread': 'error',             // fn.apply(null,args)→...args
      'prefer-rest-params': 'error',        // arguments→...rest参数
      'no-object-constructor': 'error',     // Object()→{}
      'no-new-object': 'error',             // new Object()→{}
      'dot-notation': 'error',              // obj['prop']→obj.prop(可点号访问时)
      'no-extend-native': 'error',          // 禁扩展原生原型(Array.prototype.x=等)
      'no-return-await': 'error',           // 禁多余return await(非catch场景无意义)
      'symbol-description': 'error',        // Symbol()须带描述
      'no-duplicate-imports': 'error',      // 禁重复import同一模块
      'no-useless-constructor': 'error',    // 禁无意义默认构造函数
      'no-bitwise': 'error',                // 禁位运算符(多为&/&&笔误), 需要处显式disable
      'no-param-reassign': 'error',         // 禁对函数参数重新赋值, 防调用方意外
      // 代码质量防回归规则第六批 (2026-08-04 猴王自驱lint轮, 全量核心规则扫描: builtin 292条去掉recommended/已启用后166候选,
      // 一次性临时入config实测, 95条0违规; 剔除7条已废弃(no-catch-shadow/no-native-reassign/no-negated-in-lhs/
      // no-new-symbol/no-spaced-func/lines-around-directive/id-blacklist)、9条无选项即空转(no-restricted-*×6/id-denylist/
      // id-match/jsx-quotes无JSX)、no-warning-comments(防TODO摩擦), 收78条)
      'array-bracket-spacing': 'error', 'arrow-body-style': 'error', 'arrow-spacing': 'error',
      'block-scoped-var': 'error', 'block-spacing': 'error', 'comma-spacing': 'error',
      'comma-style': 'error', 'complexity': 'error', 'computed-property-spacing': 'error',
      'consistent-this': 'error', 'default-case-last': 'error', 'default-param-last': 'error',
      'func-call-spacing': 'error', 'func-name-matching': 'error', 'generator-star-spacing': 'error',
      'grouped-accessor-pairs': 'error', 'handle-callback-err': 'error', 'key-spacing': 'error',
      'keyword-spacing': 'error', 'linebreak-style': 'error', 'lines-between-class-members': 'error',
      'logical-assignment-operators': 'error', 'max-classes-per-file': 'error', 'max-depth': 'error',
      'max-nested-callbacks': 'error', 'new-parens': 'error', 'no-await-in-loop': 'error',
      'no-buffer-constructor': 'error', 'no-caller': 'error', 'no-constructor-return': 'error',
      'no-eq-null': 'error', 'no-extra-label': 'error', 'no-extra-semi': 'error',
      'no-floating-decimal': 'error', 'no-implicit-globals': 'error', 'no-invalid-this': 'error',
      'no-label-var': 'error', 'no-lone-blocks': 'error', 'no-loop-func': 'error',
      'no-mixed-requires': 'error', 'no-mixed-spaces-and-tabs': 'error', 'no-multiple-empty-lines': 'error',
      'no-new': 'error', 'no-path-concat': 'error', 'no-script-url': 'error',
      'no-shadow': 'error', 'no-tabs': 'error', 'no-trailing-spaces': 'error',
      'no-undef-init': 'error', 'no-whitespace-before-property': 'error',
      'nonblock-statement-body-position': 'error', 'object-curly-newline': 'error',
      'one-var-declaration-per-line': 'error', 'operator-assignment': 'error',
      'operator-linebreak': 'error', 'padding-line-between-statements': 'error',
      'prefer-exponentiation-operator': 'error', 'prefer-object-has-own': 'error',
      'prefer-promise-reject-errors': 'error', 'rest-spread-spacing': 'error',
      'semi': 'error', 'semi-spacing': 'error', 'semi-style': 'error',
      'sort-imports': 'error', 'sort-vars': 'error', 'space-before-blocks': 'error',
      'space-in-parens': 'error', 'space-infix-ops': 'error', 'space-unary-ops': 'error',
      'spaced-comment': 'error', 'switch-colon-spacing': 'error', 'template-curly-spacing': 'error',
      'template-tag-spacing': 'error', 'unicode-bom': 'error', 'vars-on-top': 'error',
      'yield-star-spacing': 'error', 'callback-return': 'error', 'class-methods-use-this': 'error',
    },
    linterOptions: {
      reportUnusedDisableDirectives: 'error',   // 失效的eslint-disable注释报错, 防规则笔误/删除后静默失效
    },
  },
  {
    // 架构守卫块 (F208 2026-08-04 + F214 2026-08-04 猴王自驱lint轮)
    // ⚠️ flat config 同rule id后块覆盖前块(不合并), no-restricted-syntax 多守卫必须同块声明,
    // 否则前条静默失效(F214调试实测)。ignores取各守卫豁免并集: app.js(F214认证层)+api.js;
    // 前置核验: app.js零wx.request / api.js零globalData访问, 并集豁免零行为变化。
    // ①F208: HTTP必须走 services/api.js 统一封装, 禁直连 wx.request(绕过baseURL/token注入/
    //   统一错误处理/401登出); AST精确匹配property.name='request', wx.requestPayment不误伤。
    // ②F214: 敏感凭据storage键('token'/'userInfo')仅认证层(app.js+services/api.js)可读写,
    //   页面直读绕过401登出/统一注入且硬编码键有改名漂移风险; 不误伤页面私有键
    //   (scanHistory/station_filter)。
    // ③F214: 登录态禁直读 globalData.token 裸字段, 须走 app.getToken()(绕过storage兜底逻辑)。
    // ④F227: 端点地址单一源 — http(s) URL字面量仅允许 config/index.js(环境切换唯一声明点),
    //   运行时代码硬编码端点=绕过环境切换/灰度对照失真(F224双源漂移同族)。ignores并集新增
    //   config/**(权威源)+测试(jest断言config值/样例URL为合法用途, F220同款豁免);
    //   前置核验: config/index.js与测试对①②③零违规, 并集扩豁免零行为变化。
    //   覆盖Literal与模板字符串首段(TemplateElement.cooked), 注释不参与AST不受影响。
    files: ['**/*.js'],
    ignores: ['app.js', '**/services/api.js', 'config/**', '**/__tests__/**', '**/*.test.js'],
    rules: {
      'no-restricted-syntax': ['error',
        {
          selector: "CallExpression[callee.object.name='wx'][callee.property.name='request']",
          message: 'HTTP请求必须走 services/api.js 统一封装, 禁止直连 wx.request (架构守卫 F208)',
        },
        {
          selector: "CallExpression[callee.object.name='wx'][callee.property.name=/^(set|get|remove)Storage(Sync)?$/] > Literal[value=/^(token|userInfo)$/]",
          message: "敏感凭据键('token'/'userInfo')仅认证层(app.js/services/api.js)可读写, 登录态请用 app.getToken()/api.getUserInfo() (架构守卫 F214)",
        },
        {
          // 异步storage对象参数形态: wx.getStorage({key:'token'})
          selector: "CallExpression[callee.object.name='wx'][callee.property.name=/^(set|get|remove)Storage$/] > ObjectExpression > Property[key.name='key'] > Literal[value=/^(token|userInfo)$/]",
          message: "敏感凭据键('token'/'userInfo')仅认证层(app.js/services/api.js)可读写, 登录态请用 app.getToken()/api.getUserInfo() (架构守卫 F214)",
        },
        {
          selector: "MemberExpression[object.type='MemberExpression'][object.property.name='globalData'][property.name='token']",
          message: '登录态请走 app.getToken(), 禁直读 globalData.token 裸字段 (架构守卫 F214)',
        },
        {
          selector: "Literal[value=/^https?:\\/\\//]",
          message: '端点地址必须在 config/index.js 统一声明(环境切换单一源), 运行时代码禁硬编码 http(s) URL (架构守卫 F227)',
        },
        {
          selector: "TemplateElement[value.cooked=/^https?:\\/\\//]",
          message: '端点地址必须在 config/index.js 统一声明(环境切换单一源), 运行时代码禁硬编码 http(s) URL (架构守卫 F227)',
        },
      ],
    },
  },
  {
    // 运行时代码日志守卫 (F220 2026-08-04 猴王自驱lint轮)
    // 小程序运行时 console.log/info/debug 残留污染微信开发者工具控制台, 且可能泄露
    // 订单/位置/充电会话等敏感字段; console.warn/error 为既有catch块统一错误日志
    // (实测17处)放行。scripts/是CLI脚本(console为合法输出)不在files内天然豁免;
    // 测试文件跑jest(node环境, console为诊断输出)显式豁免防摩擦。
    files: ['app.js', 'config/**/*.js', 'components/**/*.js', 'pages/**/*.js', 'services/**/*.js', 'utils/**/*.js'],
    ignores: ['**/__tests__/**', '**/*.test.js'],
    rules: {
      'no-console': ['error', { allow: ['warn', 'error'] }],
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
