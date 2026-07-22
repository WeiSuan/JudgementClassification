from pathlib import Path

from src.pipeline.run_mvp import run


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parent
    output_path = run(project_root / "config/settings.yaml")
    print(f"Done. Output: {output_path}")
