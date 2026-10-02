"""光缆段占用台账规则验证脚本（不依赖网络，直接用 TestClient 打接口）。"""
from __future__ import annotations

import sys
from urllib.parse import quote

sys.path.insert(0, "/workspace/backend")

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def h(team: str, role: str, operator: str) -> dict[str, str]:
    """中文身份信息百分号编码后放进请求头。"""
    return {"X-Team": quote(team), "X-Role": quote(role), "X-Operator": quote(operator)}


TEAM1_CLERK = h("施工一队", "资料员", "李资料")
TEAM1_CREW = h("施工一队", "施工员", "王大锤")
TEAM2_CLERK = h("施工二队", "资料员", "赵资料")

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"  -> {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


def post(path: str, body: dict, headers: dict | None = None) -> dict:
    r = client.post(path, json=body, headers=headers or TEAM1_CLERK)
    return r.json()


def action(cid: int, act: str, headers: dict | None = None, **extra) -> dict:
    return post(f"/api/cable/{cid}/actions", {"values": {"action": act, **extra}}, headers)


# 1. 同一起终点重复登记只记一次（起终点互换也算同一段）
r = post("/api/cable", {"values": {"光缆编号": "FO-T1", "起点": "甲站", "终点": "乙站", "芯数": "12芯"}})
check("登记新光缆段成功", r["ok"], r["message"])
cid = r["entry"]["id"]
r2 = post("/api/cable", {"values": {"光缆编号": "FO-T1DUP", "起点": "乙站", "终点": "甲站", "芯数": "12芯"}})
check("起终点互换重复登记被挡", not r2["ok"] and "只记一次" in r2["message"], r2.get("message", ""))

# 2. 没勘测不许直接分配/敷设
r = action(cid, "敷设核销")
check("未勘测不许敷设核销", not r["ok"] and "尚未分配" in r["message"], r.get("message", ""))
r = action(cid, "分配孔位", slots=[{"资源类型": "管道", "资源编码": "GD-003", "孔位": "2#孔"}])
check("未勘测不许分配孔位", not r["ok"] and "勘测" in r["message"], r.get("message", ""))

# 3. 勘测 -> 分配（含冲突检测）
r = action(cid, "完成勘测")
check("完成勘测", r["ok"] and r["entry"]["status"] == "已勘测", r.get("message", ""))
r = action(cid, "分配孔位", slots=[
    {"资源类型": "管道", "资源编码": "GD-001", "孔位": "1#孔"},   # 被 FO-A01 占
    {"资源类型": "管道", "资源编码": "GD-003", "孔位": "2#孔"},   # 空闲
    {"资源类型": "杆路", "资源编码": "GL-001", "孔位": "P03"},    # 杆位允许加挂
])
check("管道冲突整批拦下并说明跟谁冲突", not r["ok"] and "FO-A01" in r["message"], r.get("message", ""))
# 去掉冲突孔位后可分配（杆位与存量缆同杆加挂允许）
r = action(cid, "分配孔位", slots=[
    {"资源类型": "管道", "资源编码": "GD-003", "孔位": "2#孔"},
    {"资源类型": "杆路", "资源编码": "GL-001", "孔位": "P03"},
])
check("空闲孔位+同杆加挂分配成功", r["ok"] and r["entry"]["status"] == "已分配", r.get("message", ""))

# 4. 同一孔位重复分配不重复记
r = action(cid, "分配孔位", slots=[{"资源类型": "管道", "资源编码": "GD-003", "孔位": "2#孔"}])
check("同缆同孔重复分配幂等无新增", not r["ok"] and "没有新增分配" in r["message"], r.get("message", ""))

# 5. 敷设核销：非资料员不能核销
r = action(cid, "敷设核销", headers=TEAM1_CREW)
check("施工员不能核销", not r["ok"] and "资料员" in r["message"], r.get("message", ""))

# 6. 敷设核销逐孔推进、重复核销不重复扣
r = action(cid, "敷设核销")  # 序号1 GD-003 2#孔
check("核销序号1", r["ok"] and "序号 1" in r["message"] and r["entry"]["status"] == "已敷设", r.get("message", ""))
r = action(cid, "敷设核销", seq=1)
check("重复核销序号1被挡且提示断点", not r["ok"] and "不重复扣" in r["message"] and "序号 2" in r["message"], r.get("message", ""))
r = action(cid, "敷设核销")  # 从中断孔位序号2接着核销
check("从断点序号2续销", r["ok"] and "序号 2" in r["message"] and "敷设完成" in r["message"], r.get("message", ""))
r = action(cid, "提交核实")
check("全部核销后核实通过", r["ok"] and r["entry"]["status"] == "已核实", r.get("message", ""))

# 7. 敷设中断场景：FO-A04 断点在序号5（GD-003 1#孔，已分配未敷设）
r = client.get("/api/cable/5").json()
check("FO-A04 当前断点正确", r["当前断点"] == "序号5 GD-003 1#孔", r.get("当前断点", ""))
r = action(5, "敷设核销")
check("FO-A04 从断点序号5续销", r["ok"] and "序号 5" in r["message"] and "敷设完成" in r["message"], r.get("message", ""))
r = action(5, "提交核实")
check("FO-A04 核实通过", r["ok"] and r["entry"]["status"] == "已核实", r.get("message", ""))

