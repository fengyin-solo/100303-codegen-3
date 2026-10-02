"""光缆段占用台账接口。

身份约定：操作人施工队与角色通过请求头 X-Team / X-Role / X-Operator 传入；
缺省按「施工一队 资料员」处理，方便本地直接联调。别的队伍打开只能查看，
只有本施工队的资料员能核销占用。
"""
from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from fastapi import APIRouter, Header, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.cable import Identity, service

router = APIRouter(prefix="/api/cable", tags=["光缆段台账"])

DEFAULT_TEAM = "施工一队"
DEFAULT_ROLE = "资料员"


def _identity(
    team: str | None, role: str | None, operator: str | None
) -> Identity:
    # HTTP 头只允许 ASCII，前端把中文做百分号编码后放进头，这里还原
    def decode(value: str | None) -> str:
        if not value:
            return ""
        try:
            return unquote(value, encoding="utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return value

    return Identity(decode(team) or DEFAULT_TEAM, decode(role) or DEFAULT_ROLE, decode(operator))


@router.get("", response_model=PageResult[dict])
def list_cables(
    keyword: str | None = Query(default=None, description="按光缆编号、起点、终点检索"),
    status: str | None = Query(default=None, description="待勘测/已勘测/已分配/已敷设/已核实"),
    team: str | None = Query(default=None, description="按施工队筛选"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """光缆段列表，含每段的孔位进度与当前敷设断点。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_cables(keyword=keyword, status=status, team=team, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stats")
def stats() -> dict[str, Any]:
    """台账核销看板：各状态光缆数、管道剩余孔位、历史占用数。"""
    return service.stats()


@router.get("/resources")
def list_resources(
    kind: str = Query(default="管道", description="管道 或 杆路"),
    keyword: str | None = Query(default=None, description="按管道/杆路编码检索"),
) -> dict[str, Any]:
    """管道孔位占用与剩余孔数；杆路各杆加挂缆数。"""
    if kind not in ("管道", "杆路"):
        raise HTTPException(status_code=400, detail="资源类型只支持「管道」「杆路」")
    items = service.list_resources(kind, keyword=keyword)
    return {"kind": kind, "total": len(items), "items": items}


@router.get("/occupancies", response_model=PageResult[dict])
def list_occupancies(
    kind: str | None = Query(default=None, description="管道/杆路"),
    code: str | None = Query(default=None, description="管道或杆路编码"),
    cable: str | None = Query(default=None, description="光缆编号"),
    historical: bool | None = Query(default=None, description="是否只看历史占用"),
    page: int = 1,
    size: int = 50,
) -> PageResult[dict]:
    """占用核销台账：每条孔位/杆位的占用方、敷设与占用状态。"""
    if size > 500:
        raise HTTPException(status_code=400, detail="每页最多 500 条")
    items, total = service.list_occupancies(
        kind=kind, code=code, cable_code=cable, historical=historical, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出光缆段全量台账（含占用明细）。"""
    cables, total = service.list_cables(page=1, size=10000)
    occupancies, _ = service.list_occupancies(page=1, size=10000)
    return {"module": "cable", "total": total, "items": cables, "occupancies": occupancies}


@router.get("/{cable_id}", response_model=dict)
def get_cable(cable_id: int) -> dict[str, Any]:
    """单段光缆明细：基础信息 + 按敷设序号排列的占用明细。"""
    entry = service.get_cable(cable_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"光缆段 {cable_id} 不存在")
    return entry


@router.post("", response_model=ActionResult)
def create_cable(
    payload: EntryPayload,
    x_team: str | None = Header(default=None),
    x_role: str | None = Header(default=None),
    x_operator: str | None = Header(default=None),
) -> ActionResult:
    """登记光缆段（起点、终点、芯数）；同一起终点重复登记只记一次，从待勘测起步。"""
    who = _identity(x_team, x_role, x_operator)
    entry, message = service.create_cable(payload.values, who)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/legacy/backfill", response_model=ActionResult)
def backfill_legacy(
    payload: EntryPayload,
    x_team: str | None = Header(default=None),
    x_role: str | None = Header(default=None),
    x_operator: str | None = Header(default=None),
) -> ActionResult:
    """存量光缆补录：按敷设顺序补占用，直接落成已核实，占用按历史登记保留。"""
    who = _identity(x_team, x_role, x_operator)
    entry, message, created = service.backfill_legacy(payload.values, who)
    result = ActionResult(ok=entry is not None, message=message, entry=entry)
    return result


@router.post("/{cable_id}/actions", response_model=ActionResult)
def run_action(
    cable_id: int,
    payload: EntryPayload,
    x_team: str | None = Header(default=None),
    x_role: str | None = Header(default=None),
    x_operator: str | None = Header(default=None),
) -> ActionResult:
    """光缆段状态流转：完成勘测、分配孔位、敷设核销、提交核实。

    - values.action: 完成勘测 / 分配孔位 / 敷设核销 / 提交核实
    - 分配孔位时 values.slots = [{资源类型, 资源编码, 孔位}, ...]
    - 敷设核销时 values.seq 指定孔位序号，不传则从当前断点接着核销
    """
    who = _identity(x_team, x_role, x_operator)
    action = str(payload.values.get("action") or "").strip()
    values = payload.values

    if action == "完成勘测":
        entry, message = service.survey(cable_id, who)
    elif action == "分配孔位":
        entry, message = service.allocate(cable_id, values.get("slots") or [], who)
    elif action == "敷设核销":
        seq = values.get("seq")
        entry, message = service.write_off_laying(cable_id, int(seq) if seq not in (None, "") else None, who)
    elif action == "提交核实":
        entry, message = service.verify(cable_id, who)
    else:
        entry, message = None, f"动作「{action}」不属于光缆台账可执行范围"

    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/occupancies/{occ_id}/release", response_model=ActionResult)
def release_occupancy(
    occ_id: int,
    payload: EntryPayload,
    x_team: str | None = Header(default=None),
    x_role: str | None = Header(default=None),
    x_operator: str | None = Header(default=None),
) -> ActionResult:
    """核销（释放）一处占用：仅本施工队资料员可操作，历史占用不许核销。"""
    who = _identity(x_team, x_role, x_operator)
    reason = str(payload.values.get("reason") or payload.remark or "").strip()
    entry, message = service.release_occupancy(occ_id, who, reason)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
