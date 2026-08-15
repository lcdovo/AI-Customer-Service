import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.utils.database import get_db
from app.models.models import Ticket, TicketStatus, TicketPriority, User
from app.schemas.schemas import TicketCreate, TicketResponse, TicketUpdate, APIResponse

router = APIRouter(prefix="/api/v1/tickets", tags=["工单管理"])

SLA_HOURS = {
    TicketPriority.LOW: 48,
    TicketPriority.MEDIUM: 24,
    TicketPriority.HIGH: 12,
    TicketPriority.URGENT: 4,
}


@router.post("/", response_model=APIResponse)
async def create_ticket(
    ticket_data: TicketCreate,
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, ticket_data.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    ticket_id = str(uuid.uuid4())
    priority = TicketPriority(ticket_data.priority)
    sla_hours = SLA_HOURS.get(priority, 24)

    ticket = Ticket(
        id=ticket_id,
        user_id=ticket_data.user_id,
        category=ticket_data.category,
        status=TicketStatus.PENDING,
        priority=priority,
        content=ticket_data.content,
        sla_deadline=datetime.utcnow() + timedelta(hours=sla_hours),
    )
    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)

    return APIResponse(
        code=0,
        message="工单创建成功",
        data={
            "id": ticket.id,
            "user_id": ticket.user_id,
            "category": ticket.category,
            "status": ticket.status.value,
            "priority": ticket.priority.value,
            "sla_deadline": ticket.sla_deadline.isoformat() if ticket.sla_deadline else None,
        },
    )


@router.get("/", response_model=APIResponse)
async def list_tickets(
    user_id: Optional[int] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    category: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
):
    query = select(Ticket)
    if user_id:
        query = query.where(Ticket.user_id == user_id)
    if status:
        query = query.where(Ticket.status == TicketStatus(status))
    if priority:
        query = query.where(Ticket.priority == TicketPriority(priority))
    if category:
        query = query.where(Ticket.category == category)

    query = query.order_by(Ticket.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    tickets = result.scalars().all()

    return APIResponse(
        code=0,
        message="获取成功",
        data=[
            {
                "id": t.id,
                "user_id": t.user_id,
                "category": t.category,
                "status": t.status.value,
                "priority": t.priority.value,
                "content": t.content,
                "assigned_to": t.assigned_to,
                "sla_deadline": t.sla_deadline.isoformat() if t.sla_deadline else None,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "resolved_at": t.resolved_at.isoformat() if t.resolved_at else None,
            }
            for t in tickets
        ],
    )


@router.get("/{ticket_id}", response_model=APIResponse)
async def get_ticket(ticket_id: str, db: AsyncSession = Depends(get_db)):
    ticket = await db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="工单不存在")

    return APIResponse(
        code=0,
        message="获取成功",
        data={
            "id": ticket.id,
            "user_id": ticket.user_id,
            "category": ticket.category,
            "status": ticket.status.value,
            "priority": ticket.priority.value,
            "content": ticket.content,
            "assigned_to": ticket.assigned_to,
            "sla_deadline": ticket.sla_deadline.isoformat() if ticket.sla_deadline else None,
            "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
            "resolved_at": ticket.resolved_at.isoformat() if ticket.resolved_at else None,
        },
    )


@router.put("/{ticket_id}", response_model=APIResponse)
async def update_ticket(
    ticket_id: str,
    ticket_data: TicketUpdate,
    db: AsyncSession = Depends(get_db),
):
    ticket = await db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="工单不存在")

    update_data = ticket_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if hasattr(ticket, key) and value is not None:
            if key == "status":
                value = TicketStatus(value)
                if value == TicketStatus.RESOLVED or value == TicketStatus.CLOSED:
                    ticket.resolved_at = datetime.utcnow()
            elif key == "priority":
                value = TicketPriority(value)
            setattr(ticket, key, value)

    ticket.updated_at = datetime.utcnow()
    await db.commit()

    return APIResponse(code=0, message="更新成功", data={"id": ticket_id})


@router.post("/{ticket_id}/assign", response_model=APIResponse)
async def assign_ticket(
    ticket_id: str,
    assignee: str,
    db: AsyncSession = Depends(get_db),
):
    ticket = await db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="工单不存在")

    ticket.assigned_to = assignee
    ticket.status = TicketStatus.PROCESSING
    ticket.updated_at = datetime.utcnow()
    await db.commit()

    return APIResponse(code=0, message="分配成功", data={"id": ticket_id, "assigned_to": assignee})
