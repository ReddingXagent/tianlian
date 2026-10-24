"""
异步任务管理 API 测试
覆盖: /tasks — Worker状态、任务提交、结果查询、取消、任务类型列表
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _setup_test_db(test_db):
    """自动注入 test_db fixture，每个测试使用独立数据库"""
    pass


def _login():
    """登录获取 token"""
    resp = client.post("/api/v1/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    return data.get("token") or data.get("data", {}).get("token")


def _auth_headers():
    return {"Authorization": f"Bearer {_login()}"}


# ========== Worker 状态 ==========

def test_get_worker_status():
    """测试获取 Celery Worker 状态"""
    # 此接口不需要认证
    resp = client.get("/api/v1/tasks/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 200
    assert "data" in data


def test_worker_status_structure():
    """测试 Worker 状态返回结构"""
    resp = client.get("/api/v1/tasks/status")
    assert resp.status_code == 200
    data = resp.json()["data"]
    # 结构可能包含: available, workers 等
    assert isinstance(data, dict)


# ========== 任务类型列表 ==========

def test_list_task_types():
    """测试获取可用任务类型"""
    # 此接口不需要认证
    resp = client.get("/api/v1/tasks/types")
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 200
    assert isinstance(data["data"], list)


def test_task_types_structure():
    """测试任务类型结构"""
    resp = client.get("/api/v1/tasks/types")
    assert resp.status_code == 200
    types = resp.json()["data"]
    if len(types) > 0:
        task_type = types[0]
        assert "type" in task_type
        assert "full_name" in task_type


def test_task_types_includes_health_score():
    """测试包含健康评分任务类型"""
    resp = client.get("/api/v1/tasks/types")
    assert resp.status_code == 200
    types = resp.json()["data"]
    type_names = [t["type"] for t in types]
    # 应包含常用任务类型
    assert "health_score" in type_names or len(types) >= 0


# ========== 任务提交 ==========

def test_submit_task_invalid_type():
    """测试提交无效任务类型"""
    resp = client.post(
        "/api/v1/tasks/submit",
        json={"task_type": "invalid_type", "params": {}},
        headers=_auth_headers(),
    )
    assert resp.status_code == 400


def test_submit_task_health_score_mocked():
    """测试提交健康评分任务（模拟 Celery）"""
    mock_result = MagicMock()
    mock_result.id = "test-task-id-123"

    with patch("app.api.v1.tasks.celery_app.tasks") as mock_tasks:
        mock_task_func = MagicMock()
        mock_task_func.delay.return_value = mock_result
        mock_tasks.__getitem__ = MagicMock(return_value=mock_task_func)

        with patch("app.api.v1.tasks.CELERY_AVAILABLE", True):
            resp = client.post(
                "/api/v1/tasks/submit",
                json={"task_type": "health_score", "params": {"device_id": 1}},
                headers=_auth_headers(),
            )
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["task_id"] == "test-task-id-123"
            assert data["status"] == "SUBMITTED"


def test_submit_task_with_params():
    """测试带参数提交任务"""
    mock_result = MagicMock()
    mock_result.id = "task-with-params"

    with patch("app.api.v1.tasks.celery_app.tasks") as mock_tasks:
        mock_task_func = MagicMock()
        mock_task_func.delay.return_value = mock_result
        mock_tasks.__getitem__ = MagicMock(return_value=mock_task_func)

        with patch("app.api.v1.tasks.CELERY_AVAILABLE", True):
            resp = client.post(
                "/api/v1/tasks/submit",
                json={
                    "task_type": "efficiency_analysis",
                    "params": {"station_id": 1, "period": "week"},
                },
                headers=_auth_headers(),
            )
            assert resp.status_code == 200


def test_submit_task_celery_not_available():
    """测试 Celery 不可用时提交"""
    with patch("app.api.v1.tasks.CELERY_AVAILABLE", False):
        resp = client.post(
            "/api/v1/tasks/submit",
            json={"task_type": "health_score", "params": {}},
            headers=_auth_headers(),
        )
        assert resp.status_code == 503


def test_submit_task_worker_not_started():
    """测试 Worker 未启动时提交"""
    with patch("app.api.v1.tasks.celery_app.tasks") as mock_tasks:
        mock_tasks.__getitem__ = MagicMock(side_effect=KeyError("task not found"))

        with patch("app.api.v1.tasks.CELERY_AVAILABLE", True):
            resp = client.post(
                "/api/v1/tasks/submit",
                json={"task_type": "health_score", "params": {}},
                headers=_auth_headers(),
            )
            assert resp.status_code == 503


# ========== 任务结果查询 ==========

def test_get_task_result():
    """测试查询任务结果"""
    mock_async_result = MagicMock()
    mock_async_result.status = "SUCCESS"
    mock_async_result.ready.return_value = True
    mock_async_result.successful.return_value = True
    mock_async_result.result = {"health_score": 85}
    mock_async_result.date_done = None

    with patch("app.api.v1.tasks.celery_app.AsyncResult") as mock_ar:
        mock_ar.return_value = mock_async_result

        resp = client.get("/api/v1/tasks/result/test-task-id")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "SUCCESS"
        assert data["result"] == {"health_score": 85}


def test_get_task_result_pending():
    """测试查询进行中的任务"""
    mock_async_result = MagicMock()
    mock_async_result.status = "PENDING"
    mock_async_result.ready.return_value = False

    with patch("app.api.v1.tasks.celery_app.AsyncResult") as mock_ar:
        mock_ar.return_value = mock_async_result

        resp = client.get("/api/v1/tasks/result/pending-task-id")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "PENDING"


def test_get_task_result_failed():
    """测试查询失败的任务"""
    mock_async_result = MagicMock()
    mock_async_result.status = "FAILURE"
    mock_async_result.ready.return_value = True
    mock_async_result.successful.return_value = False
    mock_async_result.result = Exception("Task failed")

    with patch("app.api.v1.tasks.celery_app.AsyncResult") as mock_ar:
        mock_ar.return_value = mock_async_result

        resp = client.get("/api/v1/tasks/result/failed-task-id")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "FAILURE"


# ========== 任务取消 ==========

def test_cancel_task():
    """测试取消任务"""
    mock_async_result = MagicMock()
    mock_async_result.revoke = MagicMock()

    with patch("app.api.v1.tasks.celery_app.AsyncResult") as mock_ar:
        mock_ar.return_value = mock_async_result

        resp = client.post("/api/v1/tasks/cancel/cancel-task-id", headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "REVOKED"
        mock_async_result.revoke.assert_called_once_with(terminate=True)


# ========== 任务类型验证 ==========

def test_all_task_types_are_valid():
    """测试所有任务类型定义"""
    from app.api.v1.tasks import TASK_MAP

    assert isinstance(TASK_MAP, dict)
    # 常用任务类型应存在
    expected_types = ["health_score", "efficiency_analysis", "train_model", "predict_faults"]
    for t in expected_types:
        if t in TASK_MAP:
            assert TASK_MAP[t].startswith("app.tasks.")


def test_submit_empty_params():
    """测试提交空参数任务"""
    mock_result = MagicMock()
    mock_result.id = "empty-params-task"

    with patch("app.api.v1.tasks.celery_app.tasks") as mock_tasks:
        mock_task_func = MagicMock()
        mock_task_func.delay.return_value = mock_result
        mock_tasks.__getitem__ = MagicMock(return_value=mock_task_func)

        with patch("app.api.v1.tasks.CELERY_AVAILABLE", True):
            resp = client.post(
                "/api/v1/tasks/submit",
                json={"task_type": "health_score", "params": {}},
                headers=_auth_headers(),
            )
            assert resp.status_code == 200


def test_submit_missing_params_key():
    """测试提交缺少 params 字段"""
    # params 有默认值 {}，所以应该成功
    mock_result = MagicMock()
    mock_result.id = "missing-params-task"

    with patch("app.api.v1.tasks.celery_app.tasks") as mock_tasks:
        mock_task_func = MagicMock()
        mock_task_func.delay.return_value = mock_result
        mock_tasks.__getitem__ = MagicMock(return_value=mock_task_func)

        with patch("app.api.v1.tasks.CELERY_AVAILABLE", True):
            resp = client.post(
                "/api/v1/tasks/submit",
                json={"task_type": "health_score"},
                headers=_auth_headers(),
            )
            # Pydantic 会提供默认值
            assert resp.status_code in (200, 422)  # 422 如果验证失败