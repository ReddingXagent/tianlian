// scripts/__tests__/deploy.test.js
// 部署门控脚本行为测试: 门控先行 + appid占位拦截(退出码2)
const { spawnSync } = require('child_process');
const path = require('path');

const DEPLOY = path.resolve(__dirname, '../deploy.js');

function run(args) {
  return spawnSync(process.execPath, [DEPLOY, ...args], {
    encoding: 'utf8',
    timeout: 30000,
  });
}

describe('deploy.js 部署门控', () => {
  it('--check: 门控先跑PASS, 随后appid占位拦截退2', () => {
    const r = run(['--check']);
    expect(r.status).toBe(2);
    expect(r.stdout).toContain('构建门控 PASS');
    expect(r.stdout).toContain('步骤2/4 appid校验');
    expect(r.stderr).toContain('占位符');
    expect(r.stderr).toContain('真实 appid');
  });

  it('正式模式同样被appid占位拦截, 不会触达上传', () => {
    const r = run([]);
    expect(r.status).toBe(2);
    expect(r.stdout).not.toContain('步骤4/4');
  });

  it('未知参数直接退1', () => {
    const r = run(['--bogus']);
    expect(r.status).toBe(1);
    expect(r.stderr).toContain('未知参数');
  });
});
