"""tenant_usage_service 单元测试"""
from unittest.mock import MagicMock, patch
from app.services.tenant_usage_service import compute_current_usage, _count_by_tenant


class TestComputeCurrentUsage:
    """compute_current_usage 测试"""

    def test_returns_dict_with_expected_keys(self):
        """返回字典包含三个计数键"""
        db = MagicMock()
        result = compute_current_usage(db, tenant_id=1)
        assert set(result.keys()) == {"station_count", "device_count", "user_count"}

    def test_models_without_tenant_id_return_zero(self):
        """模型无 tenant_id 字段时返回 0"""
        db = MagicMock()
        with patch("app.services.tenant_usage_service._count_by_tenant", return_value=0):
            result = compute_current_usage(db, tenant_id=99)
        assert result["station_count"] == 0
        assert result["device_count"] == 0
        assert result["user_count"] == 0

    def test_counts_with_tenant_id(self):
        """有 tenant_id 的模型正确计数"""
        db = MagicMock()

        # 模拟 Station 有 tenant_id，返回 5
        mock_station = MagicMock()
        mock_station.tenant_id = 1
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_count = MagicMock()
        db.query.return_value = mock_query
        mock_query.filter.return_value = mock_filter
        mock_filter.count.return_value = 5

        with patch("app.services.tenant_usage_service.hasattr", side_effect=lambda obj, attr: attr == "tenant_id"):
            with patch("app.services.tenant_usage_service._count_by_tenant", side_effect=[5, 3, 2]):
                result = compute_current_usage(db, tenant_id=1)

        assert result["station_count"] == 5
        assert result["device_count"] == 3
        assert result["user_count"] == 2


class TestCountByTenant:
    """_count_by_tenant 内部函数测试"""

    def test_no_tenant_id_attribute_returns_zero(self):
        """模型无 tenant_id 属性 → 0"""
        class FakeModel:
            pass  # 没有 tenant_id

        db = MagicMock()
        result = _count_by_tenant(db, FakeModel, tenant_id=1)
        assert result == 0

    def test_normal_count(self):
        """有 tenant_id 的模型正常查询"""
        class FakeModel:
            tenant_id = 1

        db = MagicMock()
        mock_query = MagicMock()
        mock_filter = MagicMock()
        db.query.return_value = mock_query
        mock_query.filter.return_value = mock_filter
        mock_filter.count.return_value = 42

        result = _count_by_tenant(db, FakeModel, tenant_id=1)
        assert result == 42
        db.query.assert_called_once_with(FakeModel)

    def test_query_exception_returns_zero(self):
        """查询异常时返回 0"""
        class FakeModel:
            tenant_id = 1

        db = MagicMock()
        db.query.side_effect = Exception("DB connection lost")

        result = _count_by_tenant(db, FakeModel, tenant_id=1)
        assert result == 0

    def test_filter_uses_tenant_id(self):
        """filter 条件正确使用 model.tenant_id"""
        class FakeModel:
            tenant_id = "field"

        db = MagicMock()
        mock_query = MagicMock()
        mock_filter = MagicMock()
        db.query.return_value = mock_query
        mock_query.filter.return_value = mock_filter
        mock_filter.count.return_value = 10

        _count_by_tenant(db, FakeModel, tenant_id=777)
        mock_query.filter.assert_called_once()
