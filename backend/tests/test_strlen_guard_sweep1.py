"""字符串长度守卫回归测试 (卡 dbc24d97, 维度O-1弹)。

覆盖代表性真缺口: 超长/非法枚举输入应 422 (pydantic), 而非落库后 500。
"""
LONG = "x" * 3000  # 远超所有目标列长


def test_alarm_rule_operator_literal(client):
    """operator 枚举白名单: 非法值 422 而非落库 String(10) 溢出。"""
    r = client.post("/api/v1/alarm-rules", json={
        "name": "t", "metric": "power", "operator": LONG, "threshold": 1.0,
    })
    assert r.status_code == 422, r.text


def test_alarm_rule_metric_max_length(client):
    r = client.post("/api/v1/alarm-rules", json={
        "name": "t", "metric": LONG, "operator": ">", "threshold": 1.0,
    })
    assert r.status_code == 422, r.text


def test_alarm_create_type_max_length(client):
    r = client.post("/api/v1/alarms", json={
        "device_id": 1, "alarm_type": LONG, "content": "c",
    })
    assert r.status_code == 422, r.text


def test_on_call_schedule_type_literal(client):
    """schedule_type 枚举白名单 (String(32) 列)。"""
    r = client.post("/api/v1/on-call/rules", json={"name": "t", "schedule_type": LONG})
    assert r.status_code == 422, r.text


def test_sms_purpose_literal(client):
    """SmsSendRequest.purpose -> SmsVerificationCode.purpose String(20)。"""
    r = client.post("/api/v1/auth/sms/send", json={"phone": "13800138000", "purpose": LONG})
    assert r.status_code == 422, r.text


def test_gateway_sn_max_length(client):
    r = client.post("/api/v1/gateways", json={"sn": LONG, "name": "g"})
    assert r.status_code == 422, r.text


def test_users_create_username_max_length(client):
    """UserCreate.username -> User.username String(50)。"""
    r = client.post("/api/v1/users", json={"username": LONG, "password": "Passw0rd!"})
    assert r.status_code == 422, r.text


def test_scan_qr_code_max_length(client):
    """ScanRequest.qr_code -> DeviceQRCode.qr_code String(200)。"""
    r = client.post("/api/v1/scan/device", json={"qr_code": LONG})
    assert r.status_code == 422, r.text


def test_interconnect_sync_direction_literal(client):
    """sync_direction 枚举白名单 (String(20) 列)。"""
    r = client.post("/api/v1/operate/interconnect/configs", json={
        "platform_code": "hw", "platform_name": "n", "api_base_url": "https://a.b",
        "sync_direction": LONG,
    })
    assert r.status_code == 422, r.text


def test_bill_period_pattern(client):
    """bill_period 必须 YYYY-MM (String(20) 列)。"""
    r = client.post("/api/v1/fleet/settlement/bills/generate", json={
        "enterprise_id": 1, "bill_period": LONG})
    assert r.status_code == 422, r.text
