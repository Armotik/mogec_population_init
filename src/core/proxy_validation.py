"""
Validation temporelle par proxys publics ou documentes.

Ce module ne cherche pas a "prouver" la verite terrain. Il fournit un cadre
reproductible pour confronter des courbes horaires simulees a des courbes de
reference externes ou semi-externes, documentees dans la configuration.
"""

from __future__ import annotations

import logging

import geopandas as gpd
import numpy as np
import pandas as pd

from src.core.temporal import build_member_timelines

logger = logging.getLogger(__name__)

MEMBER_STATE_SHARE_METRIC = "member_state_share"
MEMBER_STATE_COUNT_METRIC = "member_state_count"
ROLE_STATE_SHARE_METRIC = "role_state_share"
ROLE_STATE_COUNT_METRIC = "role_state_count"
ROLE_INTERNAL_STATE_SHARE_METRIC = "role_internal_assigned_state_share"
ROLE_INTERNAL_STATE_COUNT_METRIC = "role_internal_assigned_state_count"
BUILDING_USAGE_SHARE_METRIC = "building_usage_share"
BUILDING_USAGE_COUNT_METRIC = "building_usage_count"
SUPPORTED_PROXY_METRICS = {
    MEMBER_STATE_SHARE_METRIC,
    MEMBER_STATE_COUNT_METRIC,
    ROLE_STATE_SHARE_METRIC,
    ROLE_STATE_COUNT_METRIC,
    ROLE_INTERNAL_STATE_SHARE_METRIC,
    ROLE_INTERNAL_STATE_COUNT_METRIC,
    BUILDING_USAGE_SHARE_METRIC,
    BUILDING_USAGE_COUNT_METRIC,
}
MEMBER_STATE_METRICS = {MEMBER_STATE_SHARE_METRIC, MEMBER_STATE_COUNT_METRIC}
ROLE_STATE_METRICS = {ROLE_STATE_SHARE_METRIC, ROLE_STATE_COUNT_METRIC}
ROLE_INTERNAL_STATE_METRICS = {
    ROLE_INTERNAL_STATE_SHARE_METRIC,
    ROLE_INTERNAL_STATE_COUNT_METRIC,
}
BUILDING_USAGE_METRICS = {BUILDING_USAGE_SHARE_METRIC, BUILDING_USAGE_COUNT_METRIC}
SUPPORTED_STATES = {"domicile", "interne", "exterieur"}
SUMMARY_COLUMNS = [
    "scenario_name",
    "proxy_id",
    "label",
    "metric",
    "applicable",
    "status",
    "reason",
    "modeled_peak_hour",
    "reference_peak_hour",
    "peak_hour_gap",
    "correlation",
    "rmse",
    "mae",
    "comparison_normalization",
    "source_name",
    "extraction_date",
    "confidence",
]
CURVE_COLUMNS = [
    "scenario_name",
    "proxy_id",
    "label",
    "metric",
    "hour",
    "modeled_value",
    "reference_value",
    "modeled_compared",
    "reference_compared",
]


def _scenario_name(config: dict) -> str:
    return str(config.get("scenario", {}).get("name", "scenario"))


def _scenario_day_type(config: dict) -> str:
    day = str(config.get("scenario", {}).get("day_of_week", ""))
    weekend_days = set(config.get("temporal_model", {}).get("calendars", {}).get("weekend_days", ["Samedi", "Dimanche"]))
    if day == "Dimanche":
        return "sunday"
    if day in weekend_days:
        return "weekend"
    return "weekday"


def _scenario_season(config: dict) -> str:
    temporal_context = config.get("scenario", {}).get("temporal_context", {})
    default_context = config.get("temporal_model", {}).get("scenario_context", {})
    return str(temporal_context.get("season", default_context.get("season", "")))


