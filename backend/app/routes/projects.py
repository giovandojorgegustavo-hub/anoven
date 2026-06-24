"""
Endpoints de projects + use_cases.

anoven-shared-projects: 
  - GET / ahora incluye proyectos donde el user es member (owned + member-of)
  - DELETE /{id}: guard adicional si tiene members (>1) → 409
  - GET /mine: nueva ruta que devuelve ProjectShareView (owned + member-of con role)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.project import (
    ProjectCreate,
    ProjectResponse,
    UseCaseCreate,
    UseCaseResponse,
)
from app.schemas.project_shared import ProjectShareView
from app.services.project_service import (
    CannotDeleteDefault,
    CannotDeleteWithConversations,
    ProjectNotFound,
    ProjectService,
    UseCaseNotFound,
)
from pydantic import BaseModel, Field


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)


class UseCaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)


router = APIRouter(prefix="/projects", tags=["projects"])


def _build_project_response(project, db: Session) -> ProjectResponse:
    """Project con sus use_cases nested."""
    service = ProjectService(db)
    use_cases = service.use_case_repo.list_for_project(project.id)
    return ProjectResponse(
        id=project.id,
        user_id=project.user_id,
        slug=project.slug,
        name=project.name,
        description=project.description,
        is_default=project.is_default,
        created_at=project.created_at,
        use_cases=[UseCaseResponse.model_validate(u) for u in use_cases],
    )


@router.get("/mine", response_model=list[ProjectShareView])
def list_my_projects(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Lista todos los proyectos del user: owned + proyectos donde es member.
    Devuelve ProjectShareView con role, members_count y mentors_count.
    Ordenados: owned primero (por created_at), luego member-of (por joined_at).
    """
    from app.repositories.project_member_repo import ProjectMemberRepository
    from app.repositories.project_mentor_repo import ProjectMentorRepository

    member_repo = ProjectMemberRepository(db)
    mentor_repo = ProjectMentorRepository(db)

    # Todos los proyectos donde el user tiene un row en project_members
    memberships = member_repo.list_for_user(current_user.id)

    result = []
    for membership in memberships:
        project = membership.project
        members_count = member_repo.count_for_project(project.id)
        mentors_count = len(mentor_repo.list_for_project(project.id))
        result.append(ProjectShareView(
            id=project.id,
            slug=project.slug,
            name=project.name,
            description=project.description,
            role=membership.role,
            members_count=members_count,
            mentors_count=mentors_count,
            created_at=project.created_at,
        ))

    # Ordenar: owner primero, luego member; dentro de cada grupo por created_at
    result.sort(key=lambda p: (0 if p.role == "owner" else 1, p.created_at))
    return result


@router.get("", response_model=list[ProjectResponse])
def list_projects(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lista todos los projects del user, default primero."""
    service = ProjectService(db)
    projects = service.list_for_user(current_user.id)
    return [_build_project_response(p, db) for p in projects]


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Crea un project nuevo + use_case default 'Charla libre'."""
    service = ProjectService(db)
    project = service.create_for_user(
        user_id=current_user.id,
        name=payload.name,
        description=payload.description,
    )
    return _build_project_response(project, db)


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ProjectService(db)
    try:
        project = service.get_for_user(project_id, current_user.id)
    except ProjectNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return _build_project_response(project, db)


@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: int,
    payload: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ProjectService(db)
    try:
        project = service.update_project(
            project_id=project_id,
            user_id=current_user.id,
            name=payload.name,
            description=payload.description,
        )
    except ProjectNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return _build_project_response(project, db)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Guard: si hay más de 1 member → 409 (owner + al menos 1 member)
    from app.repositories.project_member_repo import ProjectMemberRepository
    member_count = ProjectMemberRepository(db).count_for_project(project_id)
    if member_count > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Retira a todos los miembros antes de borrar el proyecto.",
        )

    service = ProjectService(db)
    try:
        service.delete_project(project_id, current_user.id)
    except ProjectNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (CannotDeleteDefault, CannotDeleteWithConversations) as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return None


@router.patch(
    "/{project_id}/use-cases/{use_case_id}",
    response_model=UseCaseResponse,
)
def update_use_case(
    project_id: int,
    use_case_id: int,
    payload: UseCaseUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ProjectService(db)
    try:
        uc = service.update_use_case(
            project_id=project_id,
            use_case_id=use_case_id,
            user_id=current_user.id,
            name=payload.name,
            description=payload.description,
        )
    except ProjectNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except UseCaseNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return UseCaseResponse.model_validate(uc)


@router.post(
    "/{project_id}/use-cases",
    response_model=UseCaseResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_use_case(
    project_id: int,
    payload: UseCaseCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ProjectService(db)
    try:
        uc = service.create_use_case_for_user(
            project_id=project_id,
            user_id=current_user.id,
            name=payload.name,
            description=payload.description,
        )
    except ProjectNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return UseCaseResponse.model_validate(uc)
