import argparse
import csv
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Sale:
    product: str
    quantity: int
    price: float

    @property
    def total(self) -> float:
        return self.quantity * self.price


def read_sales(path: Path) -> list[Sale]:
    """Đọc dữ liệu bán hàng từ tệp CSV và bỏ qua các dòng không hợp lệ."""
    if not path.exists():
        logger.error("Tệp không tồn tại: %s", path)
        raise FileNotFoundError(f"Không tìm thấy tệp: {path}")

    sales: list[Sale] = []
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                product = row["product"].strip()
                quantity = int(row["quantity"])
                price = float(row["price"])
                if not product or quantity < 0 or price < 0:
                    raise ValueError("Dữ liệu sản phẩm, số lượng hoặc đơn giá không hợp lệ")
                sales.append(Sale(product=product, quantity=quantity, price=price))
            except (KeyError, ValueError, TypeError) as exc:
                logger.warning("Bỏ qua dòng lỗi %s: %s", row, exc)
    return sales


def summarize_sales(sales: list[Sale]) -> dict[str, float]:
    """Tổng hợp doanh thu theo từng sản phẩm."""
    summary: dict[str, float] = {}
    for item in sales:
        summary[item.product] = summary.get(item.product, 0.0) + item.total
    return summary


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="CLI đọc file CSV và tổng hợp báo cáo doanh thu")
    parser.add_argument("csv_file", type=Path, help="Đường dẫn tới tệp CSV đầu vào")
    args = parser.parse_args()

    sales = read_sales(args.csv_file)
    summary = summarize_sales(sales)
    grand_total = sum(summary.values())

    logger.info("Đã đọc hợp lệ %d dòng dữ liệu.", len(sales))
    for product, total in summary.items():
        logger.info("- %s: %.2f", product, total)
    logger.info("Tổng doanh thu: %.2f", grand_total)


if __name__ == "__main__":
    main()
