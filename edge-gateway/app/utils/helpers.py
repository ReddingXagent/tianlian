"""
天链 V3 边缘网关 - 工具函数
"""
import socket
import platform
from typing import Optional


def get_local_ip() -> Optional[str]:
    """获取本机 IP 地址"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


def get_host_info() -> dict:
    """获取主机信息"""
    return {
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "local_ip": get_local_ip(),
    }
