from __future__ import annotations

import importlib
import math

from modules.architecture import SiteParameters, build_analysis, haversine_km, walkability_score
from modules.gis import build_city_map, city_metrics, valid_places
from modules.massing import build_massing_options, select_massing_option
from modules.parametric_design import core_model, floor_plate_dimensions, generate_design_options
from modules.building_systems import circulation_model, system_summary, vertical_core_schedule
from modules.lateral_design import lateral_summary, lateral_system_options, wind_seismic_proxy
from modules.spatial_intelligence import catchment_counts, category_gaps, density_hotspots, spatial_report
from modules.trip import nearest_neighbor_order, two_opt_improve


def test_all_python_modules_import_without_side_effect_failure():
    import pathlib
    for path in sorted(pathlib.Path("modules").glob("*.py")):
        if path.name != "__init__.py":
            importlib.import_module(f"modules.{path.stem}")


def test_gis_filters_invalid_coordinates():
    places = [{"name": "Good", "latitude": 0.3, "longitude": 32.5}, {"name": "Bad", "latitude": 999, "longitude": 32.5}, {"name": "NaN", "latitude": math.nan, "longitude": 32.5}, "not-a-place"]
    assert [p["name"] for p in valid_places(places)] == ["Good"]


def test_city_metrics_and_map_are_resilient():
    places = [{"name": "A", "category": "Food", "favorite": True, "latitude": 0.3, "longitude": 32.5}, {"name": "B", "category": "Parks", "favorite": False, "latitude": 0.31, "longitude": 32.51}]
    metrics = city_metrics(places)
    assert metrics["places"] == 2 and metrics["favorites"] == 1 and metrics["categories"] == 2
    assert metrics["footprint_km2"] > 0
    assert build_city_map(places, show_heatmap=True, cluster_markers=False) is not None


def test_architecture_analysis_has_compatible_metrics_and_bounded_scores():
    analysis = build_analysis(SiteParameters(site_area_m2=2000, site_coverage_pct=40, floors=5), [])
    assert analysis["metrics"]["gross_floor_area_m2"] == 4000
    assert analysis["site_metrics"]["gross_floor_area_m2"] == 4000
    assert 0 <= analysis["urban_indicators"]["green_ratio"] <= 1
    assert 0 <= walkability_score([])["score"] <= 100
    assert haversine_km(0, 0, 0, 0) == 0
    assert analysis["recommendations"]


def test_massing_engine_produces_comparable_options():
    params = SiteParameters(site_area_m2=2000, site_coverage_pct=40, floors=4)
    options = build_massing_options(params)
    assert [o["option"] for o in options] == ["Compact", "Balanced", "Vertical"]
    assert all(o["footprint_m2"] > 0 and o["gfa_m2"] > 0 for o in options)
    assert select_massing_option(options, "vertical")["option"] == "Vertical"
    assert select_massing_option(options, "missing")["option"] == "Compact"


def test_parametric_design_is_bounded_and_geometric():
    dims = floor_plate_dimensions(1000, 1.5)
    assert dims["area_m2"] == 1000 and dims["width_m"] > 0 and dims["depth_m"] > 0
    core = core_model(1000, 12)
    assert core["core_area_m2"] == 120 and core["core_width_m"] > 0
    designs = generate_design_options(SiteParameters(site_area_m2=2000, site_coverage_pct=40, floors=4), "Balanced", 12, 1.4)
    assert len(designs) == 3
    assert all(0 <= d["design_score"] <= 100 for d in designs)


def test_building_systems_produce_safe_conceptual_outputs():
    vertical = vertical_core_schedule(4000, 4)
    assert vertical["floors"] == 4
    assert vertical["lifts"] >= 1 and vertical["stairs"] >= 1 and vertical["service_shafts"] >= 1
    circ = circulation_model(1000, 120, 12)
    assert circ["usable_program_area_m2"] > 0
    assert 0 < circ["usable_efficiency_pct"] < 100
    summary = system_summary(1000, 120, 4, 4000)
    assert "vertical" in summary and "circulation" in summary


def test_lateral_engine_is_bounded():
    options = lateral_system_options(120, 30, 20)
    assert len(options) == 4
    assert all(0 <= item["stability_score"] <= 100 for item in options)
    actions = wind_seismic_proxy(120, 30, 40, 0.2)
    assert actions["wind_pressure_kpa"] > 0 and actions["base_shear_proxy"] > 0
    result = lateral_summary(120, 30, 20, 40, 0.2, "Dual system")
    assert result["selected"]["system"] == "Dual system"


def test_spatial_intelligence_handles_empty_single_clustered_data():
    assert catchment_counts([], 400)["coverage_pct"] == 0.0
    assert spatial_report([])["dataset_places"] == 0
    assert density_hotspots([{"name": "Only", "latitude": 0.3, "longitude": 32.5}], 400)[0]["nearby_places"] == 0
    places = [{"name": "Food A", "category": "Food", "latitude": 0.3000, "longitude": 32.5000}, {"name": "Park A", "category": "Parks", "latitude": 0.3010, "longitude": 32.5010}, {"name": "Food B", "category": "Food", "latitude": 0.3020, "longitude": 32.5020}, {"name": "Bad", "category": "Food", "latitude": float("nan"), "longitude": 32.5}]
    report = spatial_report(places, ["Food", "Parks", "Transit"])
    assert report["dataset_places"] == 3
    assert report["catchment_400m"]["coverage_pct"] == 100.0
    assert report["hotspots_400m"][0]["nearby_places"] >= 1
    assert any(row["category"] == "Transit" for row in report["category_gaps"])
    assert category_gaps(places, ["Transit"])[0]["category"] == "Transit"


def test_trip_optimizers_handle_unreachable_inputs():
    matrix = [[0.0, 2.0, 4.0], [2.0, 0.0, 1.0], [4.0, 1.0, 0.0]]
    assert nearest_neighbor_order(matrix, start=0) == [0, 1, 2]
    assert two_opt_improve([0, 1, 2], matrix) == [0, 1, 2]
    unreachable = [[0.0, float("inf")], [float("inf"), 0.0]]
    assert nearest_neighbor_order(unreachable, start=0) == [0]
