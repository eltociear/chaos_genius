"""Utility functions for RCA API endpoints."""
import logging
from datetime import date, datetime

from chaos_genius.controllers.kpi_controller import get_kpi_data_from_id
from chaos_genius.databases.models.rca_data_model import RcaData
from chaos_genius.utils.datetime_helper import get_epoch_timestamp, get_rca_timestamp

logger = logging.getLogger(__name__)


def kpi_aggregation(kpi_id, timeline="last_30_days"):
    """Get KPI aggregation data."""
    try:
        kpi_info = get_kpi_data_from_id(kpi_id)
        end_date = get_rca_output_end_date(kpi_info)

        data_point = (
            RcaData.query.filter(
                (RcaData.kpi_id == kpi_id)
                & (RcaData.data_type == "agg")
                & (RcaData.timeline == timeline)
                & (RcaData.end_date <= end_date)
            )
            .order_by(RcaData.created_at.desc())
            .first()
        )

        if data_point:
            final_data = data_point.data
            final_data["analysis_date"] = get_analysis_date(kpi_id, end_date)
        else:
            final_data = {
                "group1_value": 0,
                "group2_value": 0,
                "difference": 0,
                "perc_change": 0,
                "analysis_date": "",
            }
    except Exception as err:  # noqa: B902
        logger.error(f"Error in KPI aggregation retrieval: {err}", exc_info=1)
    return final_data


def kpi_line_data(kpi_id):
    """Get KPI line data."""
    final_data = []
    try:
        kpi_info = get_kpi_data_from_id(kpi_id)
        end_date = get_rca_output_end_date(kpi_info)

        data_point = (
            RcaData.query.filter(
                (RcaData.kpi_id == kpi_id)
                & (RcaData.data_type == "line")
                & (RcaData.end_date <= end_date)
            )
            .order_by(RcaData.created_at.desc())
            .first()
        )

        final_data = data_point.data if data_point else []
    except Exception as err:  # noqa: B902
        logger.error(f"Error in KPI Line data retrieval: {err}", exc_info=1)
    return final_data


def rca_analysis(kpi_id, timeline="last_30_days", dimension=None):
    """Get RCA analysis data."""
    try:
        kpi_info = get_kpi_data_from_id(kpi_id)
        end_date = get_rca_output_end_date(kpi_info)

        data_point = (
            RcaData.query.filter(
                (RcaData.kpi_id == kpi_id)
                & (RcaData.data_type == "rca")
                & (RcaData.timeline == timeline)
                & (RcaData.end_date <= end_date)
                & (RcaData.dimension == dimension)
            )
            .order_by(RcaData.created_at.desc())
            .first()
        )

        if data_point:
            final_data = data_point.data
            final_data["analysis_date"] = get_analysis_date(kpi_id, end_date)
        else:
            final_data = {
                "chart": {
                    "chart_data": [],
                    "y_axis_lim": [],
                    "chart_table": [],
                },
                "data_table": [],
                "analysis_date": "",
            }
    except Exception as err:  # noqa: B902
        logger.error(f"Error in RCA Analysis retrieval: {err}", exc_info=1)
    return final_data


def rca_hierarchical_data(kpi_id, timeline="last_30_days", dimension=None):
    """Get RCA hierarchical data."""
    try:
        kpi_info = get_kpi_data_from_id(kpi_id)
        end_date = get_rca_output_end_date(kpi_info)

        data_point = (
            RcaData.query.filter(
                (RcaData.kpi_id == kpi_id)
                & (RcaData.data_type == "htable")
                & (RcaData.timeline == timeline)
                & (RcaData.end_date <= end_date)
                & (RcaData.dimension == dimension)
            )
            .order_by(RcaData.created_at.desc())
            .first()
        )

        if data_point:
            final_data = data_point.data
            final_data["analysis_date"] = get_analysis_date(kpi_id, end_date)
        else:
            final_data = {"data_table": [], "analysis_date": ""}
    except Exception as err:  # noqa: B902
        logger.error(
            f"Error in RCA hierarchical table retrieval: {err}", exc_info=1
        )
    return final_data


def get_rca_output_end_date(kpi_info: dict) -> date:
    """Get RCA end date."""
    end_date = None

    if kpi_info["is_static"]:
        end_date = kpi_info["static_params"].get("end_date")

    if end_date is None:
        return datetime.today().date()
    else:
        return datetime.strptime(end_date, "%Y-%m-%d").date()


def get_analysis_date(kpi_id: int, end_date: date) -> int:
    """Get analysis date for RCA."""
    data_point = (
        RcaData.query.filter(
            (RcaData.kpi_id == kpi_id)
            & (RcaData.data_type == "line")
            & (RcaData.end_date <= end_date)
        )
        .order_by(RcaData.created_at.desc())
        .first()
    )
    final_data = data_point.data if data_point else []
    analysis_date = final_data[-1]["date"]
    analysis_timestamp = get_rca_timestamp(analysis_date)
    return get_epoch_timestamp(analysis_timestamp)