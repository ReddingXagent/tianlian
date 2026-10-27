"""充电桩收费二维码 API 测试 (工作卡 fe57636f)

覆盖 app/api/v1/operate/charger_qrcode.py (挂 /api/v1/operate 前缀):
- POST /operate/charger-qrcode/generate        批量生成 (按枪展开, 幂等覆盖)
- GET  /operate/charger-qrcode/download/{id}    单张下载 (PNG)
- POST /operate/charger-qrcode/batch-download   批量打包下载 (ZIP)
- GET  /operate/charger-qrcode/list             查询列表 (按枪粒度行)

权限: router 级 require_permission("operate:manage") —— admin 通过;
viewer 无此权限 → 403; 匿名 → 401。
团队隔离: device.station_id→team, admin 豁免, 跨队 → 记错跳过/404 (不泄露存在)。

generate 会写 PNG 到 backend/uploads/qrcodes/, 测试 monkeypatch 到 tmp 避免污染仓库。
"""
import io
import uuid
import zipfile

import bcrypt
import pytest

from app.models.device import Device, DeviceType, DeviceStatus
from app.models.device_qrcode import DeviceQRCode
from app.models.station import Station, StationStatus
from app.models.user import User, UserRole

QR_URL = "/api/v1/operate/charger-qrcode"


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
        name=f"桩站{tag}{uuid.uuid4().hex[:4]}",
        code=f"ST{uuid.uuid4().hex[:6].upper()}",
        address="测试地址", status=StationStatus.NORMAL, team_id=team_id,
    )
    session.add(st); session.commit(); session.refresh(st)
    return st


def _seed_charger(session, station_id, *, gun_count=1, name=None, sn=None, tag=""):
    d = Device(
        sn=sn or f"SN-{uuid.uuid4().hex[:8]}",
        name=name or f"充电桩{tag}",
        code=f"CD{uuid.uuid4().hex[:6].upper()}",
        type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE,
        station_id=station_id, gun_count=gun_count,
    )
    session.add(d); session.commit(); session.refresh(d)
    return d


@pytest.fixture(autouse=True)
def _tmp_qrcode_dir(monkeypatch, tmp_path):
    """generate 端点用 os.path 拼装 uploads/qrcodes 写 PNG, monkeypatch os.makedirs/open
    无法整体替换; 改为让端点写 tmp 目录: 把项目 uploads 路径指向 tmp。"""
    uploads = tmp_path / "uploads" / "qrcodes"
    uploads.mkdir(parents=True, exist_ok=True)
    # 端点用 os.path.dirname(...)×4 拼出 backend/uploads/qrcodes, 无法简单 patch;
    # 改为 monkeypatch open 仅影响图片写入不现实(也写 DB)。采用更稳的方式: 让 generate
    # 在 tmp 下跑 —— patch os.path.join 拦截 qrcodes 段。
    import app.api.v1.operate.charger_qrcode as mod
    real_join = mod.os.path.join

    def _join(*parts):
        if len(parts) >= 2 and parts[-1] == "qrcodes" and "uploads" in parts:
            return str(uploads)
        return real_join(*parts)

    monkeypatch.setattr(mod.os.path, "join", _join)
    yield uploads


# ==================== 1. 生成 ====================

