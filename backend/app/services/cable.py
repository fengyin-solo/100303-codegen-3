"""光缆段台账业务规则。

领域口径：
- 光缆段按「起点 + 终点 + 敷设方式」去重，同一段重复登记只记一次；
- 管道孔位 / 杆路挂点是互斥资源：活跃占用（已分配、已核销）唯一，后到的一方
  要么等原占用被释放（撤占核销），要么被挡下并给出冲突对象；
- 加挂光缆必须沿「勘测 → 已分配 → 已敷设 → 已核实」顺序推进，没勘测不许直接敷设；
- 敷设核销按孔位序列顺序扣减，中断后从断点那个孔位接着核销，已核销孔位不重复扣；
- 存量光缆按敷设顺序整段补登，占用一律标记历史遗留、按当时登记保留，不拦截彼此；
- 只有本施工队资料员能写（登记/核销/释放/补登），其他身份只读。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.store import store

MODULE = "_cable_segment"
OCCUPANCY = "_cable_occupancy"
RESOURCE = "_cable_resource"

STATUS_ORDER = ["勘测", "已分配", "已敷设", "已核实"]
LAY_WAY_PIPE = "管道"
LAY_WAY_POLE = "杆路"
RESOURCE_TYPES = {LAY_WAY_PIPE, LAY_WAY_POLE}

# 占用状态：已分配（预占）、已核销（敷设核销扣减）都是活跃占用；已释放不占位。
OCC_ALLOCATED = "已分配"
OCC_WRITTEN_OFF = "已核销"
OCC_RELEASED = "已释放"
ACTIVE_OCC_STATUSES = {OCC_ALLOCATED, OCC_WRITTEN_OFF}

DEFAULT_TEAM_ID = "T01"
DEFAULT_TEAM_NAME = "闽工一队"
CLERK_ROLE = "资料员"


@dataclass(frozen=True)
class Operator:
    """当前操作用户：靠请求头带入，决定有没有核销资格。"""

    team_id: str
    team_name: str
    role: str

    @property
    def is_clerk(self) -> bool:
        return self.role.strip() == CLERK_ROLE

    def owns(self, segment: dict[str, Any]) -> bool:
        return str(segment.get("team_id") or "") == self.team_id

    def deny_reason(self, action: str) -> str | None:
        if not self.is_clerk:
            return f"只有本施工队的{CLERK_ROLE}能{action}，当前身份是「{self.role}」，仅可查看"
        return None


def _norm(value: Any) -> str:
    return str(value or "").strip()


def hole_key(resource_type: str, resource_code: str, hole: str) -> str:
    return f"{resource_type}|{resource_code}|{hole}"


def _occ_key(row: dict[str, Any]) -> str:
    return hole_key(str(row["资源类型"]), str(row["资源编号"]), str(row["孔位"]))


# ---------------------------------------------------------------------------
# 示例数据：一段存量管道光缆、一段存量杆路光缆，加一段敷到一半的在工光缆。
# ---------------------------------------------------------------------------
def _seed() -> dict[str, list[dict[str, Any]]]:
    resources = [
        {"id": 1, "资源类型": LAY_WAY_PIPE, "资源编号": "GD-城东-01", "资源名称": "城东路口管道", "容量": 6, "team_id": DEFAULT_TEAM_ID, "施工队": DEFAULT_TEAM_NAME},
        {"id": 2, "资源类型": LAY_WAY_PIPE, "资源编号": "GD-城东-02", "资源名称": "城东桥边管道", "容量": 4, "team_id": DEFAULT_TEAM_ID, "施工队": DEFAULT_TEAM_NAME},
        {"id": 3, "资源类型": LAY_WAY_POLE, "资源编号": "GG-001", "资源名称": "1号杆", "容量": 4, "team_id": DEFAULT_TEAM_ID, "施工队": DEFAULT_TEAM_NAME},
        {"id": 4, "资源类型": LAY_WAY_POLE, "资源编号": "GG-002", "资源名称": "2号杆", "容量": 4, "team_id": DEFAULT_TEAM_ID, "施工队": DEFAULT_TEAM_NAME},
        {"id": 5, "资源类型": LAY_WAY_POLE, "资源编号": "GG-003", "资源名称": "3号杆", "容量": 4, "team_id": DEFAULT_TEAM_ID, "施工队": DEFAULT_TEAM_NAME},
        {"id": 6, "资源类型": LAY_WAY_POLE, "资源编号": "GG-004", "资源名称": "4号杆", "容量": 4, "team_id": DEFAULT_TEAM_ID, "施工队": DEFAULT_TEAM_NAME},
    ]

    legacy_pipe = {
        "id": 1, "status": "已核实", "pending": False, "abnormal": False, "历史遗留": True,
        "光缆段编号": "CAB-2023-017", "起点": "东基站", "终点": "西基站",
        "敷设方式": LAY_WAY_PIPE, "光缆型号": "GYTA-24B1", "芯数": 24,
        "team_id": DEFAULT_TEAM_ID, "施工队": DEFAULT_TEAM_NAME,
    }
    legacy_pole = {
        "id": 2, "status": "已核实", "pending": False, "abnormal": False, "历史遗留": True,
        "光缆段编号": "CAB-2023-021", "起点": "东基站", "终点": "南光交",
        "敷设方式": LAY_WAY_POLE, "光缆型号": "GYTS-12B1", "芯数": 12,
        "team_id": DEFAULT_TEAM_ID, "施工队": DEFAULT_TEAM_NAME,
    }
    in_progress = {
        "id": 3, "status": "已分配", "pending": True, "abnormal": False, "历史遗留": False,
        "光缆段编号": "CAB-2026-004", "起点": "北机房", "终点": "东基站",
        "敷设方式": LAY_WAY_PIPE, "光缆型号": "GYTA-48B1", "芯数": 48,
        "计划孔位": [
            {"资源类型": LAY_WAY_PIPE, "资源编号": "GD-城东-01", "孔位": "4#孔"},
            {"资源类型": LAY_WAY_PIPE, "资源编号": "GD-城东-01", "孔位": "5#孔"},
            {"资源类型": LAY_WAY_PIPE, "资源编号": "GD-城东-02", "孔位": "2#孔"},
            {"资源类型": LAY_WAY_PIPE, "资源编号": "GD-城东-02", "孔位": "3#孔"},
        ],
        "team_id": DEFAULT_TEAM_ID, "施工队": DEFAULT_TEAM_NAME,
    }

    def occ(oid: int, seg: dict[str, Any], idx: int, rtype: str, code: str, hole: str,
            state: str, legacy: bool) -> dict[str, Any]:
        return {
            "id": oid, "光缆段id": seg["id"], "光缆段编号": seg["光缆段编号"],
            "资源类型": rtype, "资源编号": code, "孔位": hole, "顺序": idx,
            "状态": state, "历史遗留": legacy,
            "team_id": seg["team_id"], "施工队": seg["施工队"], "释放备注": None,
        }

    occupancy = [
        occ(1, legacy_pipe, 0, LAY_WAY_PIPE, "GD-城东-01", "1#孔", OCC_WRITTEN_OFF, True),
        occ(2, legacy_pipe, 1, LAY_WAY_PIPE, "GD-城东-01", "2#孔", OCC_WRITTEN_OFF, True),
        occ(3, legacy_pipe, 2, LAY_WAY_PIPE, "GD-城东-02", "1#孔", OCC_WRITTEN_OFF, True),
        occ(4, legacy_pole, 0, LAY_WAY_POLE, "GG-001", "第1挂点", OCC_WRITTEN_OFF, True),
        occ(5, legacy_pole, 1, LAY_WAY_POLE, "GG-002", "第1挂点", OCC_WRITTEN_OFF, True),
        occ(6, legacy_pole, 2, LAY_WAY_POLE, "GG-003", "第1挂点", OCC_WRITTEN_OFF, True),
        # 在工光缆：4 个孔已分配，前 2 个已敷设核销，断点在 GD-城东-02 的 2#孔。
        occ(7, in_progress, 0, LAY_WAY_PIPE, "GD-城东-01", "4#孔", OCC_WRITTEN_OFF, False),
        occ(8, in_progress, 1, LAY_WAY_PIPE, "GD-城东-01", "5#孔", OCC_WRITTEN_OFF, False),
        occ(9, in_progress, 2, LAY_WAY_PIPE, "GD-城东-02", "2#孔", OCC_ALLOCATED, False),
        occ(10, in_progress, 3, LAY_WAY_PIPE, "GD-城东-02", "3#孔", OCC_ALLOCATED, False),
    ]
    return {RESOURCE: resources, MODULE: [legacy_pipe, legacy_pole, in_progress], OCCUPANCY: occupancy}


store.ensure_tables(_seed())


def _next_id(rows: list[dict[str, Any]]) -> int:
    return max((int(row.get("id", 0)) for row in rows), default=0) + 1


class CableService:
    # ----------------------------- 查询 -----------------------------
    def list_segments(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        lay_way: str | None = None,
        legacy: bool | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [r for r in rows if keyword in _norm(r.get("光缆段编号"))
                    or keyword in _norm(r.get("起点")) or keyword in _norm(r.get("终点"))]
        if status:
            rows = [r for r in rows if r.get("status") == status]
        if lay_way:
            rows = [r for r in rows if r.get("敷设方式") == lay_way]
        if legacy is not None:
            rows = [r for r in rows if bool(r.get("历史遗留")) == legacy]
        rows = sorted(rows, key=lambda r: int(r.get("id", 0)))
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self._decorate(row) for row in rows[start:start + size]], total

    def get_segment(self, segment_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, segment_id)
        return self._decorate(row) if row else None

    def _occupancy_of(self, segment_id: int) -> list[dict[str, Any]]:
        rows = [r for r in store.rows(OCCUPANCY) if int(r.get("光缆段id", 0)) == segment_id]
        return sorted(rows, key=lambda r: int(r.get("顺序", 0)))

    def _decorate(self, segment: dict[str, Any]) -> dict[str, Any]:
        occ_rows = self._occupancy_of(int(segment["id"]))
        active = [r for r in occ_rows if r["状态"] != OCC_RELEASED]
        written = [r for r in occ_rows if r["状态"] == OCC_WRITTEN_OFF]
        allocated = [r for r in occ_rows if r["状态"] == OCC_ALLOCATED]
        next_hole = allocated[0] if allocated else None
        data = dict(segment)
        data["孔位总数"] = len(active)
        data["已核销数"] = len(written)
        data["已分配数"] = len(allocated)
        data["断点孔位"] = ({
            "资源类型": next_hole["资源类型"], "资源编号": next_hole["资源编号"],
            "孔位": next_hole["孔位"], "顺序": next_hole["顺序"],
        } if next_hole else None)
        data["占用明细"] = occ_rows
        return data

    def list_occupancy(self, *, resource_code: str | None = None,
                       status: str | None = None, keyword: str | None = None) -> list[dict[str, Any]]:
        rows = store.rows(OCCUPANCY)
        if resource_code:
            rows = [r for r in rows if resource_code in str(r.get("资源编号", ""))]
        if status:
            rows = [r for r in rows if r.get("状态") == status]
        if keyword:
            rows = [r for r in rows if keyword in str(r.get("光缆段编号", ""))
                    or keyword in str(r.get("资源编号", ""))]
        return sorted(rows, key=lambda r: (str(r["资源类型"]), str(r["资源编号"]), int(r["顺序"])))

    def list_resources(self, *, resource_type: str | None = None) -> list[dict[str, Any]]:
        result = []
        for res in store.rows(RESOURCE):
            if resource_type and res.get("资源类型") != resource_type:
                continue
            occ_rows = [r for r in store.rows(OCCUPANCY)
                        if str(r.get("资源编号")) == str(res["资源编号"])
                        and r.get("状态") in ACTIVE_OCC_STATUSES]
            used = len({_occ_key(r) for r in occ_rows})
            capacity = res.get("容量")
            item = dict(res)
            item["占用孔位数"] = used
            item["剩余孔位数"] = None if capacity is None else max(int(capacity) - used, 0)
            result.append(item)
        return sorted(result, key=lambda r: (str(r["资源类型"]), str(r["资源编号"])))

    def stats(self) -> dict[str, int]:
        segments = store.rows(MODULE)
        active_occ = [r for r in store.rows(OCCUPANCY) if r["状态"] in ACTIVE_OCC_STATUSES]
        return {
            "光缆段总数": len(segments),
            "勘测中": sum(1 for r in segments if r["status"] == "勘测"),
            "已分配待敷设": sum(1 for r in segments if r["status"] == "已分配"),
            "已敷设待核实": sum(1 for r in segments if r["status"] == "已敷设"),
            "已核实": sum(1 for r in segments if r["status"] == "已核实"),
            "活跃占用孔位": len(active_occ),
            "待核销孔位": sum(1 for r in active_occ if r["状态"] == OCC_ALLOCATED),
            "历史遗留占用": sum(1 for r in active_occ if r.get("历史遗留")),
        }

    # ----------------------------- 校验辅料 -----------------------------
    def _validate_holes(self, values: dict[str, Any], lay_way: str) -> tuple[list[dict[str, str]], list[str]]:
        """把前端的孔位序列归一化，并查自身重复/字段缺失。"""
        raw = values.get("孔位序列") or []
        if not isinstance(raw, list) or not raw:
            return [], ["占用孔位序列"]
        holes: list[dict[str, str]] = []
        errors: list[str] = []
        seen: set[str] = set()
        known = {str(r["资源编号"]): r for r in store.rows(RESOURCE)}
        for idx, item in enumerate(raw):
            code = _norm(item.get("资源编号"))
            hole = _norm(item.get("孔位"))
            rtype = _norm(item.get("资源类型")) or lay_way
            if not code or not hole:
                errors.append(f"第{idx + 1}个孔位缺资源编号或孔位名")
                continue
            if rtype not in RESOURCE_TYPES:
                errors.append(f"第{idx + 1}个孔位资源类型「{rtype}」不合法")
                continue
            if rtype != lay_way:
                errors.append(f"{code}/{hole} 是{rtype}资源，与敷设方式「{lay_way}」不一致")
            key = hole_key(rtype, code, hole)
            if key in seen:
                errors.append(f"{code}/{hole} 在同一段光缆里重复登记")
                continue
            seen.add(key)
            if code not in known:
                errors.append(f"资源「{code}」未在管道/杆路资源册中登记，请先补资源")
            holes.append({"资源类型": rtype, "资源编号": code, "孔位": hole})
        return holes, errors

    def _active_conflicts(self, holes: list[dict[str, str]], *,
                          ignore_segment_id: int | None = None,
                          ignore_legacy: bool = False) -> list[dict[str, Any]]:
        """孔位互斥校验：返回所有活跃占用冲突；存量补登可豁免相互拦截。"""
        active = [r for r in store.rows(OCCUPANCY) if r["状态"] in ACTIVE_OCC_STATUSES]
        if ignore_legacy:
            active = [r for r in active if not r.get("历史遗留")]
        index: dict[str, dict[str, Any]] = {_occ_key(r): r for r in active}
        conflicts = []
        for hole in holes:
            owner = index.get(hole_key(hole["资源类型"], hole["资源编号"], hole["孔位"]))
            if owner and int(owner.get("光缆段id", 0)) != ignore_segment_id:
                conflicts.append({
                    "资源类型": hole["资源类型"], "资源编号": hole["资源编号"], "孔位": hole["孔位"],
                    "冲突光缆": owner["光缆段编号"], "冲突施工队": owner.get("施工队"),
                    "冲突占用状态": owner["状态"],
                })
        return conflicts

    def _capacity_conflicts(self, holes: list[dict[str, str]]) -> list[str]:
        resources = {str(r["资源编号"]): r for r in store.rows(RESOURCE)}
        grouped: dict[str, set[str]] = {}
        for hole in holes:
            grouped.setdefault(hole["资源编号"], set()).add(hole["孔位"])
        messages = []
        for code, new_holes in grouped.items():
            res = resources.get(code)
            if not res or res.get("容量") is None:
                continue
            occupied = {str(r["孔位"]) for r in store.rows(OCCUPANCY)
                        if str(r.get("资源编号")) == code and r["状态"] in ACTIVE_OCC_STATUSES}
            if len(occupied | new_holes) > int(res["容量"]):
                messages.append(
                    f"{res['资源名称']}（{code}）共 {res['容量']} 个孔位，已占 {len(occupied)} 个，再占 {len(new_holes)} 个将超容")
        return messages

    # ----------------------------- 写操作 -----------------------------
    def register_survey(self, values: dict[str, Any], operator: Operator) -> tuple[dict[str, Any] | None, str]:
        """登记光缆段（勘测入口）：一段缆按起点、终点、敷设方式与计划占用孔位登记，
        同起点/终点/敷设方式重复登记只记一次。"""
        if reason := operator.deny_reason("登记光缆段"):
            return None, reason
        start, end = _norm(values.get("起点")), _norm(values.get("终点"))
        lay_way = _norm(values.get("敷设方式"))
        missing = [name for name, val in (("起点", start), ("终点", end), ("敷设方式", lay_way)) if not val]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        if lay_way not in RESOURCE_TYPES:
            return None, f"敷设方式只支持「{LAY_WAY_PIPE}」「{LAY_WAY_POLE}」"
        holes, errors = self._validate_holes(values, lay_way)
        if errors:
            return None, "；".join(errors)

        segments = store.rows(MODULE)
        duplicated = next((r for r in segments
                           if _norm(r.get("起点")) == start and _norm(r.get("终点")) == end
                           and _norm(r.get("敷设方式")) == lay_way), None)
        if duplicated:
            return None, (f"{start}→{end} 的{lay_way}光缆段已登记（编号 {duplicated['光缆段编号']}，"
                          f"状态{duplicated['status']}），同一段重复登记只记一次")

        with store.lock:
            segment = {
                "id": _next_id(segments),
                "光缆段编号": _norm(values.get("光缆段编号")) or f"CAB-2026-{_next_id(segments):03d}",
                "起点": start, "终点": end, "敷设方式": lay_way,
                "光缆型号": _norm(values.get("光缆型号")) or "—",
                "芯数": int(values.get("芯数") or 0),
                "计划孔位": holes,
                "team_id": operator.team_id, "施工队": operator.team_name,
                "status": "勘测", "pending": True, "abnormal": False, "历史遗留": False,
            }
            segments.append(segment)
        return self.get_segment(int(segment["id"])), "光缆段已登记，当前状态：勘测；下一步分配孔位"

    def allocate_with_holes(self, segment_id: int, values: dict[str, Any],
                            operator: Operator) -> tuple[dict[str, Any] | None, str]:
        if reason := operator.deny_reason("分配孔位"):
            return None, reason
        segment = store.find(MODULE, segment_id)
        if segment is None:
            return None, f"光缆段 {segment_id} 不存在"
        if not operator.owns(segment):
            return None, f"光缆段 {segment['光缆段编号']} 属于{segment['施工队']}，跨队只能查看，不能分配孔位"
        if segment["status"] != "勘测":
            return None, f"当前状态为「{segment['status']}」，只有勘测中的光缆段能分配孔位"
        lay_way = str(segment["敷设方式"])
        # 分配时可重提孔位序列覆盖勘测口径；没提就用登记时的计划序列。
        if "孔位序列" not in values:
            values = dict(values)
            values["孔位序列"] = segment.get("计划孔位") or []
        holes, errors = self._validate_holes(values, lay_way)
        if errors:
            return None, "；".join(errors)
        if not holes:
            return None, "该光缆段勘测时没有计划孔位，无法分配，请在分配时提交孔位序列"

        with store.lock:
            conflicts = self._active_conflicts(holes, ignore_segment_id=segment_id)
            if conflicts:
                lines = [f"{c['资源编号']}/{c['孔位']} 已被 {c['冲突光缆']}（{c['冲突施工队']}，{c['冲突占用状态']}）占用"
                         for c in conflicts]
                return None, "孔位冲突，挡下未分配：" + "；".join(lines) + "。需先由原占用方资料员核销释放后再占"
            cap_errors = self._capacity_conflicts(holes)
            if cap_errors:
                return None, "容量不足，挡下未分配：" + "；".join(cap_errors)

            occ_rows = store.rows(OCCUPANCY)
            for idx, hole in enumerate(holes):
                occ_rows.append({
                    "id": _next_id(occ_rows), "光缆段id": segment_id,
                    "光缆段编号": segment["光缆段编号"],
                    "资源类型": hole["资源类型"], "资源编号": hole["资源编号"], "孔位": hole["孔位"],
                    "顺序": idx, "状态": OCC_ALLOCATED, "历史遗留": False,
                    "team_id": operator.team_id, "施工队": operator.team_name, "释放备注": None,
                })
            segment["status"] = "已分配"
        return self.get_segment(segment_id), f"已按敷设顺序预占 {len(holes)} 个孔位，可开始敷设核销"

    def write_off_laying(self, segment_id: int, values: dict[str, Any],
                         operator: Operator) -> tuple[dict[str, Any] | None, str]:
        """敷设核销：从断点开始按序扣减；已核销的跳过不重复扣，不许跳孔。"""
        if reason := operator.deny_reason("核销占用"):
            return None, reason
        segment = store.find(MODULE, segment_id)
        if segment is None:
            return None, f"光缆段 {segment_id} 不存在"
        if not operator.owns(segment):
            return None, f"光缆段 {segment['光缆段编号']} 属于{segment['施工队']}，跨队只能查看，不能核销"
        if segment["status"] not in ("已分配", "已敷设"):
            return None, (f"当前状态为「{segment['status']}」；没勘测、没分配的光缆段不许直接登记敷设，"
                          "请先完成勘测与孔位分配")

        submitted = values.get("孔位") or []
        if isinstance(submitted, str):
            submitted = [submitted]
        if not isinstance(submitted, list) or not submitted:
            return None, "请提交本次要核销的孔位（资源编号/孔位，或只写孔位）"

        occ_rows = self._occupancy_of(segment_id)
        by_hole = {str(r["孔位"]): r for r in occ_rows}
        by_key = {_occ_key(r): r for r in occ_rows}
        targets: list[dict[str, Any]] = []
        for item in submitted:
            if isinstance(item, dict):
                resource_code, hole = _norm(item.get("资源编号")), _norm(item.get("孔位"))
            else:
                resource_code, hole = "", _norm(item)
            if not hole:
                return None, "核销孔位名称不能为空"
            row = by_key.get(hole_key(segment["敷设方式"], resource_code, hole)) if resource_code else by_hole.get(hole)
            if row is None:
                return None, f"孔位「{resource_code + '/' if resource_code else ''}{hole}」不在该光缆段的敷设序列里"
            targets.append(row)

        pending = [r for r in occ_rows if r["状态"] == OCC_ALLOCATED]
        already_written = [r for r in targets if r["状态"] == OCC_WRITTEN_OFF]
        fresh = [r for r in targets if r["状态"] == OCC_ALLOCATED]
        if not fresh:
            return self.get_segment(segment_id), "提交的孔位此前都已核销，不再重复扣减，台账无变化"

        order_expected = sorted(int(r["顺序"]) for r in pending)
        order_fresh = sorted(int(r["顺序"]) for r in fresh)
        cont = order_expected[:len(order_fresh)]
        if order_fresh != cont:
            broken = next(r for r in pending if int(r["顺序"]) == order_expected[0])
            jumped = next(r for r in fresh if int(r["顺序"]) not in cont)
            return None, (f"敷设此前中断在 {broken['资源编号']}/{broken['孔位']}，"
                          f"必须从该断点接着核销，不能跳过它先核销 {jumped['资源编号']}/{jumped['孔位']}")

        with store.lock:
            for row in fresh:
                row["状态"] = OCC_WRITTEN_OFF
            remaining = [r for r in occ_rows if r["状态"] == OCC_ALLOCATED]
            if not remaining:
                segment["status"] = "已敷设"
                segment["pending"] = True
        message = f"本次核销 {len(fresh)} 个孔位"
        if already_written:
            message += f"；另有 {len(already_written)} 个此前已核销，未重复扣"
        remaining = [r for r in occ_rows if r["状态"] == OCC_ALLOCATED]
        if remaining:
            message += f"；敷设仍中断在 {remaining[0]['资源编号']}/{remaining[0]['孔位']}"
        else:
            message += "；全段敷设完成，待核实"
        return self.get_segment(segment_id), message

    def verify(self, segment_id: int, operator: Operator) -> tuple[dict[str, Any] | None, str]:
        """已敷设 → 已核实。"""
        if reason := operator.deny_reason("核实光缆段"):
            return None, reason
        segment = store.find(MODULE, segment_id)
        if segment is None:
            return None, f"光缆段 {segment_id} 不存在"
        if not operator.owns(segment):
            return None, f"光缆段 {segment['光缆段编号']} 属于{segment['施工队']}，跨队只能查看"
        if segment["status"] != "已敷设":
            return None, f"当前状态为「{segment['status']}」，只有已敷设的光缆段能核实"
        with store.lock:
            segment["status"] = "已核实"
            segment["pending"] = False
        return self.get_segment(segment_id), "光缆段已核实，占用台账锁定"

    def release_occupancy(self, segment_id: int, values: dict[str, Any],
                          operator: Operator) -> tuple[dict[str, Any] | None, str]:
        """撤占核销：把原占用释放出来，别的光缆才能占同一个孔。"""
        if reason := operator.deny_reason("核销释放占用"):
            return None, reason
        segment = store.find(MODULE, segment_id)
        if segment is None:
            return None, f"光缆段 {segment_id} 不存在"
        if not operator.owns(segment):
            return None, f"光缆段 {segment['光缆段编号']} 属于{segment['施工队']}，跨队只能查看，不能释放其占用"
        holes = values.get("孔位") or []
        if isinstance(holes, str):
            holes = [holes]
        if not holes:
            return None, "请指明要释放的孔位"
        occ_rows = self._occupancy_of(segment_id)
        by_hole = {str(r["孔位"]): r for r in occ_rows}
        remark = _norm(values.get("remark")) or "撤占核销"
        released = 0
        with store.lock:
            for item in holes:
                resource_code = _norm(item.get("资源编号")) if isinstance(item, dict) else ""
                hole = _norm(item.get("孔位")) if isinstance(item, dict) else _norm(item)
                row = next((r for r in occ_rows if str(r["孔位"]) == hole
                            and (not resource_code or str(r["资源编号"]) == resource_code)), None)
                if row is None:
                    return None, f"孔位「{hole}」不在光缆段 {segment['光缆段编号']} 的占用序列里"
                if row["状态"] == OCC_RELEASED:
                    continue
                row["状态"] = OCC_RELEASED
                row["释放备注"] = f"{remark}（{operator.team_name}·{operator.role}）"
                released += 1
        return self.get_segment(segment_id), f"已释放 {released} 个孔位，可被其他光缆段占用"

    def import_legacy(self, values: dict[str, Any], operator: Operator) -> tuple[dict[str, Any] | None, str]:
        """存量光缆补登：按敷设顺序整段写入，占用全部标记历史遗留并保留原登记口径。"""
        if reason := operator.deny_reason("补登存量光缆"):
            return None, reason
        cables = values.get("光缆段") or []
        if not isinstance(cables, list) or not cables:
            return None, "请按光缆段列表补登"

        imported: list[dict[str, Any]] = []
        with store.lock:
            segments = store.rows(MODULE)
            occ_rows = store.rows(OCCUPANCY)
            resources = store.rows(RESOURCE)
            known_codes = {str(r["资源编号"]) for r in resources}
            for cable in cables:
                start, end = _norm(cable.get("起点")), _norm(cable.get("终点"))
                lay_way = _norm(cable.get("敷设方式"))
                if not start or not end or lay_way not in RESOURCE_TYPES:
                    return None, f"存量记录「{_norm(cable.get('光缆段编号')) or '未编号'}」起点/终点/敷设方式不全，已整批挡下"
                raw_holes = cable.get("孔位序列") or []
                if not raw_holes:
                    return None, f"存量光缆 {start}→{end} 没有占用孔位，无法补登，已整批挡下"
                holes: list[dict[str, str]] = []
                seen: set[str] = set()
                for idx, item in enumerate(raw_holes):
                    code, hole = _norm(item.get("资源编号")), _norm(item.get("孔位"))
                    rtype = _norm(item.get("资源类型")) or lay_way
                    if not code or not hole:
                        return None, f"存量光缆 {start}→{end} 第{idx + 1}个孔位信息不全，已整批挡下"
                    key = hole_key(rtype, code, hole)
                    if key in seen:
                        return None, f"存量光缆 {start}→{end} 孔位 {code}/{hole} 自相重复，已整批挡下"
                    seen.add(key)
                    holes.append({"资源类型": rtype, "资源编号": code, "孔位": hole})
                team_name = _norm(cable.get("施工队")) or operator.team_name

                segment = {
                    "id": _next_id(segments),
                    "光缆段编号": _norm(cable.get("光缆段编号")) or f"CAB-LG-{_next_id(segments):03d}",
                    "起点": start, "终点": end, "敷设方式": lay_way,
                    "光缆型号": _norm(cable.get("光缆型号")) or "—",
                    "芯数": int(cable.get("芯数") or 0),
                    "team_id": operator.team_id, "施工队": team_name,
                    "status": "已核实", "pending": False, "abnormal": False, "历史遗留": True,
                }
                segments.append(segment)
                for idx, hole in enumerate(holes):
                    # 资源册缺项时按当时登记补一条占位资源，容量未知，不丢历史。
                    if hole["资源编号"] not in known_codes:
                        resources.append({
                            "id": _next_id(resources), "资源类型": hole["资源类型"],
                            "资源编号": hole["资源编号"], "资源名称": f"存量补录{hole['资源编号']}",
                            "容量": None, "team_id": operator.team_id, "施工队": team_name,
                        })
                        known_codes.add(hole["资源编号"])
                    occ_rows.append({
                        "id": _next_id(occ_rows), "光缆段id": segment["id"],
                        "光缆段编号": segment["光缆段编号"],
                        "资源类型": hole["资源类型"], "资源编号": hole["资源编号"], "孔位": hole["孔位"],
                        "顺序": idx, "状态": OCC_WRITTEN_OFF, "历史遗留": True,
                        "team_id": operator.team_id, "施工队": team_name, "释放备注": None,
                    })
                imported.append(self._decorate(segment))
        return {"imported": imported}, f"存量补登完成，共 {len(imported)} 段；历史占用按原登记保留"

    def upsert_resource(self, values: dict[str, Any], operator: Operator) -> tuple[dict[str, Any] | None, str]:
        """维护管道/杆路资源册（容量是算剩余孔位的依据）。"""
        if reason := operator.deny_reason("维护资源册"):
            return None, reason
        rtype, code, name = _norm(values.get("资源类型")), _norm(values.get("资源编号")), _norm(values.get("资源名称"))
        if rtype not in RESOURCE_TYPES or not code:
            return None, "资源类型（管道/杆路）与资源编号必填"
        capacity = values.get("容量")
        try:
            capacity = int(capacity) if capacity not in (None, "") else None
        except (TypeError, ValueError):
            return None, "容量必须是整数孔位数"
        with store.lock:
            rows = store.rows(RESOURCE)
            row = next((r for r in rows if str(r["资源编号"]) == code and r["资源类型"] == rtype), None)
            if row:
                row["资源名称"] = name or row["资源名称"]
                if capacity is not None:
                    row["容量"] = capacity
            else:
                row = {
                    "id": _next_id(rows), "资源类型": rtype, "资源编号": code,
                    "资源名称": name or code, "容量": capacity,
                    "team_id": operator.team_id, "施工队": operator.team_name,
                }
                rows.append(row)
        return dict(row), "资源册已更新"
