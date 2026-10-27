"""
数字孪生可视化 API 测试 — 真实数据测试，无 mock。

字段契约以 frontend/src/pages/DigitalTwin/hooks/useDigitalTwin.ts 为唯一真相：
- DeviceData.digital_twin_config 期望展开式字段 (scale_x/y/z, position_x/y/z,
  rotation_x/y/z, color_primary/secondary/accent, animations, status_mapping)
- getRealtime 期望 {station, scene, devices:[{device, digital_twin_config}]}

覆盖: models/scenes/data-points CRUD + realtime(契约结构 + N+1 SQL 计数)
     + scene layout + init-default
"""
import pytest
from sqlalchemy import event


def _auth(client, username="admin", password="admin123"):
    """登录 admin 拿 token，注入 Authorization 头。"""
    resp = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert resp.status_code == 200, f"login 失败: {resp.text}"
    data = resp.json()
    token = (data.get("data", {}).get("token") or data.get("token")
             or data.get("data", {}).get("access_token") or data.get("access_token"))
    assert token, f"login 响应未含 token: {data}"
    return {"Authorization": f"Bearer {token}"}


# ─── Models CRUD（展开式字段）───

class TestDigitalTwinModels:
    """DigitalTwinModel CRUD —— 字段对齐 model 实际列(scale_x/y/z 展开式)。"""

    def test_list_requires_auth(self, anon_client):
        """未认证 401"""
        assert anon_client.get("/api/v1/digital-twin/models").status_code in (401, 403)

    def test_create_and_get_model(self, client, seed_devices):
        headers = _auth(client)
        device_id = seed_devices["inv001"].id
        body = {
            "device_id": device_id,
            "model_type": "solar_inverter",
            "scale_x": 1.5, "scale_y": 1.0, "scale_z": 0.8,
            "position_x": 10.0, "position_y": 0.0, "position_z": 5.0,
            "rotation_x": 0.0, "rotation_y": 1.57, "rotation_z": 0.0,
            "color_primary": "#1890ff", "color_secondary": "#52c41a", "color_accent": "#faad14",
            "animations": {"fan_rotation": True, "led_blink": False},
            "status_mapping": {"online": "#52c41a", "fault": "#ff4d4f"},
        }
        r = client.post("/api/v1/digital-twin/models", json=body, headers=headers)
        assert r.status_code == 201, r.text
        created = r.json()
        # 展开式字段全部回显
        assert created["device_id"] == device_id
        assert created["model_type"] == "solar_inverter"
        assert created["scale_x"] == 1.5 and created["scale_z"] == 0.8
        assert created["rotation_y"] == 1.57
        assert created["color_primary"] == "#1890ff"
        assert created["animations"]["fan_rotation"] is True
        assert created["status_mapping"]["fault"] == "#ff4d4f"
        assert "id" in created and created["id"] > 0
        # GET 单个
        r2 = client.get(f"/api/v1/digital-twin/models/{created['id']}", headers=headers)
        assert r2.status_code == 200
        assert r2.json()["id"] == created["id"]

    def test_list_filter_by_device(self, client, seed_devices):
        headers = _auth(client)
        device_id = seed_devices["inv001"].id
        client.post("/api/v1/digital-twin/models",
                    json={"device_id": device_id, "model_type": "solar_inverter"}, headers=headers)
        r = client.get(f"/api/v1/digital-twin/models?device_id={device_id}", headers=headers)
        assert r.status_code == 200
        rows = r.json()["data"]["items"]
        assert len(rows) >= 1
        assert all(m["device_id"] == device_id for m in rows)

    def test_list_filter_by_station(self, client, seed_stations, seed_devices):
        """按 station 过滤需经 device join —— station_a 含 inv001/chg001"""
        headers = _auth(client)
        station_a = seed_stations["station_a"].id
        station_b = seed_stations["station_b"].id
        client.post("/api/v1/digital-twin/models",
                    json={"device_id": seed_devices["inv001"].id, "model_type": "solar_inverter"}, headers=headers)
        client.post("/api/v1/digital-twin/models",
                    json={"device_id": seed_devices["pcs001"].id, "model_type": "pcs"}, headers=headers)
        ra = client.get(f"/api/v1/digital-twin/models?station_id={station_a}", headers=headers)
        rb = client.get(f"/api/v1/digital-twin/models?station_id={station_b}", headers=headers)
        assert ra.status_code == 200 and rb.status_code == 200
        assert all(m["device_id"] in [seed_devices["inv001"].id, seed_devices["chg001"].id] for m in ra.json()["data"]["items"])
        assert all(m["device_id"] in [seed_devices["pcs001"].id, seed_devices["off001"].id] for m in rb.json()["data"]["items"])

    def test_update_model(self, client, seed_devices):
        headers = _auth(client)
        device_id = seed_devices["chg001"].id
        r = client.post("/api/v1/digital-twin/models",
                        json={"device_id": device_id, "model_type": "charger_dc", "color_primary": "#fff"}, headers=headers)
        mid = r.json()["id"]
        r2 = client.put(f"/api/v1/digital-twin/models/{mid}",
                        json={"color_primary": "#eb2f96", "scale_x": 2.0}, headers=headers)
        assert r2.status_code == 200, r2.text
        updated = r2.json()
        assert updated["color_primary"] == "#eb2f96"
        assert updated["scale_x"] == 2.0

    def test_delete_model(self, client, seed_devices):
        headers = _auth(client)
        device_id = seed_devices["off001"].id
        r = client.post("/api/v1/digital-twin/models",
                        json={"device_id": device_id, "model_type": "battery_rack"}, headers=headers)
        mid = r.json()["id"]
        rd = client.delete(f"/api/v1/digital-twin/models/{mid}", headers=headers)
        assert rd.status_code == 200
        assert client.get(f"/api/v1/digital-twin/models/{mid}", headers=headers).status_code == 404

    def test_get_nonexistent_404(self, client):
        headers = _auth(client)
        assert client.get("/api/v1/digital-twin/models/999999", headers=headers).status_code == 404


