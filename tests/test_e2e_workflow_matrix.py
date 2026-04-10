from __future__ import annotations

from pathlib import Path

import yaml


def test_e2e_workflow_matrix_covers_all_iterations():
    matrix_path = Path("tests/e2e_workflow_matrix.yaml")
    matrix = yaml.safe_load(matrix_path.read_text(encoding="utf-8"))

    iterations = set(matrix["iterations"])
    assert iterations == {"mock", "snapshot", "live"}

    workflows = matrix["workflows"]
    assert len(workflows) >= 17

    workflow_ids = {workflow["id"] for workflow in workflows}
    assert workflow_ids == {
        "E2E-01",
        "E2E-02",
        "E2E-03",
        "E2E-04",
        "E2E-05",
        "E2E-06",
        "E2E-07",
        "E2E-08",
        "E2E-09",
        "E2E-10",
        "E2E-11",
        "E2E-12",
        "E2E-13",
        "E2E-14",
        "E2E-15",
        "E2E-16",
        "E2E-17",
    }

    for workflow in workflows:
        assert set(workflow["modes"]) == iterations
        assert workflow["required_result"]
