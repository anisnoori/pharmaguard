"""Professional reporting and export services for PharmaGuard AI.

This module keeps report assembly outside Streamlit pages. The view layer only
renders the output, while this service prepares normalized data frames, KPI
summaries, and portable export payloads.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import date, datetime
from io import BytesIO
from typing import Any

import pandas as pd

from config import INTERACTION_SEVERITY_LABELS, RISK_LABELS
from database.repositories import ReportRepository
from utils.persian import fa_number, percent_fa


@dataclass(frozen=True)
class ReportFilter:
    """Date filter selected by the report user."""

    start_date: date | None
    end_date: date | None
    report_scope: str = "executive"


@dataclass(frozen=True)
class ReportBundle:
    """Complete prepared report data for rendering and export."""

    filters: ReportFilter
    generated_at: datetime
    kpis: dict[str, int | float]
    inventory_frame: pd.DataFrame
    prediction_frame: pd.DataFrame
    interaction_frame: pd.DataFrame
    import_frame: pd.DataFrame
    activity_frame: pd.DataFrame


class ReportService:
    """Build executive and operational reports from repository data."""

    @staticmethod
    def build(filters: ReportFilter) -> ReportBundle:
        """Return a complete report bundle for the selected date range."""

        start = filters.start_date.isoformat() if filters.start_date else None
        end = filters.end_date.isoformat() if filters.end_date else None
        inventory_rows = ReportRepository.inventory_rows()
        prediction_rows = ReportRepository.prediction_rows(start, end)
        interaction_rows = ReportRepository.interaction_rows()
        import_rows = ReportRepository.import_batch_rows(start, end)
        activity_rows = ReportRepository.activity_rows(start, end)

        return ReportBundle(
            filters=filters,
            generated_at=datetime.now(),
            kpis=ReportService._build_kpis(
                inventory_rows=inventory_rows,
                prediction_rows=prediction_rows,
                interaction_rows=interaction_rows,
                import_rows=import_rows,
            ),
            inventory_frame=ReportService._inventory_frame(inventory_rows),
            prediction_frame=ReportService._prediction_frame(prediction_rows),
            interaction_frame=ReportService._interaction_frame(interaction_rows),
            import_frame=ReportService._import_frame(import_rows),
            activity_frame=ReportService._activity_frame(activity_rows),
        )

    @staticmethod
    def _build_kpis(
        inventory_rows: list[dict[str, Any]],
        prediction_rows: list[dict[str, Any]],
        interaction_rows: list[dict[str, Any]],
        import_rows: list[dict[str, Any]],
    ) -> dict[str, int | float]:
        """Calculate report KPIs from raw rows."""

        total_drugs = len(inventory_rows)
        low_stock = sum(1 for row in inventory_rows if row["stock_status"] in {"critical", "low"})
        expired = sum(1 for row in inventory_rows if row["expiration_status"] == "expired")
        expiring_soon = sum(1 for row in inventory_rows if row["expiration_status"] == "soon")
        critical_predictions = sum(1 for row in prediction_rows if row["risk_level"] == "critical")
        high_predictions = sum(1 for row in prediction_rows if row["risk_level"] == "high")
        serious_interactions = sum(
            1 for row in interaction_rows if row["severity"] in {"contraindicated", "high"}
        )
        imported_rows = sum(int(row["inserted_rows"] or 0) + int(row["updated_rows"] or 0) for row in import_rows)
        invalid_import_rows = sum(int(row["invalid_rows"] or 0) for row in import_rows)
        total_import_rows = sum(int(row["total_rows"] or 0) for row in import_rows)
        import_quality = 1.0
        if total_import_rows > 0:
            import_quality = max(0.0, 1 - (invalid_import_rows / total_import_rows))

        return {
            "total_drugs": total_drugs,
            "low_stock": low_stock,
            "expired": expired,
            "expiring_soon": expiring_soon,
            "critical_predictions": critical_predictions,
            "high_predictions": high_predictions,
            "serious_interactions": serious_interactions,
            "imported_rows": imported_rows,
            "import_quality": import_quality,
        }

    @staticmethod
    def _inventory_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
        """Create a Persian inventory report frame."""

        records = []
        for row in rows:
            records.append(
                {
                    "شناسه": int(row["id"]),
                    "نام دارو": row["name"],
                    "نام ژنریک": row["generic_name"] or "—",
                    "دسته‌بندی": row["category_name"] or "بدون دسته",
                    "تأمین‌کننده": row["supplier_name"] or "بدون تأمین‌کننده",
                    "تولیدکننده": row["manufacturer"] or "—",
                    "شماره بچ": row["batch_number"] or "—",
                    "تاریخ انقضا": row["expiration_date"] or "ثبت‌نشده",
                    "واحد": row["unit"] or "عدد",
                    "موجودی فعلی": int(row["current_stock"] or 0),
                    "حداقل مجاز": int(row["minimum_stock"] or 0),
                    "مصرف ماهانه": int(row["monthly_consumption"] or 0),
                    "کسری تا حداقل": int(row["stock_gap"] or 0),
                    "نسبت موجودی": float(row["stock_ratio"] or 0),
                    "وضعیت موجودی": ReportService._stock_status_label(row["stock_status"]),
                    "وضعیت انقضا": ReportService._expiration_status_label(row["expiration_status"]),
                    "دسترسی بازار": float(row["availability_score"] or 0),
                    "زمان تأمین": int(row["lead_time_days"] or 0),
                }
            )
        return pd.DataFrame(records)

    @staticmethod
    def _prediction_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
        """Create a Persian prediction-history report frame."""

        records = []
        for row in rows:
            records.append(
                {
                    "شناسه": int(row["id"]),
                    "نام دارو": row["drug_name"],
                    "ریسک": RISK_LABELS.get(row["risk_level"], row["risk_level"]),
                    "risk_level_raw": row["risk_level"],
                    "احتمال": float(row["probability"] or 0),
                    "اعتماد": float(row["confidence"] or 0),
                    "عوامل اصلی": row["top_factors"] or "—",
                    "اقدام پیشنهادی": row["suggested_action"] or row["recommendation"] or "—",
                    "برنامه پایش": row["monitoring_plan"] or "—",
                    "نسخه مدل": row["model_version"] or "—",
                    "زمان ثبت": row["created_at"],
                }
            )
        return pd.DataFrame(records)

    @staticmethod
    def _interaction_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
        """Create a Persian interaction knowledge-base report frame."""

        records = []
        for row in rows:
            records.append(
                {
                    "شناسه": int(row["id"]),
                    "داروی اول": row["primary_drug"],
                    "داروی دوم": row["secondary_drug"],
                    "شدت": INTERACTION_SEVERITY_LABELS.get(row["severity"], row["severity"]),
                    "severity_raw": row["severity"],
                    "توضیح بالینی": row["description"],
                    "مکانیسم": row["mechanism"] or "—",
                    "توصیه بالینی": row["clinical_recommendation"],
                    "جایگزین/اقدام": row["alternative_drugs"] or "—",
                    "برنامه پایش": row["monitoring_plan"] or "—",
                    "سطح شواهد": row["evidence_level"] or "متوسط",
                    "مرجع": row["reference"] or "—",
                }
            )
        return pd.DataFrame(records)

    @staticmethod
    def _import_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
        """Create a Persian import-batch report frame."""

        records = []
        for row in rows:
            records.append(
                {
                    "شناسه": int(row["id"]),
                    "نام فایل": row["file_name"],
                    "کل ردیف‌ها": int(row["total_rows"] or 0),
                    "ردیف معتبر": int(row["valid_rows"] or 0),
                    "ردیف نامعتبر": int(row["invalid_rows"] or 0),
                    "تکراری": int(row["duplicate_rows"] or 0),
                    "ثبت‌شده": int(row["inserted_rows"] or 0),
                    "به‌روزرسانی‌شده": int(row["updated_rows"] or 0),
                    "ردشده": int(row["skipped_rows"] or 0),
                    "زمان ورود": row["created_at"],
                }
            )
        return pd.DataFrame(records)

    @staticmethod
    def _activity_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
        """Create a Persian activity-log report frame."""

        records = []
        for row in rows:
            records.append(
                {
                    "شناسه": int(row["id"]),
                    "کاربر": row["user_name"] or "سیستم",
                    "عملیات": row["action"],
                    "نوع موجودیت": row["entity_type"] or "—",
                    "شناسه موجودیت": row["entity_id"] or "—",
                    "جزئیات": row["details"] or "—",
                    "زمان": row["created_at"],
                }
            )
        return pd.DataFrame(records)

    @staticmethod
    def _stock_status_label(status: str) -> str:
        """Translate stock status code."""

        return {
            "critical": "بحرانی",
            "low": "کمبود نزدیک",
            "healthy": "مناسب",
            "overstock": "مازاد",
        }.get(status, "نامشخص")

    @staticmethod
    def _expiration_status_label(status: str) -> str:
        """Translate expiration status code."""

        return {
            "expired": "منقضی‌شده",
            "soon": "نزدیک به انقضا",
            "valid": "معتبر",
            "unknown": "نامشخص",
        }.get(status, "نامشخص")


class ReportExportService:
    """Create downloadable report payloads."""

    @staticmethod
    def csv_bytes(frame: pd.DataFrame) -> bytes:
        """Return a UTF-8 BOM CSV payload suitable for Excel."""

        return frame.to_csv(index=False).encode("utf-8-sig")

    @staticmethod
    def excel_bytes(bundle: ReportBundle) -> bytes | None:
        """Return a multi-sheet Excel workbook or None when the engine is missing."""

        output = BytesIO()
        try:
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                ReportExportService._summary_frame(bundle).to_excel(
                    writer,
                    sheet_name="خلاصه مدیریتی",
                    index=False,
                )
                ReportExportService._safe_sheet(bundle.inventory_frame).to_excel(
                    writer,
                    sheet_name="موجودی",
                    index=False,
                )
                ReportExportService._safe_sheet(bundle.prediction_frame).to_excel(
                    writer,
                    sheet_name="پیش‌بینی‌ها",
                    index=False,
                )
                ReportExportService._safe_sheet(bundle.interaction_frame).to_excel(
                    writer,
                    sheet_name="تداخل‌ها",
                    index=False,
                )
                ReportExportService._safe_sheet(bundle.import_frame).to_excel(
                    writer,
                    sheet_name="ورود داده",
                    index=False,
                )
                ReportExportService._safe_sheet(bundle.activity_frame).to_excel(
                    writer,
                    sheet_name="فعالیت‌ها",
                    index=False,
                )
        except ModuleNotFoundError:
            return None
        return output.getvalue()

    @staticmethod
    def html_report_bytes(bundle: ReportBundle) -> bytes:
        """Return a printable RTL HTML report that can be saved as PDF."""

        start = bundle.filters.start_date.isoformat() if bundle.filters.start_date else "همه"
        end = bundle.filters.end_date.isoformat() if bundle.filters.end_date else "همه"
        sections = [
            ("خلاصه مدیریتی", ReportExportService._summary_frame(bundle)),
            ("گزارش موجودی", bundle.inventory_frame),
            ("گزارش پیش‌بینی", bundle.prediction_frame.drop(columns=["risk_level_raw"], errors="ignore")),
            ("گزارش تداخل دارویی", bundle.interaction_frame.drop(columns=["severity_raw"], errors="ignore")),
            ("تاریخچه ورود داده", bundle.import_frame),
        ]
        body = "".join(ReportExportService._html_table(title, frame) for title, frame in sections)
        document = f"""
        <!doctype html>
        <html lang="fa" dir="rtl">
        <head>
          <meta charset="utf-8">
          <title>گزارش مدیریتی فارماگارد</title>
          <style>
            body {{ font-family: Tahoma, Arial, sans-serif; direction: rtl; color: #102a43; margin: 32px; }}
            h1, h2 {{ color: #102a43; }}
            .meta {{ background: #e7f5ff; border: 1px solid #b6dffd; border-radius: 16px; padding: 16px; margin-bottom: 24px; }}
            table {{ border-collapse: collapse; width: 100%; margin: 14px 0 28px; font-size: 12px; }}
            th, td {{ border: 1px solid #d8e2ec; padding: 8px; text-align: right; vertical-align: top; }}
            th {{ background: #f0f7ff; font-weight: 700; }}
            tr:nth-child(even) {{ background: #fbfdff; }}
            @media print {{ body {{ margin: 18mm; }} .page-break {{ page-break-before: always; }} }}
          </style>
        </head>
        <body>
          <h1>گزارش مدیریتی فارماگارد هوشمند</h1>
          <div class="meta">
            <strong>بازه گزارش:</strong> {html.escape(start)} تا {html.escape(end)}<br>
            <strong>زمان تولید:</strong> {html.escape(bundle.generated_at.strftime('%Y-%m-%d %H:%M'))}<br>
            <strong>روش استفاده:</strong> این فایل را در مرورگر باز کنید و از گزینه Print، خروجی PDF بگیرید.
          </div>
          {body}
        </body>
        </html>
        """
        return document.encode("utf-8")

    @staticmethod
    def _summary_frame(bundle: ReportBundle) -> pd.DataFrame:
        """Build a human-readable KPI summary frame."""

        return pd.DataFrame(
            [
                {"شاخص": "کل داروهای ثبت‌شده", "مقدار": fa_number(bundle.kpis["total_drugs"]), "توضیح": "اندازه فعلی موجودی سامانه"},
                {"شاخص": "داروهای نیازمند اقدام موجودی", "مقدار": fa_number(bundle.kpis["low_stock"]), "توضیح": "موجودی بحرانی یا نزدیک به کمبود"},
                {"شاخص": "داروهای منقضی‌شده", "مقدار": fa_number(bundle.kpis["expired"]), "توضیح": "باید از چرخه مصرف خارج شوند"},
                {"شاخص": "نزدیک به انقضا", "مقدار": fa_number(bundle.kpis["expiring_soon"]), "توضیح": "نیازمند مصرف/جابجایی سریع‌تر"},
                {"شاخص": "پیش‌بینی‌های بحرانی", "مقدار": fa_number(bundle.kpis["critical_predictions"]), "توضیح": "در بازه انتخاب‌شده"},
                {"شاخص": "قوانین تداخل جدی", "مقدار": fa_number(bundle.kpis["serious_interactions"]), "توضیح": "منع مصرف همزمان یا شدید"},
                {"شاخص": "ردیف‌های واردشده/به‌روزرسانی‌شده", "مقدار": fa_number(bundle.kpis["imported_rows"]), "توضیح": "از فایل‌های CSV/XLSX"},
                {"شاخص": "کیفیت ورود داده", "مقدار": percent_fa(float(bundle.kpis["import_quality"])), "توضیح": "بر اساس نسبت ردیف‌های معتبر"},
            ]
        )

    @staticmethod
    def _safe_sheet(frame: pd.DataFrame) -> pd.DataFrame:
        """Return a non-empty frame so Excel sheets are always useful."""

        if frame.empty:
            return pd.DataFrame([{"پیام": "داده‌ای برای این بخش وجود ندارد."}])
        return frame.drop(columns=["risk_level_raw", "severity_raw"], errors="ignore")

    @staticmethod
    def _html_table(title: str, frame: pd.DataFrame) -> str:
        """Render one escaped HTML table section."""

        if frame.empty:
            table = "<p>داده‌ای برای این بخش وجود ندارد.</p>"
        else:
            clean_frame = frame.drop(columns=["risk_level_raw", "severity_raw"], errors="ignore")
            table = clean_frame.to_html(index=False, escape=True, border=0)
        return f"<section><h2>{html.escape(title)}</h2>{table}</section>"