# ─── Scenes CRUD ───

class TestDigitalTwinScenes:
    """DigitalTwinScene CRUD —— 字段 {station_id, name, scene_config(JSON)}。"""

    def test_create_and_list_scene(self, client, seed_stations):
        headers = _auth(client)
        station_id = seed_stations["station_a"].id
        body = {
            "station_id": station_id,
            "name": "光储充全景",
            "scene_config": {"camera": {"fov": 50, "position": [0, 10, 15]}, "background": "#0a0a1a"},
        }
        r = client.post("/api/v1/digital-twin/scenes", json=body, headers=headers)
        assert r.status_code == 201, r.text
        created = r.json()
        assert created["station_id"] == station_id
        assert created["name"] == "光储充全景"
        assert created["scene_config"]["camera"]["fov"] == 50
        # list 过滤
        r2 = client.get(f"/api/v1/digital-twin/scenes?station_id={station_id}", headers=headers)
        assert r2.status_code == 200
        assert len(r2.json()["data"]["items"]) >= 1

    def test_update_scene(self, client, seed_stations):
        headers = _auth(client)
        station_id = seed_stations["station_a"].id
        r = client.post("/api/v1/digital-twin/scenes",
                        json={"station_id": station_id, "name": "旧名", "scene_config": {}}, headers=headers)
        sid = r.json()["id"]
        r2 = client.put(f"/api/v1/digital-twin/scenes/{sid}",
                        json={"name": "新名", "scene_config": {"ambient": 0.5}}, headers=headers)
        assert r2.status_code == 200, r2.text
        upd = r2.json()
        assert upd["name"] == "新名"
        assert upd["scene_config"]["ambient"] == 0.5

    def test_delete_scene(self, client, seed_stations):
        headers = _auth(client)
        station_id = seed_stations["station_b"].id
        r = client.post("/api/v1/digital-twin/scenes",
                        json={"station_id": station_id, "name": "待删", "scene_config": {}}, headers=headers)
        sid = r.json()["id"]
        assert client.delete(f"/api/v1/digital-twin/scenes/{sid}", headers=headers).status_code == 200
        assert client.get(f"/api/v1/digital-twin/scenes/{sid}", headers=headers).status_code == 404


# ─── Data Points CRUD ───