class TestGenerate:

    def test_generate_single_gun_charger(self, client):
        """单枪桩生成 1 张二维码 (gun_no=01), 14 位桩编号 + 2 位枪号 = 16 位枪号。"""
        s = client._sesh
        st = _seed_station(s, tag="G1")
        d = _seed_charger(s, st.id, gun_count=1, tag="单枪")
        r = client.post(f"{QR_URL}/generate", json={"device_ids": [d.id]})
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["total"] == 1
        assert data["failed"] == 0
        gen = data["generated"][0]
        assert gen["device_id"] == d.id
        assert gen["gun_no"] == 1
        assert len(gen["pile_code"]) == 14
        assert len(gen["qr_code"]) == 16
        assert gen["qr_code"].endswith("01")
        assert gen["pile_code"].isdigit()
        assert gen["qr_code"].isdigit()

    def test_generate_dual_gun_charger(self, client):
        """双枪桩生成 2 张二维码 (gun_no 01/02)。"""
        s = client._sesh
        st = _seed_station(s, tag="G2")
        d = _seed_charger(s, st.id, gun_count=2, tag="双枪")
        r = client.post(f"{QR_URL}/generate", json={"device_ids": [d.id]})
        assert r.status_code == 200
        gens = r.json()["data"]["generated"]
        assert len(gens) == 2
        gun_nos = sorted(g["gun_no"] for g in gens)
        assert gun_nos == [1, 2]

    def test_generate_idempotent_overwrites(self, client):
        """同设备重复生成覆盖旧码、不新增行 (幂等)。"""
        s = client._sesh
        st = _seed_station(s, tag="G3")
        d = _seed_charger(s, st.id, gun_count=1, tag="幂等")
        client.post(f"{QR_URL}/generate", json={"device_ids": [d.id]})
        before = s.query(DeviceQRCode).filter(DeviceQRCode.device_id == d.id).count()
        assert before == 1
        # 重复生成: 行数不变, print_count 递增
        client.post(f"{QR_URL}/generate", json={"device_ids": [d.id]})
        after = s.query(DeviceQRCode).filter(DeviceQRCode.device_id == d.id).count()
        assert after == 1
        rec = s.query(DeviceQRCode).filter(DeviceQRCode.device_id == d.id, DeviceQRCode.gun_no == 1).first()
        assert rec.print_count == 2

    def test_generate_non_charger_device_in_errors(self, client):
        """非充电桩设备 → 进 errors, 非 500。"""
        s = client._sesh
        st = _seed_station(s, tag="G4")
        inv = Device(
            sn=f"SN-{uuid.uuid4().hex[:8]}", name="逆变器", code=f"INV{uuid.uuid4().hex[:6]}",
            type=DeviceType.PV_INVERTER, status=DeviceStatus.ONLINE, station_id=st.id,
        )
        s.add(inv); s.commit(); s.refresh(inv)
        r = client.post(f"{QR_URL}/generate", json={"device_ids": [inv.id]})
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 0
        assert data["failed"] == 1
        assert any(e["device_id"] == inv.id and "充电桩" in e["error"] for e in data["errors"])

    def test_generate_not_exist_device_in_errors(self, client):
        r = client.post(f"{QR_URL}/generate", json={"device_ids": [999999]})
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["failed"] == 1
        assert data["errors"][0]["error"] == "设备不存在"

    def test_generate_empty_device_ids_422(self, client):
        r = client.post(f"{QR_URL}/generate", json={"device_ids": []})
        assert r.status_code == 422  # min_length=1

    def test_generate_viewer_forbidden_403(self, client):
        """viewer 无 operate:manage → router 级 403。"""
        from app.models.user import Team
        s = client._sesh
        t = Team(name=f"队{uuid.uuid4().hex[:4]}", code=f"T{uuid.uuid4().hex[:4]}")
        s.add(t); s.commit(); s.refresh(t)
        st = _seed_station(s, team_id=t.id, tag="G5")
        d = _seed_charger(s, st.id, tag="v")
        u = _add_user(s, f"viewer_{uuid.uuid4().hex[:6]}", role=UserRole.VIEWER, team_id=t.id)
        tok = _login_token(client, u.username)
        r = client.post(f"{QR_URL}/generate", json={"device_ids": [d.id]}, headers=_auth(tok))
        assert r.status_code == 403

    def test_generate_anonymous_401(self, anon_client):
        r = anon_client.post(f"{QR_URL}/generate", json={"device_ids": [1]})
        assert r.status_code == 401


# ==================== 2. 单张下载 ====================

class TestDownloadSingle:

    def test_download_returns_png(self, client):
        s = client._sesh
        st = _seed_station(s, tag="DL1")
        d = _seed_charger(s, st.id, tag="下载")
        client.post(f"{QR_URL}/generate", json={"device_ids": [d.id]})
        r = client.get(f"{QR_URL}/download/{d.id}")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "image/png"
        assert "attachment" in r.headers["content-disposition"]
        assert len(r.content) > 0

    def test_download_specific_gun(self, client):
        s = client._sesh
        st = _seed_station(s, tag="DL2")
        d = _seed_charger(s, st.id, gun_count=2, tag="双枪下")
        client.post(f"{QR_URL}/generate", json={"device_ids": [d.id]})
        r = client.get(f"{QR_URL}/download/{d.id}", params={"gun_no": 2})
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/png"

    def test_download_device_not_exist_404(self, client):
        r = client.get(f"{QR_URL}/download/999999")
        assert r.status_code == 404

    def test_download_no_qrcode_404(self, client):
        """设备存在但未生成二维码 → 404。"""
        s = client._sesh
        st = _seed_station(s, tag="DL3")
        d = _seed_charger(s, st.id, tag="未生成")
        r = client.get(f"{QR_URL}/download/{d.id}")
        assert r.status_code == 404


