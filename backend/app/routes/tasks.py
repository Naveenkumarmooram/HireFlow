from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import current_user, recruiter_user
from app.models import (
    RecruiterTask,
    User,
)
from app.schemas import (
    RecruiterTaskInput,
    TaskUpdate,
    TaskView,
)
from app.services import get_candidate, record_audit

router = APIRouter(tags=["tasks"])


@router.get("/api/tasks", response_model=list[TaskView])
def list_tasks(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[TaskView]:
    query = select(RecruiterTask).where(RecruiterTask.organization_id == user.organization_id)
    if user.role == "interviewer":
        query = query.where(RecruiterTask.assigned_to_id == user.id)
    tasks = db.scalars(
        query.order_by(RecruiterTask.due_at.asc().nulls_last(), RecruiterTask.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return [
        TaskView(
            id=task.id,
            candidate_id=task.candidate_id,
            candidate_name=task.candidate.name if task.candidate else None,
            assigned_to_id=task.assigned_to_id,
            title=task.title,
            due_at=task.due_at,
            status=task.status,
            created_at=task.created_at,
        )
        for task in tasks
    ]


@router.post("/api/tasks", response_model=TaskView, status_code=status.HTTP_201_CREATED)
def create_task(
    data: RecruiterTaskInput,
    user: User = Depends(recruiter_user),
    db: Session = Depends(get_db),
) -> TaskView:
    candidate = (
        get_candidate(data.candidate_id, user.organization_id, db) if data.candidate_id else None
    )
    if (
        data.assigned_to_id
        and db.scalar(
            select(User.id).where(
                User.id == data.assigned_to_id,
                User.organization_id == user.organization_id,
                User.active.is_(True),
            )
        )
        is None
    ):
        raise HTTPException(status_code=404, detail="Assigned team member not found")
    task = RecruiterTask(
        organization_id=user.organization_id,
        candidate_id=candidate.id if candidate else None,
        **data.model_dump(exclude={"candidate_id"}),
    )
    db.add(task)
    db.flush()
    record_audit(db, user.organization_id, user.id, "task", task.id, "created")
    db.commit()
    db.refresh(task)
    return TaskView(
        id=task.id,
        candidate_id=task.candidate_id,
        candidate_name=candidate.name if candidate else None,
        assigned_to_id=task.assigned_to_id,
        title=task.title,
        due_at=task.due_at,
        status=task.status,
        created_at=task.created_at,
    )


@router.patch("/api/tasks/{task_id}", response_model=TaskView)
def update_task(
    task_id: str,
    data: TaskUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> TaskView:
    task = db.scalar(
        select(RecruiterTask).where(
            RecruiterTask.id == task_id,
            RecruiterTask.organization_id == user.organization_id,
        )
    )
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if user.role == "interviewer" and task.assigned_to_id != user.id:
        raise HTTPException(status_code=403, detail="Task is not assigned to you")
    task.status = data.status
    record_audit(
        db,
        user.organization_id,
        user.id,
        "task",
        task.id,
        "status_changed",
        {"status": task.status},
    )
    db.commit()
    db.refresh(task)
    return TaskView(
        id=task.id,
        candidate_id=task.candidate_id,
        candidate_name=task.candidate.name if task.candidate else None,
        assigned_to_id=task.assigned_to_id,
        title=task.title,
        due_at=task.due_at,
        status=task.status,
        created_at=task.created_at,
    )
