/**
 * 天链V3 - 4入口登录页（2026-07-02）
 *
 * 四种角色入口：
 *   🛡️ 系统管理员 — Admin（蓝色）
 *   🔧 运维工程师 — Engineer（绿色）
 *   📊 运营人员 — Operator（橙色）
 *   🚗 车队管理 — Fleet（紫色）
 *
 * 流程：选择角色卡片 → 进入对应登录表单 → 登录时携带 user_type
 *
 * 结构重构 (c56f2cee): 状态/交互 → hooks/useLogin；
 *                      select/login/reset 三视图 → components/*。纯结构性拆分，行为不变。
 */
import { useLogin } from './hooks/useLogin';
import { styles } from './constants';
import RoleSelectView from './components/RoleSelectView';
import LoginCard from './components/LoginCard';
import PasswordResetModal from './components/PasswordResetModal';

export default function LoginPage() {
  const login = useLogin();

  return (
    <div style={styles.page}>
      {login.step === 'select' ? (
        <RoleSelectView onSelect={login.handleSelectRole} />
      ) : (
        <>
          {login.selectedRole && <LoginCard login={login} />}
          {login.showResetModal && login.selectedRole && <PasswordResetModal login={login} />}
        </>
      )}
    </div>
  );
}
