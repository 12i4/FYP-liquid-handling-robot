# robot.py
"""
Robot control for the pipette platform.
用于控制移液机器人的核心类。

本文件提供两层能力：
1. 底层串口 / G-code 通讯与基础运动 (home / move_to / send_gcode 等)
2. 高层移液动作 (戴 tips / 蹭掉 tips / 移液 / 吸液 / 排液)

所有硬件参数（平台布局、器皿几何、Z 高度、注射器标定）
都集中在 deck.py 和 labware.py 中，这里不写死任何数值。
"""

from __future__ import annotations

import time
from typing import Optional

import serial

from src.deck import Deck
from src.labware import (
    LabwareType,  
    LabwareInstance,
    LABWARE_TIPRACK_96,
    LABWARE_TIPWASTE_BOX,
    LABWARE_48WELL_10MM,
    LABWARE_BEAKER_1WELL, 
    SYRINGES,
    SyringeType,
)


class Robot:
    """
    Robot wrapper around a Marlin-like firmware.

    面向用户的机器人控制类，封装：
    - 串口连接与 G-code 通讯
    - 轴运动（X/Y/Z/U）
    - 常用高层动作（戴 tip、扔 tip、移液、吸液、排液）

    使用方式示例：
    Example:
        from deck import Deck
        from robot import Robot

        deck = Deck()
        robot = Robot("COM4")
        robot.home(axes="XYZ")       # 只回 XYZ，避免 U 变形
        robot.set_absolute_mode()

        # 戴 tip：slot1 的 A1
        robot.pick_up_tip(deck, slot_id="1", well="A1")

        # 从 slot4.A1 吸 50µL 到 slot4.B3
        robot.transfer_volume(
            deck,
            src_slot="4", src_well="A1",
            dst_slot="4", dst_well="B3",
            volume_ul=50.0,
            syringe="10ml",
        )
    """

    # --------------------------------------------------
    # 初始化与串口管理 / Initialization & Serial I/O
    # --------------------------------------------------

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        timeout: float = 1.0,
        auto_connect: bool = True,
    ) -> None:
        """
        Create a robot controller.

        创建机器人控制对象。

        Args:
            port:     串口号，例如 "COM4" 或 "/dev/ttyUSB0"
            baudrate: 波特率，通常为 115200
            timeout:  串口读超时（秒）
            auto_connect: 是否在构造时自动连接串口
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout

        self._ser: Optional[serial.Serial] = None

        # 可选：当前平台与注射器信息（高层动作使用）
        # Optional: current deck and syringe settings
        self.deck: Optional[Deck] = None
        self.current_syringe: Optional[SyringeType] = None

        if auto_connect:
            self.connect()

    # ---------------------- Serial ---------------------

    def connect(self) -> None:
        """
        Open serial connection if not already open.

        打开串口连接（若尚未连接）。
        """
        if self._ser is not None and self._ser.is_open:
            return

        self._ser = serial.Serial(
            self.port,
            self.baudrate,
            timeout=self.timeout,
        )
        # 清空缓冲区，避免旧数据干扰
        self._flush_input()

    def disconnect(self) -> None:
        """
        Close serial connection.

        关闭串口连接。
        """
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None

    def _ensure_connected(self) -> None:
        """
        Ensure serial is open before any I/O.

        确保在进行读写前串口已经打开。
        """
        if self._ser is None or not self._ser.is_open:
            raise RuntimeError("Serial not connected. 未连接串口，请先调用 connect().")

    def _flush_input(self) -> None:
        """
        Flush any pending bytes from the input buffer.

        清空串口输入缓冲区，丢弃所有未读数据。
        """
        if self._ser is None:
            return
        self._ser.reset_input_buffer()

    def _write_line(self, line: str) -> None:
        """
        Write a line of G-code to the firmware.

        发送一行 G-code 到固件（自动添加换行）。
        """
        self._ensure_connected()
        data = (line.strip() + "\n").encode("ascii")
        self._ser.write(data)
        self._ser.flush()

    def _read_line(self) -> str:
        """
        Read a line from firmware (blocking up to timeout).

        从固件读取一行文本（阻塞直到 timeout）。
        """
        self._ensure_connected()
        raw = self._ser.readline()
        if not raw:
            return ""
        try:
            return raw.decode("ascii", errors="ignore").strip()
        except Exception:
            return ""

    def _drain_until_ok_or_timeout(self, overall_timeout: float) -> None:
        """
        Read lines until an 'ok' is received or timeout occurs.

        持续读取固件输出，直到收到 'ok' 或者超时。
        - 收到 'ok' → 正常返回
        - 收到 Error / error → 仍然抛 RuntimeError
        - 超时 → 只打印警告，不抛异常（避免 GUI 弹框）
        """
        start = time.time()
        while True:
            line = self._read_line()
            if line:
                # 简单调试输出：可根据需要保留或注释
                # print(f"[FW] {line}")
                if line.startswith("Error") or "error" in line.lower():
                    raise RuntimeError(f"Firmware error: {line}")
                if line.strip().lower() == "ok":
                    return
            # overall_timeout 为 None 或 <=0 时视为「无限等待」
            if overall_timeout is not None and overall_timeout > 0:
                if time.time() - start > overall_timeout:
                    # 超时：只给出一个终端 warning，然后返回，不抛 TimeoutError
                    print("[WARN] Timeout waiting for 'ok' from firmware, "
                          "ignore and continue.")
                    return

    # --------------------------------------------------
    # G-code 封装 / G-code wrapper
    # --------------------------------------------------

    def send_gcode(
        self,
        gcode: str,
        wait_ok: bool = True,
        overall_timeout: float = 9999.0,
    ) -> None:
        """
        Send a raw G-code command to the firmware.

        发送一条原始 G-code 指令到固件。

        Args:
            gcode:            要发送的 G-code 字符串（不含换行）
            wait_ok:          是否等待固件返回 'ok'
            overall_timeout:  等待 'ok' 的最长时间（秒）
        """
        self._write_line(gcode)
        if wait_ok:
            self._drain_until_ok_or_timeout(overall_timeout)

    def dwell(self, seconds: float) -> None:
        """
        Firmware-side dwell using G4.

        使用 G4 命令让固件等待指定时间（秒），
        比 Python 的 time.sleep 更安全，因为电机运动由固件控制。
        """
        ms = int(seconds * 1000)
        self.send_gcode(f"G4 P{ms}", wait_ok=True, overall_timeout=seconds + 5.0)

    # --------------------------------------------------
    # Homing / Coordinate Modes
    # --------------------------------------------------

    def home_all(self, timeout: float = 9999.0) -> None:
        """
        Home all axes with a plain G28.

        使用 G28 指令对所有轴进行回零。
        注意：Z 轴行程较长，默认使用较大的超时时间。
        """
        self.send_gcode("G28", wait_ok=True, overall_timeout=timeout)
        # ---------- 追加：把 U 轴抬起来以避免挤压注射器 ----------
        # 假设 U=5mm 是安全高度（避免变形）
        self.send_gcode("G1 U5 F200")
        # ---------------------------------------------------------

    def home(self, axes: str = "XYZU", timeout: float = 9999.0) -> None:
        """
        Home selected axes with G28.

        使用 G28 指令对指定轴回零。

        Example / 示例:
            home("X")    → G28 X
            home("YZ")   → G28 Y Z
            home("U")    → G28 U
        """
        axes = axes.upper()
        parts = ["G28"]
        for a in axes:
            if a in ("X", "Y", "Z", "U"):
                parts.append(a)
        cmd = " ".join(parts)
        self.send_gcode(cmd, wait_ok=True, overall_timeout=timeout)

    def set_absolute_mode(self) -> None:
        """
        Set absolute positioning mode (G90).

        设置绝对坐标模式（G90）。
        """
        self.send_gcode("G90")

    def set_relative_mode(self) -> None:
        """
        Set relative positioning mode (G91).

        设置相对坐标模式（G91）。
        """
        self.send_gcode("G91")

    # --------------------------------------------------
    # 轴运动 / Axis movement
    # --------------------------------------------------

    def move_to(
        self,
        x: Optional[float] = None,
        y: Optional[float] = None,
        z: Optional[float] = None,
        u: Optional[float] = None,
        feedrate: Optional[float] = None,
        overall_timeout: float = 999.0,
    ) -> None:
        """
        Move axes to target position using G1 (in current coord mode).

        使用 G1 命令将各轴移动到目标位置（遵循当前坐标模式：G90/G91）。

        Args:
            x, y, z, u: 目标坐标（如果为 None 则忽略该轴）
            feedrate:   进给速度 (mm/min)，为 None 时不改变当前 F
            overall_timeout: 此次运动的最大等待时间（秒）
        """
        parts = ["G1"]
        if x is not None:
            parts.append(f"X{x:.3f}")
        if y is not None:
            parts.append(f"Y{y:.3f}")
        if z is not None:
            parts.append(f"Z{z:.3f}")
        if u is not None:
            parts.append(f"U{u:.3f}")
        if feedrate is not None:
            parts.append(f"F{feedrate:.0f}")

        cmd = " ".join(parts)
        self.send_gcode(cmd, wait_ok=True, overall_timeout=overall_timeout)

    def move_relative(
        self,
        dx: float = 0.0,
        dy: float = 0.0,
        dz: float = 0.0,
        du: float = 0.0,
        feedrate: Optional[float] = None,
        overall_timeout: float = 999.0,
    ) -> None:
        """
        Relative move using G91 + G1 + G90.

        通过先切换到相对模式，再执行 G1，最后切回绝对模式，完成一次相对运动。

        Args:
            dx,dy,dz,du: 相对位移量
            feedrate:    进给速度 (mm/min)
        """
        # 切换相对模式
        self.set_relative_mode()

        parts = ["G1"]
        if dx != 0.0:
            parts.append(f"X{dx:.3f}")
        if dy != 0.0:
            parts.append(f"Y{dy:.3f}")
        if dz != 0.0:
            parts.append(f"Z{dz:.3f}")
        if du != 0.0:
            parts.append(f"U{du:.3f}")
        if feedrate is not None:
            parts.append(f"F{feedrate:.0f}")

        cmd = " ".join(parts)
        self.send_gcode(cmd, wait_ok=True, overall_timeout=overall_timeout)

        # 切回绝对模式
        self.set_absolute_mode()


    def get_position(self) -> dict:
        """
        Query current XYZU position from firmware using M114.
        返回示例字典: {"X": 123.45, "Y": 67.89, "Z": 10.00, "U": 5.00}
        """
        self._ensure_connected()
        self._write_line("M114")

        # 连续读几行直到包含坐标
        for _ in range(20):
            line = self._read_line()
            if not line:
                continue
            # M114 格式示例:
            # "X:10.000 Y:20.000 Z:30.000 U:5.000 Count ...."
            if "X:" in line:
                parts = line.replace(",", " ").split()
                pos = {}
                for p in parts:
                    if ":" in p:
                        key, val = p.split(":", 1)
                        if key in ("X", "Y", "Z", "U"):
                            try:
                                pos[key] = float(val)
                            except ValueError:
                                pass
                return pos
        return {}

    # --------------------------------------------------
    # 高层功能：注射器选择 / Syringe selection
    # --------------------------------------------------

    def set_syringe(self, syringe_name: str) -> None:
        """
        Select current syringe type by name (e.g. '10ml').

        设置当前使用的注射器类型（例如 "10ml"）。
        所有基于体积的 U 轴运动会使用该标定信息。
        """
        if syringe_name not in SYRINGES:
            raise KeyError(f"Unknown syringe type: {syringe_name}")
        self.current_syringe = SYRINGES[syringe_name]

    def _get_syringe(self, syringe_name: str | None = None) -> SyringeType:
        """
        Helper to obtain syringe calibration.

        辅助函数：获取当前使用的注射器标定信息。
        如果传入 syringe_name，则以传入优先；
        否则回落到 self.current_syringe。
        """
        if syringe_name is not None:
            if syringe_name not in SYRINGES:
                raise KeyError(f"Unknown syringe type: {syringe_name}")
            return SYRINGES[syringe_name]
        if self.current_syringe is None:
            raise RuntimeError("No syringe selected. 请先调用 set_syringe() 或传入 syringe_name。")
        return self.current_syringe

    # --------------------------------------------------
    # 高层功能：戴 tip / Remove tip
    # --------------------------------------------------

    def pick_up_tip(
        self,
        deck: Deck,
        slot_id: str,
        well: str,
        n_cycles: int = 2,
    ) -> None:
        """
        Pick up a tip from a tip rack in a given slot and well.

        从指定 Slot 的 tip 盒（tip rack）上，在指定孔位戴上一个 tip。

        Args:
            deck:    Deck 实例（平台布局）
            slot_id: 槽位编号，例如 "1"
            well:    孔位，例如 "A1", "B3"
            n_cycles: 在接触高度和压入高度之间来回“捣”的次数
        """
        slot = deck.slots[slot_id]
        tiprack = LabwareInstance(
            LABWARE_TIPRACK_96,
            slot,
            label=f"tiprack_slot{slot_id}",
            deck=deck,
        )

        t = tiprack.type
        z_safe = t.safe_z
        z_touch = t.tip_touch_z
        z_press = t.tip_press_z
        z_full = t.tip_full_z

        if z_touch is None or z_press is None or z_full is None:
            raise RuntimeError("Tiprack LabwareType missing tip Z settings.")

        self.set_absolute_mode()

        # 1) 抬到安全高度 / move up to safe height
        self.move_to(z=z_safe, feedrate=750.0)

        # 2) 移动到指定孔位上方 / move above target well
        x, y = tiprack.well_position_machine(well)
        self.move_to(x=x, y=y, feedrate=7500.0)

        # 3) 下到“刚接触”高度 / go to touch height
        self.move_to(z=z_touch, feedrate=750.0)
        self.dwell(0.2)

        # 4) 上下“捣几次”帮助对准和插入 / up-down cycles
        for _ in range(n_cycles):
            self.move_to(z=z_press, feedrate=600.0)
            self.dwell(0.2)
            self.move_to(z=z_touch, feedrate=600.0)
            self.dwell(0.2)

        # 5) 一插到底 / final full insertion
        self.move_to(z=z_full, feedrate=750.0)
        self.dwell(0.2)

        # 6) 略微抬起到 press 高度，再回安全高度 / slightly up then safe height
        self.move_to(z=z_press, feedrate=750.0)
        self.move_to(z=z_safe, feedrate=600.0)

    def drop_tip_scrape(
        self,
        deck: Deck,
        slot_id: str,
        edge: str = "left",
        slot_half_width: float = 64.0,   # 写死：槽位中心到边界约 64 mm
        extra_scrape: float = 20.0,      # 多蹭出去的距离（固定为 10 mm）
    ) -> None:
        """
        Remove a used tip by scraping it against the wall of a tip waste box.

        通过将 tip 在废 tip 盒的侧壁“蹭”出来，从而抛弃用过的 tip。
        """

        slot = deck.slots[slot_id]
        waste = LabwareInstance(
            LABWARE_TIPWASTE_BOX,
            slot,
            label=f"tipwaste_slot{slot_id}",
            deck=deck,
        )

        t = waste.type
        z_safe = t.safe_z
        z_scrape = t.scrape_z
        if z_scrape is None:
            raise RuntimeError("Tip waste LabwareType missing scrape_z.")

        cx, cy = deck.slot_center_machine(slot_id)

        self.set_absolute_mode()

        # 1) 抬到安全高度
        self.move_to(z=z_safe, feedrate=600.0)

        # 2) 去槽位中心
        self.move_to(x=cx, y=cy, feedrate=7500.0)

        # 3) 下到蹭 tip 的高度
        self.move_to(z=z_scrape, feedrate=750.0)

        # 4) 计算左右蹭掉的位置
        if edge == "left":
            x_target = cx - slot_half_width - extra_scrape  # 左边界外多 10 mm
        elif edge == "right":
            x_target = cx + slot_half_width + extra_scrape  # 右边界外多 10 mm
        else:
            raise ValueError("edge must be 'left' or 'right'.")

        # 侧向蹭掉 tip
        self.move_to(x=x_target, y=cy, feedrate=2000.0)

        # 5) 抬回安全高度
        self.move_to(z=z_safe, feedrate=600.0)


    # --------------------------------------------------
    # 高层功能：移液 / Liquid transfer
    # --------------------------------------------------

    def transfer_volume(
        self,
        deck: Deck,
        src_slot: str,
        src_well: str,
        dst_slot: str,
        dst_well: str,
        volume_ul: float,
        syringe: str = "10ml",
        feed_xy: float = 3000.0,
        feed_z_down: float = 200.0,
        feed_z_up: float = 300.0,
        feed_u: float = 200.0,
    ) -> None:
        """
        Transfer a given volume from (src_slot, src_well) to (dst_slot, dst_well).

        使用当前注射器标定，将指定体积的液体，从源孔转移到目标孔。

        Args:
            deck:      Deck 实例
            src_slot:  源板所在槽位编号，例如 "4"
            src_well:  源孔位，例如 "A1"
            dst_slot:  目标板所在槽位编号
            dst_well:  目标孔位
            volume_ul: 需要转移的体积（µL）
            syringe:   使用的注射器名称，例如 "10ml"
            feed_xy:   XY 平面移动速度 (mm/min)
            feed_z_down/up: Z 方向下降/上升速度
            feed_u:    U 轴推拉速度
        """
        # 选择注射器类型 / select syringe type
        syr = self._get_syringe(syringe)

        # 计算 U 轴行程 / compute U travel
        dU = volume_ul * syr.u_per_ul
        u_base = syr.u_base
        u_asp = u_base + dU

        if syr.u_min is not None and u_base < syr.u_min:
            raise ValueError("u_base below syringe u_min.")
        if syr.u_max is not None and u_asp > syr.u_max:
            raise ValueError("U travel exceeds syringe u_max, check volume.")

        # 源、目标板实例（这里假设使用的是同一类 48 孔板）
        # Instantiate source and destination plates (48-well in this example)
        src_plate = LabwareInstance(
            LABWARE_48WELL_10MM,
            deck.slots[src_slot],
            label=f"plate_src_slot{src_slot}",
            deck=deck,
        )
        dst_plate = LabwareInstance(
            LABWARE_48WELL_10MM,
            deck.slots[dst_slot],
            label=f"plate_dst_slot{dst_slot}",
            deck=deck,
        )

        t_src = src_plate.type
        t_dst = dst_plate.type

        # Z 高度：安全高度 + 吸液高度 + 注液高度
        # Z heights
        z_safe_src = t_src.safe_z
        z_asp = t_src.aspirate_z or t_src.bottom_z

        z_safe_dst = t_dst.safe_z
        z_disp = t_dst.dispense_z or t_dst.bottom_z

        self.set_absolute_mode()

        # ---------- 吸液阶段 / Aspirate ----------
        # 1) U 回到基准位置 / reset U to base
        self.move_to(u=u_base, feedrate=feed_u)

        # 2) 抬到源板安全高度 / safe Z above source plate
        self.move_to(z=z_safe_src, feedrate=feed_z_up)

        # 3) XY 移到源孔 / move to source well
        x_src, y_src = src_plate.well_position_machine(src_well)
        self.move_to(x=x_src, y=y_src, feedrate=feed_xy)

        # 4) 下探到吸液高度 / go down to aspiration height
        self.move_to(z=z_asp, feedrate=feed_z_down)

        # 5) U 轴向外拉，完成吸液 / pull plunger to aspirate
        self.move_to(u=u_asp, feedrate=feed_u)

        # 6) 抬回安全高度 / back to safe Z
        self.move_to(z=z_safe_src, feedrate=feed_z_up)

        # ---------- 注液阶段 / Dispense ----------
        # 1) 抬到目标板安全高度 / safe Z above destination plate
        self.move_to(z=z_safe_dst, feedrate=feed_z_up)

        # 2) XY 移动到目标孔 / move to destination well
        x_dst, y_dst = dst_plate.well_position_machine(dst_well)
        self.move_to(x=x_dst, y=y_dst, feedrate=feed_xy)

        # 3) 下探到注液高度 / go down to dispense height
        self.move_to(z=z_disp, feedrate=feed_z_down)

        # 4) U 轴回到基准位置，完成注液 / push plunger back to base
        self.move_to(u=u_base, feedrate=feed_u)

        # 5) 抬回安全高度 / back to safe Z
        self.move_to(z=z_safe_dst, feedrate=feed_z_up)

    # --------------------------------------------------
    # 高层功能：显式吸液 / 排液
    # Explicit aspirate / dispense (no internal volume tracking)
    # --------------------------------------------------

    def aspirate(
        self,
        volume_ul: float,
        syringe: str | None = None,
        deck: Optional[Deck] = None,
        slot_id: Optional[str] = None,
        labware_type: LabwareType = LABWARE_48WELL_10MM,
        well: Optional[str] = None,
        z_safe: Optional[float] = None,
        z_aspirate: Optional[float] = None,
        feed_xy: float = 7500.0,
        feed_z_down: float = 600.0,
        feed_z_up: float = 750.0,
        feed_u: float = 200.0,
    ) -> None:
        """
        Aspirate a given volume by pulling the U axis.

        显式执行一次“吸液”动作，通过 U 轴的相对移动完成拉液，
        不在内部记录或检查当前注射器内的液量。

        两种使用方式：
        1) 基于孔位：
           传入 deck + slot_id + well，不传 z_safe / z_aspirate。
           将自动根据该槽位的 48 孔板几何信息确定安全高度和吸液高度。
        2) 基于当前 XY：
           不传 deck/slot_id/well，而传入 z_safe、z_aspirate，
           在当前 XY 位置上下移动 Z，然后相对移动 U 轴。

        Args:
            volume_ul:   本次需要吸入的体积（µL）
            syringe:     使用的注射器名称；若为 None，则使用 set_syringe() 设定的当前注射器
            deck:        Deck 实例；用于按 slot + well 方式寻址
            slot_id:     槽位编号（如 "4"），用于孔位吸液模式
            well:        孔位编号（如 "A1"）
            z_safe:      当前 XY 模式下的安全 Z 高度（若不使用 slot/well）
            z_aspirate:  当前 XY 模式下的吸液高度
            feed_xy:     XY 平面移动速度
            feed_z_down: Z 方向下降速度
            feed_z_up:   Z 方向上升速度
            feed_u:      U 轴移动速度（mm/min）
        """
        syr = self._get_syringe(syringe)
        dU = volume_ul * syr.u_per_ul  # 本次需要拉动的 U 行程（相对） / relative U travel

        self.set_absolute_mode()

        # 模式一：基于 slot + well 的吸液（默认使用 48 孔板）
        if deck is not None and slot_id is not None and well is not None:
            plate = LabwareInstance(
                labware_type,
                deck.slots[slot_id],
                label=f"asp_plate_slot{slot_id}",
                deck=deck,
            )
            t = plate.type
            z_safe_local = t.safe_z
            z_asp_local = t.aspirate_z or t.bottom_z

            # 1) 抬到安全高度
            # self.move_to(z=z_safe_local, feedrate=feed_z_up)

            # 2) XY 移到指定孔位
            # x, y = plate.well_position_machine(well)
            # self.move_to(x=x, y=y, feedrate=feed_xy)

            # 调整为先移动XY再移动Z
            # self.move_to(z=z_safe_local, feedrate=feed_z_up)

            if labware_type is LABWARE_BEAKER_1WELL:
                # 目标是烧杯：先抬 Z 再走 XY，避免用孔板的低高度撞杯壁
                self.move_to(z=z_safe_local, feedrate=feed_z_up)
                x, y = plate.well_position_machine(well)
                self.move_to(x=x, y=y, feedrate=feed_xy)
            else:
                # 目标是孔板：假定当前已经在足够高的安全高度，
                # 先 XY 离开烧杯区域，再按孔板几何调整 Z
                x, y = plate.well_position_machine(well)
                self.move_to(x=x, y=y, feedrate=feed_xy)

            # 3) 下探到吸液高度
            self.move_to(z=z_asp_local, feedrate=feed_z_down)

            # 4) U 轴相对拉动，完成吸液
            self.move_relative(du=dU, feedrate=feed_u)

            # 5) 回到安全高度
            self.move_to(z=z_safe_local, feedrate=feed_z_up)
            return

        # 模式二：基于当前 XY 的吸液（例如烧杯）
        if z_safe is None or z_aspirate is None:
            raise ValueError(
                "For current-XY aspirate, z_safe and z_aspirate must be provided. "
                "当前 XY 吸液模式需要显式给出 z_safe 和 z_aspirate。"
            )

        # 1) 抬到安全高度
        self.move_to(z=z_safe, feedrate=feed_z_up)
        # 2) 下探到吸液高度
        self.move_to(z=z_aspirate, feedrate=feed_z_down)
        # 3) U 轴相对拉动
        self.move_relative(du=dU, feedrate=feed_u)
        # 4) 回到安全高度
        self.move_to(z=z_safe, feedrate=feed_z_up)

    def dispense(
        self,
        volume_ul: float,
        syringe: str | None = None,
        deck: Optional[Deck] = None,
        slot_id: Optional[str] = None,
        labware_type: LabwareType = LABWARE_48WELL_10MM,
        well: Optional[str] = None,
        z_safe: Optional[float] = None,
        z_dispense: Optional[float] = None,
        feed_xy: float = 7500.0,
        feed_z_down: float = 600.0,
        feed_z_up: float = 750.0,
        feed_u: float = 200.0,
    ) -> None:
        """
        Dispense a given volume by pushing the U axis.

        显式执行一次“排液”动作，通过 U 轴的相对移动完成推出，
        不在内部记录或检查当前注射器内的剩余液量。

        两种使用方式与 aspirate 相同：
        1) 基于孔位（deck + slot_id + well），自动采用 48 孔板的安全高度和注液高度；
        2) 基于当前 XY（z_safe + z_dispense），例如烧杯中心位置。

        Args:
            volume_ul:   本次需要排出的体积（µL）
            syringe:     使用的注射器名称；若为 None，则使用当前注射器
            deck:        Deck 实例；用于按 slot + well 方式寻址
            slot_id:     槽位编号（如 "4"）
            well:        孔位编号（如 "A1"）
            z_safe:      当前 XY 模式下的安全 Z 高度
            z_dispense:  当前 XY 模式下的注液高度
            feed_xy:     XY 平面移动速度
            feed_z_down: Z 方向下降速度
            feed_z_up:   Z 方向上升速度
            feed_u:      U 轴移动速度（mm/min）
        """
        syr = self._get_syringe(syringe)
        dU = volume_ul * syr.u_per_ul  # 本次需要推回的 U 行程（相对）

        self.set_absolute_mode()

        # 模式一：基于 slot + well 的排液（48 孔板）
        if deck is not None and slot_id is not None and well is not None:
            plate = LabwareInstance(
                labware_type,
                deck.slots[slot_id],
                label=f"disp_plate_slot{slot_id}",
                deck=deck,
            )
            t = plate.type
            z_safe_local = t.safe_z
            z_disp_local = t.dispense_z or t.bottom_z

            if labware_type is LABWARE_BEAKER_1WELL:
                # 目标是烧杯：先抬 Z 再走 XY，避免用孔板的低高度撞杯壁
                self.move_to(z=z_safe_local, feedrate=feed_z_up)
                x, y = plate.well_position_machine(well)
                self.move_to(x=x, y=y, feedrate=feed_xy)
            else:
                # 目标是孔板：假定当前已经在足够高的安全高度，
                # 先 XY 离开烧杯区域，再按孔板几何调整 Z
                x, y = plate.well_position_machine(well)
                self.move_to(x=x, y=y, feedrate=feed_xy)

            # 3) 下探到注液高度
            self.move_to(z=z_disp_local, feedrate=feed_z_down)

            # 4) U 轴相对推回，完成排液
            self.move_relative(du=-dU, feedrate=feed_u)

            # 5) 回到安全高度
            self.move_to(z=z_safe_local, feedrate=feed_z_up)
            return

        # 模式二：基于当前 XY 的排液（例如烧杯）
        if z_safe is None or z_dispense is None:
            raise ValueError(
                "For current-XY dispense, z_safe and z_dispense must be provided. "
                "当前 XY 排液模式需要显式给出 z_safe 和 z_dispense。"
            )

        # 1) 抬到安全高度
        self.move_to(z=z_safe, feedrate=feed_z_up)
        # 2) 下探到注液高度
        self.move_to(z=z_dispense, feedrate=feed_z_down)
        # 3) U 轴相对推回
        self.move_relative(du=-dU, feedrate=feed_u)
        # 4) 回到安全高度
        self.move_to(z=z_safe, feedrate=feed_z_up)

    def dispense_to_beaker(
        self,
        deck: Deck,
        slot_id: str,
        volume_ul: float,
        syringe: str | None = None,
        feed_xy: float = 7500.0,
        feed_z_down: float = 600.0,
        feed_z_up: float = 750.0,
        feed_u: float = 200.0,
    ) -> None:
        """
        向某个槽位中心的烧杯排液。
        默认使用 LABWARE_BEAKER_1WELL，在该 slot 的 A1 位置。
        """
        self.dispense(
            volume_ul=volume_ul,
            syringe=syringe,
            deck=deck,
            slot_id=slot_id,
            well="A1",                          # 烧杯唯一的“孔位”
            labware_type=LABWARE_BEAKER_1WELL,  # ★ 用烧杯几何
            feed_xy=feed_xy,
            feed_z_down=feed_z_down,
            feed_z_up=feed_z_up,
            feed_u=feed_u,
        )
        
    def aspirate_from_beaker(
        self,
        deck: Deck,
        slot_id: str,
        volume_ul: float,
        syringe: str | None = None,
        feed_xy: float = 7500.0,
        feed_z_down: float = 600.0,
        feed_z_up: float = 750.0,
        feed_u: float = 200.0,
    ) -> None:
        """
        向某个槽位中心的烧杯排液。
        默认使用 LABWARE_BEAKER_1WELL，在该 slot 的 A1 位置。
        """
        self.aspirate(
            volume_ul=volume_ul,
            syringe=syringe,
            deck=deck,
            slot_id=slot_id,
            well="A1",                          # 烧杯唯一的“孔位”
            labware_type=LABWARE_BEAKER_1WELL,  # ★ 用烧杯几何
            feed_xy=feed_xy,
            feed_z_down=feed_z_down,
            feed_z_up=feed_z_up,
            feed_u=feed_u,
        )
