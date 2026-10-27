#!/usr/bin/env python3
"""天链V3 - Mock数据补齐脚本 (schema修正版)"""

import sqlite3, random, datetime, json, hashlib

DB = 'backend/tianlian_v3.db'

def now(): return datetime.datetime.now()
def rt(d=30): return (now() - datetime.timedelta(days=random.randint(0,d), hours=random.randint(0,23), minutes=random.randint(0,59))).strftime('%Y-%m-%d %H:%M:%S')
def rd(d=365): return (now() - datetime.timedelta(days=random.randint(0,d))).strftime('%Y-%m-%d')
def hp(p): return hashlib.sha256(p.encode()).hexdigest()

CITIES = [
    ('北京',39.9042,116.4074),('上海',31.2304,121.4737),('广州',23.1291,113.2644),
    ('深圳',22.5431,114.0579),('杭州',30.2741,120.1551),('成都',30.5728,104.0668),
    ('武汉',30.5928,114.3055),('南京',32.0603,118.7969),('西安',34.3416,108.9398),
    ('长沙',28.2282,112.9388),('郑州',34.7466,113.6253),('重庆',29.4316,106.9123),
    ('苏州',31.2990,120.5853),('昆明',25.0389,102.7183),('合肥',31.8206,117.2272),
    ('济南',36.6681,116.9972)
]

DTYPES = ['inverter','charger','meter','gateway','battery','transformer']
DSTATUS = ['online','offline','fault','maintenance']

