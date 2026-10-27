import time
from locust import HttpUser, task, between

class TianlianUser(HttpUser):
    wait_time = between(0.5, 2)
    
    def on_start(self):
        """用户启动时登录获取token"""
        login_response = self.client.post("/api/v1/auth/login", 
            data={"username": "admin", "password": "admin123"},
            name="POST /api/v1/auth/login")
        if login_response.status_code == 200:
            body = login_response.json()
            self.token = body.get("data", {}).get("token")
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            self.token = None
            self.headers = {}
    
    @task(5)
    def health_check(self):
        """健康检查（无需认证，最高频）"""
        self.client.get("/api/v1/health")
    
    @task(3)
    def health_devices(self):
        """设备健康状态（需认证）"""
        if self.token:
            self.client.get("/api/v1/health/devices", headers=self.headers)
    
    @task(2)
    def auth_logout(self):
        """模拟登出（需认证）"""
        if self.token:
            self.client.post("/api/v1/auth/logout", headers=self.headers)
    
    @task(1)
    def auth_refresh(self):
        """刷新token（需认证）"""
        if self.token:
            self.client.post("/api/v1/auth/refresh", headers=self.headers)
    
    @task(3)
    def get_alarm_rules(self):
        """告警规则列表"""
        if self.token:
            self.client.get("/api/v1/alarms/rules", headers=self.headers, 
                          name="GET /api/v1/alarms/rules")
    
    @task(1)
    def get_alarm_notices(self):
        """告警通知列表"""
        if self.token:
            self.client.get("/api/v1/alarm-notices", headers=self.headers)