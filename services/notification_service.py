"""Notification generation and preference orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from database.repositories import (
    NotificationRepository,
    ReportRepository,
    UserPreferenceRepository,
)
from models.entities import NotificationRecord, UserPreferences


@dataclass(frozen=True)
class NotificationGenerationSummary:
    """Summary of generated operational notifications."""

    created_count: int
    skipped_duplicate_count: int
    evaluated_count: int


class NotificationService:
    """Build actionable healthcare notifications from platform data."""

    @staticmethod
    def get_preferences(user_id: int) -> UserPreferences:
        """Return persistent notification preferences for one user."""

        return UserPreferenceRepository.get(user_id)

    @staticmethod
    def update_preferences(user_id: int, values: dict[str, Any]) -> None:
        """Persist notification and theme preferences."""

        UserPreferenceRepository.update(user_id, values)

    @staticmethod
    def inbox(
        user_id: int,
        include_read: bool = True,
        severity: str = "all",
    ) -> list[NotificationRecord]:
        """Return notifications for the notification center."""

        return NotificationRepository.list_for_user(
            user_id=user_id,
            include_read=include_read,
            severity=severity,
            limit=80,
        )

    @staticmethod
    def unread_count(user_id: int) -> int:
        """Return unread notifications for navbar badges."""

        return NotificationRepository.unread_count(user_id)

    @staticmethod
    def generate_operational_alerts(user_id: int) -> NotificationGenerationSummary:
        """Generate alerts for stock, expiration, and prediction risks.

        The method is intentionally user-triggered to avoid creating duplicate
        notifications on every Streamlit rerun.
        """

        preferences = UserPreferenceRepository.get(user_id)
        if not preferences.notifications_enabled:
            return NotificationGenerationSummary(0, 0, 0)

        created = 0
        skipped = 0
        evaluated = 0
        for row in ReportRepository.inventory_rows():
            evaluated += 1
            result = NotificationService._alerts_for_inventory_row(row, preferences)
            for alert in result:
                source_type = str(alert["source_entity_type"])
                source_id = int(alert["source_entity_id"])
                alert_type = str(alert["notification_type"])
                if NotificationRepository.exists_unread_source(
                    user_id=user_id,
                    source_entity_type=source_type,
                    source_entity_id=source_id,
                    notification_type=alert_type,
                ):
                    skipped += 1
                    continue
                NotificationRepository.create(user_id=user_id, **alert)
                created += 1
        return NotificationGenerationSummary(created, skipped, evaluated)

    @staticmethod
    def _alerts_for_inventory_row(
        row: dict[str, Any],
        preferences: UserPreferences,
    ) -> list[dict[str, Any]]:
        """Convert a report inventory row to actionable alert payloads."""

        alerts: list[dict[str, Any]] = []
        drug_id = int(row["id"])
        drug_name = str(row["name"])
        stock_status = str(row.get("stock_status", "healthy"))
        expiration_status = str(row.get("expiration_status", "unknown"))
        stock_gap = int(row.get("stock_gap") or 0)
        current_stock = int(row.get("current_stock") or 0)
        minimum_stock = int(row.get("minimum_stock") or 0)

        if preferences.low_stock_alerts and stock_status in {"critical", "low"}:
            severity = "critical" if stock_status == "critical" else "warning"
            title = "هشدار موجودی بحرانی" if stock_status == "critical" else "هشدار کمبود موجودی"
            message = (
                f"موجودی {drug_name} برابر {current_stock} است و حداقل مجاز "
                f"{minimum_stock} ثبت شده. کسری فعلی: {stock_gap}."
            )
            alerts.append(
                {
                    "title": title,
                    "message": message,
                    "severity": severity,
                    "notification_type": "low_stock",
                    "source_entity_type": "drug",
                    "source_entity_id": drug_id,
                    "action_page": "drugs",
                }
            )

        if preferences.expiration_alerts and expiration_status in {"expired", "soon"}:
            severity = "critical" if expiration_status == "expired" else "warning"
            title = "داروی منقضی‌شده" if expiration_status == "expired" else "نزدیک به انقضا"
            expiration_date = str(row.get("expiration_date") or "ثبت نشده")
            alerts.append(
                {
                    "title": title,
                    "message": f"تاریخ انقضای {drug_name}: {expiration_date}. وضعیت باید بررسی شود.",
                    "severity": severity,
                    "notification_type": "expiration",
                    "source_entity_type": "drug",
                    "source_entity_id": drug_id,
                    "action_page": "reports",
                }
            )
        return alerts

    @staticmethod
    def mark_read(notification_id: int, user_id: int) -> None:
        """Mark one notification as read."""

        NotificationRepository.mark_read(notification_id, user_id)

    @staticmethod
    def mark_all_read(user_id: int) -> None:
        """Mark all notifications as read."""

        NotificationRepository.mark_all_read(user_id)

    @staticmethod
    def delete(notification_id: int, user_id: int) -> None:
        """Delete a personal notification or hide a global one."""

        NotificationRepository.delete(notification_id, user_id)
