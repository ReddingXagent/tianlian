#!/bin/bash
cd /Users/xxx/.openclaw/workspace/projects/tianlian-cloud
assistant-model -p "为以下12个路由创建pytest测试文件：
1. backend/app/api/v1/protocol_instances.py → backend/tests/test_protocol_instances.py
2. backend/app/api/v1/cross_pod.py → backend/tests/test_cross_pod.py
3. backend/app/api/v1/pod_routes.py → backend/tests/test_pod_routes.py
4. backend/app/api/v1/chat.py → backend/tests/test_chat.py
5. backend/app/api/v1/dashboard.py → backend/tests/test_dashboard.py
6. backend/app/api/v1/enterprises.py → backend/tests/test_enterprises.py
7. backend/app/api/v1/parking.py → backend/tests/test_parking.py
8. backend/app/api/v1/v2g.py → backend/tests/test_v2g.py
9. backend/app/api/v1/permissions.py → backend/tests/test_permissions.py
10. backend/app/api/v1/ai_model_config_api.py → backend/tests/test_ai_model_config.py
11. backend/app/api/v1/notifications.py → backend/tests/test_notifications.py
12. backend/app/api/v1/cache.py → backend/tests/test_cache.py

注意：dashboard 可能已有 test_dashboard_large_screen.py，先检查。chat 可能已有测试。避免重复。

要求：
- 参考已有测试风格
- 每个路由至少3个测试用例（小路由如cache/notifications至少2个）
- 先读路由源码理解端点，再写测试
- 可分多次commit
- 写完后运行: cd backend && python -m pytest tests/test_protocol_instances.py tests/test_cross_pod.py tests/test_pod_routes.py tests/test_chat.py tests/test_dashboard.py tests/test_enterprises.py tests/test_parking.py tests/test_v2g.py tests/test_permissions.py tests/test_ai_model_config.py tests/test_notifications.py tests/test_cache.py -v
- 全部通过后 git add + git commit -m 'test: 剩余12路由测试补齐'
- 输出pytest结果和git commit hash作为验收证据" --model model-b-5.2 --max-turns 50
