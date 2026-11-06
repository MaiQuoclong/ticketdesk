from pathlib import Path

import pytest

from sales import Sale, read_sales, summarize_sales


def test_total() -> None:
    assert Sale("Bút", 2, 10.0).total == 20.0


def test_skip_invalid_row(tmp_path: Path) -> None:
    f = tmp_path / "data.csv"
    f.write_text("product,quantity,price\nBút,2,10\nVở,abc,5\n", encoding="utf-8")
    sales = read_sales(f)
    assert len(sales) == 1
    assert sales[0].product == "Bút"


def test_file_not_found(tmp_path: Path) -> None:
    missing = tmp_path / "missing.csv"
    with pytest.raises(FileNotFoundError):
        read_sales(missing)


def test_summarize_sales() -> None:
    items = [
        Sale("Bút", 2, 10.0),
        Sale("Vở", 3, 15.0),
        Sale("Bút", 1, 10.0),
    ]
    summary = summarize_sales(items)
    assert summary == {"Bút": 30.0, "Vở": 45.0}
