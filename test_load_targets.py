"""Self-check for load_targets. Run: python3 test_load_targets.py"""
import io, os, pathlib, sys, urllib.request

import generate

CSV = "slug,agency_name,status\na,A Ltd,ready\nb,B Ltd,draft\n"


def test_local_fallback(tmp):
    os.environ.pop("TARGETS_URL", None)
    generate.ROOT = tmp
    (tmp / "targets.csv").write_text(CSV, encoding="utf-8")
    rows = generate.load_targets()
    assert [r["slug"] for r in rows] == ["a", "b"], rows
    assert rows[1]["status"] == "draft"


def test_url(tmp):
    os.environ["TARGETS_URL"] = "https://example.invalid/sheet.csv"

    class Fake(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    urllib.request.urlopen = lambda url, timeout=None: Fake(CSV.encode())
    rows = generate.load_targets()
    assert [r["agency_name"] for r in rows] == ["A Ltd", "B Ltd"], rows


if __name__ == "__main__":
    tmp = pathlib.Path(__file__).parent / ".selfcheck"
    tmp.mkdir(exist_ok=True)
    test_local_fallback(tmp)
    test_url(tmp)
    (tmp / "targets.csv").unlink()
    tmp.rmdir()
    print("load_targets ok")