class TestDigitalTwinDataPoints:
    """DigitalTwinDataPoint CRUD —— 字段 {device_id, param_key, display_name, ...}。"""

    def test_create_and_list_data_point(self, client, seed_devices):
        headers = _auth(client)
        device_id = seed_devices["inv001"].id
        body = {
            "device_id": device_id,
            "param_key": "grid_voltage_a",
            "display_name": "A相电压",
            "unit": "V",
            "visual_type": "color",
            "normal_range": {"min": 0, "max": 240},
            "warn_range": {"min": 240, "max": 260},
            "danger_range": {"min": 260, "max": 300},
            "normal_color": "#52c41a", "warn_color": "#faad14", "danger_color": "#ff4d4f",
            "show_value": True, "show_unit": True, "decimal_places": 1,
        }
        r = client.post("/api/v1/digital-twin/data-points", json=body, headers=headers)
        assert r.status_code == 201, r.text
        created = r.json()
        assert created["device_id"] == device_id
        assert created["param_key"] == "grid_voltage_a"
        assert created["display_name"] == "A相电压"
        assert created["normal_range"]["max"] == 240
        assert created["danger_color"] == "#ff4d4f"
        # list 过滤（分页响应结构）
        r2 = client.get(f"/api/v1/digital-twin/data-points?device_id={device_id}", headers=headers)
        assert r2.status_code == 200
        body = r2.json()["data"]
        assert body["total"] >= 1
        assert body["page"] == 1 and body["page_size"] == 20
        assert any(it["id"] == created["id"] for it in body["items"])

    def test_update_data_point(self, client, seed_devices):
        headers = _auth(client)
        device_id = seed_devices["chg001"].id
        r = client.post("/api/v1/digital-twin/data-points",
                        json={"device_id": device_id, "param_key": "charger_power",
                              "display_name": "充电功率", "unit": "kW"}, headers=headers)
        pid = r.json()["id"]
        r2 = client.put(f"/api/v1/digital-twin/data-points/{pid}",
                        json={"display_name": "输出功率", "decimal_places": 2}, headers=headers)
        assert r2.status_code == 200, r2.text
        assert r2.json()["display_name"] == "输出功率"
        assert r2.json()["decimal_places"] == 2

    def test_delete_data_point(self, client, seed_devices):
        headers = _auth(client)
        device_id = seed_devices["pcs001"].id
        r = client.post("/api/v1/digital-twin/data-points",
                        json={"device_id": device_id, "param_key": "battery_soc",
                              "display_name": "电池SOC"}, headers=headers)
        pid = r.json()["id"]
        assert client.delete(f"/api/v1/digital-twin/data-points/{pid}", headers=headers).status_code == 200
        assert client.get(f"/api/v1/digital-twin/data-points", headers=headers).status_code == 200

    def test_list_data_points_pagination(self, client, seed_devices):
        """分页契约：page_size 上限、total 计数、page 越界返回空 items。"""
        headers = _auth(client)
        device_id = seed_devices["chg001"].id
        for i in range(3):
            r = client.post("/api/v1/digital-twin/data-points",
                            json={"device_id": device_id, "param_key": f"pag_{i}",
                                  "display_name": f"分页{i}"}, headers=headers)
            assert r.status_code == 201, r.text
        # 默认分页结构
        r = client.get(f"/api/v1/digital-twin/data-points?device_id={device_id}", headers=headers)
        assert r.status_code == 200
        body = r.json()["data"]
        assert set(body) >= {"items", "total", "page", "page_size"}
        assert body["total"] == 3
        assert body["page"] == 1 and body["page_size"] == 20
        assert len(body["items"]) == 3
        # page_size 生效
        r2 = client.get(f"/api/v1/digital-twin/data-points?device_id={device_id}&page_size=2", headers=headers)
        assert len(r2.json()["data"]["items"]) == 2
        assert r2.json()["data"]["total"] == 3
        # page 越界 → 空 items
        r3 = client.get(f"/api/v1/digital-twin/data-points?device_id={device_id}&page=99", headers=headers)
        assert r3.json()["data"]["items"] == []
        assert r3.json()["data"]["total"] == 3
        # page_size 上限（>100 → 422）
        r4 = client.get(f"/api/v1/digital-twin/data-points?page_size=101", headers=headers)
        assert r4.status_code == 422

    def test_create_data_point_invalid_visual_type_400(self, client, seed_devices):
        """visual_type 非法值 → 400（与 model_type 的 _coerce_model_type 风格一致）。"""
        headers = _auth(client)
        device_id = seed_devices["inv001"].id
        r = client.post("/api/v1/digital-twin/data-points",
                        json={"device_id": device_id, "param_key": "bad_vis",
                              "display_name": "非法可视化", "visual_type": "glow"},
                        headers=headers)
        assert r.status_code == 400, r.text
        # 合法值仍可正常创建
        r2 = client.post("/api/v1/digital-twin/data-points",
                         json={"device_id": device_id, "param_key": "ok_vis",
                               "display_name": "合法", "visual_type": "scale"},
                         headers=headers)
        assert r2.status_code == 201, r2.text
        assert r2.json()["visual_type"] == "scale"

    def test_update_data_point_invalid_visual_type_400(self, client, seed_devices):
        """更新时 visual_type 非法值同样 → 400。"""
        headers = _auth(client)
        device_id = seed_devices["chg001"].id
        r = client.post("/api/v1/digital-twin/data-points",
                        json={"device_id": device_id, "param_key": "p",
                              "display_name": "x"}, headers=headers)
        pid = r.json()["id"]
        r2 = client.put(f"/api/v1/digital-twin/data-points/{pid}",
                        json={"visual_type": "bogus"}, headers=headers)
        assert r2.status_code == 400, r2.text


