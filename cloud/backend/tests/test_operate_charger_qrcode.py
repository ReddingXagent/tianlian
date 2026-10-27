"""
运营-充电桩收费二维码 API 测试 — 工作卡 c7523ad8

云快充协议 V1.6 改造（丁哥 01:00 提出）：
- 桩编号 14 位纯数字（6 位国标行政区划码 + 8 位桩序号）
- 枪号 16 位（14 位桩编号 + 2 位枪号尾缀）
- 单双枪语义：Device.gun_count 决定二维码张数（单枪 1 张尾缀 01，双枪 2 张 01/02）

覆盖 /api/v1/operate/charger-qrcode*:
- 桩编号/枪号生成规则（纯函数）
- 批量生成: POST /charger-qrcode/generate （含双枪展开、幂等、旧 20 位覆盖）
- 单张下载: GET /charger-qrcode/download/{device_id}?gun_no=
- 批量下载ZIP: POST /charger-qrcode/batch-download （双枪展开两张）
- 列表查询: GET /charger-qrcode/list （按枪返回行）
- 异常: 非充电桩设备、设备不存在、未生成即下载
"""
import io
import zipfile

import pytest

from app.api.v1.operate.charger_qrcode import (
    generate_pile_code,
    generate_gun_code,
    DEFAULT_REGION_CODE,
)


# ── 桩编号 / 枪号生成（纯函数） ──

class TestPileCode:
    def test_basic_format_14_digits(self):
        code = generate_pile_code("320106", 1)
        assert len(code) == 14
        assert code.isdigit()
        assert code == "320106" + "00000001"

    def test_region_padding(self):
        """短行政区划码右补 0 到 6 位"""
        code = generate_pile_code("3201", 1)
        assert code[:6] == "320100"
        assert len(code) == 14

    def test_region_truncation(self):
        """超长行政区划码截断到 6 位"""
        code = generate_pile_code("3201069", 1)
        assert code[:6] == "320106"
        assert len(code) == 14

    def test_pile_seq_padding(self):
        code = generate_pile_code("320106", 42)
        assert code[6:] == "00000042"

    def test_pile_seq_wraps(self):
        """桩序号取模 1e8（8 位上限）"""
        code = generate_pile_code("320106", 100000001)
        assert code[6:] == "00000001"

    def test_none_region_uses_default(self):
        code = generate_pile_code(None, 1)
        assert code[:6] == DEFAULT_REGION_CODE
        assert len(code) == 14
        assert code.isdigit()


class TestGunCode:
    def test_gun_code_16_digits(self):
        pile = generate_pile_code("320106", 1)
        g1 = generate_gun_code(pile, 1)
        assert len(g1) == 16
        assert g1.isdigit()
        assert g1[:14] == pile
        assert g1[-2:] == "01"

    def test_gun2_suffix(self):
        pile = generate_pile_code("320106", 1)
        assert generate_gun_code(pile, 2)[-2:] == "02"

    def test_gun_no_padding(self):
        pile = generate_pile_code("320106", 1)
        assert generate_gun_code(pile, 5)[-2:] == "05"

    def test_gun_no_wraps(self):
        """枪号取模 100（2 位尾缀上限）"""
        pile = generate_pile_code("320106", 1)
        assert generate_gun_code(pile, 101)[-2:] == "01"


# ── API 测试 ──

def _login(client):
    r = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _make_charger(session, station_id, gun_count, code):
    """在指定站点造一个 N 枪充电桩（直连 session，不走 HTTP）。"""
    from app.models.device import Device, DeviceType, DeviceStatus
    dev = Device(
        sn=f"SN-{code}", name=f"桩{code}", code=code,
        type=DeviceType.CHARGER_DC, status=DeviceStatus.ONLINE,
        station_id=station_id, gun_count=gun_count,
    )
    session.add(dev)
    session.commit()
    session.refresh(dev)
    return dev


GEN_URL = "/api/v1/operate/charger-qrcode/generate"


