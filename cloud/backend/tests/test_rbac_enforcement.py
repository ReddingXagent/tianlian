"""
RBAC 写端点鉴权测试 (P1 安全, 卡 b9d16fae)

全局 enforce_auth(app/api/v1/auth.py) 只验 token(认证), 不查角色(授权)。
本测试验证高危写端点已补 require_permission 细粒度授权:
  - viewer  打写端点 → 403
  - admin   打写端点 → 非 401/403 (2xx 或正常业务错误码均可)
  - operator 打运营面/API Key → 通过 (operate:manage / api_key:manage)
  - operator 打用户管理/系统配置 → 403 (user:* / system:config 仅 admin)

⚠️ 关键测试坑: require_permission (app/middleware/permission.py) 内部用
`from app.core.database import SessionLocal` 直接连库查 user, 不走 get_db
dependency override。conftest 的 client fixture 只 override get_db, 不动
SessionLocal, 故此处必须 monkeypatch app.core.database.SessionLocal 指向
测试库, 并在该库 seed admin/viewer/operator —— 否则 require_permission 查不
到用户返回 401, 测试会误判。同源坑见 [[service-sessionlocal-import-binding-test-pitfall]]。
"""
import bcrypt
import pytest
from sqlalchemy.orm import sessionmaker

from app.models.user import User, UserRole


@pytest.fixture
def rbac_env(client, monkeypatch):
    """client + SessionLocal override + seed viewer/operator.

    require_permission 用 SessionLocal() 查 user; conftest client fixture
    仅 override get_db 不动 SessionLocal, 故补 monkeypatch 使权限检查落到
    测试库。admin 由 conftest client fixture 已 seed (admin/admin123)。
    """
    import app.core.database as db_module

    s = client._sesh
    engine = s.get_bind()

    for uname, pwd, role in [
        ("rbac_viewer", "view123", UserRole.VIEWER),
        ("rbac_operator", "op123", UserRole.OPERATOR),
    ]:
        if not s.query(User).filter(User.username == uname).first():
            s.add(User(
                username=uname,
                password_hash=bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(),
                real_name=uname,
                role=role,
                status="active",
            ))
    s.commit()

    # require_permission 函数内 `from app.core.database import SessionLocal`
    # 每次调用读取模块属性当前值, monkeypatch 后即指向测试库 engine。
    TestSesh = sessionmaker(bind=engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestSesh)
    yield client


def _login(client, username, password):
    r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, f"login failed {username}: {r.status_code} {r.text}"
    return r.json()["data"]["token"]


