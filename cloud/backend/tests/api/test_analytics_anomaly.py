"""异常检测 API 测试 (工作卡 fe57636f)

覆盖 app/api/v1/analytics/anomaly.py (挂 /api/v1/analytics 前缀):
- POST /analytics/anomaly-detection   设备异常检测 (温度/电压/电流/功率/SOC 五维统计)

权限: _ROUTER_DEPENDENCIES = get_current_user + require_write_permission("analytics:manage")
      POST 写需 analytics:manage —— admin 通过, viewer 无此权限 → 403, 匿名 → 401。
team scoping (任务卡 b640bdd9): assert_device_team_access 先校验, device.station_id→team,
      admin 豁免, 跨团队/不存在 → 404 (不泄露存在)。

检测器阈值 (anomaly.py):
- 温度: ≥5 个 battery_temperature, 任一 > mean+3*std → temperature_high/low
- 电压: 三相均值 >250 或 <210; 最近5点不平衡度 >5%
- 电流: ≥3 个电流值, 任一 >100A → current_high
- 功率: ≥5 个 grid_power_total, 任一 >100kW → power_high
- SOC: ≥5 个 battery_soc, 任一 <20% → soc_low (critical 若 <10%)
"""
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import pytest

from app.models.device import Device, DeviceType, DeviceStatus
from app.models.station import Station, StationStatus
from app.models.telemetry import Telemetry
from app.models.user import User, UserRole

ANOMALY_URL = "/api/v1/analytics/anomaly-detection"


# ─── helpers ───

def _add_user(session, username, *, role=UserRole.VIEWER, team_id=None, password="pw123456"):
    u = User(
        username=username, real_name=username, role=role, team_id=team_id,
        status="active",
        password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
    )
    session.add(u); session.commit(); session.refresh(u)
    return u


