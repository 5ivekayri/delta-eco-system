from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Service-owned metadata; never import another service's models."""

