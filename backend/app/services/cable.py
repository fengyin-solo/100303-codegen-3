"""光缆段占用台账业务规则。

口径说明：
- 一段光缆按「起点 + 终点」登记，同一段（起终点互换视为同一段）重复登记只记一次。
- 管道孔位互斥：同一管道的同一个孔位，占用中只允许挂一条光缆；冲突时拦下并说明
  与哪条光缆冲突，必须由原占用方本队资料员核销占用后才能再占。杆路杆位支持多缆加挂，
  不做互斥。
- 光缆段状态只能沿 待勘测 → 已勘测 → 已分配 → 已敷设 → 已核实 单向推进，没勘测
  不许直接登记敷设。
- 敷设按「序号」逐孔核销：已核销的孔位不重复扣；敷设中断后从中断孔位接着核销。
- 存量光缆按敷设顺序补录，直接落成「已核实」，其占用标记为历史占用，按当时登记的
  一份保留，不允许再改或核销。
- 只有本施工队的资料员能核销占用（敷设核销、释放占用）；别的队伍只能查看。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

CABLE = "cable"
DUCT = "duct"
POLE = "poleroute"
OCC = "cable_occupancy"

REQUIRED_FIELDS = ["光缆编号", "起点", "终点", "芯数"]
STATUS_ORDER = ["待勘测", "已勘测", "已分配", "已敷设", "已核实"]
# 管道孔位的占用状态
ST_ALLOCATED = "已分配"
ST_LAID = "已敷设"
ST_RELEASED = "已核销"
OCC_ACTIVE = "占用中"


class Identity:
    """当前操作人：施工队 + 角色。别的队伍打开只能看，本队只有资料员能核销。"""

    def __init__(self, team: str, role: str, name: str) -> None:
        self.team = team.strip()
        self.role = role.strip()
        self.name = name.strip() or (self.role or "操作员")

    @property
    def is_clerk(self) -> bool:
        return self.role == "资料员"

    def label(self) -> str:
        return f"{self.team}·{self.name}（{self.role or '未注明角色'}）"


class CableService:
    # ---------- 查询 ----------
    def list_cables(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        team: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(CABLE)
        if keyword:
            rows = [
                row
                for row in rows
                if keyword in str(row.get("光缆编号", ""))
                or keyword in str(row.get("起点", ""))
                or keyword in str(row.get("终点", ""))
            ]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if team:
            rows = [row for row in rows if row.get("施工队") == team]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self._with_progress(dict(row)) for row in rows[start:start + size]], total

    def get_cable(self, cable_id: int) -> dict[str, Any] | None:
        row = store.find(CABLE, cable_id)
        if row is None:
            return None
        detail = self._with_progress(dict(row))
        detail["占用明细"] = [
            dict(o) for o in sorted(
                (o for o in store.rows(OCC) if int(o.get("cable_id", 0)) == cable_id),
                key=lambda o: int(o.get("序号", 0)),
            )
        ]
        return detail

    def list_resources(
        self,
        kind: str,
        *,
        keyword: str | None = None,
    ) -> list[dict[str, Any]]:
        """管道/杆路清单，并算出每段还剩几个孔（杆位按加挂缆数统计）。"""
        table = DUCT if kind == "管道" else POLE
        code_field = "管道编号" if kind == "管道" else "杆路编号"
        pos_field = "孔位列表" if kind == "管道" else "杆位列表"
        result: list[dict[str, Any]] = []
        for row in store.rows(table):
            if keyword and keyword not in str(row.get(code_field, "")):
                continue
            item = dict(row)
            positions: list[str] = list(row.get(pos_field, []))
            holes = []
            for pos in positions:
                holder = self._holder(kind, str(row[code_field]), pos)
                holes.append({
                    "孔位": pos,
                    "占用中": holder is not None,
                    "占用光缆": holder.get("光缆编号") if holder else "",
                    "历史": bool(holder and holder.get("历史")),
                })
            if kind == "管道":
                item["剩余孔数"] = sum(1 for h in holes if not h["占用中"])
                item["占用孔数"] = sum(1 for h in holes if h["占用中"])
            else:
                cables_on_poles = {
                    pos: len(self._active_by_position(kind, str(row[code_field]), pos))
                    for pos in positions
                }
                item["各杆加挂缆数"] = cables_on_poles
            item["孔位状态"] = holes
            result.append(item)
        return result

    def list_occupancies(
        self,
        *,
        kind: str | None = None,
        code: str | None = None,
        cable_code: str | None = None,
        historical: bool | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(OCC)
        if kind:
            rows = [row for row in rows if row.get("资源类型") == kind]
        if code:
            rows = [row for row in rows if code in str(row.get("资源编码", ""))]
        if cable_code:
            rows = [row for row in rows if cable_code in str(row.get("光缆编号", ""))]
        if historical is not None:
            rows = [row for row in rows if bool(row.get("历史")) == historical]
        rows = sorted(
            rows,
            key=lambda r: (str(r.get("资源编码", "")), str(r.get("孔位", ""))),
        )
        total = len(rows)
        start = max(page - 1, 0) * size
        return [dict(row) for row in rows[start:start + size]], total

    def stats(self) -> dict[str, Any]:
        cables = store.rows(CABLE)
        occ = store.rows(OCC)
        ducts = self.list_resources("管道")
        return {
            "光缆段总数": len(cables),
            "待勘测": sum(1 for c in cables if c.get("status") == "待勘测"),
            "敷设中断": sum(1 for c in cables if c.get("status") == "已敷设"),
            "已核实": sum(1 for c in cables if c.get("status") == "已核实"),
            "占用记录": len([o for o in occ if o.get("占用状态") == OCC_ACTIVE]),
            "管道剩余孔位": sum(int(d.get("剩余孔数", 0)) for d in ducts),
            "历史占用": sum(1 for o in occ if o.get("历史")),
        }

    # ---------- 登记 ----------
    def create_cable(self, values: dict[str, Any], who: Identity) -> tuple[dict[str, Any] | None, str]:
        missing = [f for f in REQUIRED_FIELDS if not str(values.get(f) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        start, end = str(values["起点"]).strip(), str(values["终点"]).strip()
        dup = self._find_section(start, end)
        if dup is not None:
            return None, (
                f"光缆段 {start}—{end} 已登记为 {dup.get('光缆编号')}"
                f"（状态：{dup.get('status')}），同一段只记一次，不重复登记"
            )
        rows = store.rows(CABLE)
        entry = {"id": max((int(r.get("id", 0)) for r in rows), default=0) + 1}
        entry.update({f: str(values[f]).strip() for f in REQUIRED_FIELDS})
        entry["施工队"] = str(values.get("施工队") or who.team).strip() or "未指派"
        entry["登记日期"] = str(values.get("登记日期") or date.today().isoformat())
        entry["敷设日期"] = ""
        entry["备注"] = str(values.get("备注") or "").strip()
        # 新登记一律从「待勘测」起步，不许直接登记成已敷设/已核实
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return self._with_progress(entry), f"光缆段 {entry['光缆编号']} 已登记，当前状态：待勘测，请先发起勘测"

    def backfill_legacy(
        self, values: dict[str, Any], who: Identity
    ) -> tuple[dict[str, Any] | None, str, list[dict[str, Any]]]:
        """存量光缆补录：按敷设顺序补杆路与管道孔位，直接落成已核实 + 历史占用。"""
        if not who.team:
            return None, "未识别到施工队身份，存量补录请以本队资料员身份操作", []
        missing = [f for f in REQUIRED_FIELDS if not str(values.get(f) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}", []
        start, end = str(values["起点"]).strip(), str(values["终点"]).strip()
        dup = self._find_section(start, end)
        if dup is not None:
            return None, f"光缆段 {start}—{end} 已登记为 {dup.get('光缆编号')}，同一段只记一次，存量补录不重复登记", []
        slots = values.get("slots") or []
        if not isinstance(slots, list) or not slots:
            return None, "存量补录必须按敷设顺序提供占用的杆路/管道孔位", []

        created: list[dict[str, Any]] = []
        conflicts: list[str] = []
        for seq, slot in enumerate(slots, start=1):
            kind = str(slot.get("资源类型") or "").strip()
            code = str(slot.get("资源编码") or "").strip()
            pos = str(slot.get("孔位") or "").strip()
            problem = self._validate_slot(kind, code, pos)
            if problem:
                conflicts.append(f"第{seq}处 {code or '?'} {pos or '?'}：{problem}")
                continue
            # 存量补录同样遵守一孔一缆：被占则跳过并说明，历史台账保持一致
            holder = self._holder(kind, code, pos)
            if holder is not None:
                conflicts.append(
                    f"第{seq}处 {kind} {code} {pos}：已被光缆 {holder.get('光缆编号')} 占用，"
                    "孔位冲突，未补录该处"
                )
                continue
            created.append({
                "资源类型": kind, "资源编码": code, "孔位": pos, "序号": seq,
                "_valid": True,
            })
        # 冲突的孔位不计入序号断档：落库时按实际成功处重新编号，保证敷设顺序连续
        if not created:
            return None, "存量补录未成功：所有孔位均未通过校验（" + "；".join(conflicts) + "）", []

        rows = store.rows(CABLE)
        cable = {"id": max((int(r.get("id", 0)) for r in rows), default=0) + 1}
        cable.update({f: str(values[f]).strip() for f in REQUIRED_FIELDS})
        cable["施工队"] = str(values.get("施工队") or who.team).strip()
        lay_date = str(values.get("敷设日期") or values.get("登记日期") or "").strip()
        cable["登记日期"] = str(values.get("登记日期") or lay_date or date.today().isoformat())
        cable["敷设日期"] = lay_date
        cable["备注"] = str(values.get("备注") or "存量补录，历史占用按当时登记保留").strip()
        cable["status"] = "已核实"
        cable["pending"] = False
        cable["abnormal"] = False
        rows.append(cable)

        occ_rows = store.rows(OCC)
        next_id = max((int(o.get("id", 0)) for o in occ_rows), default=0) + 1
        for new_seq, item in enumerate(created, start=1):
            occ_rows.append({
                "id": next_id,
                "cable_id": cable["id"],
                "光缆编号": cable["光缆编号"],
                "施工队": cable["施工队"],
                "序号": new_seq,
                "资源类型": item["资源类型"],
                "资源编码": item["资源编码"],
                "孔位": item["孔位"],
                "敷设状态": ST_LAID,
                "占用状态": OCC_ACTIVE,
                "历史": True,
                "敷设日期": lay_date,
                "敷设核销人": "历史补录",
                "敷设核销时间": lay_date or date.today().isoformat(),
            })
            next_id += 1
        message = f"存量光缆 {cable['光缆编号']} 已补录 {len(created)} 处占用，落成「已核实」"
        if conflicts:
            message += "；以下孔位因冲突未补录：" + "；".join(conflicts)
        return self._with_progress(cable), message, created

    # ---------- 状态流转 ----------
    def survey(self, cable_id: int, who: Identity) -> tuple[dict[str, Any] | None, str]:
        cable, denied = self._load_for_team(cable_id, who)
        if denied:
            return None, denied
        if cable["status"] != "待勘测":
            return None, f"光缆 {cable['光缆编号']} 已完成勘测（当前：{cable['status']}），无需重复勘测"
        cable["status"] = "已勘测"
        return self._with_progress(cable), f"光缆 {cable['光缆编号']} 勘测完成，可分配管道孔位/杆路杆位"

    def allocate(
        self, cable_id: int, slots: list[dict[str, Any]], who: Identity
    ) -> tuple[dict[str, Any] | None, str]:
        cable, denied = self._load_for_team(cable_id, who)
        if denied:
            return None, denied
        if cable["status"] not in ("已勘测", "已分配"):
            return None, (
                f"光缆 {cable['光缆编号']} 当前为「{cable['status']}」，"
                "须先完成勘测才能分配孔位，未勘测不许直接登记敷设"
            )
        if not isinstance(slots, list) or not slots:
            return None, "未提供要分配的孔位（管道/杆路 + 编码 + 孔位）"

        occ_rows = store.rows(OCC)
        existing = [o for o in occ_rows if int(o.get("cable_id", 0)) == cable_id and o.get("占用状态") == OCC_ACTIVE]
        existing_keys = {(str(o.get("资源类型")), str(o.get("资源编码")), str(o.get("孔位"))) for o in existing}

        prepared: list[tuple[str, str, str]] = []
        seen_this_request: set[tuple[str, str, str]] = set()
        problems: list[str] = []
        for idx, slot in enumerate(slots, start=1):
            kind = str(slot.get("资源类型") or "").strip()
            code = str(slot.get("资源编码") or "").strip()
            pos = str(slot.get("孔位") or "").strip()
            problem = self._validate_slot(kind, code, pos)
            if problem:
                problems.append(f"第{idx}处 {code or '?'} {pos or '?'}：{problem}")
                continue
            key = (kind, code, pos)
            if key in existing_keys or key in seen_this_request:
                # 本光缆已占的位置重复提交视为幂等跳过，不算冲突
                continue
            # 只有管道孔位互斥；杆路同一杆允许多条光缆加挂
            if kind == "管道":
                holder = self._holder(kind, code, pos)
                if holder is not None:
                    problems.append(
                        f"第{idx}处 管道 {code} {pos}：已被光缆 {holder.get('光缆编号')}"
                        f"（{holder.get('施工队')}）占用，必须先由该队资料员核销原占用后才能再占，"
                        "本次分配已整批拦下"
                    )
                    continue
            seen_this_request.add(key)
            prepared.append(key)

        # 分配是一份完整方案：任一处校验/冲突不过，整批不生效，改完重新提交
        if problems:
            return None, "孔位分配已拦下，未登记任何占用：" + "；".join(problems)
        if not prepared:
            return None, "提交的孔位均已在本光缆占用中，没有新增分配"

        next_seq = max((int(o.get("序号", 0)) for o in existing), default=0) + 1
        next_id = max((int(o.get("id", 0)) for o in occ_rows), default=0) + 1
        for kind, code, pos in prepared:
            occ_rows.append({
                "id": next_id,
                "cable_id": cable_id,
                "光缆编号": cable["光缆编号"],
                "施工队": cable["施工队"],
                "序号": next_seq,
                "资源类型": kind,
                "资源编码": code,
                "孔位": pos,
                "敷设状态": ST_ALLOCATED,
                "占用状态": OCC_ACTIVE,
                "历史": False,
                "敷设日期": "",
                "分配人": who.label(),
            })
            next_id += 1
            next_seq += 1
        cable["status"] = "已分配"
        message = f"光缆 {cable['光缆编号']} 已分配 {len(prepared)} 处孔位/杆位"
        if problems:
            message += "；冲突已拦下：" + "；".join(problems)
        return self._with_progress(cable), message

    def write_off_laying(
        self, cable_id: int, seq: int | None, who: Identity
    ) -> tuple[dict[str, Any] | None, str]:
        """敷设核销：从中断孔位接着核销；已核销的孔位不重复扣。仅本队资料员可操作。"""
        cable, denied = self._load_for_clerk(cable_id, who)
        if denied:
            return None, denied
        if cable["status"] not in ("已分配", "已敷设"):
            return None, (
                f"光缆 {cable['光缆编号']} 当前为「{cable['status']}」，"
                "孔位尚未分配，不能登记敷设核销"
            )
        active = sorted(
            (o for o in store.rows(OCC) if int(o.get("cable_id", 0)) == cable_id and o.get("占用状态") == OCC_ACTIVE),
            key=lambda o: int(o.get("序号", 0)),
        )
        pending = [o for o in active if o.get("敷设状态") == ST_ALLOCATED]
        if not pending:
            return None, f"光缆 {cable['光缆编号']} 所有孔位均已核销敷设，不重复扣"

        if seq is None:
            target = pending[0]  # 默认从断掉的那个孔位接着核销
        else:
            target = next((o for o in pending if int(o.get("序号", 0)) == seq), None)
            if target is None:
                already = next((o for o in active if int(o.get("序号", 0)) == seq), None)
                if already is not None and already.get("敷设状态") == ST_LAID:
                    nxt = pending[0]
                    return None, (
                        f"序号 {seq}（{already.get('资源编码')} {already.get('孔位')}）"
                        f"已于 {already.get('敷设核销时间', '此前')} 核销，不重复扣；"
                        f"请从断点序号 {nxt.get('序号')}（{nxt.get('资源编码')} {nxt.get('孔位')}）接着核销"
                    )
                return None, f"序号 {seq} 不在光缆 {cable['光缆编号']} 的占用登记里"

        # 从 target 起只核销一个孔位；前面的孔位必须已核销，避免跳孔敷设
        earlier = [o for o in active if int(o.get("序号", 0)) < int(target["序号"])]
        gap = next((o for o in earlier if o.get("敷设状态") == ST_ALLOCATED), None)
        if gap is not None:
            return None, (
                f"序号 {target['序号']}（{target.get('资源编码')} {target.get('孔位')}）之前还有"
                f"序号 {gap['序号']}（{gap.get('资源编码')} {gap.get('孔位')}）未核销，"
                "敷设须从中断孔位顺序往后，不许跳孔"
            )

        today = date.today().isoformat()
        target["敷设状态"] = ST_LAID
        target["敷设日期"] = today
        target["敷设核销人"] = who.label()
        target["敷设核销时间"] = today
        if not cable.get("敷设日期"):
            cable["敷设日期"] = today

        still_pending = [o for o in active if o.get("敷设状态") == ST_ALLOCATED]
        if still_pending:
            cable["status"] = "已敷设"
            nxt = still_pending[0]
            return self._with_progress(cable), (
                f"已核销序号 {target['序号']}（{target.get('资源编码')} {target.get('孔位')}）的敷设；"
                f"敷设中断在序号 {nxt['序号']}（{nxt.get('资源编码')} {nxt.get('孔位')}），下次从该孔位接着核销"
            )
        cable["status"] = "已敷设"
        return self._with_progress(cable), (
            f"序号 {target['序号']}（{target.get('资源编码')} {target.get('孔位')}）已核销，"
            f"光缆 {cable['光缆编号']} 全部孔位敷设完成，可提交核实"
        )

    def verify(self, cable_id: int, who: Identity) -> tuple[dict[str, Any] | None, str]:
        cable, denied = self._load_for_team(cable_id, who)
        if denied:
            return None, denied
        if cable["status"] != "已敷设":
            order_idx = STATUS_ORDER.index(cable["status"]) if cable["status"] in STATUS_ORDER else 0
            if order_idx > STATUS_ORDER.index("已敷设"):
                return None, f"光缆 {cable['光缆编号']} 已核实，无需重复操作"
            return None, f"光缆 {cable['光缆编号']} 当前为「{cable['status']}」，未完成敷设不能核实"
        active = [o for o in store.rows(OCC) if int(o.get("cable_id", 0)) == cable_id and o.get("占用状态") == OCC_ACTIVE]
        unlaid = [o for o in active if o.get("敷设状态") != ST_LAID]
        if unlaid:
            desc = "、".join(f"序号{o.get('序号')} {o.get('资源编码')} {o.get('孔位')}" for o in unlaid)
            return None, f"还有 {len(unlaid)} 处孔位未核销敷设（{desc}），核实已拦下"
        cable["status"] = "已核实"
        cable["pending"] = False
        return self._with_progress(cable), f"光缆 {cable['光缆编号']} 已核实，占用台账正式生效"

    def release_occupancy(
        self, occ_id: int, who: Identity, reason: str
    ) -> tuple[dict[str, Any] | None, str]:
        """核销（释放）一处占用：仅光缆所属施工队的资料员可操作，历史占用不许动。"""
        occ = store.find(OCC, occ_id)
        if occ is None:
            return None, f"占用记录 {occ_id} 不存在"
        if who.team != occ.get("施工队"):
            return None, (
                f"该占用属于 {occ.get('施工队')}，{who.team} 只能查看，"
                "核销占用须由本施工队资料员操作"
            )
        if not who.is_clerk:
            return None, f"只有 {who.team} 的资料员能核销占用，{who.name}（{who.role}）无权核销"
        if occ.get("历史"):
            return None, "该占用为存量光缆历史登记，按当时登记的一份保留，不允许核销或修改"
        if occ.get("占用状态") != OCC_ACTIVE:
            return None, f"该孔位占用此前已核销（{occ.get('释放时间', '')}），不重复核销"
        today = date.today().isoformat()
        occ["占用状态"] = ST_RELEASED
        occ["释放人"] = who.label()
        occ["释放时间"] = today
        occ["释放原因"] = reason or "现场拆除/改路"
        return dict(occ), (
            f"已核销 {occ.get('光缆编号')} 对 {occ.get('资源编码')} {occ.get('孔位')} 的占用，"
            "该孔位已释放，可重新分配给其他光缆"
        )

    # ---------- 内部工具 ----------
    def _load_for_team(self, cable_id: int, who: Identity) -> tuple[dict[str, Any] | None, str]:
        cable = store.find(CABLE, cable_id)
        if cable is None:
            return None, f"光缆段 {cable_id} 不存在"
        if who.team and who.team != cable.get("施工队"):
            return None, f"光缆 {cable.get('光缆编号')} 属于 {cable.get('施工队')}，{who.team} 打开只能查看"
        return cable, ""

    def _load_for_clerk(self, cable_id: int, who: Identity) -> tuple[dict[str, Any] | None, str]:
        cable, denied = self._load_for_team(cable_id, who)
        if denied:
            return None, denied
        if not who.is_clerk:
            return None, f"只有 {who.team} 的资料员能核销，{who.name}（{who.role}）请改用资料员身份"
        return cable, ""

    def _find_section(self, start: str, end: str) -> dict[str, Any] | None:
        """起终点互换视为同一段光缆，重复登记只记一次。"""
        for row in store.rows(CABLE):
            a, b = str(row.get("起点", "")).strip(), str(row.get("终点", "")).strip()
            if (a, b) == (start, end) or (a, b) == (end, start):
                return row
        return None

    def _validate_slot(self, kind: str, code: str, pos: str) -> str:
        if kind not in ("管道", "杆路"):
            return "资源类型必须是「管道」或「杆路」"
        table = DUCT if kind == "管道" else POLE
        code_field = "管道编号" if kind == "管道" else "杆路编号"
        pos_field = "孔位列表" if kind == "管道" else "杆位列表"
        row = next((r for r in store.rows(table) if str(r.get(code_field)) == code), None)
        if row is None:
            return f"{kind} {code} 不存在，请先核对资源编码"
        if pos not in [str(p) for p in row.get(pos_field, [])]:
            return f"{kind} {code} 没有 {pos}，可选：{'、'.join(str(p) for p in row.get(pos_field, []))}"
        return ""

    def _active_by_position(self, kind: str, code: str, pos: str) -> list[dict[str, Any]]:
        return [
            o
            for o in store.rows(OCC)
            if o.get("资源类型") == kind
            and str(o.get("资源编码")) == code
            and str(o.get("孔位")) == pos
            and o.get("占用状态") == OCC_ACTIVE
        ]

    def _holder(self, kind: str, code: str, pos: str) -> dict[str, Any] | None:
        """管道孔位当前占用方；杆路可能多缆加挂，取其中一条用于展示。"""
        holders = self._active_by_position(kind, code, pos)
        return holders[0] if holders else None

    def _with_progress(self, cable: dict[str, Any]) -> dict[str, Any]:
        active = [
            o
            for o in store.rows(OCC)
            if int(o.get("cable_id", 0)) == int(cable.get("id", 0))
            and o.get("占用状态") == OCC_ACTIVE
        ]
        laid = [o for o in active if o.get("敷设状态") == ST_LAID]
        cable["孔位总数"] = len(active)
        cable["已敷设孔位"] = len(laid)
        pending = sorted(
            (o for o in active if o.get("敷设状态") == ST_ALLOCATED),
            key=lambda o: int(o.get("序号", 0)),
        )
        if pending:
            nxt = pending[0]
            cable["当前断点"] = f"序号{nxt.get('序号')} {nxt.get('资源编码')} {nxt.get('孔位')}"
        else:
            cable["当前断点"] = ""
        return cable


service = CableService()
