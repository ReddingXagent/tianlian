#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API Gateway 模型测试
"""
import pytest
from app.models.api_gateway import (
    ApiClient, ApiEndpoint, ApiRequestLog,
    OAuthAuthorizationCode, RateLimitRule, ApiUsageQuota, ThirdPartyIntegration
)

class TestApiGatewayModel:
    def test_api_client_columns(self):
        cols = [c.name for c in ApiClient.__table__.columns]
        assert "id" in cols
        assert "client_id" in cols
        assert "client_secret_hash" in cols
        assert "name" in cols
        assert "status" in cols
        assert "rate_limit" in cols

    def test_api_endpoint_columns(self):
        cols = [c.name for c in ApiEndpoint.__table__.columns]
        assert "id" in cols
        assert "path" in cols
        assert "method" in cols

    def test_api_request_log_columns(self):
        cols = [c.name for c in ApiRequestLog.__table__.columns]
        assert "id" in cols
        assert "client_id" in cols
        assert "endpoint" in cols  # ApiRequestLog uses endpoint
        assert "response_status" in cols

    def test_oauth_columns(self):
        cols = [c.name for c in OAuthAuthorizationCode.__table__.columns]
        assert "id" in cols
        assert "code" in cols
        assert "client_id" in cols

    def test_rate_limit_rule_columns(self):
        cols = [c.name for c in RateLimitRule.__table__.columns]
        assert "id" in cols
        assert "endpoint_pattern" in cols  # RateLimitRule uses endpoint_pattern
        assert "limit_per_minute" in cols  # RateLimitRule uses limit_per_minute

    def test_usage_quota_columns(self):
        cols = [c.name for c in ApiUsageQuota.__table__.columns]
        assert "id" in cols
        assert "client_id" in cols
        assert "monthly_limit" in cols  # ApiUsageQuota uses monthly_limit

    def test_third_party_columns(self):
        cols = [c.name for c in ThirdPartyIntegration.__table__.columns]
        assert "id" in cols
        assert "name" in cols
        assert "webhook_secret" in cols  # ThirdPartyIntegration uses webhook_secret