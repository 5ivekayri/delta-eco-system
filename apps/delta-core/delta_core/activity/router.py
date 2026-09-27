from datetime import datetime

from fastapi import APIRouter, Query, Request
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from delta_contracts.storage import serialize
from delta_core.activity.models import ActivityEvent

router = APIRouter(prefix='/api/v1/activity')


@router.get('')
def activity(request: Request, limit: int = Query(30, ge=1, le=100),
             event_type: str | None = Query(None, max_length=64),
             before_time: datetime | None = None,
             before_id: str | None = Query(None, max_length=36),
             include_heartbeats: bool = False):
    query = select(ActivityEvent)
    if event_type:
        query = query.where(ActivityEvent.event_type == event_type)
    elif not include_heartbeats:
        query = query.where(ActivityEvent.event_type != 'HEARTBEAT')
    if before_time is not None:
        query = query.where(or_(ActivityEvent.created_at < before_time,
            and_(ActivityEvent.created_at == before_time, ActivityEvent.id < (before_id or ''))))
    query = query.order_by(ActivityEvent.created_at.desc(), ActivityEvent.id.desc()).limit(limit + 1)
    with Session(request.app.state.engine) as session:
        rows = list(session.scalars(query))
        items = [serialize(row) for row in rows[:limit]]
    last = items[-1] if len(rows) > limit else None
    return {'items': items, 'next_cursor': {'before_time': last['created_at'], 'before_id': last['id']} if last else None}