def _hdr(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def viewer_token(rbac_env):
    return _login(rbac_env, "rbac_viewer", "view123")


@pytest.fixture
def operator_token(rbac_env):
    return _login(rbac_env, "rbac_operator", "op123")


# ── 样本写端点 (method, path, json_body) ──
# per-endpoint 端点(users/security/api_key/pricing)用合法 body, 确保权限检查
#   能先于/独立于 body 校验执行 (避免 422 掩盖 403);
# router 级端点(operate/*)的 body 不影响 (router dependency 在 body 解析前执行)。
WRITE_ENDPOINTS = [
    # 用户管理 (per-endpoint: user:create / user:edit / user:delete)
    ("POST", "/api/v1/users",
     {"username": "_rbac_v", "password": "p123456", "real_name": "v"}),
    ("PUT", "/api/v1/users/999999", {"role": "admin"}),  # 提权路径: 改 role
    ("DELETE", "/api/v1/users/999999", None),
    # 安全设置 (per-endpoint: system:config)
    ("PUT", "/api/v1/security/settings", {"max_login_attempts": 5}),
    # API Key (per-endpoint: api_key:manage)
    ("POST", "/api/v1/api-keys", {"name": "_rbac_k"}),
    ("DELETE", "/api/v1/api-keys/999999", None),
    # 计费 (per-endpoint: system:config)
    ("POST", "/api/v1/pricing",
     {"name": "_rbac_p", "period_type": "peak", "start_time": "08:00", "end_time": "12:00"}),
    ("DELETE", "/api/v1/pricing/999999", None),
    # 运营管理面 (router-level: operate:manage)
    ("POST", "/api/v1/operate/charger-qrcode/generate", {"station_id": 999999, "count": 1}),
    ("POST", "/api/v1/operate/interconnect/configs", {"platform_code": "TEST", "name": "_rbac"}),
    ("POST", "/api/v1/operate/invoice-platforms", {"platform_name": "_rbac", "platform_type": "other"}),
    ("POST", "/api/v1/operate/supervision/configs", {"platform_type": "national_grid", "name": "_rbac"}),
    # ── 卡 b9d16fae 二期: 管理面8模块写端点样本 (锁死 viewer 403 防回归) ──
    # 审计结论: 26/28 端点已有等价授权(roles/permissions→_check_admin_or_permission
    #   system:role/user:role; tenant→_is_admin; ssl→require_platform_admin;
    #   payment/invoice/global_config + notification 模板/规则→system:config);
    #   唯一真实缺口 notification 渠道开关 (下方 notif.switches) 已修。
    #   此处每模块1样本固定 viewer=403 / admin=非401/403, 防止后续回归。
    ("POST", "/api/v1/roles", {"name": "_rbac_role", "display_name": "rbac role"}),                    # roles.py
    ("POST", "/api/v1/system-config/roles", {"name": "_rbac_p_role", "display_name": "rbac p role"}),  # permissions.py
    ("POST", "/api/v1/tenants", {"name": "_rbac_tenant", "code": "_rbac_t_code"}),                     # tenant.py
    ("PUT", "/api/v1/ssl/certificates/_rbac.example.com/config", {"auto_renew": True}),                # ssl_certificates.py (admin→404 非401/403)
    ("PUT", "/api/v1/system-config/notification/switches", {}),                                        # notification.py (本期修复点)
    ("POST", "/api/v1/system-config/payment-channels", {"name": "_rbac_pay", "channel_type": "im_b"}),  # payment.py
    ("PUT", "/api/v1/system-config/invoice", {}),                                                      # invoice.py
    ("PUT", "/api/v1/system-config/global", {}),                                                       # global_config.py
    # ── 卡 1bd3b6e2 P2: 业务域写端点样本 (router-level require_write_permission,
    #   守卫在 body 解析前执行 → viewer 必 403 / admin 非 401/403) ──
    ("POST", "/api/v1/devices", {"name": "_rbac_d", "device_code": "_rbac_dc", "station_id": 999999}),   # 设备域 device:edit
    ("POST", "/api/v1/charging/strategy/switch", {"mode": "auto"}),                                      # 充电域 charging:manage
    ("POST", "/api/v1/enterprises", {"name": "_rbac_e", "contact": "x", "phone": "13800000099"}),       # 车队域 fleet:manage
    ("POST", "/api/v1/work-orders", {"title": "_rbac_w"}),                                              # 运维域 workorder:edit
    ("POST", "/api/v1/notifications/templates", {"name": "_rbac_nt", "content": "x"}),                  # 通知域 notification:manage
    ("POST", "/api/v1/webhooks", {"name": "_rbac_wh", "url": "http://x.invalid"}),                      # 通知域 notification:manage
    ("POST", "/api/v1/knowledge/articles", {"title": "_rbac_k", "content": "x"}),                       # 知识库 knowledge:manage
    ("DELETE", "/api/v1/report-mgmt/999999", None),                                                    # 报告 report:manage (用 DELETE 规避 create_report raw INSERT NOT NULL; 不存在→404)
    ("POST", "/api/v1/engineers", {"name": "_rbac_eng", "password": "p123456"}),                        # 工程师 engineer:manage
    ("POST", "/api/v1/tasks/submit", {"task_type": "health_score"}),                                    # 异步任务 analytics:manage
    ("POST", "/api/v1/fleet/carbon/calculate", {}),                                                    # 碳排放 report:manage (per-endpoint require_platform_admin 堆叠, admin 通过)
    # ── 卡 e74fea5a P2 续: 剩余业务域写端点扩面 (router-level require_write_permission,
    #   守卫在 body/路径参数解析前执行 → viewer 必 403 / admin 非 401/403)。每模块1样本防回归。 ──
    ("POST", "/api/v1/diagnosis/device", {}),                                                          # diagnosis.py healing:manage
    ("POST", "/api/v1/enterprises/999999/transactions", {}),                                           # enterprise_transactions.py fleet:manage
    ("POST", "/api/v1/enterprises/999999/vehicles", {}),                                               # enterprise_vehicles.py fleet:manage
    ("POST", "/api/v1/fault-diagnosis/alarm-diagnosis", {}),                                           # fault_diagnosis.py healing:manage
    ("POST", "/api/v1/fleet/alert-rules", {}),                                                         # fleet_alerts.py fleet:manage
    ("POST", "/api/v1/fleet/carbon/certificates/apply", {}),                                           # fleet_carbon_certificates.py fleet:manage
    ("POST", "/api/v1/fleet/policies", {}),                                                            # fleet_charging_policies.py fleet:manage
    ("POST", "/api/v1/fleet/funds", {}),                                                               # fleet_funds.py fleet:manage
    ("POST", "/api/v1/gateways", {}),                                                                  # gateways.py device:edit
    ("POST", "/api/v1/healing/rules", {}),                                                             # healing.py healing:manage
    ("POST", "/api/v1/health/calculate/999999", {}),                                                   # health_monitor.py analytics:manage
    ("POST", "/api/v1/inspection/plans", {}),                                                          # inspection.py workorder:edit
    ("POST", "/api/v1/log-analysis/analyze", {}),                                                      # log_analysis.py healing:manage
    ("POST", "/api/v1/maintenance-records", {}),                                                       # maintenance_records.py workorder:edit
    ("POST", "/api/v1/notification-configs", {}),                                                      # notification_configs.py notification:manage
    ("POST", "/api/v1/notification-rules", {}),                                                        # notification_rules.py notification:manage
    ("POST", "/api/v1/orders/999999/settle", {}),                                                      # order_fees.py charging:manage
    ("POST", "/api/v1/parking/discounts", {}),                                                         # parking.py operate:manage
    ("POST", "/api/v1/runbook/execute/999999", {}),                                                    # runbook.py healing:manage
    ("POST", "/api/v1/runbooks/templates", {}),                                                        # runbook_templates.py healing:manage
    ("POST", "/api/v1/spare-parts", {}),                                                               # spare_parts.py workorder:edit
    ("POST", "/api/v1/stations", {}),                                                                  # stations.py station:edit
    ("POST", "/api/v1/vpp/stations", {}),                                                              # vpp.py device:edit
]


# ===== viewer: 全部写端点必须 403 =====
@pytest.mark.parametrize("method,path,body", WRITE_ENDPOINTS)
def test_viewer_forbidden_on_write_endpoints(rbac_env, viewer_token, method, path, body):
    resp = rbac_env.request(method, path, json=body, headers=_hdr(viewer_token))
    assert resp.status_code == 403, (
        f"viewer 写 {method} {path} 应 403, 实际 {resp.status_code}\n{resp.text}"
    )


# ===== admin: 全部写端点必须 非 401/403 =====
@pytest.mark.parametrize("method,path,body", WRITE_ENDPOINTS)
def test_admin_allowed_on_write_endpoints(rbac_env, method, path, body):
    # client fixture 默认注入 admin token
    resp = rbac_env.request(method, path, json=body)
    assert resp.status_code not in (401, 403), (
        f"admin 写 {method} {path} 被拒: {resp.status_code}\n{resp.text}"
    )


# ===== operator: 运营面 + API Key 可写 (operate:manage / api_key:manage) =====
OPERATOR_OK_ENDPOINTS = [
    ("POST", "/api/v1/operate/charger-qrcode/generate", {"station_id": 999999, "count": 1}),
    ("POST", "/api/v1/operate/supervision/configs", {"platform_type": "national_grid", "name": "_rbac_op"}),
    ("POST", "/api/v1/api-keys", {"name": "_rbac_op_k"}),
]


@pytest.mark.parametrize("method,path,body", OPERATOR_OK_ENDPOINTS)
def test_operator_allowed_on_operate_endpoints(rbac_env, operator_token, method, path, body):
    resp = rbac_env.request(method, path, json=body, headers=_hdr(operator_token))
    assert resp.status_code not in (401, 403), (
        f"operator 写 {method} {path} 被拒: {resp.status_code}\n{resp.text}"
    )


# ===== operator: 用户管理/系统配置仍 403 (user:* / system:config 仅 admin) =====
OPERATOR_FORBIDDEN_ENDPOINTS = [
    ("POST", "/api/v1/users",
     {"username": "_rbac_op_u", "password": "p123456", "real_name": "x"}),
    ("PUT", "/api/v1/security/settings", {"max_login_attempts": 5}),
    ("POST", "/api/v1/pricing",
     {"name": "_rbac_op_p", "period_type": "peak", "start_time": "08:00", "end_time": "12:00"}),
]


@pytest.mark.parametrize("method,path,body", OPERATOR_FORBIDDEN_ENDPOINTS)
def test_operator_forbidden_on_admin_endpoints(rbac_env, operator_token, method, path, body):
    resp = rbac_env.request(method, path, json=body, headers=_hdr(operator_token))
    assert resp.status_code == 403, (
        f"operator 写 {method} {path} 应 403, 实际 {resp.status_code}\n{resp.text}"
    )
