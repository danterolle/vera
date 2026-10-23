from pathlib import Path


def test_authored_files_stay_below_two_hundred_lines() -> None:
    root = Path(__file__).parents[2]
    paths = [
        *root.glob("src/**/*"),
        *root.glob("tests/**/*"),
        *root.glob("docs/**/*"),
        root / "README.md",
        root / "pyproject.toml",
        root / ".env.example",
        root / ".gitignore",
        root / ".github/workflows/ci.yml",
    ]
    checked = {
        path
        for path in paths
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
        and path.name != ".DS_Store"
    }
    violations = {
        str(path.relative_to(root)): len(path.read_text(encoding="utf-8").splitlines())
        for path in checked
        if len(path.read_text(encoding="utf-8").splitlines()) > 200
    }
    assert violations == {}
