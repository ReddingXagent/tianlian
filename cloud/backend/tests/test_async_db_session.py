"""异步 DB 会话回归守卫 (卡 52f731ac)

验证含真实 await 的端点经 get_async_db 拿到的 AsyncSession 满足两条核心契约:
1. 绑定到测试库 (非生产 tianlian_v3.db) —— 由 conftest override 模块级 AsyncSessionLocal 实现;
2. 同步 Session 写入的数据对异步读可见 (SQLite WAL 跨引擎事务可见性)。

任一契约被破坏 (删除 conftest 的 AsyncSessionLocal override / 把端点改回同步 db.query /
conftest 用 asyncio.run(dispose) 污染事件循环) → 本测试红。本次改造修复的两个 bug
(test_train_requires_auth 读生产库得 400、device_control 单元测试事件循环被污染) 均属此类回归。
"""


def test_async_session_reads_sync_seeded_data(client, seed_stations, seed_devices):
    """async dashboard 端点必须读到同步 fixture seed 的 4 台设备。

    seed_devices 经 client._sesh (同步 Session) 写入测试库; /predictive-maintenance/dashboard
    是含 await 的 async 端点, 经 get_async_db → AsyncSessionLocal 读取。两者必须指向同一测试库,
    否则 total_devices ≠ 4 (若读到生产库 tianlian_v3.db, 设备数不固定; 若 async session 未 override
    则根本连错库)。这是卡 52f731ac 改造的核心契约 —— async 端点的 DB IO 必须经 AsyncSession
    落到与同步 session 相同的测试库, 而非阻塞事件循环或读到生产库。
    """
    resp = client.get("/api/v1/predictive-maintenance/dashboard")
    assert resp.status_code == 200
    body = resp.json()
    # admin (client 默认登录) 是 platform_admin → dashboard 不做 team scoping, 读全部 4 台
    assert body["total_devices"] == 4