class TestGenerateQRCode:
    def test_generate_for_single_gun_charger(self, client, seed_users, seed_devices):
        """单枪桩生成 1 张码，桩号 14 位、枪号 16 位"""
        token = _login(client)
        chg = seed_devices["chg001"]  # gun_count 默认 1
        r = client.post(GEN_URL, json={"device_ids": [chg.id]}, headers=_auth_headers(token))
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["total"] == 1
        assert data["failed"] == 0
        item = data["generated"][0]
        assert item["device_id"] == chg.id
        assert len(item["pile_code"]) == 14
        assert item["pile_code"].isdigit()
        assert item["gun_no"] == 1
        assert len(item["qr_code"]) == 16
        assert item["qr_code"][:14] == item["pile_code"]
        assert item["qr_code"].isdigit()

    def test_generate_double_gun_expands(self, client, seed_users, seed_stations):
        """双枪桩按 gun_count 展开为 2 行（尾缀 01/02）"""
        token = _login(client)
        dev = _make_charger(client._sesh, seed_stations["station_a"].id, gun_count=2, code="DBL001")
        r = client.post(GEN_URL, json={"device_ids": [dev.id]}, headers=_auth_headers(token))
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["total"] == 2
        assert data["failed"] == 0
        guns = sorted(it["gun_no"] for it in data["generated"])
        assert guns == [1, 2]
        pile = data["generated"][0]["pile_code"]
        assert len(pile) == 14
        suffixes = sorted(it["qr_code"][-2:] for it in data["generated"])
        assert suffixes == ["01", "02"]
        for it in data["generated"]:
            assert it["pile_code"] == pile  # 同桩同桩号
            assert len(it["qr_code"]) == 16
            assert it["qr_code"][:14] == pile

    def test_generate_idempotent_regenerates(self, client, seed_users, seed_devices):
        """重复生成幂等：枪号不变、DB 不新增行"""
        from app.models.device_qrcode import DeviceQRCode
        token = _login(client)
        chg = seed_devices["chg001"]
        r1 = client.post(GEN_URL, json={"device_ids": [chg.id]}, headers=_auth_headers(token))
        code1 = r1.json()["data"]["generated"][0]["qr_code"]
        r2 = client.post(GEN_URL, json={"device_ids": [chg.id]}, headers=_auth_headers(token))
        code2 = r2.json()["data"]["generated"][0]["qr_code"]
        assert code1 == code2
        rows = client._sesh.query(DeviceQRCode).filter(DeviceQRCode.device_id == chg.id).all()
        assert len(rows) == 1  # 单枪，幂等不翻倍

    def test_generate_overwrites_old_20char_record(self, client, seed_users, seed_devices):
        """旧 20 位记录被幂等覆盖为新 16 位枪号（边界：老数据迁移场景）"""
        from app.models.device_qrcode import DeviceQRCode
        token = _login(client)
        chg = seed_devices["chg001"]
        s = client._sesh
        old = DeviceQRCode(
            device_id=chg.id, gun_no=1,
            qr_code="MA1234567000100000001",  # 旧 20 位含字母
            is_active=True,
        )
        s.add(old)
        s.commit()
        r = client.post(GEN_URL, json={"device_ids": [chg.id]}, headers=_auth_headers(token))
        assert r.status_code == 200, r.text
        s.expire_all()
        row = s.query(DeviceQRCode).filter(DeviceQRCode.device_id == chg.id).first()
        assert len(row.qr_code) == 16
        assert row.qr_code.isdigit()  # 不再含字母

    def test_generate_double_to_single_deactivates_extra(self, client, seed_users, seed_stations):
        """双枪→单枪重生成：多余枪行置 is_active=False（旧码失效可接受）"""
        from app.models.device_qrcode import DeviceQRCode
        token = _login(client)
        dev = _make_charger(client._sesh, seed_stations["station_a"].id, gun_count=2, code="D2S001")
        # 先按双枪生成
        client.post(GEN_URL, json={"device_ids": [dev.id]}, headers=_auth_headers(token))
        # 改成单枪再生成
        dev.gun_count = 1
        client._sesh.commit()
        client.post(GEN_URL, json={"device_ids": [dev.id]}, headers=_auth_headers(token))
        rows = client._sesh.query(DeviceQRCode).filter(DeviceQRCode.device_id == dev.id).all()
        active = [r for r in rows if r.is_active]
        assert len(active) == 1
        assert active[0].gun_no == 1

    def test_generate_custom_region_code(self, client, seed_users, seed_devices):
        """自定义 6 位行政区划码"""
        token = _login(client)
        chg = seed_devices["chg001"]
        r = client.post(
            GEN_URL,
            json={"device_ids": [chg.id], "region_code": "110108"},
            headers=_auth_headers(token),
        )
        assert r.status_code == 200
        pile = r.json()["data"]["generated"][0]["pile_code"]
        assert pile.startswith("110108")

    def test_generate_invalid_region_code_422(self, client, seed_users, seed_devices):
        """非 6 位数字行政区划码 → 422"""
        token = _login(client)
        chg = seed_devices["chg001"]
        r = client.post(
            GEN_URL,
            json={"device_ids": [chg.id], "region_code": "MA9999"},  # 含字母
            headers=_auth_headers(token),
        )
        assert r.status_code == 422

    def test_generate_rejects_non_charger(self, client, seed_users, seed_devices):
        """非充电桩设备应报错"""
        token = _login(client)
        inv = seed_devices["inv001"]  # PV_INVERTER
        r = client.post(GEN_URL, json={"device_ids": [inv.id]}, headers=_auth_headers(token))
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 0
        assert data["failed"] == 1
        assert "非充电桩" in data["errors"][0]["error"]

    def test_generate_nonexistent_device(self, client, seed_users):
        token = _login(client)
        r = client.post(GEN_URL, json={"device_ids": [99999]}, headers=_auth_headers(token))
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["failed"] == 1
        assert "不存在" in data["errors"][0]["error"]

    def test_generate_requires_auth(self, anon_client, seed_devices):
        chg = seed_devices["chg001"]
        r = anon_client.post(GEN_URL, json={"device_ids": [chg.id]})
        assert r.status_code in (401, 403)