# ─── Realtime（前端契约结构 + N+1 SQL 计数）───

class TestDigitalTwinRealtime:
    """GET /realtime?station_id=X —— 前端 useDigitalTwin 期望的 {station, scene, devices}。"""

    def test_realtime_requires_auth(self, anon_client):
        assert anon_client.get("/api/v1/digital-twin/realtime?station_id=1").status_code in (401, 403)

    def test_realtime_structure_matches_frontend(self, client, seed_stations, seed_devices):
        """前端契约: {station:{id,name,address}, scene|null, devices:[{device, digital_twin_config}]}"""
        headers = _auth(client)
        station_id = seed_stations["station_a"].id
        # 给 station_a 的两设备建孪生配置
        for key, mtype in [("inv001", "solar_inverter"), ("chg001", "charger_dc")]:
            client.post("/api/v1/digital-twin/models",
                        json={"device_id": seed_devices[key].id, "model_type": mtype,
                              "color_primary": "#fff", "scale_x": 1.0},
                        headers=headers)
        r = client.get(f"/api/v1/digital-twin/realtime?station_id={station_id}", headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        # station 段
        assert body["station"]["id"] == station_id
        assert body["station"]["name"]  # Station.name 非空
        assert "address" in body["station"]
        # scene 段（键必须存在，值可为 null）
        assert "scene" in body
        # devices 段
        assert isinstance(body["devices"], list)
        assert len(body["devices"]) == 2
        first = body["devices"][0]
        assert "device" in first and "digital_twin_config" in first
        # device 字段（前端 DeviceData.device）
        d = first["device"]
        for f in ["id", "name", "type", "status", "health_score"]:
            assert f in d, f"device 缺字段 {f}"
        # digital_twin_config 展开式字段（前端 useDigitalTwin L19-38 逐字段）
        cfg = first["digital_twin_config"]
        expected = ["id", "model_type", "scale_x", "scale_y", "scale_z",
                    "position_x", "position_y", "position_z",
                    "rotation_x", "rotation_y", "rotation_z",
                    "color_primary", "color_secondary", "color_accent",
                    "animations", "status_mapping", "created_at", "updated_at"]
        for f in expected:
            assert f in cfg, f"digital_twin_config 缺字段 {f}"

    def test_realtime_handles_no_config(self, client, seed_stations, seed_devices):
        """设备无孪生配置时 digital_twin_config 应为 null，不崩。"""
        headers = _auth(client)
        station_id = seed_stations["station_a"].id
        # 不建任何 model 配置
        r = client.get(f"/api/v1/digital-twin/realtime?station_id={station_id}", headers=headers)
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body["devices"], list)
        # station_a 有 inv001/chg001 两设备
        assert len(body["devices"]) == 2
        # 无配置 → digital_twin_config 为 null
        assert all(item["digital_twin_config"] is None for item in body["devices"])
        assert all("device" in item for item in body["devices"])

    def test_realtime_no_n_plus_1_on_config_load(self, client, seed_stations, seed_devices):
        """N+1 断言: 设备孪生配置必须批量(IN)加载。

        关键: 必须变化「设备总数」而非「有配置的设备数」。realtime 总是加载站点
        全部设备，故 per-device N+1 的查询数随设备总数线性增长；只改配置数而设备
        总数恒定(原测试的缺陷)会让 N+1 实现也产生 delta=0，给出虚假信心。

        本测试: station_a 初始 2 设备(均建配置)；场景2 再为 station_a 新建第3设备
        并建配置(设备总数 2→3)。批量 IN 加载查询数不增(delta=0)；per-device N+1
        每多一设备多一次查询(delta>=1)。"""
        from app.models.device import Device, DeviceType, DeviceStatus
        headers = _auth(client)
        station_id = seed_stations["station_a"].id
        engine = client._sesh.bind

        def _count_realtime_queries():
            counter = {"n": 0}

            def _on_cursor(conn, cursor, statement, params, ctx, executemany):
                counter["n"] += 1

            event.listen(engine, "after_cursor_execute", _on_cursor)
            try:
                r = client.get(f"/api/v1/digital-twin/realtime?station_id={station_id}", headers=headers)
                assert r.status_code == 200, r.text
            finally:
                event.remove(engine, "after_cursor_execute", _on_cursor)
            return counter["n"]

        # 场景1: station_a 2 设备(inv001/chg001)，均建孪生配置
        for key, mtype in [("inv001", "solar_inverter"), ("chg001", "charger_dc")]:
            client.post("/api/v1/digital-twin/models",
                        json={"device_id": seed_devices[key].id, "model_type": mtype}, headers=headers)
        n1 = _count_realtime_queries()

        # 场景2: 为 station_a 新建第3设备(设备总数 2→3)并建配置
        s = client._sesh
        extra = Device(sn="SN-TEST-N1", name="逆变器#2", code="INV002",
                       type=DeviceType.PV_INVERTER, status=DeviceStatus.ONLINE,
                       station_id=station_id, rated_power=30.0)
        s.add(extra)
        s.commit()
        s.refresh(extra)
        client.post("/api/v1/digital-twin/models",
                    json={"device_id": extra.id, "model_type": "solar_inverter"}, headers=headers)
        n2 = _count_realtime_queries()

        delta = n2 - n1
        # 批量加载: 设备总数 2→3 查询数不增(delta=0); N+1: delta>=1
        assert delta <= 0, (
            f"N+1 未修复: 设备孪生配置非批量加载。"
            f"设备总数 2→3，查询数 {n1}→{n2}（增量 {delta}），批量 IN 应为增量 0。"
        )

    def test_realtime_nonexistent_station_404(self, client):
        """station_id 提供但站点不存在 → 404（与 layout 一致，不再静默返回空）。"""
        headers = _auth(client)
        r = client.get("/api/v1/digital-twin/realtime?station_id=999999", headers=headers)
        assert r.status_code == 404, r.text


