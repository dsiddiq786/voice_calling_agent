import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class MenuItem:
    id: str
    name: str
    price: int
    category: str
    aliases: Tuple[str, ...]
    details: Tuple[str, ...] = ()
    price_from: bool = False


def normalize(text: str) -> str:
    text = text.casefold().replace("ـ", " ")
    text = re.sub(r"[^\w\u0600-\u06ff]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


class Menu:
    def __init__(self, path: Path = ROOT / "data" / "menu.json") -> None:
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.restaurant = payload["restaurant"]
        self.items: Dict[str, MenuItem] = {}
        for raw in payload["items"]:
            aliases = tuple(dict.fromkeys([raw["name"], *raw.get("aliases", [])]))
            self.items[raw["id"]] = MenuItem(
                id=raw["id"], name=raw["name"], price=raw["price"],
                category=raw["category"], aliases=aliases,
                details=tuple(raw.get("details", [])),
                price_from=bool(raw.get("price_from", False)),
            )

    def match_all(self, text: str) -> List[Tuple[MenuItem, str]]:
        normalized = normalize(text)
        matches: List[Tuple[int, MenuItem, str]] = []
        for item in self.items.values():
            best: Optional[str] = None
            for alias in item.aliases:
                candidate = normalize(alias)
                if candidate and re.search(rf"(?<!\w){re.escape(candidate)}(?!\w)", normalized):
                    if best is None or len(candidate) > len(best):
                        best = candidate
            if best:
                matches.append((normalized.index(best), item, best))
        matches.sort(key=lambda row: row[0])
        # Prefer the longest alias where menu names overlap.
        claimed: List[Tuple[int, int]] = []
        result: List[Tuple[MenuItem, str]] = []
        for _, item, alias in sorted(matches, key=lambda row: (-len(row[2]), row[0])):
            start = normalized.index(alias)
            end = start + len(alias)
            if any(start < right and end > left for left, right in claimed):
                continue
            claimed.append((start, end))
            result.append((item, alias))
        result.sort(key=lambda row: normalized.index(row[1]))
        return result

    def categories(self) -> Iterable[str]:
        return dict.fromkeys(item.category for item in self.items.values())


MENU = Menu()