class TestDownloadQRCode:
    def test_download_after_generate(self, client, seed_users, seed_devices):
        """生成后下载单张二维码（默认枪 1）"""
        token = _login(client)
        chg = seed_devices["chg001"]
        client.post(GEN_URL, json={"device_ids": [chg.id]}, headers=_auth_headers(token))
        r = client.get(
            f"/api/v1/operate/charger-qrcode/download/{chg.id}",
            headers=_auth_headers(token),
        )
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/png"
        assert r.content[:4] == b"\x89PNG"

    def test_download_specific_gun_no(self, client, seed_users, seed_stations):
        """双枪桩下载指定枪号（gun_no=2）"""
        token = _login(client)
        dev = _make_charger(client._sesh, seed_stations["station_a"].id, gun_count=2, code="DL001")
        client.post(GEN_URL, json={"device_ids": [dev.id]}, headers=_auth_headers(token))
        r = client.get(
            f"/api/v1/operate/charger-qrcode/download/{dev.id}?gun_no=2",
            headers=_auth_headers(token),
        )
        assert r.status_code == 200
        assert r.content[:4] == b"\x89PNG"

    def test_download_without_generate_404(self, client, seed_users, seed_devices):
        token = _login(client)
        chg = seed_devices["chg001"]
        r = client.get(
            f"/api/v1/operate/charger-qrcode/download/{chg.id}",
            headers=_auth_headers(token),
        )
        assert r.status_code == 404

    def test_download_nonexistent_device_404(self, client, seed_users):
        token = _login(client)
        r = client.get(
            "/api/v1/operate/charger-qrcode/download/99999",
            headers=_auth_headers(token),
        )
        assert r.status_code == 404


class TestBatchDownload:
    def test_batch_download_zip(self, client, seed_users, seed_devices):
        """单枪桩批量下载返回 ZIP（1 张）"""
        token = _login(client)
        chg = seed_devices["chg001"]
        client.post(GEN_URL, json={"device_ids": [chg.id]}, headers=_auth_headers(token))
        r = client.post(
            "/api/v1/operate/charger-qrcode/batch-download",
            json={"device_ids": [chg.id]},
            headers=_auth_headers(token),
        )
        assert r.status_code == 200
        assert "application/zip" in r.headers["content-type"]
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        names = zf.namelist()
        assert len(names) == 1
        assert names[0].endswith(".png")

    def test_batch_download_double_gun_two_files(self, client, seed_users, seed_stations):
        """双枪桩批量下载 ZIP 内含 2 张（按枪展开）"""
        token = _login(client)
        dev = _make_charger(client._sesh, seed_stations["station_a"].id, gun_count=2, code="BD001")
        client.post(GEN_URL, json={"device_ids": [dev.id]}, headers=_auth_headers(token))
        r = client.post(
            "/api/v1/operate/charger-qrcode/batch-download",
            json={"device_ids": [dev.id]},
            headers=_auth_headers(token),
        )
        assert r.status_code == 200
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        names = zf.namelist()
        assert len(names) == 2
        for n in names:
            assert n.endswith(".png")

    def test_batch_download_empty_404(self, client, seed_users, seed_devices):
        token = _login(client)
        chg = seed_devices["chg001"]
        r = client.post(
            "/api/v1/operate/charger-qrcode/batch-download",
            json={"device_ids": [chg.id]},
            headers=_auth_headers(token),
        )
        assert r.status_code == 404