# 8. 一孔一缆：原占用核销前别人不能占；核销后可占
# 占用记录 id=1: FO-A01(一队) 占 GD-001 1#孔 —— 历史占用，不许核销
r = post("/api/cable/occupancies/1/release", {"values": {"reason": "测试"}}, TEAM1_CLERK)
check("历史占用不许核销", not r["ok"] and "历史" in r["message"], r.get("message", ""))
# id=17 现在 FO-A04 已核实，GD-003 1#孔 非历史，找一条非历史占用测试释放
# 用 FO-A03 的 GD-001 3#孔（id=8，一队，非历史）
r = post("/api/cable/occupancies/8/release", {"values": {"reason": "现场改路"}}, TEAM2_CLERK)
check("别的队伍只能查看不能核销", not r["ok"] and "只能查看" in r["message"], r.get("message", ""))
r = post("/api/cable/occupancies/8/release", {"values": {"reason": "现场改路"}}, TEAM1_CREW)
check("本队施工员不能核销", not r["ok"] and "资料员" in r["message"], r.get("message", ""))
r = post("/api/cable/occupancies/8/release", {"values": {"reason": "现场改路"}}, TEAM1_CLERK)
check("本队资料员核销占用成功", r["ok"] and "已释放" in r["message"], r.get("message", ""))
r = post("/api/cable/occupancies/8/release", {"values": {"reason": "再销一次"}}, TEAM1_CLERK)
check("重复核销占用被挡", not r["ok"] and "不重复核销" in r["message"], r.get("message", ""))
# 释放后别的队伍也能占这个孔
r = post("/api/cable", {"values": {"光缆编号": "FO-T2", "起点": "丙站", "终点": "丁站", "芯数": "24芯"}}, TEAM2_CLERK)
cid2 = r["entry"]["id"]
action(cid2, "完成勘测", headers=TEAM2_CLERK)
r = action(cid2, "分配孔位", headers=TEAM2_CLERK,
           slots=[{"资源类型": "管道", "资源编码": "GD-001", "孔位": "3#孔"}])
check("释放后孔位可重新被占用", r["ok"], r.get("message", ""))

# 9. 二队光缆（FO-B02 id=6），一队打开只能查看
r = action(6, "完成勘测", headers=TEAM1_CLERK)
check("跨队操作被挡", not r["ok"] and "只能查看" in r["message"], r.get("message", ""))
r = action(6, "完成勘测", headers=TEAM2_CLERK)
check("本队勘测成功", r["ok"], r.get("message", ""))

# 10. 存量补录：按顺序落历史占用，管道冲突跳过
r = post("/api/cable/legacy/backfill", {"values": {
    "光缆编号": "FO-LEG1", "起点": "戊镇", "终点": "己镇", "芯数": "12芯",
    "敷设日期": "2024-05-01",
    "slots": [
        {"资源类型": "管道", "资源编码": "GD-002", "孔位": "3#孔"},  # 空闲
        {"资源类型": "管道", "资源编码": "GD-002", "孔位": "1#孔"},  # 被 FO-A01 占
        {"资源类型": "杆路", "资源编码": "GL-002", "孔位": "P12"},
    ],
}}, TEAM1_CLERK)
check("存量补录成功且冲突孔位跳过说明", r["ok"] and "已补录 2" in r["message"] and "FO-A01" in r["message"], r.get("message", ""))
leg = client.get(f"/api/cable/{r['entry']['id']}").json()
check("补录光缆直接已核实且占用标历史", leg["status"] == "已核实" and all(o["历史"] for o in leg["占用明细"]), str(leg))
# 补录的历史占用不能核销
leg_occ_id = leg["占用明细"][0]["id"]
r = post(f"/api/cable/occupancies/{leg_occ_id}/release", {"values": {}}, TEAM1_CLERK)
check("补录的历史占用不能核销", not r["ok"] and "历史" in r["message"], r.get("message", ""))
# 存量同一段不能补两次
r = post("/api/cable/legacy/backfill", {"values": {
    "光缆编号": "FO-LEG2", "起点": "己镇", "终点": "戊镇", "芯数": "12芯", "slots": []}}, TEAM1_CLERK)
check("存量补录重复段被挡", not r["ok"] and "只记一次" in r["message"], r.get("message", ""))

# 11. 资源视图：剩余孔数统计
res = client.get("/api/cable/resources?kind=管道").json()
gd = {item["管道编号"]: item for item in res["items"]}
# GD-001: 4孔，1#2#存量占，3#一队释放后被二队新缆占，4#空闲 => 剩1
check("GD-001 剩余孔数=1", gd["GD-001"]["剩余孔数"] == 1, str(gd["GD-001"]))
# GD-002: 1#2#存量占，3#被补录历史占用 => 剩0
check("GD-002 剩余孔数=0", gd["GD-002"]["剩余孔数"] == 0, str(gd["GD-002"]))
# GD-003: 1# FO-A04占，2# 测试缆占 => 剩0
check("GD-003 剩余孔数=0", gd["GD-003"]["剩余孔数"] == 0, str(gd["GD-003"]))

# 12. 录入校验：不存在的管道/孔位
r = action(cid, "分配孔位", headers=TEAM1_CLERK,
           slots=[{"资源类型": "管道", "资源编码": "GD-001", "孔位": "9#孔"}])
# cid 已核实，会先被状态拦下
check("已核实光缆不可再分配", not r["ok"], r.get("message", ""))

# 13. 未勘测不许直接核实
r = post("/api/cable", {"values": {"光缆编号": "FO-T3", "起点": "庚", "终点": "辛", "芯数": "8芯"}}, TEAM1_CLERK)
cid3 = r["entry"]["id"]
r = action(cid3, "提交核实")
check("未敷设不许核实", not r["ok"] and "未完成敷设" in r["message"], r.get("message", ""))

# 14. 看板统计字段
s = client.get("/api/cable/stats").json()
check("看板含管道剩余孔位", "管道剩余孔位" in s and "历史占用" in s, str(s))

print()
if fails:
    print(f"{len(fails)} 项失败：{fails}")
    sys.exit(1)
print("全部规则验证通过")
