# labware.py
"""
LABWARE TYPES + SYRINGE TYPES
实验平台所有器皿与注射器的类型定义。

本文件统一存放：
1. LabwareType：器皿几何（孔位布局、偏移、孔间距）+ Z 高度参数
2. SyringeType：注射器 U 轴 ↔ 体积（µL）映射表
3. LabwareInstance：某个 slot 上实际的器皿实例（计算孔位坐标）

No hardcoded numbers should appear in robot.py.
robot.py 不应含有任何硬编码数字，所有硬件参数均来自本文件。
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Tuple, Dict

from src.deck import Deck, DeckSlot


# ======================================================
# 1. 注射器类型 (U-axis ↔ volume)
# ======================================================

@dataclass
class SyringeType:
    """
    Syringe calibration model.
    注射器标定模型：

    - name          名称（如 "10ml"）
    - max_volume_ul 最大容量（µL）
    - u_per_ul      每 1 µL 需要移动多少 U 单位（线性近似）
    - u_base        每次吸液起始 U 位置（通常 10）
    - u_min/u_max   可选的机械行程限制
    """
    name: str
    max_volume_ul: float
    u_per_ul: float
    u_base: float
    u_min: float | None = None
    u_max: float | None = None


# Example syringe: 1ml (placeholder values)
# 示例 1ml 注射器（占位数值，之后可根据实验重新标定）
Syringe_1ml = SyringeType(
    name="1ml",
    max_volume_ul=1000.0,
    u_per_ul=0.06,        # 示例：每 1µL ≈ 0.5 U（请之后标定）
    u_base=5.0,
    u_min=0.0,
    u_max=65.0,
)

SYRINGES: Dict[str, SyringeType] = {
    "1ml": Syringe_1ml,
}


# ======================================================
# 2. 器皿类型 LabwareType
# ======================================================

@dataclass
class LabwareType:
    """
    Describe an SBS labware type (96 tips, 48 wells, beaker holder, tip waste box…).

    涵盖几何与高度信息：

    Geometry 几何:
    - rows / cols     行列数
    - pitch_x/y       孔间距（mm）
    - offset_x/y      A1 相对 slot 中心的偏移（deck 坐标）

    Z Heights 高度（machine Z）:
    - safe_z          安全高度（水平移动用）
    - bottom_z        孔底 / 液面附近
    - aspirate_z      吸液高度（None → 使用 bottom_z）
    - dispense_z      注液高度（None → bottom_z）

    Tip handling (tiprack / waste box only):
    - tip_touch_z     轻触 tip
    - tip_press_z     加压
    - tip_full_z      完全插入
    - scrape_z        蹭掉 tip 的高度
    """

    name: str
    rows: int
    cols: int
    pitch_x: float
    pitch_y: float
    offset_x: float
    offset_y: float
    safe_z: float
    bottom_z: float

    aspirate_z: float | None = None
    dispense_z: float | None = None

    tip_touch_z: float | None = None
    tip_press_z: float | None = None
    tip_full_z: float | None = None
    scrape_z: float | None = None


# ======================================================
# 3. LabwareInstance (把几何映射到 slot / deck / machine)
# ======================================================

@dataclass
class LabwareInstance:
    """
    Physical instance of a LabwareType on a deck slot.

    某个 slot 上实际摆放的器皿实例，用来计算孔位坐标。
    """

    type: LabwareType
    slot: DeckSlot
    label: str
    deck: Deck

    def _well_rc(self, well: str) -> Tuple[int, int]:
        """Convert well name 'A1' → (row_idx, col_idx)"""
        well = well.strip().upper()
        row_char = well[0]
        col = int(well[1:]) - 1
        row = ord(row_char) - ord("A")

        if not (0 <= row < self.type.rows):
            raise ValueError(f"Row out of range: {well}")
        if not (0 <= col < self.type.cols):
            raise ValueError(f"Column out of range: {well}")

        return row, col

    def well_position_deck(self, well: str) -> Tuple[float, float]:
        """Return well coordinate in DECK space."""
        r, c = self._well_rc(well)
        x = self.slot.x_deck + self.type.offset_x + c * self.type.pitch_x
        y = self.slot.y_deck + self.type.offset_y + r * self.type.pitch_y
        return x, y

    def well_position_machine(self, well: str) -> Tuple[float, float]:
        """Return well coordinate in MACHINE space."""
        x_d, y_d = self.well_position_deck(well)
        return self.deck.deck_to_machine(x_d, y_d)


# ======================================================
# 4. 具体器皿类型定义
# ======================================================

# ---------------------
# Tip Rack (96 tips)
# ---------------------
LABWARE_TIPRACK_96 = LabwareType(
    name="tiprack_96",
    rows=8,
    cols=12,
    pitch_x=9.0,
    pitch_y=9.0,
    offset_x=-49.7,
    offset_y=-31.5,
    safe_z=100.0,
    bottom_z=0.0,

    tip_touch_z=170.0,
    tip_press_z=172.0,
    tip_full_z=176.0,

    scrape_z=152.0,
)


# ---------------------
# Tip Waste Box (用于蹭掉 tips)
# ---------------------
LABWARE_TIPWASTE_BOX = LabwareType(
    name="tip_waste_box",
    rows=1,
    cols=1,
    pitch_x=0,
    pitch_y=0,
    offset_x=0,
    offset_y=0,

    safe_z=100.0,      # 水平移动安全高度
    bottom_z=0.0,

    scrape_z=170.0,    # 蹭 tip 的高度 = 当初烧杯高度
)


# ---------------------
# 48-well Plate (10mm)
# ---------------------
LABWARE_48WELL_10MM = LabwareType(
    name="48well_10mm",
    rows=6,
    cols=8,
    pitch_x=12.47,
    pitch_y=12.47,
    offset_x=-43.88,
    offset_y=-32.04,

    safe_z=158.0,
    bottom_z=170.0,
)

# ---------------------
# Beaker (1 well, center of slot)
# ---------------------
LABWARE_BEAKER_1WELL = LabwareType(
    name="beaker_1well",
    rows=1,
    cols=1,
    pitch_x=0.0,
    pitch_y=0.0,
    offset_x=0.0,   # A1 slot 中心
    offset_y=0.0,

    # 
    safe_z=100.0,     # 水平移动安全高度
    bottom_z=150.0,   # 接近烧杯底/液面附近

    aspirate_z=150.0,   # 吸液高度（略低于液面）
    dispense_z=150.0,   # 排液高度（略高一点防止扎到杯底）
)