# ─── Scene Layout ───

class TestDigitalTwinSceneLayout:
    def test_scene_layout(self, client, seed_stations, seed_devices):
        headers = _auth(client)
        station_id = seed_stations["station_a"].id
        # 建 scene
        rs = client.post("/api/v1/digital-twin/scenes",
                         json={"station_id": station_id, "name": "布局场景",
                               "scene_config": {"background": "#0a0a1a"}}, headers=headers)
        sid = rs.json()["id"]
        # 建一个 model
        rm = client.post("/api/v1/digital-twin/models",
                         json={"device_id": seed_devices["inv001"].id, "model_type": "solar_inverter"}, headers=headers)
        mid = rm.json()["id"]
        # GET layout
        r = client.get(f"/api/v1/digital-twin/scenes/{sid}/layout", headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "scene" in body and "models" in body
        assert body["scene"]["id"] == sid

    def test_scene_layout_nonexistent_404(self, client):
        headers = _auth(client)
        assert client.get("/api/v1/digital-twin/scenes/999999/layout", headers=headers).status_code == 404


# ─── Init Default ───

class TestDigitalTwinInitDefault:
    def test_init_default_creates_scene_and_models(self, client, seed_stations, seed_devices):
        headers = _auth(client)
        station_id = seed_stations["station_a"].id
        r = client.post(f"/api/v1/digital-twin/init-default?station_id={station_id}", headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["scene_id"]
        assert body.get("models_count", 0) > 0
        # 验证 scene 落库
        rs = client.get(f"/api/v1/digital-twin/scenes?station_id={station_id}", headers=headers)
        assert any(s["id"] == body["scene_id"] for s in rs.json()["data"]["items"])

    def test_init_default_idempotent(self, client, seed_stations):
        """重复初始化不报错，返回已存在的 scene_id。"""
        headers = _auth(client)
        station_id = seed_stations["station_b"].id
        r1 = client.post(f"/api/v1/digital-twin/init-default?station_id={station_id}", headers=headers)
        sid1 = r1.json()["scene_id"]
        r2 = client.post(f"/api/v1/digital-twin/init-default?station_id={station_id}", headers=headers)
        assert r2.status_code == 200
        assert r2.json()["scene_id"] == sid1


# ─── WS handler 读路径写放大 + 并发初始化（卡 ac881e11）───

class TestDigitalTwinHandlerBatchInit:
    """digital_twin_handler.get_station_digital_twin_data —— 首调批量初始化:
    1) 多设备站点首次调用仅 1 次 commit (N 事务 → 1);
    2) 双线程并发首调不产生重复 scene 行、不抛未处理 IntegrityError。"""

    @staticmethod
    def _patch_counting_sessionlocal(test_db, monkeypatch):
        """包装 SessionLocal, 对每个新 session 的 commit 计数。"""
        # handler 运行时读 app.core.database.SessionLocal, 须 patch 该模块属性
        import app.core.database as db_mod
        real_local = test_db["SessionLocal"]
        counter = {"n": 0}

        class _CountingLocal:
            def __call__(self):
                s = real_local()
                real_commit = s.commit

                def _counting_commit(*a, **kw):
                    counter["n"] += 1
                    return real_commit(*a, **kw)

                s.commit = _counting_commit
                return s

        monkeypatch.setattr(db_mod, "SessionLocal", _CountingLocal())
        return counter

    @staticmethod
    def _seed_fresh_station(test_db, n_devices=3):
        """独立新站 + n 台 PV 设备, 无 scene 无 twin_config。"""
        import uuid
        from app.models.station import Station, StationStatus
        from app.models.device import Device, DeviceType, DeviceStatus
        db = test_db["session"]
        suffix = uuid.uuid4().hex[:6]
        st = Station(name=f"批量站{suffix}", code=f"BT{suffix}", address="x",
                     status=StationStatus.NORMAL)
        db.add(st)
        db.commit()
        db.refresh(st)
        devs = []
        for i in range(n_devices):
            dev = Device(sn=f"SN-BT-{suffix}-{i}", name=f"批量设备{i}",
                         code=f"BT{suffix}D{i}", type=DeviceType.PV_INVERTER,
                         status=DeviceStatus.ONLINE, station_id=st.id)
            db.add(dev)
            db.commit()
            db.refresh(dev)
            devs.append(dev)
        return st, devs

    def test_first_call_single_commit(self, test_db, monkeypatch):
        """多设备站点首调: 3 设备缺配置 + 缺 scene → 仅 1 次 commit。"""
        from app.ws.digital_twin_handler import DigitalTwinHandler
        commit_calls = self._patch_counting_sessionlocal(test_db, monkeypatch)
        st, devs = self._seed_fresh_station(test_db, n_devices=3)

        result = DigitalTwinHandler().get_station_digital_twin_data(st.id)
        assert "error" not in result
        assert len(result["devices"]) == 3
        assert all(d["digital_twin_config"]["id"] for d in result["devices"])
        assert result["scene"]["id"]
        assert commit_calls["n"] == 1, (
            f"写放大未修复: 首调应仅 1 次 commit, 实际 {commit_calls['n']} 次"
        )
        # 数据确实落库
        from app.models.digital_twin import DigitalTwinModel, DigitalTwinScene
        db = test_db["session"]
        assert db.query(DigitalTwinModel).filter(
            DigitalTwinModel.device_id.in_([d.id for d in devs])).count() == 3
        assert db.query(DigitalTwinScene).filter(
            DigitalTwinScene.station_id == st.id).count() == 1

    def test_warm_call_no_extra_commit(self, test_db, monkeypatch):
        """二次调用(scene/配置齐备) 零额外 commit —— 读路径不再写。"""
        from app.ws.digital_twin_handler import DigitalTwinHandler
        commit_calls = self._patch_counting_sessionlocal(test_db, monkeypatch)
        st, devs = self._seed_fresh_station(test_db, n_devices=2)
        DigitalTwinHandler().get_station_digital_twin_data(st.id)  # 首调初始化
        assert commit_calls["n"] == 1
        result = DigitalTwinHandler().get_station_digital_twin_data(st.id)  # 热调用
        assert "error" not in result
        assert commit_calls["n"] == 1, (
            f"读路径写放大: 配置齐备后调用不应再 commit, 实际 {commit_calls['n'] - 1} 次"
        )

    def test_concurrent_first_call_no_duplicate_scene(self, test_db, monkeypatch):
        """双线程并发首调: 无异常、scene 恰 1 行、每设备 twin_config 恰 1 行。"""
        import threading
        from app.ws.digital_twin_handler import DigitalTwinHandler
        self._patch_counting_sessionlocal(test_db, monkeypatch)
        st, devs = self._seed_fresh_station(test_db, n_devices=2)

        results, errors = [], []
        barrier = threading.Barrier(2)

        def _worker():
            try:
                barrier.wait(timeout=5)
                results.append(
                    DigitalTwinHandler().get_station_digital_twin_data(st.id))
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        t1 = threading.Thread(target=_worker)
        t2 = threading.Thread(target=_worker)
        t1.start()
        t2.start()
        t1.join(timeout=15)
        t2.join(timeout=15)

        assert not errors, f"并发首调抛异常: {errors!r}"
        assert len(results) == 2 and all("error" not in r for r in results)

        from app.models.digital_twin import DigitalTwinModel, DigitalTwinScene
        db = test_db["session"]
        scene_count = db.query(DigitalTwinScene).filter(
            DigitalTwinScene.station_id == st.id).count()
        assert scene_count == 1, f"并发重复建默认场景: {scene_count} 行"
        cfg_count = db.query(DigitalTwinModel).filter(
            DigitalTwinModel.device_id.in_([d.id for d in devs])).count()
        assert cfg_count == len(devs), f"并发重复建 twin_config: {cfg_count} 行"


# ─── DB 写操作异常保护（卡 d8acd3f9）───

class TestDigitalTwinDbErrorProtection:
    """DB 写操作失败 → db.rollback() + 路由级 HTTPException(500,'内部错误')，
    不泄露内部异常。验证点：500 状态码 + message='内部错误' + rollback 被调用 +
    原数据未被破坏。"""

    @staticmethod
    def _patch_commit_boom(client, monkeypatch):
        """patch 同一个 session.commit 抛 RuntimeError + spy rollback 计数。

        路由 db 即 client._sesh (conftest get_db override 返回同一 session 实例)。
        返回 rollback 计数器 dict，断言 rollback_calls["n"] >= 1 即证明路由 except
        调用了 rollback。
        """
        sesh = client._sesh
        rollback_calls = {"n": 0}
        real_rollback = sesh.rollback

        def _spy_rollback(*a, **kw):
            rollback_calls["n"] += 1
            return real_rollback(*a, **kw)

        def _boom(*a, **kw):
            raise RuntimeError("simulated db commit failure")

        monkeypatch.setattr(sesh, "commit", _boom)
        monkeypatch.setattr(sesh, "rollback", _spy_rollback)
        return rollback_calls

    def test_create_model_db_failure(self, client, seed_devices, monkeypatch):
        """POST /models commit 失败 → 500 + rollback, 数据未落库。"""
        headers = _auth(client)
        device_id = seed_devices["inv001"].id
        rollback_calls = self._patch_commit_boom(client, monkeypatch)

        r = client.post("/api/v1/digital-twin/models",
                        json={"device_id": device_id, "model_type": "solar_inverter"},
                        headers=headers)
        assert r.status_code == 500, r.text
        # 路由级保护抛 HTTPException(500,"内部错误"): 裸 TestClient app 返回 detail,
        # 生产 app.main 经 http_exception_handler 返回 message; 两者择一。
        assert r.json().get("detail") == "内部错误" or r.json().get("message") == "内部错误", r.text
        assert "simulated" not in r.text  # 不泄露内部异常明文
        assert rollback_calls["n"] >= 1  # rollback 被调用
        # rollback 生效: 还原 commit 后查询, model 未落库
        monkeypatch.undo()
        rget = client.get(f"/api/v1/digital-twin/models?device_id={device_id}", headers=headers)
        assert rget.status_code == 200
        assert rget.json()["data"]["items"] == []

    def test_update_model_db_failure_preserves_data(self, client, seed_devices, monkeypatch):
        """PUT /models/{id} commit 失败 → 500 + rollback, 原值未被破坏。"""
        headers = _auth(client)
        # 先正常创建一条 model (commit 成功, 此时未 patch)
        rc = client.post("/api/v1/digital-twin/models",
                         json={"device_id": seed_devices["chg001"].id,
                               "model_type": "charger_dc", "color_primary": "#ffffff"},
                         headers=headers)
        assert rc.status_code == 201, rc.text
        mid = rc.json()["id"]

        rollback_calls = self._patch_commit_boom(client, monkeypatch)
        r = client.put(f"/api/v1/digital-twin/models/{mid}",
                       json={"color_primary": "#eb2f96", "scale_x": 2.0}, headers=headers)
        assert r.status_code == 500, r.text
        assert r.json().get("detail") == "内部错误" or r.json().get("message") == "内部错误", r.text
        assert "simulated" not in r.text
        assert rollback_calls["n"] >= 1
        # rollback 保护: 原值仍在 (update 未落库)
        monkeypatch.undo()
        rget = client.get(f"/api/v1/digital-twin/models/{mid}", headers=headers)
        assert rget.status_code == 200
        assert rget.json()["color_primary"] == "#ffffff"

    def test_delete_scene_db_failure(self, client, seed_stations, monkeypatch):
        """DELETE /scenes/{id} commit 失败 → 500 + rollback, scene 仍在。"""
        headers = _auth(client)
        rc = client.post("/api/v1/digital-twin/scenes",
                         json={"station_id": seed_stations["station_a"].id,
                               "name": "待删场景", "scene_config": {}}, headers=headers)
        sid = rc.json()["id"]

        rollback_calls = self._patch_commit_boom(client, monkeypatch)
        r = client.delete(f"/api/v1/digital-twin/scenes/{sid}", headers=headers)
        assert r.status_code == 500, r.text
        assert r.json().get("detail") == "内部错误" or r.json().get("message") == "内部错误", r.text
        assert rollback_calls["n"] >= 1
        # rollback 保护: scene 未被删除
        monkeypatch.undo()
        assert client.get(f"/api/v1/digital-twin/scenes/{sid}", headers=headers).status_code == 200

    def test_init_default_db_failure(self, client, seed_stations, monkeypatch):
        """POST /init-default (flush + 多 add + commit) commit 失败 → 500 + rollback。"""
        headers = _auth(client)
        station_id = seed_stations["station_b"].id  # station_b 无既有 scene
        rollback_calls = self._patch_commit_boom(client, monkeypatch)

        r = client.post(f"/api/v1/digital-twin/init-default?station_id={station_id}", headers=headers)
        assert r.status_code == 500, r.text
        assert r.json().get("detail") == "内部错误" or r.json().get("message") == "内部错误", r.text
        assert "simulated" not in r.text
        assert rollback_calls["n"] >= 1
        # rollback 生效: 未留下脏 scene
        monkeypatch.undo()
        rs = client.get(f"/api/v1/digital-twin/scenes?station_id={station_id}", headers=headers)
        assert rs.json()["data"]["items"] == []
