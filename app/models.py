from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Salle(Base):
    __tablename__ = "salles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)

    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    stations = relationship("Station", back_populates="salle")
    salle_offers = relationship("SalleOffer", back_populates="salle", cascade="all, delete-orphan")
    salle_users = relationship("SalleUser", back_populates="salle", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)

    # NULL autorisés chacun, mais CHECK impose au moins l'un des deux.
    email: Mapped[str | None] = mapped_column(String(256), unique=True, nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)

    avatar: Mapped[str | None] = mapped_column(String(512), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    user_roles = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")
    salle_users = relationship("SalleUser", back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("(email IS NOT NULL) OR (phone IS NOT NULL)", name="ck_users_email_or_phone"),
    )


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    key: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)  # ex: admin/manager
    name: Mapped[str] = mapped_column(String(64), nullable=False)

    user_roles = relationship("UserRole", back_populates="role", cascade="all, delete-orphan")
    role_permissions = relationship("RolePermission", back_populates="role", cascade="all, delete-orphan")


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(256), nullable=True)


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), primary_key=True)
    permission_id: Mapped[int] = mapped_column(ForeignKey("permissions.id"), primary_key=True)

    role = relationship("Role", back_populates="role_permissions")
    permission = relationship("Permission")


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), primary_key=True)

    user = relationship("User", back_populates="user_roles")
    role = relationship("Role", back_populates="user_roles")


class SalleUser(Base):
    __tablename__ = "salle_users"

    salle_id: Mapped[int] = mapped_column(ForeignKey("salles.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), primary_key=True)

    salle = relationship("Salle", back_populates="salle_users")
    user = relationship("User", back_populates="salle_users")
    role = relationship("Role")


class Station(Base):
    __tablename__ = "stations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # Une "salle" regroupe plusieurs stations (optionnel).
    salle_id: Mapped[Optional[int]] = mapped_column(ForeignKey("salles.id"), nullable=True, index=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    broadlink_ip: Mapped[str] = mapped_column(String(64), nullable=False)
    ir_code_hdmi1: Mapped[str] = mapped_column(Text, nullable=True)
    ir_code_hdmi2: Mapped[str] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    salle = relationship("Salle", back_populates="stations")
    station_offers = relationship("StationOffer", back_populates="station", cascade="all, delete-orphan")


class Offer(Base):
    __tablename__ = "offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    price_xof: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="paystack")
    station_id: Mapped[Optional[int]] = mapped_column(ForeignKey("stations.id"), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    station = relationship("Station")


class StationOffer(Base):
    __tablename__ = "station_offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id"), nullable=False, index=True)
    offer_id: Mapped[int] = mapped_column(ForeignKey("offers.id"), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        # Une offre ne peut pas être rattachée 2 fois à la même station.
        # (La contrainte exacte sera aussi créée dans la migration.)
    )

    station = relationship("Station", back_populates="station_offers")
    offer = relationship("Offer")


class SalleOffer(Base):
    __tablename__ = "salle_offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    salle_id: Mapped[int] = mapped_column(ForeignKey("salles.id"), nullable=False, index=True)
    offer_id: Mapped[int] = mapped_column(ForeignKey("offers.id"), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    salle = relationship("Salle", back_populates="salle_offers")
    offer = relationship("Offer")


class GameSession(Base):
    __tablename__ = "game_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id"), nullable=False)
    offer_id: Mapped[int] = mapped_column(ForeignKey("offers.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    payment_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    payment_reference: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    payment_status: Mapped[str] = mapped_column(String(32), default="pending")
    status: Mapped[str] = mapped_column(String(32), default="pending")
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    end_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    customer_email: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    customer_phone: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    station = relationship("Station")
    offer = relationship("Offer")
    user = relationship("User")


class EventLog(Base):
    __tablename__ = "event_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    level: Mapped[str] = mapped_column(String(16), default="info")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id"), nullable=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("game_sessions.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SessionExtension(Base):
    __tablename__ = "session_extensions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("game_sessions.id"), nullable=False, index=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    extra_minutes: Mapped[int] = mapped_column(Integer, nullable=False)

    payment_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    payment_reference: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    payment_status: Mapped[str] = mapped_column(String(32), default="pending")  # pending/paid/failed
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending/applied/failed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    customer_phone: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    session = relationship("GameSession")
    user = relationship("User")


class PaymentProviderConfig(Base):
    __tablename__ = "payment_provider_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    paystack_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    cinetpay_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
