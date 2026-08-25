from __future__ import annotations

import csv
import io
from pathlib import Path

from scripts.run_tabular_commercial_acceptance import (
    ONLINE_SHOPPERS,
    ONLINE_SHOPPERS_FEATURES,
    PROJECTIONS,
    SEOUL_BIKE,
    SEOUL_BIKE_FEATURES,
    project_online_shoppers,
    project_seoul_bike,
    render_markdown_report,
)


def _online_shoppers_payload(row_count: int = 620) -> bytes:
    output = io.StringIO(newline="")
    fieldnames = [
        "Administrative",
        "Administrative_Duration",
        "Informational",
        "Informational_Duration",
        "ProductRelated",
        "ProductRelated_Duration",
        "BounceRates",
        "ExitRates",
        "PageValues",
        "SpecialDay",
        "Month",
        "OperatingSystems",
        "Browser",
        "Region",
        "TrafficType",
        "VisitorType",
        "Weekend",
        "Revenue",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for index in range(1, row_count + 1):
        writer.writerow(
            {
                "Administrative": index % 9,
                "Administrative_Duration": index * 0.7,
                "Informational": index % 4,
                "Informational_Duration": index * 0.3,
                "ProductRelated": (index % 50) + 1,
                "ProductRelated_Duration": index * 2.2,
                "BounceRates": (index % 20) / 100,
                "ExitRates": (index % 25) / 100,
                "PageValues": index % 17,
                "SpecialDay": (index % 6) / 10,
                "Month": "May",
                "OperatingSystems": 2,
                "Browser": 1,
                "Region": 3,
                "TrafficType": 4,
                "VisitorType": "Returning_Visitor",
                "Weekend": "FALSE",
                "Revenue": "TRUE" if index % 5 == 0 else "FALSE",
            }
        )
    return output.getvalue().encode("utf-8")


def _seoul_bike_payload(row_count: int = 520) -> bytes:
    output = io.StringIO(newline="")
    fieldnames = [
        "Date",
        "Rented Bike Count",
        "Hour",
        "Temperature(°C)",
        "Humidity(%)",
        "Wind speed (m/s)",
        "Visibility (10m)",
        "Dew point temperature(°C)",
        "Solar Radiation (MJ/m2)",
        "Rainfall(mm)",
        "Snowfall (cm)",
        "Seasons",
        "Holiday",
        "Functioning Day",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for index in range(1, row_count + 1):
        writer.writerow(
            {
                "Date": "01/12/2017",
                "Rented Bike Count": 100 + (index % 400),
                "Hour": index % 24,
                "Temperature(°C)": 2.0 + (index % 30),
                "Humidity(%)": 30 + (index % 60),
                "Wind speed (m/s)": 0.5 + (index % 20) / 10,
                "Visibility (10m)": 500 + index,
                "Dew point temperature(°C)": -4.0 + (index % 25),
                "Solar Radiation (MJ/m2)": (index % 30) / 10,
                "Rainfall(mm)": 0 if index % 17 else 1.5,
                "Snowfall (cm)": 0 if index % 29 else 0.8,
                "Seasons": "Winter",
                "Holiday": "No Holiday",
                "Functioning Day": "Yes",
            }
        )
    return output.getvalue().encode("utf-8")


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_official_source_contracts_are_pinned_and_attributed() -> None:
    assert ONLINE_SHOPPERS.dataset_id == 468
    assert ONLINE_SHOPPERS.doi == "10.24432/C5F88Q"
    assert ONLINE_SHOPPERS.license_name == "CC BY 4.0"
    assert ONLINE_SHOPPERS.archive_sha256 == (
        "2972e6184d3ad7beaaa831d9fc2b059dc3ee29df69d1ec593c466a5cd8485d14"
    )
    assert SEOUL_BIKE.dataset_id == 560
    assert SEOUL_BIKE.doi == "10.24432/C5F62R"
    assert SEOUL_BIKE.license_name == "CC BY 4.0"
    assert SEOUL_BIKE.archive_sha256 == (
        "139e9908f0a3544bb222386855c9ce107e96467306bb8e4ce936aab59e7baac4"
    )
    assert set(PROJECTIONS) == {"classification", "regression"}
    assert "VisitorType" in PROJECTIONS["classification"].excluded_columns
    assert "Date" in PROJECTIONS["regression"].excluded_columns


def test_online_shoppers_projection_is_numeric_reproducible_and_injects_missing(tmp_path: Path) -> None:
    first_path = tmp_path / "online_first.csv"
    second_path = tmp_path / "online_second.csv"
    first = project_online_shoppers(_online_shoppers_payload(), first_path)
    second = project_online_shoppers(_online_shoppers_payload(), second_path)

    assert first["sha256"] == second["sha256"]
    assert first["row_count"] == 620
    assert first["columns"] == [*ONLINE_SHOPPERS_FEATURES, "purchase_completed"]
    assert first["controlled_missing_values"] == {
        "administrative_duration": 2,
        "bounce_rates": 2,
    }
    rows = _read_rows(first_path)
    assert rows[210]["administrative_duration"] == ""
    assert rows[306]["bounce_rates"] == ""
    assert {row["purchase_completed"] for row in rows} == {"purchase", "no_purchase"}
    assert "VisitorType" not in rows[0]


def test_seoul_bike_projection_is_numeric_reproducible_and_injects_missing(tmp_path: Path) -> None:
    first_path = tmp_path / "bike_first.csv"
    second_path = tmp_path / "bike_second.csv"
    first = project_seoul_bike(_seoul_bike_payload(), first_path)
    second = project_seoul_bike(_seoul_bike_payload(), second_path)

    assert first["sha256"] == second["sha256"]
    assert first["row_count"] == 520
    assert first["columns"] == [*SEOUL_BIKE_FEATURES, "rented_bike_count"]
    assert first["controlled_missing_values"] == {
        "temperature_c": 3,
        "solar_radiation_mj_m2": 2,
    }
    rows = _read_rows(first_path)
    assert rows[172]["temperature_c"] == ""
    assert rows[256]["solar_radiation_mj_m2"] == ""
    assert "Date" not in rows[0]
    assert float(rows[0]["rented_bike_count"]) > 0


def test_report_documents_source_and_full_product_chain() -> None:
    report = {
        "status": "passed",
        "generated_at": "2026-08-25T00:00:00+00:00",
        "environment": {},
        "summary": {
            "scenario_count": 2,
            "passed_scenarios": 2,
            "check_count": 2,
            "passed_checks": 2,
            "duration_seconds": 1.0,
        },
        "sources": [
            {
                "source": {
                    "name": ONLINE_SHOPPERS.name,
                    "dataset_id": ONLINE_SHOPPERS.dataset_id,
                    "landing_url": ONLINE_SHOPPERS.landing_url,
                    "doi": ONLINE_SHOPPERS.doi,
                    "license": ONLINE_SHOPPERS.license_name,
                    "license_url": ONLINE_SHOPPERS.license_url,
                    "citation": ONLINE_SHOPPERS.citation,
                    "archive_sha256": ONLINE_SHOPPERS.archive_sha256,
                },
                "projection": {
                    "row_count": 620,
                    "feature_columns": list(ONLINE_SHOPPERS_FEATURES),
                    "target_column": "purchase_completed",
                    "excluded_columns": ["VisitorType"],
                    "sha256": "a" * 64,
                    "controlled_missing_value_count": 4,
                },
            }
        ],
        "scenarios": [
            {
                "task_head": "classification",
                "status": "passed",
                "checks": [{"name": "lifecycle_to_production", "status": "passed"}],
            }
        ],
    }

    markdown = render_markdown_report(report)

    assert ONLINE_SHOPPERS.landing_url in markdown
    assert ONLINE_SHOPPERS.doi in markdown
    assert "CC BY 4.0" in markdown
    assert "lifecycle_to_production" in markdown
    assert "real project, import, configuration, training, inference, comparison, lifecycle and export services" in markdown
