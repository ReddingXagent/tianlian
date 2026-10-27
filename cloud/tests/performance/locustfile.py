"""
天链V3 性能压测脚本 (Locust)

用法:
    pip install locust
    locust -f tests/performance/locustfile.py --host=http://demo.example.com
    # 浏览器打开 http://localhost:8089 设置并发数
"""

import random
import uuid
from locust import HttpUser, task, between, tag


class TianLianUser(HttpUser):
    """天链V3 模拟用户"""

    wait_time = between(1, 5)  # 每个操作间隔 1-5 秒
    token: str = ""

    def on_start(self):
        """用户初始化: 登录获取token"""
        self.token = self.login()

    def login(self) -> str:
        """模拟登录"""
        response = self.client.post("/api/v1/auth/login", json={
            "username": "admin",
            "password": "admin123"
        }, name="登录")
        if response.status_code == 200:
            data = response.json()
            return data.get("access_token", "")
        return ""

    def _headers(self) -> dict:
        """请求头"""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        } if self.token else {}

    # ========== 核心API压测 ==========

    @tag("health")
    @task(1)
    def health_check(self):
        """健康检查"""
        self.client.get("/api/v1/health", name="健康检查")

    @tag("devices")
    @task(3)
    def list_devices(self):
        """设备列表 (高频率)"""
        self.client.get("/api/v1/devices", headers=self._headers(),
                        name="设备列表", params={"skip": 0, "limit": 20})

    @tag("devices")
    @task(1)
    def device_detail(self):
        """设备详情"""
        self.client.get(f"/api/v1/devices/{uuid.uuid4().hex[:12]}",
                        headers=self._headers(), name="设备详情")

    @tag("stations")
    @task(2)
    def list_stations(self):
        """站点列表"""
        self.client.get("/api/v1/stations", headers=self._headers(),
                        name="站点列表", params={"skip": 0, "limit": 10})

    @tag("alarms")
    @task(2)
    def list_alarms(self):
        """告警列表"""
        self.client.get("/api/v1/alarms", headers=self._headers(),
                        name="告警列表", params={"skip": 0, "limit": 20})

    @tag("alarms")
    @task(1)
    def alarm_stats(self):
        """告警统计"""
        self.client.get("/api/v1/alarms/stats", headers=self._headers(),
                        name="告警统计")

    @tag("workorders")
    @task(2)
    def list_workorders(self):
        """工单列表"""
        self.client.get("/api/v1/workorders", headers=self._headers(),
                        name="工单列表", params={"skip": 0, "limit": 10})

    @tag("telemetry")
    @task(1)
    def recent_telemetry(self):
        """遥测数据 (实时数据)"""
        self.client.get("/api/v1/telemetry/recent", headers=self._headers(),
                        name="遥测数据")

    @tag("dashboard")
    @task(1)
    def dashboard_stats(self):
        """仪表盘数据"""
        self.client.get("/api/v1/dashboard/stats", headers=self._headers(),
                        name="仪表盘")

    @tag("reports")
    @task(1)
    def report_list(self):
        """报表列表"""
        self.client.get("/api/v1/reports", headers=self._headers(),
                        name="报表列表", params={"skip": 0, "limit": 10})

    @tag("knowledge")
    @task(1)
    def search_knowledge(self):
        """知识库搜索"""
        self.client.get("/api/v1/knowledge/search", headers=self._headers(),
                        name="知识库搜索", params={"q": "逆变器"})

    @tag("monitor")
    @task(1)
    def monitor_services(self):
        """服务监控"""
        self.client.get("/api/v1/monitor/services", headers=self._headers(),
                        name="服务监控")


class AdminUser(TianLianUser):
    """管理员用户 - 更激进的操作"""
    wait_time = between(2, 8)

    @task(2)
    def list_all_devices(self):
        self.client.get("/api/v1/devices", headers=self._headers(),
                        name="管理员-全量设备", params={"skip": 0, "limit": 100})

    @task(1)
    def system_config(self):
        self.client.get("/api/v1/config/system", headers=self._headers(),
                        name="系统配置")

    @task(1)
    def operation_logs(self):
        self.client.get("/api/v1/logs", headers=self._headers(),
                        name="操作日志", params={"skip": 0, "limit": 50, "days": 7})

    @task(1)
    def team_members(self):
        self.client.get("/api/v1/teams", headers=self._headers(),
                        name="团队列表")

    @task(1)
    def audit_logs(self):
        self.client.get("/api/v1/audit/logs", headers=self._headers(),
                        name="审计日志", params={"skip": 0, "limit": 50})