def seed(conn):
    cur = conn.cursor()
    
    # === stations (16) ===
    c = cur.execute("SELECT COUNT(*) FROM stations").fetchone()[0]
    if c < 16:
        for i,(city,lat,lon) in enumerate(CITIES):
            cur.execute("INSERT OR IGNORE INTO stations (name,code,province,city,district,address,lat,lon,status,health_score,total_power,total_devices,gun_count) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (f'{city}光伏电站',f'ST{2026001+i}',city+'省',city,'高新区',f'{city}市高新区新能源产业园{random.randint(1,99)}号',lat,lon,'active',round(0.85+random.random()*0.15,2),1000+random.randint(0,5000),random.randint(3,10),0))
        conn.commit()
        print(f"  stations: +{16-c}")
    else: print(f"  stations: {c} OK")
    
    # === teams (6) - no status column ===
    c = cur.execute("SELECT COUNT(*) FROM teams").fetchone()[0]
    if c < 6:
        for name,desc in [('运维一队','华东区站点运维'),('运维二队','华南区站点运维'),('运维三队','华北区站点运维'),('技术支持组','技术专家团队'),('安全监督组','安全巡检专项'),('应急响应组','24小时应急抢修')]:
            cur.execute("INSERT INTO teams (name,leader_id,description) VALUES (?,?,?)",(name,None,desc))
        conn.commit()
        print(f"  teams: +{6-c}")
    else: print(f"  teams: {c} OK")
    
    # === users (8) ===
    c = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if c < 8:
        users = [
            ('admin',hp('admin123'),'管理员','13800000001','admin','L1',1,'active'),
            ('zhangwei',hp('123456'),'张伟','13800000002','operator','L1',1,'active'),
            ('liqiang',hp('123456'),'李强','13800000003','operator','L1',2,'active'),
            ('wangfang',hp('123456'),'王芳','13800000004','operator','L1',3,'active'),
            ('zhaoming',hp('123456'),'赵明','13800000005','technician','L2',4,'active'),
            ('liuna',hp('123456'),'刘娜','13800000006','technician','L2',5,'active'),
            ('chenlei',hp('123456'),'陈磊','13800000007','technician','L2',6,'active'),
            ('yangjing',hp('123456'),'杨静','13800000008','viewer','L1',None,'active'),
            # 公开演示账号: 只读 viewer, 登录凭据在 README 公示; demo/locked 由后端保护, 禁止改密/改资料/删除
            ('demo',hp('demo12345'),'演示账号','13800000010','viewer','L1',None,'active'),
        ]
        for u in users:
            cur.execute("INSERT OR IGNORE INTO users (username,password_hash,real_name,phone,role,level,team_id,status) VALUES (?,?,?,?,?,?,?,?)",u)
        conn.commit()
        print(f"  users: +{len(users)}")
    else: print(f"  users: {c} OK")
    
    # === devices (50) ===
    c = cur.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
    if c < 50:
        sids = [r[0] for r in cur.execute("SELECT id FROM stations").fetchall()]
        models = {'inverter':['TL-INV-3000','TL-INV-5000','TL-INV-10K'],'charger':['TL-CHG-60KW','TL-CHG-120KW','TL-CHG-240KW'],'meter':['TL-MET-01A','TL-MET-03A'],'gateway':['TL-GW-100','TL-GW-200'],'battery':['TL-BAT-100AH','TL-BAT-200AH'],'transformer':['TL-TR-50KVA','TL-TR-100KVA']}
        need = 50-c
        for i in range(need):
            dt = random.choice(DTYPES)
            model = random.choice(models[dt])
            cur.execute("INSERT INTO devices (sn,name,code,type,model,manufacturer,rated_power,rated_voltage,rated_current,station_id,location,status,health_score,install_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (f'{dt[:3].upper()}{random.randint(100000,999999)}',f'{model}-{i+1:03d}',f'{dt.upper()}{202600001+i}',dt,model,'天链科技',random.choice([10,20,30,50,100]),random.choice([220,380,690,800]),random.choice([10,20,50,100]),random.choice(sids),f'{random.choice(["A区","B区","C区","D区"])}{random.randint(1,20)}号位',random.choices(DSTATUS,weights=[7,1,1,1])[0],round(0.85+random.random()*0.15,2),rd(365)))
        conn.commit()
        print(f"  devices: +{need}")
    else: print(f"  devices: {c} OK")
    
    # Get IDs for FK
    devs = [r[0] for r in cur.execute("SELECT id FROM devices").fetchall()]
    sts = [r[0] for r in cur.execute("SELECT id FROM stations").fetchall()]
    uids = [r[0] for r in cur.execute("SELECT id FROM users").fetchall()]
    unames = [(r[0],r[1] or r[0]) for r in cur.execute("SELECT username,real_name FROM users").fetchall()]
    
    # === alarms (25) ===
    c = cur.execute("SELECT COUNT(*) FROM alarms").fetchone()[0]
    if c < 25:
        msgs = {'critical':['逆变器过压保护','电池过温保护','电网频率异常','绝缘故障','直流母线过压','IGBT模块故障'],'warning':['逆变器温度偏高','电池SOC偏低','电网电压波动','MPPT异常','通讯延迟','功率因数偏低'],'info':['例行维护提醒','系统升级通知','数据采集正常','通信恢复','电量结算完成','远程校准完成']}
        need = 25-c
        for _ in range(need):
            lv = random.choices(['critical','warning','info'],weights=[2,4,4])[0]
            st = random.choices(['active','acknowledged','resolved'],weights=[3,3,4])[0]
            msg = random.choice(msgs[lv])
            cur.execute("INSERT INTO alarms (device_id,station_id,alarm_type,level,content,status,handler_id,handle_desc,created_at,handled_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (random.choice(devs),random.choice(sts),msg,lv,msg,st,random.choice(uids) if st!='active' else None,f'已处理：{random.choice(["复位重启","参数调整","部件更换"])}' if st!='active' else None,rt(7),rt(3) if st!='active' else None))
        conn.commit()
        print(f"  alarms: +{need}")
    else: print(f"  alarms: {c} OK")
    
    # === work_orders (15) - old table ===
    c = cur.execute("SELECT COUNT(*) FROM work_orders").fetchone()[0]
    if c < 15:
        titles = ['逆变器故障排查','电池组均衡维护','充电桩通讯修复','系统软件升级','例行巡检','设备更换','线缆检查','接地检测','防雷检查','数据采集异常','MPPT优化','功率模块更换','冷却系统维护','通讯模块重置','安全防护升级']
        need = 15-c
        for i in range(need):
            st = random.choice(['pending','assigned','in_progress','resolved','closed'])
            cur.execute("INSERT INTO work_orders (id,type,level,device_id,station_id,assignee_id,creator_id,status,fault_desc,solution,create_time,accept_time,finish_time) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (f'WO{rt(0)[:10].replace("-","")}{i:04d}',random.choice(['repair','maintenance','inspection','upgrade']),random.choice(['P0','P1','P2']),random.choice(devs),random.choice(sts),random.choice(uids),random.choice(uids),st,titles[i] if i<len(titles) else f'工单{i+1}',f'已完成处理' if st in ['resolved','closed'] else None,rt(14),rt(10) if st!='pending' else None,rt(5) if st=='closed' else None))
        conn.commit()
        print(f"  work_orders: +{need}")
    else: print(f"  work_orders: {c} OK")
    
    # === workorders (15) - new table ===
    c = cur.execute("SELECT COUNT(*) FROM work_orders").fetchone()[0]
    if c < 15:
        titles = ['逆变器故障排查','电池组均衡维护','充电桩通讯修复','系统软件升级','例行巡检','设备更换','线缆检查','接地检测','防雷检查','数据采集异常','MPPT优化','功率模块更换','冷却系统维护','通讯模块重置','安全防护升级']
        need = 15-c
        for i in range(need):
            cr = random.choice(unames)
            asgn = random.choice(unames)
            st = random.choice(['pending','assigned','in_progress','resolved','closed'])
            cur.execute("INSERT INTO work_orders (no,title,description,type,priority,status,source,device_id,station_id,creator_id,creator_name,assignee_id,assignee_name,ai_suggestion,result,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (f'WO{20260501+i:08d}',titles[i] if i<len(titles) else f'工单{i+1}',f'详细描述：需对{titles[i] if i<len(titles) else "设备"}进行维护',random.choice(['repair','maintenance','inspection','upgrade']),random.choice(['P0','P1','P2']),st,'system',random.choice(devs),random.choice(sts),random.choice(uids),cr[1],random.choice(uids),asgn[1],f'建议：{random.choice(["检查接线","更换模块","升级固件","调整参数"])}','in_progress' if st not in ['pending','closed'] else ('completed' if st=='closed' else None),rt(14)))
        conn.commit()
        print(f"  workorders: +{need}")
    else: print(f"  workorders: {c} OK")
    
    # === knowledge_articles (20) ===
    c = cur.execute("SELECT COUNT(*) FROM knowledge_articles").fetchone()[0]
    if c < 20:
        arts = [
            ('逆变器日常维护指南','运维指南','逆变器是光伏系统的核心设备，日常维护包括：1.检查散热风扇运转情况；2.清洁散热片；3.检查接线端子紧固；4.记录运行参数。建议每月进行一次全面检查。','运维指南'),
            ('常见电网侧故障诊断','故障处理','电网侧故障包括过压、欠压、频率异常等。诊断步骤：1.查看电网电压波形；2.检查电网频率；3.分析故障录波；4.对比历史数据。','故障处理'),
            ('高压安全操作规程','安全规范','在操作高压设备前必须：1.穿戴绝缘装备；2.验电确认无电；3.挂接地线；4.设置警示标识。严禁单人作业。','安全规范'),
            ('TL-3000逆变器操作手册','设备手册','TL-3000逆变器采用三电平拓扑结构，额定功率30kW，最大效率98.6%。安装前请确认安装位置通风良好、环境温度-25~60℃、湿度<95%。','设备手册'),
            ('电池组均衡维护流程','操作流程','电池组均衡维护周期为30天。步骤：1.断开电池组；2.测量单体电压；3.计算压差；4.对压差>50mV的单体进行均衡充电；5.记录维护数据。','操作流程'),
            ('MPPT效率优化指南','运维指南','MPPT最大功率点跟踪优化可提升发电量3-8%。优化方法：1.清洁组件表面；2.检查组串匹配；3.调整倾角；4.更新MPPT算法参数。','运维指南'),
            ('BMS通讯异常排查','故障处理','BMS通讯异常可能由以下原因引起：1.RS485接线松动；2.终端电阻缺失；3.通讯模块故障；4.电磁干扰。排查步骤：先检查物理连接，再检查通讯参数。','故障处理'),
            ('充电桩故障码手册','设备手册','充电桩故障码分类：P0-功率控制类、P1-充电模块类、P2-BMS通讯类、P3-计量类、P4-安全类。每个故障码对应详细的诊断和修复指南。','设备手册'),
            ('防雷系统检测规范','安全规范','防雷系统应每季度检测一次：1.接地电阻<4Ω；2.避雷器动作次数；3.浪涌保护器状态；4.等电位连接可靠性。','安全规范'),
            ('数据采集器校准流程','操作流程','数据采集器校准周期为6个月。校准项目：1.电压精度±0.5%；2.电流精度±0.5%；3.功率精度±1%；4.时间同步±1s。','操作流程'),
            ('运维巡检标准流程','运维指南','运维巡检分为日检、周检、月检。日检：远程查看运行数据；周检：现场检查设备状态；月检：全面检测+数据分析。','运维指南'),
            ('功率模块更换步骤','故障处理','功率模块更换前需：1.确认备件型号匹配；2.断开直流侧和交流侧；3.等待电容放电完成；4.按标识接线；5.上电测试。','故障处理'),
            ('受限空间作业安全','安全规范','受限空间作业必须执行审批制度：1.作业前审批；2.通风检测；3.专人监护；4.应急准备。严禁未经审批进入。','安全规范'),
            ('SCADA系统使用手册','设备手册','SCADA系统提供实时监控和数据采集功能。主要功能：1.实时数据展示；2.历史数据查询；3.告警管理；4.报表生成。','设备手册'),
            ('应急预案启动流程','操作流程','应急响应分为三级：一级(重大事故)、二级(设备故障)、三级(一般异常)。启动流程：发现→报告→评估→启动→处置→总结。','操作流程'),
            ('光伏组件清洗指南','运维指南','组件清洗周期：一般地区3个月，多尘地区1个月。清洗方法：1.清晨或傍晚清洗；2.使用纯净水；3.软毛刷轻刷；4.禁止踩踏组件。','运维指南'),
            ('储能系统充放电策略','操作流程','储能系统充放电策略：1.谷时充电(23:00-7:00)；2.峰时放电(10:00-12:00,14:00-17:00)；3.SOC范围20%-90%；4.温度保护>50℃停止充电。','操作流程'),
            ('逆变器固件升级指南','操作流程','固件升级步骤：1.备份当前配置；2.下载最新固件；3.通过USB或网络上传；4.等待升级完成(约5分钟)；5.重启设备；6.验证版本。','操作流程'),
            ('配电系统巡检要点','运维指南','配电系统巡检要点：1.断路器状态；2.母线温度；3.电缆接头；4.保护装置；5.接地系统。使用红外热成像仪检测异常发热点。','运维指南'),
            ('故障诊断AI系统说明','设备手册','AI故障诊断系统基于深度学习，支持：1.故障自动识别；2.根因分析；3.修复建议；4.预防措施。诊断准确率>92%。','设备手册'),
        ]
        for title,cat,content,tags in arts:
            cur.execute("INSERT OR IGNORE INTO knowledge_articles (title,category,content,author_id,view_count,published,tags) VALUES (?,?,?,?,?,?,?)",(title,cat,content,1,random.randint(10,500),True,tags))
        conn.commit()
        print(f"  knowledge_articles: +{len(arts)}")
    else: print(f"  knowledge_articles: {c} OK")
    
    # === login_logs (30) - use audit_logs ===
    c = cur.execute("SELECT COUNT(*) FROM audit_logs WHERE action='login'").fetchone()[0]
    if c < 30:
        need = 30-c
        for _ in range(need):
            ok = random.random()>0.15
            cur.execute("INSERT INTO audit_logs (user_id,username,action,module,ip,status,message,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (random.randint(1,8),random.choice([u[0] for u in unames]),'login','auth',f'192.168.1.{random.randint(2,254)}',random.choice(['Chrome/120','Safari/17','Edge/120']),'success' if ok else 'failed','登录成功' if ok else random.choice(['密码错误','账号不存在','账号已锁定']),rt(7)))
        conn.commit()
        print(f"  audit_logs(login): +{need}")
    else: print(f"  audit_logs(login): {c} OK")
    
    # === device_health_records (30) ===
    c = cur.execute("SELECT COUNT(*) FROM device_health_records").fetchone()[0]
    if c < 30:
        need = min(30-c,len(devs))
        for did in devs[:need]:
            cur.execute("INSERT INTO device_health_records (device_id,electrical_safe_score,thermal_score,comm_score,power_quality_score,mechanical_score,total_score,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (did,round(80+random.random()*20),round(80+random.random()*20),round(80+random.random()*20),round(80+random.random()*20),round(80+random.random()*20),round(0.85+random.random()*0.15,2),rt(1)))
        conn.commit()
        print(f"  device_health_records: +{need}")
    else: print(f"  device_health_records: {c} OK")
    
    # === audit_logs (operations) ===
    c = cur.execute("SELECT COUNT(*) FROM audit_logs WHERE action IN ('create_device','update_alarm','delete_workorder','export_report','config_change','remote_command','user_create','station_update')").fetchone()[0]
    if c < 30:
        actions = ['create_device','update_alarm','delete_workorder','export_report','config_change','remote_command','user_create','station_update']
        resources = ['device','alarm','workorder','user','station','report','config','knowledge']
        need = 30-c
        for _ in range(need):
            cur.execute("INSERT INTO audit_logs (user_id,username,action,module,target_id,target_desc,ip_address,user_agent,result,timestamp) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (random.randint(1,8),random.choice([u[0] for u in unames]),random.choice(actions),random.choice(resources),str(random.randint(1,50)),random.choice(resources),f'192.168.1.{random.randint(2,254)}','Chrome/120','success',rt(7)))
        conn.commit()
        print(f"  audit_logs(ops): +{need}")
    else: print(f"  audit_logs(ops): {c} OK")
    
    # === gateways (16) ===
    c = cur.execute("SELECT COUNT(*) FROM gateways").fetchone()[0]
    if c < 16:
        need = min(16-c,len(sts))
        for sid in sts[:need]:
            cur.execute("INSERT INTO gateways (sn,name,model,manufacturer,station_id,status,firmware_version,ip_address,mac_address,location,health_score,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (f'GW{random.randint(100000,999999)}',f'采控网关-{sid}',random.choice(['TL-GW-100','TL-GW-200']),'天链科技',sid,random.choices(['online','offline'],weights=[8,2])[0],f'V{random.randint(1,3)}.{random.randint(0,9)}.{random.randint(0,9)}',f'10.0.{random.randint(1,254)}.{random.randint(1,254)}',f'{random.randint(2,15):02X}:{random.randint(0,255):02X}:{random.randint(0,255):02X}:{random.randint(0,255):02X}:{random.randint(0,255):02X}:{random.randint(0,255):02X}',f'{sid}号站点机房',round(0.85+random.random()*0.15,2),rt(90)))
        conn.commit()
        print(f"  gateways: +{need}")
    else: print(f"  gateways: {c} OK")
    
    # === telemetry (50) ===
    c = cur.execute("SELECT COUNT(*) FROM telemetry").fetchone()[0]
    if c < 50:
        inv_devs = [r[0] for r in cur.execute("SELECT id FROM devices WHERE type IN ('inverter','charger','battery')").fetchall()]
        if not inv_devs: inv_devs = devs[:10]
        need = 50-c
        cols = "device_id,grid_voltage_a,grid_current_a,grid_power_a,grid_reactive_a,grid_voltage_b,grid_current_b,grid_power_b,grid_reactive_b,grid_voltage_c,grid_current_c,grid_power_c,grid_reactive_c,grid_frequency,grid_power_total,grid_reactive_total,grid_power_factor,inv_voltage_a,inv_current_a,inv_power_a,inv_voltage_b,inv_current_b,inv_power_b,inv_voltage_c,inv_current_c,inv_power_c,inv_power_total,battery_voltage,battery_current,battery_power,battery_soc,battery_soh,battery_temperature,pv1_voltage,pv1_current,pv2_voltage,pv2_current,pv_power_total,bus_voltage_pos,bus_voltage_neg,daily_generation,total_generation,run_mode,system_status"
        for _ in range(need):
            cur.execute(f"INSERT INTO telemetry ({cols}) VALUES ({','.join(['?']*44)})",
                (random.choice(inv_devs),round(220+random.random()*20,1),round(5+random.random()*20,1),round(1000+random.random()*3000,0),round(100+random.random()*500,0),round(220+random.random()*20,1),round(5+random.random()*20,1),round(1000+random.random()*3000,0),round(100+random.random()*500,0),round(220+random.random()*20,1),round(5+random.random()*20,1),round(1000+random.random()*3000,0),round(100+random.random()*500,0),round(50+random.random()*0.2,2),round(3000+random.random()*9000,0),round(300+random.random()*1500,0),round(0.85+random.random()*0.15,2),round(250+random.random()*30,1),round(5+random.random()*20,1),round(1000+random.random()*3000,0),round(250+random.random()*30,1),round(5+random.random()*20,1),round(1000+random.random()*3000,0),round(250+random.random()*30,1),round(5+random.random()*20,1),round(1000+random.random()*3000,0),round(3000+random.random()*9000,0),round(400+random.random()*100,1),round(5+random.random()*30,1),round(2000+random.random()*5000,0),round(30+random.random()*60,1),round(85+random.random()*14,1),round(25+random.random()*20,1),round(300+random.random()*200,1),round(2+random.random()*10,1),round(300+random.random()*200,1),round(2+random.random()*10,1),round(2000+random.random()*6000,0),round(600+random.random()*100,1),round(600+random.random()*100,1),round(10+random.random()*50,1),round(1000+random.random()*10000,0),random.randint(1,5),random.randint(1,3)))
        conn.commit()
        print(f"  telemetry: +{need}")
    else: print(f"  telemetry: {c} OK")
    
    # === fault_codes (30) - different schema ===
    c = cur.execute("SELECT COUNT(*) FROM fault_codes").fetchone()[0]
    if c < 30:
        faults = [
            ('0x01','电网过压','inverter','grid','critical','电网电压超过保护阈值',['电网电压异常','保护阈值设置过低','电压传感器故障'],['检查电网电压','确认保护阈值设置','更换电压传感器'],['复位重启','调整保护参数'],30,95,True,True),
            ('0x02','电网欠压','inverter','grid','critical','电网电压低于保护阈值',['电网电压异常','线路阻抗过大','负载突变'],['检查电网电压','检查线路连接','确认负载状态'],['调整保护参数','增加稳压设备'],30,95,True,True),
            ('0x03','电网过频','inverter','grid','warning','电网频率超过50.5Hz',['电网频率异常','发电机调速器故障'],['检查电网频率','确认电网稳定性'],['记录并监控'],60,90,False,True),
            ('0x04','电网欠频','inverter','grid','warning','电网频率低于49.5Hz',['电网频率异常','负载过重'],['检查电网频率','确认负载状态'],['记录并监控'],60,90,False,True),
            ('0x10','绝缘故障','inverter','safety','critical','直流侧绝缘电阻过低',['直流线缆老化','接线盒进水','组件破损'],['测量绝缘电阻','定位故障组串','排查接线盒'],['更换线缆','修复接地系统'],15,85,True,False),
            ('0x11','漏电流保护','inverter','safety','critical','漏电流超过安全阈值',['接地系统异常','电容漏电','EMC滤波器故障'],['检查接地系统','排查漏电源','测量对地电阻'],['修复接地','更换滤波器件'],15,88,True,False),
            ('0x20','逆变器过温','inverter','thermal','warning','散热器温度超过85℃',['散热风扇故障','散热片积灰','环境温度过高'],['检查散热风扇','清洁散热片','检查环境温度'],['更换风扇','改善通风'],30,92,False,True),
            ('0x21','IGBT过温','inverter','thermal','critical','IGBT模块温度超过100℃',['冷却系统故障','负载过重','导热硅脂老化'],['立即停机检查','确认冷却系统','检查负载状态'],['更换冷却器件','降低功率'],10,85,True,False),
            ('0x30','直流母线过压','inverter','dc','critical','直流母线电压超过设定值',['输入电压过高','电容老化','负载突变'],['检查输入电压','确认电容状态','检查负载'],['更换电容','调整输入'],15,90,True,False),
            ('0x31','直流母线欠压','inverter','dc','warning','直流母线电压低于设定值',['输入电源异常','电容故障','接触不良'],['检查输入电源','确认电容状态','检查接线'],['更换电容','紧固接线'],30,88,False,True),
            ('0x40','MPPT异常','inverter','mppt','warning','MPPT跟踪效率低于80%',['组件遮挡','组串失配','MPPT算法异常'],['检查组件表面','检查组串匹配','更新算法参数'],['清洁组件','调整配置'],60,85,False,True),
            ('0x50','通讯中断','gateway','comm','warning','与监控中心通讯中断',['网络故障','通讯模块故障','配置错误'],['检查网络连接','确认通讯模块','检查配置'],['更换模块','修复网络'],30,90,False,True),
            ('P001','充电模块故障','charger','module','critical','充电模块输出异常',['模块内部故障','输入电源异常','负载短路'],['检查模块输入输出','确认模块状态','检查负载'],['更换模块'],15,88,True,False),
            ('P002','BMS通讯异常','charger','comm','warning','与BMS通讯中断',['CAN总线故障','BMS供电异常','终端电阻缺失'],['检查CAN总线','确认BMS供电','检查终端电阻'],['修复总线','更换模块'],30,85,False,True),
            ('P003','过流保护','charger','safety','critical','充电电流超过额定值',['充电参数设置错误','电池短路','控制逻辑异常'],['检查充电参数','确认电池状态','检查控制逻辑'],['调整参数','更换电池'],10,92,True,False),
            ('P004','过温保护','charger','thermal','warning','充电模块温度过高',['散热系统故障','环境温度过高','持续大功率充电'],['检查散热系统','降低充电功率','改善通风'],['修复散热'],30,90,False,True),
            ('B001','电芯过压','battery','cell','critical','单体电压超过4.2V',['均衡电路故障','充电控制异常','电压采样偏差'],['检查均衡电路','确认充电参数','校准电压采样'],['修复均衡','更换电芯'],15,93,True,False),
            ('B002','电芯欠压','battery','cell','critical','单体电压低于2.5V',['过度放电','自放电过大','电芯老化'],['检查电池状态','确认充电策略','评估电芯寿命'],['激活充电','更换电芯'],15,90,True,False),
            ('B003','电池过温','battery','thermal','warning','电池温度超过50℃',['充放电功率过大','冷却系统故障','环境温度过高'],['检查冷却系统','降低充放电功率','改善通风'],['修复冷却'],30,88,False,True),
            ('T001','变压器过温','transformer','thermal','warning','绕组温度超过130℃',['冷却系统故障','过载运行','环境温度过高'],['检查冷却系统','降低负载','检查环境'],['修复冷却','降低负载'],30,85,False,True),
            ('T002','油位异常','transformer','oil','critical','油位低于安全线',['渗漏油','油温变化','油位计故障'],['补充绝缘油','检查渗漏','校准油位计'],['补油、检修'],60,90,True,False),
            ('M001','计量偏差','meter','meter','warning','电量计量偏差超过2%',['CT极性接反','计量芯片故障','校准参数漂移'],['校准计量模块','确认CT极性','检查计量芯片'],['重新校准','更换芯片'],60,85,False,True),
            ('G001','网关离线','gateway','comm','warning','网关设备离线',['网络故障','电源故障','系统崩溃'],['检查网络连接','确认电源状态','重启设备'],['修复网络、重启'],30,92,False,True),
            ('G002','数据采集异常','gateway','data','warning','数据采集不完整或异常',['传感器故障','采集模块异常','通讯干扰'],['检查传感器','确认采集模块','排查干扰源'],['更换传感器'],30,88,False,True),
            ('0x60','功率因数异常','inverter','power','info','功率因数低于0.9',['无功补偿不足','负载特性变化','参数设置错误'],['检查无功补偿设置','确认负载特性','调整参数'],['调整参数'],120,80,False,True),
            ('0x70','谐波超标','inverter','power','warning','THD超过5%',['滤波器故障','非线性负载','器件老化'],['检查滤波器状态','确认负载特性','检测器件'],['修复滤波器'],60,85,False,True),
            ('0x80','孤岛保护','inverter','safety','critical','检测到电网孤岛运行',['电网断电','保护设置异常','检测电路故障'],['检查电网连接','确认保护设置','检测电路'],['恢复电网连接'],5,95,True,False),
            ('B004','SOC校准异常','battery','bms','info','SOC估算偏差超过5%',['校准周期过长','充放电循环不完整','温度影响'],['执行完整充放电循环','更新校准算法','检查温度传感器'],['校准SOC'],120,75,False,True),
            ('0x41','组串失配','inverter','pv','info','光伏组串电流差异过大',['组件老化不一致','遮挡不均','组串配置不当'],['检查组串配置','排查遮挡问题','评估组件状态'],['调整配置、清洁'],60,80,False,True),
            ('P010','计量异常','charger','meter','warning','充电电量计量偏差过大',['计量模块故障','CT精度下降','校准参数漂移'],['校准计量模块','检查CT精度','更新校准参数'],['重新校准'],60,85,False,True),
        ]
        for code,name,dtype,cat,level,desc,causes,steps,suggs,resp,acc,auto,remote in faults:
            cur.execute("INSERT INTO fault_codes (fault_code,fault_name,fault_description,device_type,fault_category,fault_level,possible_causes,diagnosis_steps,repair_suggestions,response_time_minutes,avg_repair_time_minutes,auto_stop,remote_fixable,enabled) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (code,name,desc,dtype,cat,level,json.dumps(causes,ensure_ascii=False),json.dumps(steps,ensure_ascii=False),json.dumps(suggs,ensure_ascii=False),resp,resp*3,auto,remote,True))
        conn.commit()
        print(f"  fault_codes: +{len(faults)}")
    else: print(f"  fault_codes: {c} OK")
    
    # === alarm_rules (10) ===
    c = cur.execute("SELECT COUNT(*) FROM alarm_rules").fetchone()[0]
    if c < 10:
        rules = [
            ('逆变器过温告警','inverter','temperature','>',85.0,'warning','[1,2]',True),
            ('电池过压告警','battery','voltage','>',4.2,'critical','[1,3]',True),
            ('电网频率异常','inverter','grid_frequency','<',49.5,'critical','[1]',True),
            ('充电桩过流告警','charger','current','>',250.0,'critical','[1,2]',True),
            ('通讯中断告警','gateway','comm_status','=',0,'warning','[1,4]',True),
            ('绝缘电阻过低','inverter','insulation_resistance','<',1.0,'critical','[1,3]',True),
            ('电池SOC过低','battery','soc','<',10.0,'warning','[1,6]',True),
            ('功率因数偏低','inverter','power_factor','<',0.9,'info','[1]',True),
            ('变压器油温过高','transformer','temperature','>',100.0,'critical','[1,5]',True),
            ('直流母线过压','inverter','bus_voltage','>',850.0,'critical','[1,3]',True),
        ]
        for name,dt,met,op,thr,lv,notify,en in rules:
            cur.execute("INSERT INTO alarm_rules (name,device_type,metric,operator,threshold,level,notify_users,enabled) VALUES (?,?,?,?,?,?,?,?)",(name,dt,met,op,thr,lv,notify,en))
        conn.commit()
        print(f"  alarm_rules: +{len(rules)}")
    else: print(f"  alarm_rules: {c} OK")
    
    # === diagnosis_rules (10) - different schema ===
    c = cur.execute("SELECT COUNT(*) FROM diagnosis_rules").fetchone()[0]
    if c < 10:
        rules = [
            ('电网过压诊断','检查电网电压→确认保护阈值→排查电网侧问题','inverter','grid',json.dumps([{'metric':'grid_voltage','op':'>','value':253}]),1,'电网过压故障',['检查电网稳定性','确认保护设置']),
            ('绝缘故障诊断','测量绝缘电阻→定位故障组串→排查接线盒','inverter','safety',json.dumps([{'metric':'insulation_resistance','op':'<','value':1}]),1,'直流侧绝缘故障',['检查直流线缆','排查接地故障']),
            ('过温故障诊断','检查散热风扇→清洁散热片→检查环境温度','inverter','thermal',json.dumps([{'metric':'temperature','op':'>','value':85}]),2,'设备过温',['改善通风','更换风扇']),
            ('BMS通讯诊断','检查CAN线→确认终端电阻→检查BMS供电','charger','comm',json.dumps([{'metric':'comm_status','op':'=','value':0}]),2,'BMS通讯中断',['修复CAN总线','确认BMS供电']),
            ('电芯过压诊断','检查均衡电路→确认充电参数→校准电压采样','battery','cell',json.dumps([{'metric':'cell_voltage','op':'>','value':4.2}]),1,'电芯过压故障',['修复均衡电路','更换电芯']),
            ('充电桩过流诊断','检查充电参数→确认电池状态→检查控制逻辑','charger','safety',json.dumps([{'metric':'current','op':'>','value':250}]),1,'充电过流保护',['调整充电参数','检查电池']),
            ('变压器过温诊断','检查冷却系统→降低负载→检查环境','transformer','thermal',json.dumps([{'metric':'temperature','op':'>','value':130}]),2,'变压器过温',['修复冷却系统','降低负载']),
            ('网关离线诊断','检查网络连接→确认电源状态→重启设备','gateway','comm',json.dumps([{'metric':'online_status','op':'=','value':0}]),2,'网关设备离线',['修复网络','重启设备']),
            ('MPPT异常诊断','检查组件表面→检查组串匹配→更新算法','inverter','mppt',json.dumps([{'metric':'mppt_efficiency','op':'<','value':0.8}]),3,'MPPT跟踪效率低',['清洁组件','调整配置']),
            ('谐波超标诊断','检查滤波器状态→确认负载特性→检测器件','inverter','power',json.dumps([{'metric':'thd','op':'>','value':5}]),3,'谐波含量超标',['修复滤波器','更换器件']),
        ]
        for name,desc,dt,cat,conds,pri,result,actions in rules:
            cur.execute("INSERT INTO diagnosis_rules (name,description,device_type,fault_category,conditions,priority,diagnosis_result,repair_actions,enabled) VALUES (?,?,?,?,?,?,?,?,?)",(name,desc,dt,cat,conds,pri,result,json.dumps(actions,ensure_ascii=False),True))
        conn.commit()
        print(f"  diagnosis_rules: +{len(rules)}")
    else: print(f"  diagnosis_rules: {c} OK")
    
    # === firmware (5) ===
    c = cur.execute("SELECT COUNT(*) FROM firmware").fetchone()[0]
    if c < 5:
        fws = [
            ('V3.2.1','TL-GW-200','/firmware/gw200_v3.2.1.bin',2048000,'a1b2c3d4','修复通讯稳定性问题，优化数据采集','2026-04-15','published'),
            ('V3.2.0','TL-GW-200','/firmware/gw200_v3.2.0.bin',2048000,'e5f6g7h8','支持MQTT协议，新增边缘计算功能','2026-03-01','published'),
            ('V2.8.3','TL-INV-3000','/firmware/inv3000_v2.8.3.bin',1024000,'i9j0k1l2','优化MPPT算法，提升转换效率','2026-04-20','published'),
            ('V2.8.2','TL-INV-3000','/firmware/inv3000_v2.8.2.bin',1024000,'m3n4o5p6','修复电网频率异常保护逻辑','2026-02-15','archived'),
            ('V1.5.0','TL-CHG-120KW','/firmware/chg120_v1.5.0.bin',1536000,'q7r8s9t0','支持新国标充电协议','2026-05-01','published'),
        ]
        for v,m,p,s,cs,cl,dt,st in fws:
            cur.execute("INSERT INTO firmware (version,model,file_path,file_size,checksum,changelog,release_date,status) VALUES (?,?,?,?,?,?,?,?)",(v,m,p,s,cs,cl,dt,st))
        conn.commit()
        print(f"  firmware: +{len(fws)}")
    else: print(f"  firmware: {c} OK")
    
    # === roles (5) ===
    c = cur.execute("SELECT COUNT(*) FROM roles").fetchone()[0]
    if c < 5:
        roles = [
            ('admin','系统管理员',json.dumps(['*']),True),
            ('operator','运维操作员',json.dumps(['device:read','device:write','alarm:read','alarm:write','workorder:read','workorder:write','station:read']),False),
            ('technician','技术工程师',json.dumps(['device:read','alarm:read','workorder:read','workorder:write','knowledge:read','knowledge:write']),False),
            ('viewer','只读查看者',json.dumps(['device:read','alarm:read','station:read','report:read']),False),
            ('security','安全管理员',json.dumps(['alarm:read','workorder:read','security:read','security:write','login_log:read']),False),
        ]
        for n,d,p,sys in roles:
            cur.execute("INSERT INTO roles (name,description,permissions,is_system) VALUES (?,?,?,?)",(n,d,p,sys))
        conn.commit()
        print(f"  roles: +{len(roles)}")
    else: print(f"  roles: {c} OK")


if __name__ == '__main__':
    print("="*50)
    print("天链V3 Mock数据补齐 (schema修正版)")
    print("="*50)
    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA foreign_keys = OFF")
    print("\n开始补齐...")
    seed(conn)
    print("\n"+"="*50)
    print("最终统计:")
    cur = conn.cursor()
    for t in [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]:
        print(f"  {t}: {cur.execute(f'SELECT COUNT(*) FROM [{t}]').fetchone()[0]}")
    conn.close()
    print("="*50)
    print("✅ 完成")