def _coerce_reference_curve(reference_curve: object) -> np.ndarray:
    if isinstance(reference_curve, dict):
        values = [float(reference_curve[str(hour)]) if str(hour) in reference_curve else float(reference_curve[hour]) for hour in range(24)]
    elif isinstance(reference_curve, (list, tuple)):
        if len(reference_curve) != 24:
            raise ValueError("Une `reference_curve` doit contenir exactement 24 valeurs.")
        values = [float(value) for value in reference_curve]
    else:
        raise ValueError("Le champ `reference_curve` doit etre une liste de 24 valeurs ou un dictionnaire heure -> valeur.")
    return np.asarray(values, dtype=float)


def _normalize_for_comparison(values: np.ndarray, method: str) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    if method == "none":
        return values
    if method == "max":
        denominator = float(np.nanmax(np.abs(values))) if values.size else 0.0
    elif method == "sum":
        denominator = float(np.nansum(np.abs(values))) if values.size else 0.0
    else:
        raise ValueError(f"Normalisation inconnue: {method}")

    if denominator <= 0.0:
        return np.zeros_like(values, dtype=float)
    return values / denominator


def _status_min_threshold(value: float, pass_min: float, warn_min: float) -> str:
    if value >= pass_min:
        return "pass"
    if value >= warn_min:
        return "warn"
    return "fail"


def _status_max_threshold(value: float, pass_max: float, warn_max: float) -> str:
    if value <= pass_max:
        return "pass"
    if value <= warn_max:
        return "warn"
    return "fail"


def _combine_statuses(statuses: list[str]) -> str:
    if any(status == "fail" for status in statuses):
        return "fail"
    if any(status == "warn" for status in statuses):
        return "warn"
    return "pass"


def _correlation(modeled: np.ndarray, reference: np.ndarray) -> float:
    if modeled.size == 0 or reference.size == 0:
        return 0.0
    if np.allclose(modeled, modeled[0]) and np.allclose(reference, reference[0]):
        return 1.0 if np.allclose(modeled, reference) else 0.0
    if np.std(modeled) == 0.0 or np.std(reference) == 0.0:
        return 0.0
    return float(np.corrcoef(modeled, reference)[0, 1])


def _empty_summary() -> pd.DataFrame:
    return pd.DataFrame(columns=SUMMARY_COLUMNS)


def _empty_curves() -> pd.DataFrame:
    return pd.DataFrame(columns=CURVE_COLUMNS)


def _proxy_applicability(proxy_cfg: dict, config: dict) -> tuple[bool, str]:
    applicability = proxy_cfg.get("applicability", {})
    if not applicability:
        return True, "applicable"

    scenario_day_type = _scenario_day_type(config)
    allowed_day_types = applicability.get("day_types")
    if allowed_day_types and scenario_day_type not in set(allowed_day_types):
        return False, f"day_type_mismatch:{scenario_day_type}"

    allowed_holidays = applicability.get("school_holidays")
    if allowed_holidays is not None:
        is_school_holiday = bool(config.get("scenario", {}).get("is_school_holiday", False))
        normalized_allowed = {bool(value) for value in allowed_holidays}
        if is_school_holiday not in normalized_allowed:
            return False, f"school_holiday_mismatch:{is_school_holiday}"

    allowed_seasons = applicability.get("seasons")
    if allowed_seasons and _scenario_season(config) not in set(allowed_seasons):
        return False, f"season_mismatch:{_scenario_season(config)}"

    return True, "applicable"


def _state_series_for_subset(subset: pd.DataFrame, state: str, as_share: bool = True) -> np.ndarray:
    if subset.empty:
        return np.zeros(24, dtype=float)

    hourly_counts: list[float] = []
    denominator = float(len(subset))
    for hour in range(24):
        hour_count = int(subset["timeline_states"].str[hour].eq(state).sum())
        hourly_counts.append(hour_count / denominator if as_share and denominator > 0.0 else float(hour_count))
    return np.asarray(hourly_counts, dtype=float)


def _member_state_series(member_timelines: pd.DataFrame, state: str, role: str | None = None, as_share: bool = True) -> np.ndarray:
    if member_timelines.empty:
        return np.zeros(24, dtype=float)

    subset = member_timelines if role is None else member_timelines[member_timelines["role"] == role]
    return _state_series_for_subset(subset, state=state, as_share=as_share)


