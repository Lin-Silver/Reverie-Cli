from pathlib import Path

from reverie.engine import create_project_skeleton
from reverie.tools.reverie_engine import ReverieEngineTool


def test_engine_tool_can_report_health_benchmark_and_package(tmp_path: Path) -> None:
    project_root = tmp_path / "engine_project"
    create_project_skeleton(
        project_root,
        project_name="Engine Project",
        dimension="2D",
        sample_name="2d_platformer",
        overwrite=True,
    )

    tool = ReverieEngineTool({"project_root": str(project_root)})

    health = tool.execute(action="project_health", output_dir=".")
    assert health.success is True
    assert health.data["health"]["score"] >= 60

    benchmark = tool.execute(
        action="benchmark_project",
        output_dir=".",
        iterations=2,
        output_path="playtest/logs/engine_benchmark.json",
    )
    assert benchmark.success is True
    assert Path(benchmark.data["output_path"]).exists()
    assert benchmark.data["benchmarks"]["scene_instantiation"]["iterations"] == 2

    package = tool.execute(action="package_project", output_dir=".", include_smoke=False)
    assert package.success is True
    assert Path(package.data["package_path"]).exists()
    assert package.data["file_count"] > 0
