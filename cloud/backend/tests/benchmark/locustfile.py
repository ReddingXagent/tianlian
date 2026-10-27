"""
Locust 性能测试脚本

运行:
    locust -f locustfile.py --host=http://localhost:8000

测试场景:
1. 登录认证
2. 获取站点列表
3. 获取设备列表
4. 获取告警列表
5. 创建工单
6. AI诊断分析
"""
from locust import HttpUser, task, between
import random
import json


class TianlianUser(HttpUser):
    """天链V3 用户行为模拟"""
    
    wait_time = between(1, 5)  # 请求间隔 1-5 秒
    
    def on_start(self):
        """登录获取 token"""
        self.token = None
        self.login()
    
    def login(self):
        """模拟登录"""
        try:
            response = self.client.post(
                "/api/v1/auth/login",
                data={"username": "admin", "password": "admin123"}
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 200:
                    self.token = data["data"]["token"]
        except Exception as e:
            print(f"Login failed: {e}")
    
    def get_headers(self):
        """获取认证头"""
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}
    
    @task(10)
    def get_stations(self):
        """获取站点列表 - 高频操作"""
        self.client.get("/api/v1/stations", headers=self.get_headers())
    
    @task(10)
    def get_devices(self):
        """获取设备列表 - 高频操作"""
        self.client.get("/api/v1/devices", headers=self.get_headers())
    
    @task(8)
    def get_alarms(self):
        """获取告警列表"""
        self.client.get("/api/v1/alarms?status=active", headers=self.get_headers())
    
    @task(8)
    def get_stats(self):
        """获取统计数据"""
        self.client.get("/api/v1/stats/overview", headers=self.get_headers())
    
    @task(5)
    def get_health(self):
        """健康检查"""
        self.client.get("/api/v1/health")
    
    @task(3)
    def create_workorder(self):
        """创建工单 - 低频写操作"""
        data = {
            "station_id": random.randint(1, 21),
            "title": f"性能测试工单 {random.randint(1, 10000)}",
            "description": "Locust 自动生成的测试工单",
            "priority": random.choice(["low", "medium", "high"]),
            "type": random.choice(["repair", "maintenance", "inspection"]),
        }
        self.client.post("/api/v1/workorders", json=data, headers=self.get_headers())
    
    @task(2)
    def ai_diagnosis(self):
        """AI 诊断分析 - 资源密集型操作"""
        data = {
            "device_id": random.randint(1, 50),
            "logs": [
                "[2026-05-19 10:00:00] [WARN] 设备温度偏高: 75°C",
                "[2026-05-19 10:05:00] [ERROR] 通信超时",
            ]
        }
        self.client.post("/api/v1/log-analysis/analyze", json=data, headers=self.get_headers())
    
    @task(1)
    def get_telemetry(self):
        """获取遥测数据 - 数据量大"""
        device_id = random.randint(1, 50)
        self.client.get(f"/api/v1/telemetry/device/{device_id}/latest", headers=self.get_headers())


class MobileUser(HttpUser):
    """移动端用户行为"""
    
    wait_time = between(3, 10)
    
    def on_start(self):
        self.token = None
        self.login()
    
    def login(self):
        try:
            response = self.client.post(
                "/api/v1/auth/login",
                data={"username": "admin", "password": "admin123"}
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 200:
                    self.token = data["data"]["token"]
        except Exception as e:
            print(f"Login failed: {e}")
    
    def get_headers(self):
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}
    
    @task(10)
    def mobile_dashboard(self):
        """移动端首页"""
        self.client.get("/api/v1/stats/overview", headers=self.get_headers())
    
    @task(5)
    def mobile_scan(self):
        """扫码报修"""
        data = {
            "device_id": random.randint(1, 50),
            "issue_type": random.choice(["fault", "maintenance", "other"]),
            "description": "移动端扫码报修测试",
        }
        self.client.post("/api/v1/scan/device", json=data, headers=self.get_headers())


# 压力测试配置
# locust -f locustfile.py --host=http://localhost:8000 -u 100 -r 10 -t 5m
# -u 100: 100 个并发用户
# -r 10: 每秒启动 10 个用户
# -t 5m: 运行 5 分钟
