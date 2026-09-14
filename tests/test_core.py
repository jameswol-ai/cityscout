from __future__ import annotations

import importlib
import math

from modules.architecture import SiteParameters, build_analysis, haversine_km, walkability_score
from modules.gis import build_city_map, city_metrics, valid_places
from modules.spatial_intelligence import catchment_counts, category_gaps, density_hotspots, spatial_report
from modules.trip import nearest_neighbor_order, two_opt_improve


def test_all_python_modules_import_without_side_effect_failure():
    import pathlib

    for path in sorted(pathlib.Path("modules").glob("*.py")):
        if path.name == "__init__.py":
            continue
        importlib.import_module(f"modules.{path.stem}")


def test_gis_filters_invalid_coordinates():
    places = [
        {"name": "Good", "latitude": 0.3, "longitude": 32.5},
        {"name": "Bad", "latitude": 999, "longitude": 32.5},
        {"name": "NaN", "latitude": math.nan, "longitude": 32.5},
        "not-a-place",
    ]
    valid = valid_places(places)
    assert [p["name"] for p in valid] == ["Good"]


def test_city_metrics_and_map_are_resilient():
    places = [
        {"name": "A", "category": "Food", "favorite": True, "latitude": 0.3, "longitude": 32.5},
        {"name": "B", "category": "Parks", "favorite": False, "latitude": 0.31, "longitude": 32.51},
    ]
    metrics = city_metrics(places)
    assert metrics["places"] == 2
    assert metrics["favorites"] == 1
    assert metrics["categories"] == 2
    assert metrics["footprint_km2"] > 0
    fmap = build_city_map(places, show_heatmap=True, cluster_markers=False)
    assert fmap is not None


def test_architecture_analysis_has_bounded_scores():
    params = SiteParameters(site_area_m2=2000, site_coverage_pct=40, floors=5)
    analysis = build_analysis(params, [])
    assert analysis["site_metrics"]["gross_floor_area_m2"] == 4000
    assert 0 <= analysis["urban_indicators"]["green_ratio"] <= 1
    assert 0 <= walkability_score([]) <= 100
    assert haversine_km(0, 0, 0, 0) == 0


def test_trip_optimizers_handle_small_and_unreachable_inputs():
    matrix = [[0.0, 2.0, 4.0], [2.0, 0.0, 1.0], [4.0, 1.0, 0.0]]
    order = nearest_neighbor_order(matrix, start=0)
    assert order == [0, 1, 2]
    assert two_opt_improve(order, matrix) == [0, 1, 2]

    unreachable = [[0.0, float("inf")], [float("inf"), 0.0]]
    assert nearest_neighbor_order(unreachable, start=0) == [0]


def test_spatial_intelligence_handles_empty_single_and_clustered_data():
    assert catchment_counts([], 400)["coverage_pct"] == 0.0
    assert spatial_report([])["dataset_places"] == 0
    assert density_hotspots([{"name": "Only", "latitude": 0.3, "longitude": 32.5}], 400)[0]["nearby_places"] == 0

    places = [
        {"name": "Food A", "category": "Food", "latitude": 0.3000, "longitude": 32.5000},
        {"name": "Park A", "category": "Parks", "latitude": 0.3010, "longitude": 32.5010},
        {"name": "Food B", "category": "Food", "latitude": 0.3020, "longitude": 32.5020},
        {"name": "Bad", "category": "Food", "latitude": float("nan"), "longitude": 32.5},
    ]
    report = spatial_report(places, ["Food", "Parks", "Transit"])
    assert report["dataset_places"] == 3
    assert report["catchment_400m"]["coverage_pct"] == 100.0
    assert report["hotspots_400m"][0]["nearby_places"] >= 1
    assert any(row["category"] == "Transit" for row in report["category_gaps"])
