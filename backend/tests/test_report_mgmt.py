#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
报告管理 Report Mgmt API 测试
报告 CRUD、统计
"""
import inspect

import pytest


def _login(client):
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    return resp.json().get("token") or resp.json().get("data", {}).get("token")


def test_report_list(client, seed_users):
    """获取报告列表"""
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/api/v1/report-mgmt", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data


def test_create_report(client, seed_users):
    """创建报告"""
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post("/api/v1/report-mgmt", json={
        "title": "测试报告",
        "type": "月报",
        "station_id": 1,
        "author": "admin",
        "status": "draft",
        "content": "{\"summary\": \"测试报告内容\"}",
        "period_start": "2026-06-01",
        "period_end": "2026-06-30",
    }, headers=headers)
    assert resp.status_code == 200


def test_get_report_detail(client, seed_users):
    """获取报告详情（存在）"""
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    # 先创建一个报告
    create_resp = client.post("/api/v1/report-mgmt", json={
        "title": "详情测试报告",
        "type": "周报",
        "station_id": 1,
        "author": "admin",
        "status": "draft",
        "content": "{\"detail\": \"test\"}",
        "period_start": "2026-01-01",
        "period_end": "2026-01-07",
    }, headers=headers)
    assert create_resp.status_code == 200, f"Create failed: {create_resp.text}"
    report_id = create_resp.json()["data"]["id"]

    resp = client.get(f"/api/v1/report-mgmt/{report_id}", headers=headers)
    assert resp.status_code == 200


def test_get_report_not_found(client, seed_users):
    """获取不存在的报告"""
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/api/v1/report-mgmt/99999", headers=headers)
    assert resp.status_code == 404


def test_report_stats_summary(client, seed_users):
    """报告统计信息"""
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/api/v1/report-mgmt/stats/summary", headers=headers)
    assert resp.status_code == 200


def test_delete_report(client, seed_users):
    """删除报告"""
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    # 先创建一个报告
    create_resp = client.post("/api/v1/report-mgmt", json={
        "title": "待删除报告",
        "type": "日报",
        "station_id": 1,
        "author": "admin",
        "status": "draft",
        "content": "{}",
        "period_start": "2026-01-01",
        "period_end": "2026-01-01",
    }, headers=headers)
    assert create_resp.status_code == 200, f"Create failed: {create_resp.text}"
    report_id = create_resp.json()["data"]["id"]

    resp = client.delete(f"/api/v1/report-mgmt/{report_id}", headers=headers)
    assert resp.status_code == 200


def test_delete_report_not_found(client, seed_users):
    """删除不存在的报告"""
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.delete("/api/v1/report-mgmt/99999", headers=headers)
    assert resp.status_code == 404


def _create_report(client, headers):
    create_resp = client.post("/api/v1/report-mgmt", json={
        "title": "更新测试报告",
        "type": "月报",
        "station_id": 1,
        "author": "admin",
        "status": "draft",
        "content": "{\"old\": true}",
        "period_start": "2026-01-01",
        "period_end": "2026-01-31",
    }, headers=headers)
    assert create_resp.status_code == 200, f"Create failed: {create_resp.text}"
    return create_resp.json()["data"]["id"]


def test_update_report(client, seed_users):
    """更新报告字段成功，updated_at 被刷新（卡 c8811e05：NOW() SQLite 不兼容修复）"""
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    report_id = _create_report(client, headers)

    before = client.get(f"/api/v1/report-mgmt/{report_id}", headers=headers).json()["data"]
    resp = client.put(f"/api/v1/report-mgmt/{report_id}", json={
        "title": "更新后标题",
        "status": "published",
        "content": "{\"new\": true}",
    }, headers=headers)
    assert resp.status_code == 200, f"Update failed: {resp.text}"
    assert resp.json()["data"]["id"] == report_id

    after = client.get(f"/api/v1/report-mgmt/{report_id}", headers=headers).json()["data"]
    assert after["title"] == "更新后标题"
    assert after["status"] == "published"
    assert after["content"] == "{\"new\": true}"
    assert after["updated_at"] != before["updated_at"], (
        f"updated_at 未刷新: before={before['updated_at']} after={after['updated_at']}"
    )


def test_update_report_cross_team_404(client, seed_users):
    """非 admin 用户更新他 team 站点报告 → 404"""
    from app.models.user import Team, User
    from app.models.station import Station

    s = client._sesh
    team_other = Team(name="T-REPORT-OTHER")
    s.add(team_other)
    s.commit()
    s.add(Station(name="他队站", code="STA-REPORT-OTHER", team_id=team_other.id))
    # engineer1 挂到另一个 team（无站点）→ 对方站点的报告对其不可见
    engineer = s.query(User).filter(User.username == "engineer1").first()
    my_team = Team(name="T-REPORT-MINE")
    s.add(my_team)
    s.commit()
    engineer.team_id = my_team.id
    s.commit()

    token = _login_engineer(client)
    headers = {"Authorization": f"Bearer {token}"}
    other_station_id = s.query(Station).filter(Station.code == "STA-REPORT-OTHER").first().id
    create_resp = client.post("/api/v1/report-mgmt", json={
        "title": "他队报告", "type": "周报", "station_id": other_station_id,
        "author": "admin", "status": "draft", "content": "{}",
    }, headers={"Authorization": f"Bearer {_login(client)}"})
    assert create_resp.status_code == 200
    report_id = create_resp.json()["data"]["id"]

    resp = client.put(f"/api/v1/report-mgmt/{report_id}", json={"title": "越权改"}, headers=headers)
    assert resp.status_code == 404


def _login_engineer(client):
    resp = client.post("/api/v1/auth/login", data={"username": "engineer1", "password": "eng123"})
    assert resp.status_code == 200
    return resp.json().get("token") or resp.json().get("data", {}).get("token")


def test_update_report_no_fields_400(client, seed_users):
    """空 payload 更新 → 400"""
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    report_id = _create_report(client, headers)

    resp = client.put(f"/api/v1/report-mgmt/{report_id}", json={}, headers=headers)
    assert resp.status_code == 400


def _create_keyword_report(client, headers, title, station_id=1):
    create_resp = client.post("/api/v1/report-mgmt", json={
        "title": title,
        "type": "月报",
        "station_id": station_id,
        "author": "admin",
        "status": "draft",
        "content": "{}",
    }, headers=headers)
    assert create_resp.status_code == 200, f"Create failed: {create_resp.text}"
    return create_resp.json()["data"]["id"]


def test_list_reports_keyword_match(client, seed_users):
    """keyword 命中：标题包含关键词返回（卡 89363330：ILIKE SQLite 崩溃修复回归）"""
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    _create_keyword_report(client, headers, "站点A充电月报")

    resp = client.get("/api/v1/report-mgmt", params={"keyword": "充电月报"}, headers=headers)
    assert resp.status_code == 200, f"keyword 查询崩溃: {resp.text}"
    items = resp.json()["data"]["items"]
    assert any("充电月报" in it["title"] for it in items)


def test_list_reports_keyword_no_match(client, seed_users):
    """keyword 未命中：空列表"""
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    _create_keyword_report(client, headers, "站点A充电月报")

    resp = client.get("/api/v1/report-mgmt", params={"keyword": "不存在的关键词"}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["items"] == []
    assert data["total"] == 0


def test_list_reports_keyword_case_insensitive(client, seed_users):
    """大小写不敏感：大写 keyword 命中小写标题（lower+LIKE 语义锚点）"""
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    _create_keyword_report(client, headers, "monthly ev charging report")

    resp = client.get("/api/v1/report-mgmt", params={"keyword": "EV CHARGING"}, headers=headers)
    assert resp.status_code == 200, f"keyword 查询崩溃: {resp.text}"
    items = resp.json()["data"]["items"]
    assert any("monthly ev charging report" == it["title"] for it in items)


def test_list_reports_keyword_wildcard_literal(client, seed_users):
    """keyword 中 %/_ 按字面匹配（卡 128f4296：LIKE 未转义 → % 枚举全表）"""
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    _create_keyword_report(client, headers, "效率100%分析报告")
    _create_keyword_report(client, headers, "站点A充电月报")

    # "%" 单独作为 keyword 不再枚举全表，仅命中含字面 % 的标题
    resp = client.get("/api/v1/report-mgmt", params={"keyword": "%"}, headers=headers)
    assert resp.status_code == 200
    assert [it["title"] for it in resp.json()["data"]["items"]] == ["效率100%分析报告"]

    # "_" 单独作为 keyword 不再充当单字符通配（两条标题均不含字面 _ → 空结果）
    resp = client.get("/api/v1/report-mgmt", params={"keyword": "_"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 0

    # 含 % 的字面 keyword 精确命中
    resp = client.get("/api/v1/report-mgmt", params={"keyword": "100%"}, headers=headers)
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert [it["title"] for it in items] == ["效率100%分析报告"]


def test_report_mgmt_no_positional_indexing():
    """list_reports/get_report 禁止 r[N]/row[N] 位置索引（卡 128f4296：SELECT * 列序漂移静默串数据）"""
    import re
    import app.api.v1.report_mgmt as rm

    src = inspect.getsource(rm.list_reports) + inspect.getsource(rm.get_report)
    assert "SELECT *" not in src, "禁止 SELECT *，须显式列清单"
    assert not re.search(r"\b(r|row)\[\d+\]", src), "禁止位置索引序列化，须命名访问"


def test_list_reports_keyword_team_scoping(client, seed_users):
    """keyword + team scoping 叠加：非 admin 用户 keyword 搜索只见本 team"""
    from app.models.user import Team, User
    from app.models.station import Station

    s = client._sesh
    my_team = Team(name="T-KW-MINE")
    s.add(my_team)
    s.commit()
    my_station = Station(name="本队站", code="STA-KW-MINE", team_id=my_team.id)
    other_team = Team(name="T-KW-OTHER")
    s.add(other_team)
    s.commit()
    other_station = Station(name="他队站", code="STA-KW-OTHER", team_id=other_team.id)
    s.add_all([my_station, other_station])
    s.commit()

    admin_headers = {"Authorization": f"Bearer {_login(client)}"}
    # 本 team 站点报告（标题含关键词）+ 他 team 站点报告（标题同样含关键词）
    _create_keyword_report(client, admin_headers, "team可见充电月报", station_id=my_station.id)
    _create_keyword_report(client, admin_headers, "team外充电月报", station_id=other_station.id)

    engineer = s.query(User).filter(User.username == "engineer1").first()
    engineer.team_id = my_team.id
    s.commit()

    headers = {"Authorization": f"Bearer {_login_engineer(client)}"}
    resp = client.get("/api/v1/report-mgmt", params={"keyword": "充电月报"}, headers=headers)
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["title"] == "team可见充电月报"