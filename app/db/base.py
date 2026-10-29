from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for persisted domain models.

    Domain models and their constraints are introduced in the next data-model issue.
    """
