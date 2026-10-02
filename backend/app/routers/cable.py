"""光缆段台账接口：光缆段登记、孔位分配/敷设核销、存量补登、占用与资源余量查询。

身份口径（请求头，缺省即本队资料员，方便直接联调）：
- X-Team-Id / X-Team-Name：当前操作人所属施工队；
- X-Role：资料员才能写，其他角色与其他队伍只能查看。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.cable import (
    DEFAULT_TEAM_ID,
    DEFAULT_TEAM_NAME,
    CableService,
    Operator,
)

router = APIRouter(prefix="/api/cable", tags=["光缆段台账"])

service = CableService()


def get_operator(
    x_team_id: str | None = Header(default=None),
    x_team_name: str | None = Header(default=None),
    x_role: str | None = Header(default=None),
) -> Operator:
    return Operator(
        team_id=(x_team_id or DEFAULT_TEAM_ID).strip(),
        team_name=(x_team_name or DEFAULT_TEAM_NAME).strip(),
        role=(x_role or "资料员").strip(),
    )


@router.get("/stats")
def stats() -> dict[str, int]:
    """台账看板：各阶段光缆段数量、活跃/待核销/历史孔位数量。"""
    return service.stats()


@router.get("/segments", response_model=PageResult[dict])
def list_segments(
    keyword: str | None = Query(default=None, description="按编号/起点/终点检索"),
    status: str | None = Query(default=None, description="勘测、已分配、已敷设、已核实"),
    lay_way: str | None = Query(default=None, description="管道、杆路"),
    legacy: bool | None = Query(default=None, description="是否仅看存量遗留"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """光缆段台账列表，支持按阶段、敷设方式与存量标记过滤。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条")
    items, total = service.list_segments(
        keyword=keyword, status=status, lay_way=lay_way, legacy=legacy, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/segments/{segment_id}")
def get_segment(segment_id: int) -> dict[str, Any]:
    """光缆段明细：带孔位序列、核销进度与断点。"""
    segment = service.get_segment(segment_id)
    if segment is None:
        raise HTTPException(status_code=404, detail=f"光缆段 {segment_id} 不存在")
    return segment


@router.get("/occupancy")
def list_occupancy(
    resource_code: str | None = None,
    status: str | None = Query(default=None, description="已分配、已核销、已释放"),
    keyword: str | None = None,
) -> dict[str, Any]:
    """占用核销台账：每一行是「某光缆段占用某资源某孔位」。"""
    items = service.list_occupancy(resource_code=resource_code, status=status, keyword=keyword)
    return {"total": len(items), "items": items}


@router.get("/resources")
def list_resources(resource_type: str | None = None) -> dict[str, Any]:
    """管道/杆路资源余量：容量减去活跃占用，得到还剩几个孔。"""
    items = service.list_resources(resource_type=resource_type)
    return {"total": len(items), "items": items}


@router.post("/segments", response_model=ActionResult)
def register_segment(payload: EntryPayload, operator: Operator = Depends(get_operator)) -> ActionResult:
    """登记光缆段（勘测入口）：同起点+终点+敷设方式重复登记只记一次。"""
    entry, message = service.register_survey(payload.values, operator)
    return ActionResult(ok=entry is not None, message=message, entry=entry)


@router.post("/segments/{segment_id}/allocate", response_model=ActionResult)
def allocate(segment_id: int, payload: EntryPayload,
             operator: Operator = Depends(get_operator)) -> ActionResult:
    """勘测 → 已分配：提交孔位序列并做互斥/容量校验，有冲突整单挡下。"""
    entry, message = service.allocate_with_holes(segment_id, payload.values, operator)
    return ActionResult(ok=entry is not None, message=message, entry=entry)


@router.post("/segments/{segment_id}/write-off", response_model=ActionResult)
def write_off_laying(segment_id: int, payload: EntryPayload,
                     operator: Operator = Depends(get_operator)) -> ActionResult:
    """敷设核销：从断点按序扣减孔位；已核销的不重复扣，跳孔会被挡下。"""
    entry, message = service.write_off_laying(segment_id, payload.values, operator)
    return ActionResult(ok=entry is not None, message=message, entry=entry)


@router.post("/segments/{segment_id}/verify", response_model=ActionResult)
def verify(segment_id: int, operator: Operator = Depends(get_operator)) -> ActionResult:
    """已敷设 → 已核实：状态机最后一步。"""
    entry, message = service.verify(segment_id, operator)
    return ActionResult(ok=entry is not None, message=message, entry=entry)


@router.post("/segments/{segment_id}/release", response_model=ActionResult)
def release(segment_id: int, payload: EntryPayload,
            operator: Operator = Depends(get_operator)) -> ActionResult:
    """撤占核销：释放原占用后，同一孔位才能被其他光缆段占用。"""
    entry, message = service.release_occupancy(segment_id, payload.values, operator)
    return ActionResult(ok=entry is not None, message=message, entry=entry)


@router.post("/legacy-import", response_model=ActionResult)
def legacy_import(payload: EntryPayload,
                  operator: Operator = Depends(get_operator)) -> ActionResult:
    """存量光缆按敷设顺序整段补登，历史占用按当时登记保留，不参与互斥拦截。"""
    entry, message = service.import_legacy(payload.values, operator)
    return ActionResult(ok=entry is not None, message=message, entry=entry)


@router.post("/resources", response_model=ActionResult)
def upsert_resource(payload: EntryPayload,
                    operator: Operator = Depends(get_operator)) -> ActionResult:
    """登记/更新管道或杆路资源及其孔位容量。"""
    entry, message = service.upsert_resource(payload.values, operator)
    return ActionResult(ok=entry is not None, message=message, entry=entry)
