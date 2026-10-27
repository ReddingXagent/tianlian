"""
天链V3 后端 Phase47d 性能压测脚本
目标: 100 并发 P99<500ms

运行:
    locust -f locustfile.py --host=http://localhost:8090 -u 100 -r 10 -t 90s --csv=locust_results --headless

场景:
1. 登录认证 (一次性 per user)
2. Dashboard 统计概览 (高频 GET)
3. 站点列表 (高频 GET)
4. 设备列表 (高频 GET)
5. 告警列表 (中频 GET)
6. 工单列表 (中频 GET)
7. 遥测数据 (中频 GET)
8. 创建工单 (低频 POST)
9. 健康检查 (低频 GET)
"""
from locust import HttpUser, task, between, events
import random
import time

# 全局统计
_shared_token = None
_statistics = {
    "login_success": 0,
    "login_fail": 0,
    "errors": {},
}


class TianlianUser(HttpUser):
    """天链V3 后端用户行为模拟"""
    
    wait_time = between(1, 3)  # 模拟真实用户请求间隔
    
    def on_start(self):
        """每个虚拟用户启动时登录获取 token"""
        self.token = None
        self.user_id = None
        self._login()
    
    def _login(self):
        """登录并获取 JWT token"""
        try:
            response = self.client.post(
                "/api/v1/auth/login",
                data={"username": "admin", "password": "admin123"}
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 200:
                    self.token = data["data"]["token"]
                    self.user_id = data["data"]["user"]["id"]
                    _statistics["login_success"] += 1
                else:
                    _statistics["login_fail"] += 1
            else:
                _statistics["login_fail"] += 1
        except Exception as e:
            _statistics["login_fail"] += 1
            # 静默处理，不打断测试
    
    def _headers(self):
        """获取带认证的请求头"""
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}
    
    # ─── 高频端点 (weight=10) ───
    
    @task(10)
    def get_stats_overview(self):
        """Dashboard 统计概览 - 最高频"""
        self.client.get("/api/v1/stats/overview", headers=self._headers(), name="/api/v1/stats/overview")
    
    @task(10)
    def get_stations(self):
        """站点列表 - 高频"""
        self.client.get("/api/v1/stations", headers=self._headers(), name="/api/v1/stations")
    
    @task(10)
    def get_devices(self):
        """设备列表 - 高频"""
        self.client.get("/api/v1/devices", headers=self._headers(), name="/api/v1/devices")
    
    # ─── 中频端点 (weight=6) ───
    
    @task(6)
    def get_alarms(self):
        """告警列表"""
        self.client.get("/api/v1/alarms?status=active", headers=self._headers(), name="/api/v1/alarms")
    
    @task(6)
    def get_workorders(self):
        """工单列表"""
        self.client.get("/api/v1/workorders", headers=self._headers(), name="/api/v1/workorders")
    
    @task(6)
    def get_telemetry_latest(self):
        """遥测最新数据"""
        device_id = random.randint(1, 50)
        self.client.get(
            f"/api/v1/telemetry/device/{device_id}/latest",
            headers=self._headers(),
            name="/api/v1/telemetry/device/{id}/latest"
        )
    
    # ─── 低频端点 (weight=3) ───
    
    @task(3)
    def get_users(self):
        """用户列表"""
        self.client.get("/api/v1/users", headers=self._headers(), name="/api/v1/users")
    
    @task(3)
    def get_dashboard_stats(self):
        """Dashboard 详细统计"""
        self.client.get("/api/v1/stats/dashboard", headers=self._headers(), name="/api/v1/stats/dashboard")
    
    @task(3)
    def get_teams(self):
        """团队列表"""
        self.client.get("/api/v1/teams", headers=self._headers(), name="/api/v1/teams")
    
    # ─── 写操作 (weight=2) ───
    
    @task(2)
    def create_workorder(self):
        """创建工单 - 写操作"""
        data = {
            "station_id": random.randint(1, 21),
            "title": f"压测工单 {random.randint(1, 999999)}",
            "description": "Locust 性能压测自动生成",
            "priority": random.choice(["low", "medium", "high"]),
            "type": random.choice(["repair", "maintenance", "inspection"]),
        }
        self.client.post(
            "/api/v1/workorders",
            json=data,
            headers=self._headers(),
            name="/api/v1/workorders [POST]"
        )
    
    @task(2)
    def get_health(self):
        """健康检查 - 无认证"""
        self.client.get("/api/v1/health", name="/api/v1/health")
    
    # ─── 极低频 (weight=1) ───
    
    @task(1)
    def get_device_health(self):
        """设备健康度"""
        self.client.get("/api/v1/health/device-health", headers=self._headers(), name="/api/v1/health/device-health")


class ReadOnlyUser(HttpUser):
    """只读用户场景 - 模拟 viewer 角色"""
    
    wait_time = between(2, 5)
    
    def on_start(self):
        self.token = None
        try:
            response = self.client.post(
                "/api/v1/auth/login",
                data={"username": "admin", "password": "admin123"}
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 200:
                    self.token = data["data"]["token"]
        except Exception:
            pass
    
    def _headers(self):
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}
    
    @task(5)
    def view_dashboard(self):
        self.client.get("/api/v1/stats/overview", headers=self._headers(), name="/api/v1/stats/overview")
    
    @task(5)
    def view_alarms(self):
        self.client.get("/api/v1/alarms", headers=self._headers(), name="/api/v1/alarms")
    
    @task(3)
    def view_stations(self):
        self.client.get("/api/v1/stations", headers=self._headers(), name="/api/v1/stations")
    
    @task(2)
    def view_devices(self):
        self.client.get("/api/v1/devices", headers=self._headers(), name="/api/v1/devices")


# ─── 事件钩子: 记录自定义统计 ───

@events.init.add_listener
def on_locust_init(environment, **kwargs):
    """测试开始时初始化"""
    print("=" * 60)
    print("天链V3 后端 Phase47d 性能压测")
    print(f"目标主机: {environment.host}")
    print(f"并发用户: {environment.runner.target_user_count if environment.runner else 'N/A'}")
    print("=" * 60)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """测试结束统计"""
    print("=" * 60)
    print(f"登录成功: {_statistics['login_success']}")
    print(f"登录失败: {_statistics['login_fail']}")
    print("=" * 60)