def _login_token(client, username, password="pw123456"):
    r = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, f"登录失败 {username}: {r.text[:200]}"
    return r.json()["data"]["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _seed_station(session, *, team_id=None, tag=""):
    st = Station(
        name=f"异检站{tag}{uuid.uuid4().hex[:4]}",
        code=f"ST{uuid.uuid4().hex[:6].upper()}",
        address="测试地址", status=StationStatus.NORMAL, team_id=team_id,
    )
    session.add(st); session.commit(); session.refresh(st)
    return st


def _seed_device(session, station_id, *, tag=""):
    d = Device(
        sn=f"SN-{uuid.uuid4().hex[:8]}", name=f"设备{tag}",
        code=f"DEV{uuid.uuid4().hex[:6].upper()}",
        type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE, station_id=station_id,
    )
    session.add(d); session.commit(); session.refresh(d)
    return d


def _seed_telemetry(session, device_id, rows):
    """rows: list[dict] 度量字段; 自动补递增 timestamp (now 往前, 步长 1 分钟, 在 24h 窗口内)。"""
    base = datetime.now(timezone.utc) - timedelta(minutes=len(rows) + 5)
    for i, fields in enumerate(rows):
        t = Telemetry(
            device_id=device_id,
            timestamp=base + timedelta(minutes=i),
            **fields,
        )
        session.add(t)
    session.commit()


# ==================== 1. 正常检测路径 ====================

class TestDetectAnomalies:

    def test_detect_soc_low_anomaly(self, client):
        """SOC 过低 (含 <10%) → soc_low (critical), 返回结构化异常 + 建议措施。"""
        s = client._sesh
        st = _seed_station(s, tag="A1")
        d = _seed_device(s, st.id, tag="soc")
        # 前 5 点正常 SOC, 第 6 点骤降到 5% (<10 → critical)
        rows = [{"battery_soc": 50.0}] * 5 + [{"battery_soc": 5.0}]
        _seed_telemetry(s, d.id, rows)
        r = client.post(ANOMALY_URL, json={"device_id": d.id, "hours": 24})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["device_id"] == d.id
        types = [a["type"] for a in data["detected_anomalies"]]
        assert "soc_low" in types
        soc_low = next(a for a in data["detected_anomalies"] if a["type"] == "soc_low")
        assert soc_low["severity"] == "critical"  # <10 → critical
        # critical 分数高 → 总体 severity 应在 high/critical
        assert data["severity"] in ("critical", "high")
        assert data["anomaly_score"] > 0
        assert data["suggested_actions"]  # 非空建议

    def test_detect_current_high_anomaly(self, client):
        """电流过高 (>100A, 含 >150 → critical) → current_high。"""
        s = client._sesh
        st = _seed_station(s, tag="A2")
        d = _seed_device(s, st.id, tag="curr")
        rows = [{"grid_current_a": 30.0}] * 3 + [{"grid_current_a": 200.0}]  # 200A > 150 → critical
        _seed_telemetry(s, d.id, rows)
        r = client.post(ANOMALY_URL, json={"device_id": d.id})
        assert r.status_code == 200
        types = [a["type"] for a in r.json()["detected_anomalies"]]
        assert "current_high" in types

    def test_detect_no_anomaly_returns_empty(self, client):
        """全正常数据 → 无异常, anomaly_score=0, severity=low。"""
        s = client._sesh
        st = _seed_station(s, tag="A3")
        d = _seed_device(s, st.id, tag="ok")
        # 一切指标落在正常区间
        rows = [{
            "battery_soc": 60.0,
            "battery_temperature": 25.0,
            "grid_power_total": 30.0,
            "grid_current_a": 20.0,
        }] * 6
        _seed_telemetry(s, d.id, rows)
        r = client.post(ANOMALY_URL, json={"device_id": d.id})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["detected_anomalies"] == []
        assert data["anomaly_score"] == 0.0
        assert data["severity"] == "low"

    def test_default_hours_is_24(self, client):
        """不传 hours 默认 24 (schema 默认值), 端点正常返回。"""
        s = client._sesh
        st = _seed_station(s, tag="A4")
        d = _seed_device(s, st.id, tag="def")
        _seed_telemetry(s, d.id, [{"battery_soc": 50.0}] * 6)
        r = client.post(ANOMALY_URL, json={"device_id": d.id})
        assert r.status_code == 200


# ==================== 2. 边界 / 404 ====================

class TestAnomalyNotFound:

    def test_device_not_exist_404(self, client):
        r = client.post(ANOMALY_URL, json={"device_id": 999999, "hours": 24})
        assert r.status_code == 404  # assert_device_team_access 先拦

    def test_no_telemetry_404(self, client):
        """设备存在但无遥测数据 → 404「没有遥测数据」。"""
        s = client._sesh
        st = _seed_station(s, tag="B1")
        d = _seed_device(s, st.id, tag="空")
        r = client.post(ANOMALY_URL, json={"device_id": d.id, "hours": 24})
        assert r.status_code == 404
        assert "遥测" in r.json()["detail"]

    def test_telemetry_out_of_window_404(self, client):
        """遥测数据在 hours 窗口外 → 等同无数据 → 404。"""
        s = client._sesh
        st = _seed_station(s, tag="B2")
        d = _seed_device(s, st.id, tag="窗外")
        # 写 48h 前的数据, 查询窗口 1h
        old = datetime.now(timezone.utc) - timedelta(hours=48)
        s.add(Telemetry(device_id=d.id, timestamp=old, battery_soc=5.0))
        s.commit()
        r = client.post(ANOMALY_URL, json={"device_id": d.id, "hours": 1})
        assert r.status_code == 404


# ==================== 3. team scoping ====================

class TestAnomalyTeamScoping:

    def test_cross_team_device_404(self, client):
        """持 analytics:manage 但跨 team → 404 (assert_device_team_access 在端点内, 不泄露)。

        注意: _ROUTER_DEPENDENCIES 的 require_write_permission 在端点函数前执行,
        viewer 会先撞 403 到不了 team 校验; 故这里用 OPERATOR (持 analytics:manage) 跨 team,
        权限通过后才进 assert_device_team_access → 404。
        """
        from app.models.user import Team
        s = client._sesh
        t_other = Team(name=f"队他{uuid.uuid4().hex[:4]}", code=f"TO{uuid.uuid4().hex[:4]}")
        t_mine = Team(name=f"队我{uuid.uuid4().hex[:4]}", code=f"TM{uuid.uuid4().hex[:4]}")
        s.add_all([t_other, t_mine]); s.commit(); s.refresh(t_other); s.refresh(t_mine)
        st_other = _seed_station(s, team_id=t_other.id, tag="x")
        d_other = _seed_device(s, st_other.id, tag="他人设备")
        _seed_telemetry(s, d_other.id, [{"battery_soc": 5.0}] * 6)
        u = _add_user(s, f"oper_{uuid.uuid4().hex[:6]}", role=UserRole.OPERATOR, team_id=t_mine.id)
        tok = _login_token(client, u.username)
        r = client.post(ANOMALY_URL, json={"device_id": d_other.id}, headers=_auth(tok))
        assert r.status_code == 404

    def test_admin_sees_other_team_device(self, client):
        """admin 豁免 team scoping, 可检测他人 team 设备。"""
        from app.models.user import Team
        s = client._sesh
        t_other = Team(name=f"队他{uuid.uuid4().hex[:4]}", code=f"TO{uuid.uuid4().hex[:4]}")
        s.add(t_other); s.commit(); s.refresh(t_other)
        st_other = _seed_station(s, team_id=t_other.id, tag="adm")
        d_other = _seed_device(s, st_other.id, tag="管理员查")
        _seed_telemetry(s, d_other.id, [{"battery_soc": 50.0}] * 6)
        # client 默认 admin token
        r = client.post(ANOMALY_URL, json={"device_id": d_other.id})
        assert r.status_code == 200


# ==================== 4. 权限 ====================

class TestAnomalyPermission:

    def test_viewer_forbidden_403(self, client):
        """viewer 无 analytics:manage → POST 写 403 (路由级依赖在 body 解析前)。"""
        from app.models.user import Team
        s = client._sesh
        t = Team(name=f"队{uuid.uuid4().hex[:4]}", code=f"T{uuid.uuid4().hex[:4]}")
        s.add(t); s.commit(); s.refresh(t)
        st = _seed_station(s, team_id=t.id, tag="P1")
        d = _seed_device(s, st.id, tag="v")
        u = _add_user(s, f"viewer_{uuid.uuid4().hex[:6]}", role=UserRole.VIEWER, team_id=t.id)
        tok = _login_token(client, u.username)
        r = client.post(ANOMALY_URL, json={"device_id": d.id}, headers=_auth(tok))
        assert r.status_code == 403

    def test_anonymous_401(self, anon_client):
        r = anon_client.post(ANOMALY_URL, json={"device_id": 1})
        assert r.status_code == 401

    def test_missing_device_id_422(self, client):
        """缺 device_id → Pydantic 422。"""
        r = client.post(ANOMALY_URL, json={"hours": 24})
        assert r.status_code == 422
