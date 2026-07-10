"""User profile and account-security business logic."""

from __future__ import annotations

from database.repositories import ActivityLogRepository, UserRepository
from models.entities import UserProfile


class ProfileService:
    """Coordinate user profile updates and audit logging."""

    @staticmethod
    def get_profile(user_id: int) -> UserProfile | None:
        """Return current profile."""

        return UserRepository.get_profile(user_id)  # type: ignore[attr-defined]

    @staticmethod
    def update_identity(user_id: int, full_name: str, email: str) -> None:
        """Update full name and email with validation."""

        UserRepository.update_identity(user_id, full_name, email)  # type: ignore[attr-defined]
        ActivityLogRepository.log(
            user_id=user_id,
            action="profile_update",
            entity_type="user",
            entity_id=user_id,
            details="اطلاعات هویتی حساب کاربری به‌روزرسانی شد.",
        )

    @staticmethod
    def change_password(user_id: int, current_password: str, new_password: str) -> None:
        """Change password after current-password validation."""

        UserRepository.change_password(user_id, current_password, new_password)  # type: ignore[attr-defined]
        ActivityLogRepository.log(
            user_id=user_id,
            action="password_change",
            entity_type="user",
            entity_id=user_id,
            details="رمز عبور حساب کاربری تغییر کرد.",
        )
