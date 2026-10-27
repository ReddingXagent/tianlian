#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SSL Certificate 模型测试
"""
import pytest
from app.models.ssl_certificate import SSLCertificate

class TestSSLCertificateModel:
    def test_ssl_certificate_columns(self):
        cols = [c.name for c in SSLCertificate.__table__.columns]
        assert "id" in cols
        assert "domain" in cols  # SSLCertificate uses domain
        assert "domain" in cols
        assert "cert_path" in cols  # SSLCertificate uses cert_path
        assert "key_path" in cols  # SSLCertificate uses key_path
        assert "issuer" in cols
        assert "not_before" in cols  # SSLCertificate uses not_before
        assert "not_after" in cols  # SSLCertificate uses not_after
        assert "status" in cols
        assert "nginx_conf_path" in cols  # SSLCertificate uses nginx_conf_path

    def test_domain_indexed(self):
        assert SSLCertificate.__table__.columns["domain"].index