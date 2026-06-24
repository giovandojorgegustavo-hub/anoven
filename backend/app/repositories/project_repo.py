"""
Repositories para Project y UseCase.
"""

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.project import Project, UseCase


class ProjectRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, project_id: int) -> Project | None:
        return self.db.get(Project, project_id)

    def get_default_for_user(self, user_id: int) -> Project | None:
        stmt = (
            select(Project)
            .where(Project.user_id == user_id)
            .where(Project.is_default == True)
        )
        return self.db.execute(stmt).scalars().first()

    def list_for_user(self, user_id: int) -> list[Project]:
        stmt = (
            select(Project)
            .where(Project.user_id == user_id)
            .order_by(Project.is_default.desc(), Project.created_at)
        )
        return list(self.db.execute(stmt).scalars().all())

    def create(
        self,
        user_id: int,
        slug: str,
        name: str,
        description: str | None = None,
        is_default: bool = False,
    ) -> Project:
        project = Project(
            user_id=user_id,
            slug=slug,
            name=name,
            description=description,
            is_default=is_default,
        )
        self.db.add(project)
        self.db.commit()
        self.db.refresh(project)
        return project

    def update(
        self,
        project: Project,
        name: str | None = None,
        description: str | None = None,
    ) -> Project:
        if name is not None:
            project.name = name
        if description is not None:
            project.description = description
        self.db.commit()
        self.db.refresh(project)
        return project

    def delete(self, project: Project) -> None:
        self.db.delete(project)
        self.db.commit()


class UseCaseRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, use_case_id: int) -> UseCase | None:
        return self.db.get(UseCase, use_case_id)

    def get_default_for_project(self, project_id: int) -> UseCase | None:
        stmt = (
            select(UseCase)
            .where(UseCase.project_id == project_id)
            .where(UseCase.is_default == True)
        )
        return self.db.execute(stmt).scalars().first()

    def list_for_project(self, project_id: int) -> list[UseCase]:
        stmt = (
            select(UseCase)
            .where(UseCase.project_id == project_id)
            .order_by(UseCase.is_default.desc(), UseCase.created_at)
        )
        return list(self.db.execute(stmt).scalars().all())

    def create(
        self,
        project_id: int,
        slug: str,
        name: str,
        description: str | None = None,
        is_default: bool = False,
    ) -> UseCase:
        uc = UseCase(
            project_id=project_id,
            slug=slug,
            name=name,
            description=description,
            is_default=is_default,
        )
        self.db.add(uc)
        self.db.commit()
        self.db.refresh(uc)
        return uc

    def update(
        self,
        uc: UseCase,
        name: str | None = None,
        description: str | None = None,
    ) -> UseCase:
        if name is not None:
            uc.name = name
        if description is not None:
            uc.description = description
        self.db.commit()
        self.db.refresh(uc)
        return uc
