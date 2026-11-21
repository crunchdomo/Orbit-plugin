"""Offset pagination helpers."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Page:
    number: int
    size: int
    total: int

    @property
    def offset(self) -> int:
        return (self.number - 1) * self.size

    @property
    def pages(self) -> int:
        return max(1, -(-self.total // self.size))

    @property
    def has_next(self) -> bool:
        return self.number < self.pages


def parse_page(raw: str | None, size: int, total: int) -> Page:
    """Build a Page from a query-string value, clamping to the valid range."""
    if size < 1:
        raise ValueError("size must be at least 1")
    try:
        number = int(raw) if raw is not None else 1
    except ValueError:
        number = 1
    last = max(1, -(-total // size))
    return Page(number=min(max(number, 1), last), size=size, total=total)