class TestListQRCodes:
    def test_list_empty(self, client, seed_users, seed_devices):
        token = _login(client)
        r = client.get("/api/v1/operate/charger-qrcode/list", headers=_auth_headers(token))
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] >= 0

    def test_list_after_generate_returns_gun_rows(self, client, seed_users, seed_devices):
        """生成后列表按枪返回行（含 gun_no / 16 位 qr_code）"""
        token = _login(client)
        chg = seed_devices["chg001"]
        client.post(GEN_URL, json={"device_ids": [chg.id]}, headers=_auth_headers(token))
        r = client.get("/api/v1/operate/charger-qrcode/list", headers=_auth_headers(token))
        assert r.status_code == 200
        data = r.json()["data"]
        item = next(i for i in data["items"] if i["device_id"] == chg.id and i.get("gun_no") == 1)
        assert item["has_qrcode"] is True
        assert len(item["pile_code"]) == 14
        assert len(item["qr_code"]) == 16

    def test_list_double_gun_two_rows(self, client, seed_users, seed_stations):
        """双枪桩列表返回 2 行（按枪）"""
        token = _login(client)
        dev = _make_charger(client._sesh, seed_stations["station_a"].id, gun_count=2, code="LT001")
        client.post(GEN_URL, json={"device_ids": [dev.id]}, headers=_auth_headers(token))
        r = client.get("/api/v1/operate/charger-qrcode/list", headers=_auth_headers(token))
        rows = [i for i in r.json()["data"]["items"] if i["device_id"] == dev.id]
        assert len(rows) == 2
        assert sorted(i["gun_no"] for i in rows) == [1, 2]

    def test_list_pagination(self, client, seed_users, seed_devices):
        token = _login(client)
        r = client.get(
            "/api/v1/operate/charger-qrcode/list?page=1&page_size=1",
            headers=_auth_headers(token),
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["page"] == 1
        assert data["page_size"] == 1
        assert len(data["items"]) <= 1

    def test_list_filter_by_station(self, client, seed_users, seed_devices, seed_stations):
        token = _login(client)
        sta = seed_stations["station_a"]
        r = client.get(
            f"/api/v1/operate/charger-qrcode/list?station_id={sta.id}",
            headers=_auth_headers(token),
        )
        assert r.status_code == 200


class TestListQueryCountCard11f7d020:
    """卡 11f7d020: list N+1 消除 — SELECT 数不随设备数线性增长 + 行内容对齐"""

    def test_list_query_count_and_rows(self, client, seed_users, seed_stations):
        from sqlalchemy import event as sa_event
        token = _login(client)
        # 5 台充电桩（含双枪），逐台生成二维码
        devs = []
        for i in range(5):
            dev = _make_charger(client._sesh, seed_stations["station_a"].id,
                                gun_count=2 if i == 0 else 1, code=f"NQL{i:03d}")
            devs.append(dev)
            r = client.post(GEN_URL, json={"device_ids": [dev.id]}, headers=_auth_headers(token))
            assert r.status_code == 200, r.text

        counter = {"n": 0}

        def _before(conn, cursor, statement, parameters, context, executemany):
            if statement.strip().upper().startswith("SELECT"):
                counter["n"] += 1

        eng = client._sesh.get_bind()
        sa_event.listen(eng, "before_cursor_execute", _before)
        try:
            r = client.get(
                "/api/v1/operate/charger-qrcode/list?page=1&page_size=100",
                headers=_auth_headers(token),
            )
        finally:
            sa_event.remove(eng, "before_cursor_execute", _before)
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        rows = [i for i in data["items"] if i["device_id"] in {d.id for d in devs}]
        # 行内容对齐: 双枪 2 行 + 单枪 4×1 行, 字段齐备
        assert len(rows) == 6
        assert sorted(i["gun_no"] for i in rows if i["device_id"] == devs[0].id) == [1, 2]
        for row in rows:
            assert row["has_qrcode"] is True
            assert row["station_name"] == "测试电站A"
            assert len(row["qr_code"]) == 16
        # 查询数硬上界: 原实现 = 设备 count+分页 + 每设备 qrcode/station 2 查询 ≈ 12+；
        # 批量化后 ≤ 8
        assert counter["n"] <= 8, f"N+1 未消除: list 触发 {counter['n']} 条 SELECT"
