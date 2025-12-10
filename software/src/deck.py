# deck.py
"""
DECK (平台布局)
Deck describes the coordinate system and all SBS slots on your lab platform.

平台布局文件，描述整个平台的坐标系统，以及所有的 Slot（SBS 槽位）中心位置。
这里不再依赖 deck.json，所有布局信息直接写在 Python 常量中，便于用户调整。
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Tuple


# ------------------------------------------------------
# 固定的整个平台布局  (用户可修改)
# Fixed platform layout (editable by user)
# ------------------------------------------------------

DECK_LAYOUT = {
    # deck(0,0) 在 machine 坐标系的位置
    # Position of deck-origin (0,0) in the machine coordinate system
    "origin_machine": {
        "x": -8,
        "y": -5,
    },

    # 6-slot standard layout (3 × 2)
    # 每个槽位中心在 deck 坐标系中的位置
    "slots": {
        "1": {"x": 90.9, "y": 70.0},
        "2": {"x": 242.1, "y": 70.0},
        "3": {"x": 90.9, "y": 170.0},
        "4": {"x": 242.1, "y": 170.0},
        "5": {"x": 90.9, "y": 270.0},
        "6": {"x": 242.1, "y": 270.0},
    },
}


# ------------------------------------------------------
# 数据结构
# ------------------------------------------------------

@dataclass
class DeckSlot:
    """
    Single SBS slot.

    单个 SBS 槽位，保存其在 deck 坐标系下的中心位置。
    """
    slot_id: str
    x_deck: float
    y_deck: float


class Deck:
    """
    Deck object representing the whole platform.

    Deck 表示整个实验平台：
    - 负责 deck 坐标 → machine 坐标 的转换
    - 保存所有 Slot 的中心坐标
    """

    def __init__(self) -> None:
        origin = DECK_LAYOUT["origin_machine"]
        self.origin_x = float(origin["x"])
        self.origin_y = float(origin["y"])

        self.slots: Dict[str, DeckSlot] = {}
        for slot_id, coords in DECK_LAYOUT["slots"].items():
            self.slots[slot_id] = DeckSlot(
                slot_id=slot_id,
                x_deck=float(coords["x"]),
                y_deck=float(coords["y"]),
            )

    # --------------------------------------------------
    # 坐标变换 / Coordinate transform
    # --------------------------------------------------

    def deck_to_machine(self, x_deck: float, y_deck: float) -> Tuple[float, float]:
        """
        Convert from deck space to machine space.

        将 deck 坐标转换为 machine 坐标。
        """
        return (
            self.origin_x + x_deck,
            self.origin_y + y_deck,
        )

    def slot_center_machine(self, slot_id: str) -> Tuple[float, float]:
        """
        Return slot center in machine coordinates.

        返回某个 Slot 的中心（machine 坐标系）。
        """
        slot = self.slots[slot_id]
        return self.deck_to_machine(slot.x_deck, slot.y_deck)