def _internally_assigned_members(
    member_timelines: pd.DataFrame,
    role: str,
) -> pd.DataFrame:
    if member_timelines.empty:
        return member_timelines.iloc[0:0].copy()

    subset = member_timelines[member_timelines["role"] == role].copy()
    return subset[~subset["assigned_destination_id"].isin(["DOMICILE", "EXTERIEUR", "None", None])]


def _role_internal_assigned_state_series(
    member_timelines: pd.DataFrame,
    role: str,
    state: str,
    as_share: bool = True,
) -> np.ndarray:
    subset = _internally_assigned_members(member_timelines, role)
    return _state_series_for_subset(subset, state=state, as_share=as_share)


def _building_usage_series(gdf: gpd.GeoDataFrame, usage_any_of: list[str], as_share: bool = True) -> np.ndarray:
    hourly_columns = [f"pop_h{hour}" for hour in range(24) if f"pop_h{hour}" in gdf.columns]
    if len(hourly_columns) != 24:
        return np.zeros(24, dtype=float)

    mask = gdf.get("usage_1", pd.Series(index=gdf.index, dtype=object)).isin(usage_any_of)
    selected = gdf.loc[mask, hourly_columns].fillna(0.0).sum(axis=0).to_numpy(dtype=float)
    if not as_share:
        return selected

    total = gdf[hourly_columns].fillna(0.0).sum(axis=0).to_numpy(dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        shares = np.divide(selected, total, out=np.zeros_like(selected, dtype=float), where=total > 0.0)
    return shares


def _modeled_series_for_proxy(gdf: gpd.GeoDataFrame, member_timelines: pd.DataFrame, proxy_cfg: dict) -> np.ndarray:
    metric = str(proxy_cfg["metric"])
    if metric == MEMBER_STATE_SHARE_METRIC:
        return _member_state_series(member_timelines, state=str(proxy_cfg["state"]), as_share=True)
    if metric == MEMBER_STATE_COUNT_METRIC:
        return _member_state_series(member_timelines, state=str(proxy_cfg["state"]), as_share=False)
    if metric == ROLE_STATE_SHARE_METRIC:
        return _member_state_series(
            member_timelines,
            state=str(proxy_cfg["state"]),
            role=str(proxy_cfg["role"]),
            as_share=True,
        )
    if metric == ROLE_STATE_COUNT_METRIC:
        return _member_state_series(
            member_timelines,
            state=str(proxy_cfg["state"]),
            role=str(proxy_cfg["role"]),
            as_share=False,
        )
    if metric == ROLE_INTERNAL_STATE_SHARE_METRIC:
        return _role_internal_assigned_state_series(
            member_timelines,
            role=str(proxy_cfg["role"]),
            state=str(proxy_cfg["state"]),
            as_share=True,
        )
    if metric == ROLE_INTERNAL_STATE_COUNT_METRIC:
        return _role_internal_assigned_state_series(
            member_timelines,
            role=str(proxy_cfg["role"]),
            state=str(proxy_cfg["state"]),
            as_share=False,
        )
    if metric == BUILDING_USAGE_SHARE_METRIC:
        return _building_usage_series(gdf, usage_any_of=list(proxy_cfg["usage_any_of"]), as_share=True)
    if metric == BUILDING_USAGE_COUNT_METRIC:
        return _building_usage_series(gdf, usage_any_of=list(proxy_cfg["usage_any_of"]), as_share=False)
    raise ValueError(f"Type de proxy non supporte: {metric}")


def _proxy_thresholds(proxy_cfg: dict) -> dict:
    thresholds = proxy_cfg.get("thresholds", {})
    return {
        "correlation_pass_min": float(thresholds.get("correlation_pass_min", 0.80)),
        "correlation_warn_min": float(thresholds.get("correlation_warn_min", 0.60)),
        "rmse_pass_max": float(thresholds.get("rmse_pass_max", 0.08)),
        "rmse_warn_max": float(thresholds.get("rmse_warn_max", 0.15)),
        "peak_gap_pass_max_hours": float(thresholds.get("peak_gap_pass_max_hours", 1.0)),
        "peak_gap_warn_max_hours": float(thresholds.get("peak_gap_warn_max_hours", 2.0)),
    }


def _not_applicable_summary_row(
    scenario_name: str,
    proxy_id: str,
    label: str,
    metric: str,
    comparison_normalization: str,
    evidence: dict,
    applicability_reason: str,
) -> dict:
    return {
        "scenario_name": scenario_name,
        "proxy_id": proxy_id,
        "label": label,
        "metric": metric,
        "applicable": False,
        "status": "info",
        "reason": applicability_reason,
        "modeled_peak_hour": None,
        "reference_peak_hour": None,
        "peak_hour_gap": None,
        "correlation": None,
        "rmse": None,
        "mae": None,
        "comparison_normalization": comparison_normalization,
        "source_name": evidence.get("source_name", "n/a"),
        "extraction_date": evidence.get("extraction_date", "n/a"),
        "confidence": evidence.get("confidence", "n/a"),
    }


def _comparison_metrics(modeled: np.ndarray, reference: np.ndarray) -> dict:
    correlation = _correlation(modeled, reference)
    rmse = float(np.sqrt(np.mean((modeled - reference) ** 2)))
    mae = float(np.mean(np.abs(modeled - reference)))
    modeled_peak_hour = int(np.argmax(modeled)) if modeled.size else None
    reference_peak_hour = int(np.argmax(reference)) if reference.size else None
    peak_hour_gap = abs(modeled_peak_hour - reference_peak_hour) if modeled_peak_hour is not None and reference_peak_hour is not None else None
    return {
        "correlation": correlation,
        "rmse": rmse,
        "mae": mae,
        "modeled_peak_hour": modeled_peak_hour,
        "reference_peak_hour": reference_peak_hour,
        "peak_hour_gap": peak_hour_gap,
    }


def _evaluated_summary_row(
    scenario_name: str,
    proxy_id: str,
    label: str,
    metric: str,
    comparison_normalization: str,
    evidence: dict,
    status: str,
    metrics: dict,
) -> dict:
    return {
        "scenario_name": scenario_name,
        "proxy_id": proxy_id,
        "label": label,
        "metric": metric,
        "applicable": True,
        "status": status,
        "reason": "evaluated",
        "modeled_peak_hour": metrics["modeled_peak_hour"],
        "reference_peak_hour": metrics["reference_peak_hour"],
        "peak_hour_gap": int(metrics["peak_hour_gap"]) if metrics["peak_hour_gap"] is not None else None,
        "correlation": round(metrics["correlation"], 4),
        "rmse": round(metrics["rmse"], 4),
        "mae": round(metrics["mae"], 4),
        "comparison_normalization": comparison_normalization,
        "source_name": evidence.get("source_name", "n/a"),
        "extraction_date": evidence.get("extraction_date", "n/a"),
        "confidence": evidence.get("confidence", "n/a"),
    }


def _curve_rows(
    scenario_name: str,
    proxy_id: str,
    label: str,
    metric: str,
    modeled: np.ndarray,
    reference: np.ndarray,
    modeled_compared: np.ndarray,
    reference_compared: np.ndarray,
) -> list[dict]:
    return [
        {
            "scenario_name": scenario_name,
            "proxy_id": proxy_id,
            "label": label,
            "metric": metric,
            "hour": hour,
            "modeled_value": float(modeled[hour]),
            "reference_value": float(reference[hour]),
            "modeled_compared": float(modeled_compared[hour]),
            "reference_compared": float(reference_compared[hour]),
        }
        for hour in range(24)
    ]


def _evaluate_proxy(gdf: gpd.GeoDataFrame, config: dict, member_timelines: pd.DataFrame, proxy_cfg: dict) -> tuple[dict, list[dict]]:
    scenario_name = _scenario_name(config)
    proxy_id = str(proxy_cfg["proxy_id"])
    label = str(proxy_cfg.get("label", proxy_id))
    metric = str(proxy_cfg["metric"])
    comparison_normalization = str(proxy_cfg.get("comparison_normalization", "max"))
    evidence = proxy_cfg.get("evidence", {})

    is_applicable, applicability_reason = _proxy_applicability(proxy_cfg, config)
    if not is_applicable:
        logger.info("Proxy %s ignore pour le scenario %s (%s).", proxy_id, scenario_name, applicability_reason)
        return (
            _not_applicable_summary_row(
                scenario_name,
                proxy_id,
                label,
                metric,
                comparison_normalization,
                evidence,
                applicability_reason,
            ),
            [],
        )

    modeled = _modeled_series_for_proxy(gdf, member_timelines, proxy_cfg)
    reference = _coerce_reference_curve(proxy_cfg["reference_curve"])
    modeled_compared = _normalize_for_comparison(modeled, comparison_normalization)
    reference_compared = _normalize_for_comparison(reference, comparison_normalization)

    metrics = _comparison_metrics(modeled_compared, reference_compared)

    thresholds = _proxy_thresholds(proxy_cfg)
    status = _combine_statuses(
        [
            _status_min_threshold(
                metrics["correlation"],
                pass_min=thresholds["correlation_pass_min"],
                warn_min=thresholds["correlation_warn_min"],
            ),
            _status_max_threshold(
                metrics["rmse"],
                pass_max=thresholds["rmse_pass_max"],
                warn_max=thresholds["rmse_warn_max"],
            ),
            _status_max_threshold(
                float(metrics["peak_hour_gap"] or 0.0),
                pass_max=thresholds["peak_gap_pass_max_hours"],
                warn_max=thresholds["peak_gap_warn_max_hours"],
            ),
        ]
    )

    summary_row = _evaluated_summary_row(
        scenario_name,
        proxy_id,
        label,
        metric,
        comparison_normalization,
        evidence,
        status,
        metrics,
    )
    curve_rows = _curve_rows(
        scenario_name,
        proxy_id,
        label,
        metric,
        modeled,
        reference,
        modeled_compared,
        reference_compared,
    )
    return summary_row, curve_rows


def evaluate_temporal_proxies(gdf: gpd.GeoDataFrame, config: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Evalue les proxys temporels definis dans `config.proxy_validation`.

    Returns
    -------
    tuple[pandas.DataFrame, pandas.DataFrame]
        1. Tableau de synthese par proxy.
        2. Tableau long heure par heure pour tracer les courbes.
    """
    proxy_cfg = config.get("proxy_validation", {})
    proxies = [proxy for proxy in proxy_cfg.get("temporal_proxies", []) if proxy.get("enabled", True)]
    if not proxies:
        logger.info("Aucun proxy temporel actif dans le scenario %s.", _scenario_name(config))
        return _empty_summary(), _empty_curves()

    needs_member_timelines = any(
        str(proxy.get("metric")) in MEMBER_STATE_METRICS | ROLE_STATE_METRICS | ROLE_INTERNAL_STATE_METRICS
        for proxy in proxies
    )
    member_timelines = build_member_timelines(gdf, config) if needs_member_timelines else pd.DataFrame()

    summary_rows: list[dict] = []
    curve_rows: list[dict] = []
    for proxy in proxies:
        summary_row, proxy_curve_rows = _evaluate_proxy(gdf, config, member_timelines, proxy)
        summary_rows.append(summary_row)
        curve_rows.extend(proxy_curve_rows)

    summary = pd.DataFrame(summary_rows, columns=SUMMARY_COLUMNS)
    curves = pd.DataFrame(curve_rows, columns=CURVE_COLUMNS)
    return summary, curves


def proxy_validation_report(gdf: gpd.GeoDataFrame, config: dict) -> pd.DataFrame:
    """
    Retourne uniquement le tableau de synthese des proxys temporels.
    """
    summary, _ = evaluate_temporal_proxies(gdf, config)
    return summary


def proxy_validation_curves(gdf: gpd.GeoDataFrame, config: dict) -> pd.DataFrame:
    """
    Retourne les courbes horaires modele vs reference, au format long.
    """
    _, curves = evaluate_temporal_proxies(gdf, config)
    return curves