# ==================== 3. 批量下载 ====================

class TestBatchDownload:

    def test_batch_download_returns_zip(self, client):
        s = client._sesh
        st = _seed_station(s, tag="BD1")
        d1 = _seed_charger(s, st.id, tag="批1")
        d2 = _seed_charger(s, st.id, gun_count=2, tag="批2")
        client.post(f"{QR_URL}/generate", json={"device_ids": [d1.id, d2.id]})
        r = client.post(f"{QR_URL}/batch-download", json={"device_ids": [d1.id, d2.id]})
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "application/zip"
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        names = zf.namelist()
        # d1 单枪 1 张 + d2 双枪 2 张 = 3 张 png
        assert len(names) == 3
        assert all(n.endswith(".png") for n in names)

    def test_batch_download_no_qrcodes_404(self, client):
        """无可下载二维码 (设备未生成 / 非充电桩) → 404。"""
        s = client._sesh
        st = _seed_station(s, tag="BD2")
        d = _seed_charger(s, st.id, tag="空批")
        r = client.post(f"{QR_URL}/batch-download", json={"device_ids": [d.id]})
        assert r.status_code == 404

    def test_batch_download_skips_non_charger(self, client):
        """非充电桩设备静默跳过 (不报错), 仅打包充电桩二维码。"""
        s = client._sesh
        st = _seed_station(s, tag="BD3")
        chg = _seed_charger(s, st.id, tag="混1")
        inv = Device(
            sn=f"SN-{uuid.uuid4().hex[:8]}", name="逆变器", code=f"INV{uuid.uuid4().hex[:6]}",
            type=DeviceType.PV_INVERTER, status=DeviceStatus.ONLINE, station_id=st.id,
        )
        s.add(inv); s.commit(); s.refresh(inv)
        client.post(f"{QR_URL}/generate", json={"device_ids": [chg.id]})
        r = client.post(f"{QR_URL}/batch-download", json={"device_ids": [chg.id, inv.id]})
        assert r.status_code == 200
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        assert len(zf.namelist()) == 1  # 仅充电桩那 1 张


# ==================== 4. 列表 ====================

class TestListQrcodes:

    def test_list_returns_rows(self, client):
        s = client._sesh
        st = _seed_station(s, tag="LS1")
        d = _seed_charger(s, st.id, gun_count=2, tag="列表")
        client.post(f"{QR_URL}/generate", json={"device_ids": [d.id]})
        r = client.get(f"{QR_URL}/list")
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["total"] >= 1
        # 该设备 2 把枪展开成 2 行
        rows = [it for it in data["items"] if it["device_id"] == d.id]
        assert len(rows) == 2
        assert all(it["has_qrcode"] for it in rows)
        assert all(len(it["qr_code"]) == 16 for it in rows)

    def test_list_device_without_qrcode_marked(self, client):
        """未生成二维码的充电桩 → 列表占位行 has_qrcode=False。"""
        s = client._sesh
        st = _seed_station(s, tag="LS2")
        d = _seed_charger(s, st.id, tag="无码桩")
        r = client.get(f"{QR_URL}/list")
        assert r.status_code == 200
        rows = [it for it in r.json()["data"]["items"] if it["device_id"] == d.id]
        assert rows and rows[0]["has_qrcode"] is False

    def test_list_filter_by_station(self, client):
        s = client._sesh
        st1 = _seed_station(s, tag="LS3a")
        st2 = _seed_station(s, tag="LS3b")
        d1 = _seed_charger(s, st1.id, tag="站1桩")
        _seed_charger(s, st2.id, tag="站2桩")
        client.post(f"{QR_URL}/generate", json={"device_ids": [d1.id]})
        r = client.get(f"{QR_URL}/list", params={"station_id": st1.id})
        assert r.status_code == 200
        for it in r.json()["data"]["items"]:
            assert it["device_id"] == d1.id
