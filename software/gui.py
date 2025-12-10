from __future__ import annotations

"""
Improved GUI for the pipette robot.

Changes:
- Language toggle (English / 中文) at top-left.
- Tip operations (pick / drop) in one tab.
- Transfer and Position/Jog in one tab.
- Protocol tab with extra step types: aspirate / dispense.
"""

import json
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from src.robot import Robot
from src.deck import Deck
from src.labware import SYRINGES, LABWARE_BEAKER_1WELL
import requests


GPT_API_URL = "http://43.165.0.74:8000/generate_protocol"


class PipetteGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root

        # 当前语言：zh / en
        self.current_lang = "zh"
        self.root.title(self._l("Pipette Robot GUI", "移液机器人界面"))

        self.robot: Robot | None = None
        self.deck: Deck | None = None
        self.protocol_steps: list[dict] = []

        # ---------- 样式 ----------
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TLabelframe", padding=8)
        style.configure("TButton", padding=4)
        style.configure("TNotebook.Tab", padding=(12, 6))

        # 顶部语言切换条
        topbar = ttk.Frame(root)
        topbar.pack(fill="x", padx=8, pady=(8, 4))

        self.btn_lang = ttk.Button(topbar, command=self.on_toggle_language)
        self._update_lang_button_text()
        self.btn_lang.pack(side="left")

        # 主容器
        self.main_frame = ttk.Frame(root)
        self.main_frame.pack(fill="both", expand=True)

        self._build_main_ui()

    # ==================================================
    # 语言
    # ==================================================
    def _l(self, en: str, zh: str) -> str:
        return zh if self.current_lang == "zh" else en

    def _update_lang_button_text(self) -> None:
        if self.current_lang == "zh":
            self.btn_lang.config(text="English")
        else:
            self.btn_lang.config(text="中文")

    def on_toggle_language(self) -> None:
        self.current_lang = "en" if self.current_lang == "zh" else "zh"
        self.root.title(self._l("Pipette Robot GUI", "移液机器人界面"))
        self._update_lang_button_text()

        for child in self.main_frame.winfo_children():
            child.destroy()
        self._build_main_ui()

    # ==================================================
    # 主界面
    # ==================================================
    def _build_main_ui(self) -> None:
        # ---------- 连接 / 回零 ----------
        frm_top = ttk.LabelFrame(
            self.main_frame,
            text=self._l("Connection / Homing", "连接与回零"),
        )
        frm_top.pack(fill="x", padx=8, pady=4)

        ttk.Label(frm_top, text=self._l("Port:", "串口:")).grid(
            row=0, column=0, sticky="w", padx=4, pady=2
        )
        self.var_port = tk.StringVar(value="COM4")
        ttk.Entry(frm_top, textvariable=self.var_port, width=10).grid(
            row=0, column=1, padx=4, pady=2
        )

        ttk.Button(
            frm_top,
            text=self._l("Connect", "连接"),
            command=self.on_connect,
        ).grid(row=0, column=2, padx=4, pady=2)
        ttk.Button(
            frm_top,
            text=self._l("Disconnect", "断开"),
            command=self.on_disconnect,
        ).grid(row=0, column=3, padx=4, pady=2)

        ttk.Button(
            frm_top,
            text=self._l("Home XYZ", "回零 XYZ"),
            command=self.on_home_xyz,
        ).grid(row=1, column=0, padx=4, pady=2)
        ttk.Button(
            frm_top,
            text=self._l("Home All", "全轴回零"),
            command=self.on_home_all,
        ).grid(row=1, column=1, padx=4, pady=2)

        ttk.Label(frm_top, text=self._l("Syringe:", "注射器:")).grid(
            row=0, column=4, sticky="e", padx=4, pady=2
        )
        self.var_syringe = tk.StringVar(value="1ml")
        cmb_syr = ttk.Combobox(
            frm_top,
            textvariable=self.var_syringe,
            values=list(SYRINGES.keys()),
            width=8,
            state="readonly",
        )
        cmb_syr.grid(row=0, column=5, padx=4, pady=2)

        # ---------- Notebook ----------
        nb = ttk.Notebook(self.main_frame)
        nb.pack(fill="both", expand=True, padx=8, pady=4)

        self._build_tab_tips(nb)
        self._build_tab_work(nb)
        self._build_tab_protocol(nb)
        self._build_tab_gpt_chat(nb)

        # ---------- 日志 ----------
        frm_log = ttk.LabelFrame(self.main_frame, text=self._l("Log", "日志"))
        frm_log.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.txt_log = tk.Text(frm_log, height=8, wrap="word")
        self.txt_log.pack(fill="both", expand=True, padx=4, pady=4)

    # ==================================================
    # Tab1：Tips（戴 / 扔）
    # ==================================================
    def _build_tab_tips(self, nb: ttk.Notebook) -> None:
        frm = ttk.Frame(nb)
        nb.add(frm, text=self._l("Tips", "吸头操作"))

        # 戴 tip
        frm_pick = ttk.LabelFrame(frm, text=self._l("Pick Tip", "戴吸头"))
        frm_pick.grid(row=0, column=0, padx=8, pady=8, sticky="nsew")

        ttk.Label(frm_pick, text=self._l("Slot:", "槽位:")).grid(
            row=0, column=0, padx=4, pady=4, sticky="e"
        )
        ttk.Label(frm_pick, text=self._l("Well:", "孔位:")).grid(
            row=1, column=0, padx=4, pady=4, sticky="e"
        )

        self.var_tip_slot = tk.StringVar(value="1")
        self.var_tip_well = tk.StringVar(value="A1")

        ttk.Entry(frm_pick, textvariable=self.var_tip_slot, width=6).grid(
            row=0, column=1, padx=4, pady=4
        )
        ttk.Entry(frm_pick, textvariable=self.var_tip_well, width=6).grid(
            row=1, column=1, padx=4, pady=4
        )

        ttk.Button(
            frm_pick,
            text=self._l("Pick Up Tip", "戴吸头"),
            command=self.on_pick_tip,
        ).grid(row=2, column=0, columnspan=2, padx=4, pady=8)

        # 扔 tip
        frm_drop = ttk.LabelFrame(frm, text=self._l("Drop Tip", "扔吸头"))
        frm_drop.grid(row=0, column=1, padx=8, pady=8, sticky="nsew")

        ttk.Label(frm_drop, text=self._l("Waste Slot:", "废槽位:")).grid(
            row=0, column=0, padx=4, pady=4, sticky="e"
        )
        self.var_waste_slot = tk.StringVar(value="2")
        ttk.Entry(frm_drop, textvariable=self.var_waste_slot, width=6).grid(
            row=0, column=1, padx=4, pady=4
        )

        ttk.Label(frm_drop, text=self._l("Edge:", "方向:")).grid(
            row=1, column=0, padx=4, pady=4, sticky="e"
        )
        self.var_edge = tk.StringVar(value="left")
        cmb_edge = ttk.Combobox(
            frm_drop,
            textvariable=self.var_edge,
            values=["left", "right"],
            width=8,
            state="readonly",
        )
        cmb_edge.grid(row=1, column=1, padx=4, pady=4)

        ttk.Button(
            frm_drop,
            text=self._l("Scrape Tip", "去除吸头"),
            command=self.on_drop_tip,
        ).grid(row=2, column=0, columnspan=2, padx=4, pady=8)

        frm.columnconfigure(0, weight=1)
        frm.columnconfigure(1, weight=1)

    # ==================================================
    # Tab2：Work（移液 + 坐标/Jog）
    # ==================================================
    def _build_tab_work(self, nb: ttk.Notebook) -> None:
        frm = ttk.Frame(nb)
        nb.add(frm, text=self._l("Work", "移液 / 坐标"))

        # 左侧：移液
        frm_transfer = ttk.LabelFrame(frm, text=self._l("Transfer", "移液"))
        frm_transfer.grid(row=0, column=0, padx=8, pady=8, sticky="nsew")

        ttk.Label(frm_transfer, text=self._l("Src Slot:", "源槽位:")).grid(
            row=0, column=0, padx=4, pady=2, sticky="e"
        )
        ttk.Label(frm_transfer, text=self._l("Src Well:", "源孔:")).grid(
            row=1, column=0, padx=4, pady=2, sticky="e"
        )

        self.var_src_slot = tk.StringVar(value="4")
        self.var_src_well = tk.StringVar(value="A1")

        ttk.Entry(frm_transfer, textvariable=self.var_src_slot, width=6).grid(
            row=0, column=1, padx=4, pady=2
        )
        ttk.Entry(frm_transfer, textvariable=self.var_src_well, width=6).grid(
            row=1, column=1, padx=4, pady=2
        )

        ttk.Label(frm_transfer, text=self._l("Dst Slot:", "目标槽位:")).grid(
            row=0, column=2, padx=4, pady=2, sticky="e"
        )
        ttk.Label(frm_transfer, text=self._l("Dst Well:", "目标孔:")).grid(
            row=1, column=2, padx=4, pady=2, sticky="e"
        )

        self.var_dst_slot = tk.StringVar(value="4")
        self.var_dst_well = tk.StringVar(value="B3")

        ttk.Entry(frm_transfer, textvariable=self.var_dst_slot, width=6).grid(
            row=0, column=3, padx=4, pady=2
        )
        ttk.Entry(frm_transfer, textvariable=self.var_dst_well, width=6).grid(
            row=1, column=3, padx=4, pady=2
        )

        ttk.Label(frm_transfer, text=self._l("Volume (µL):", "体积 (µL):")).grid(
            row=2, column=0, padx=4, pady=4, sticky="e"
        )
        self.var_volume = tk.StringVar(value="50.0")
        ttk.Entry(frm_transfer, textvariable=self.var_volume, width=8).grid(
            row=2, column=1, padx=4, pady=4
        )

        ttk.Button(
            frm_transfer,
            text=self._l("Transfer", "执行移液"),
            command=self.on_transfer,
        ).grid(row=3, column=0, columnspan=4, padx=4, pady=8)

        # 右侧：坐标 + Jog
        frm_pos = ttk.LabelFrame(frm, text=self._l("Position (M114)", "坐标 (M114)"))
        frm_pos.grid(row=0, column=1, padx=8, pady=8, sticky="nsew")

        self.var_pos_x = tk.StringVar(value="0.0")
        self.var_pos_y = tk.StringVar(value="0.0")
        self.var_pos_z = tk.StringVar(value="0.0")
        self.var_pos_u = tk.StringVar(value="0.0")

        ttk.Label(frm_pos, text="X:").grid(row=0, column=0, padx=4, pady=2, sticky="e")
        ttk.Label(frm_pos, text="Y:").grid(row=1, column=0, padx=4, pady=2, sticky="e")
        ttk.Label(frm_pos, text="Z:").grid(row=2, column=0, padx=4, pady=2, sticky="e")
        ttk.Label(frm_pos, text="U:").grid(row=3, column=0, padx=4, pady=2, sticky="e")

        ttk.Entry(frm_pos, textvariable=self.var_pos_x, width=10, state="readonly").grid(
            row=0, column=1, padx=4, pady=2
        )
        ttk.Entry(frm_pos, textvariable=self.var_pos_y, width=10, state="readonly").grid(
            row=1, column=1, padx=4, pady=2
        )
        ttk.Entry(frm_pos, textvariable=self.var_pos_z, width=10, state="readonly").grid(
            row=2, column=1, padx=4, pady=2
        )
        ttk.Entry(frm_pos, textvariable=self.var_pos_u, width=10, state="readonly").grid(
            row=3, column=1, padx=4, pady=2
        )

        ttk.Button(
            frm_pos,
            text=self._l("Refresh", "刷新"),
            command=self.on_refresh_position,
        ).grid(row=4, column=0, columnspan=2, padx=4, pady=4)

        frm_jog = ttk.LabelFrame(frm_pos, text=self._l("Jog", "Jog 控制"))
        frm_jog.grid(row=0, column=2, rowspan=5, padx=8, pady=4, sticky="nsew")

        ttk.Label(frm_jog, text=self._l("Step (mm):", "步长 (mm):")).grid(
            row=0, column=0, padx=4, pady=2, sticky="e"
        )
        self.var_jog_step = tk.StringVar(value="1.0")
        cmb_step = ttk.Combobox(
            frm_jog,
            textvariable=self.var_jog_step,
            values=["0.1", "0.5", "1.0", "5.0", "10.0"],
            width=6,
            state="readonly",
        )
        cmb_step.grid(row=0, column=1, padx=4, pady=2)

        ttk.Button(frm_jog, text="Y+", command=lambda: self.on_jog(0, +1, 0, 0)).grid(
            row=1, column=1, padx=4, pady=2
        )
        ttk.Button(frm_jog, text="Y-", command=lambda: self.on_jog(0, -1, 0, 0)).grid(
            row=3, column=1, padx=4, pady=2
        )
        ttk.Button(frm_jog, text="X-", command=lambda: self.on_jog(-1, 0, 0, 0)).grid(
            row=2, column=0, padx=4, pady=2
        )
        ttk.Button(frm_jog, text="X+", command=lambda: self.on_jog(+1, 0, 0, 0)).grid(
            row=2, column=2, padx=4, pady=2
        )

        ttk.Button(frm_jog, text="Z+", command=lambda: self.on_jog(0, 0, +1, 0)).grid(
            row=1, column=3, padx=4, pady=2
        )
        ttk.Button(frm_jog, text="Z-", command=lambda: self.on_jog(0, 0, -1, 0)).grid(
            row=3, column=3, padx=4, pady=2
        )

        ttk.Button(frm_jog, text="U+", command=lambda: self.on_jog(0, 0, 0, +1)).grid(
            row=1, column=4, padx=4, pady=2
        )
        ttk.Button(frm_jog, text="U-", command=lambda: self.on_jog(0, 0, 0, -1)).grid(
            row=3, column=4, padx=4, pady=2
        )

        frm.columnconfigure(0, weight=1)
        frm.columnconfigure(1, weight=1)

    # ==================================================
    # Tab3：Protocol（含 aspirate / dispense）
    # ==================================================
    def _build_tab_protocol(self, nb: ttk.Notebook) -> None:
        frm = ttk.Frame(nb)
        nb.add(frm, text=self._l("Protocol", "协议"))

        ttk.Label(frm, text=self._l("Step Type:", "步骤类型:")).grid(
            row=0, column=0, padx=4, pady=2, sticky="e"
        )
        self.var_step_type = tk.StringVar(value="transfer")
        cmb_type = ttk.Combobox(
            frm,
            textvariable=self.var_step_type,
            values=[
                "home_xyz",
                "pick_tip",
                "drop_tip",
                "transfer",
                "aspirate",
                "dispense",
                "dwell",
            ],
            width=12,
            state="readonly",
        )
        cmb_type.grid(row=0, column=1, padx=4, pady=2)

        ttk.Label(frm, text=self._l("Params (JSON):", "参数 (JSON):")).grid(
            row=1, column=0, padx=4, pady=2, sticky="ne"
        )
        self.txt_step_params = tk.Text(frm, height=6, width=52)
        self.txt_step_params.grid(row=1, column=1, columnspan=3, padx=4, pady=2)

        if self.current_lang == "en":
            example = (
                "Examples:\n"
                "transfer: {\"src_slot\":\"4\",\"src_well\":\"A1\","
                "\"dst_slot\":\"4\",\"dst_well\":\"B3\",\"volume_ul\":50}\n"
                "pick_tip: {\"slot\":\"1\",\"well\":\"A1\"}\n"
                "drop_tip: {\"slot\":\"2\",\"edge\":\"left\"}\n"
                "aspirate well: {\"slot\":\"4\",\"well\":\"A1\",\"volume_ul\":50}\n"
                "aspirate XY:   {\"z_safe\":152.0,\"z_aspirate\":158.0,\"volume_ul\":50}\n"
                "dispense well: {\"slot\":\"4\",\"well\":\"B3\",\"volume_ul\":50}\n"
                "dispense XY:   {\"z_safe\":152.0,\"z_dispense\":158.0,\"volume_ul\":50}\n"
                "dwell: {\"seconds\":2.0}"
            )
        else:
            example = (
                "示例:\n"
                "transfer: {\"src_slot\":\"4\",\"src_well\":\"A1\","
                "\"dst_slot\":\"4\",\"dst_well\":\"B3\",\"volume_ul\":50}\n"
                "pick_tip: {\"slot\":\"1\",\"well\":\"A1\"}\n"
                "drop_tip: {\"slot\":\"2\",\"edge\":\"left\"}\n"
                "aspirate 孔位: {\"slot\":\"4\",\"well\":\"A1\",\"volume_ul\":50}\n"
                "aspirate 当前XY: {\"z_safe\":152.0,\"z_aspirate\":158.0,\"volume_ul\":50}\n"
                "dispense 孔位: {\"slot\":\"4\",\"well\":\"B3\",\"volume_ul\":50}\n"
                "dispense 当前XY: {\"z_safe\":152.0,\"z_dispense\":158.0,\"volume_ul\":50}\n"
                "dwell: {\"seconds\":2.0}"
            )

        ttk.Label(frm, text=example, justify="left").grid(
            row=2, column=0, columnspan=4, padx=4, pady=2, sticky="w"
        )

        ttk.Label(frm, text=self._l("Steps:", "步骤列表:")).grid(
            row=3, column=0, padx=4, pady=2, sticky="w"
        )
        self.lst_steps = tk.Listbox(frm, height=8, width=70)
        self.lst_steps.grid(row=4, column=0, columnspan=4, padx=4, pady=2, sticky="nsew")

        # 语言切换时重建列表
        for i, step in enumerate(self.protocol_steps, start=1):
            self.lst_steps.insert("end", f"{i:02d}. {step.get('type')} {step.get('params')}")

        ttk.Button(
            frm,
            text=self._l("Add Step", "添加步骤"),
            command=self.on_add_step,
        ).grid(row=5, column=0, padx=4, pady=4)

        ttk.Button(
            frm,
            text=self._l("Delete Selected", "删除选中"),
            command=self.on_delete_step,
        ).grid(row=5, column=1, padx=4, pady=4)

        ttk.Button(
            frm,
            text=self._l("Save Protocol", "保存协议"),
            command=self.on_save_protocol,
        ).grid(row=5, column=2, padx=4, pady=4)

        ttk.Button(
            frm,
            text=self._l("Load Protocol", "载入协议"),
            command=self.on_load_protocol,
        ).grid(row=5, column=3, padx=4, pady=4)

        ttk.Button(
            frm,
            text=self._l("Run Protocol", "执行协议"),
            command=self.on_run_protocol,
        ).grid(row=6, column=0, columnspan=4, padx=4, pady=6)

        frm.rowconfigure(4, weight=1)
        frm.columnconfigure(1, weight=1)
        frm.columnconfigure(2, weight=1)

    # ==================================================
    # 工具函数
    # ==================================================
    def log(self, text: str) -> None:
        self.txt_log.insert("end", text + "\n")
        self.txt_log.see("end")
        self.root.update_idletasks()

    def require_robot(self) -> Robot:
        if self.robot is None or self.deck is None:
            messagebox.showerror(
                self._l("Error", "错误"),
                self._l("Robot not connected.", "未连接机器人。"),
            )
            raise RuntimeError("Robot not connected.")
        return self.robot

    def _get_jog_step(self) -> float:
        try:
            return float(self.var_jog_step.get())
        except Exception:
            return 1.0

    # ==================================================
    # 连接 / 回零
    # ==================================================
    def on_connect(self) -> None:
        try:
            port = self.var_port.get().strip()
            self.robot = Robot(port)
            self.deck = Deck()
            syringe_name = self.var_syringe.get()
            self.robot.set_syringe(syringe_name)
            self.log(f"Connected to {port}, syringe={syringe_name}")
        except Exception as e:
            messagebox.showerror(self._l("Error", "错误"), f"Connect failed: {e}")
            self.log(f"[ERROR] Connect failed: {e}")

    def on_disconnect(self) -> None:
        if self.robot is not None:
            try:
                self.robot.disconnect()
                self.log("Disconnected.")
            except Exception as e:
                self.log(f"[WARN] Disconnect error: {e}")
        self.robot = None
        self.deck = None

    def on_home_xyz(self) -> None:
        try:
            robot = self.require_robot()
            self.log("Homing XYZ...")
            robot.home("XYZ", timeout=9999.0)
            self.log("Homing XYZ done.")
        except Exception as e:
            messagebox.showerror(self._l("Error", "错误"), f"Homing XYZ failed: {e}")
            self.log(f"[ERROR] Homing XYZ: {e}")

    def on_home_all(self) -> None:
        try:
            robot = self.require_robot()
            self.log("Homing all axes...")
            robot.home_all(timeout=9999.0)
            self.log("Homing all axes done.")
        except Exception as e:
            messagebox.showerror(self._l("Error", "错误"), f"Homing all failed: {e}")
            self.log(f"[ERROR] Homing all: {e}")

    # ==================================================
    # Tip 操作
    # ==================================================
    def on_pick_tip(self) -> None:
        try:
            robot = self.require_robot()
            slot_id = self.var_tip_slot.get().strip()
            well = self.var_tip_well.get().strip()
            self.log(f"Pick tip: slot={slot_id}, well={well}")
            robot.pick_up_tip(self.deck, slot_id=slot_id, well=well)
            self.log("Pick tip done.")
        except Exception as e:
            messagebox.showerror(self._l("Error", "错误"), f"Pick tip failed: {e}")
            self.log(f"[ERROR] Pick tip: {e}")

    def on_drop_tip(self) -> None:
        try:
            robot = self.require_robot()
            slot_id = self.var_waste_slot.get().strip()
            edge = self.var_edge.get()
            self.log(f"Drop tip: slot={slot_id}, edge={edge}")
            robot.drop_tip_scrape(self.deck, slot_id=slot_id, edge=edge)
            self.log("Drop tip done.")
        except Exception as e:
            messagebox.showerror(self._l("Error", "错误"), f"Drop tip failed: {e}")
            self.log(f"[ERROR] Drop tip: {e}")

    # ==================================================
    # 移液
    # ==================================================
    def on_transfer(self) -> None:
        try:
            robot = self.require_robot()
            src_slot = self.var_src_slot.get().strip()
            src_well = self.var_src_well.get().strip()
            dst_slot = self.var_dst_slot.get().strip()
            dst_well = self.var_dst_well.get().strip()
            volume_ul = float(self.var_volume.get().strip())
            syringe_name = self.var_syringe.get()

            self.log(
                f"Transfer {volume_ul} µL from {src_slot}.{src_well} "
                f"to {dst_slot}.{dst_well} (syringe={syringe_name})"
            )

            robot.transfer_volume(
                self.deck,
                src_slot=src_slot,
                src_well=src_well,
                dst_slot=dst_slot,
                dst_well=dst_well,
                volume_ul=volume_ul,
                syringe=syringe_name,
            )
            self.log("Transfer done.")
        except Exception as e:
            messagebox.showerror(self._l("Error", "错误"), f"Transfer failed: {e}")
            self.log(f"[ERROR] Transfer: {e}")

    # ==================================================
    # 坐标 / Jog
    # ==================================================
    def on_refresh_position(self) -> None:
        try:
            robot = self.require_robot()
            pos = robot.get_position()
            if not pos:
                self.log("[WARN] No position data received.")
                return

            self.var_pos_x.set(f"{pos.get('X', 0.0):.3f}")
            self.var_pos_y.set(f"{pos.get('Y', 0.0):.3f}")
            self.var_pos_z.set(f"{pos.get('Z', 0.0):.3f}")
            self.var_pos_u.set(f"{pos.get('U', 0.0):.3f}")
            self.log(f"Position: {pos}")
        except Exception as e:
            messagebox.showerror(self._l("Error", "错误"), f"Get position failed: {e}")
            self.log(f"[ERROR] Get position: {e}")


    def on_jog(self, sx: int, sy: int, sz: int, su: int) -> None:
        try:
            robot = self.require_robot()
            step = self._get_jog_step()

            dx = sx * step
            dy = sy * step
            dz = sz * step
            du = su * step

            # 根据移动的轴自动选择速度
            if sx != 0 or sy != 0:
                feed = 3000.0      # XY 轴速度
            elif sz != 0:
                feed = 1000.0      # Z 轴速度
            elif su != 0:
                feed = 200.0       # U 轴速度
            else:
                feed = 1000.0      # fallback

            self.log(f"Jog: dX={dx}, dY={dy}, dZ={dz}, dU={du}, F={feed}")
            robot.move_relative(dx=dx, dy=dy, dz=dz, du=du, feedrate=feed)

        except Exception as e:
            messagebox.showerror(self._l("Error", "错误"), f"Jog failed: {e}")
            self.log(f"[ERROR] Jog: {e}")


    # ==================================================
    # 协议
    # ==================================================
    def on_add_step(self) -> None:
        try:
            step_type = self.var_step_type.get()
            raw = self.txt_step_params.get("1.0", "end").strip()
            params = json.loads(raw) if raw else {}
            step = {"type": step_type, "params": params}
            self.protocol_steps.append(step)
            self.lst_steps.insert("end", f"{len(self.protocol_steps):02d}. {step_type} {params}")
            self.log(f"Added step: {step}")
        except json.JSONDecodeError as e:
            messagebox.showerror(self._l("Error", "错误"), f"JSON parse error: {e}")
        except Exception as e:
            messagebox.showerror(self._l("Error", "错误"), f"Add step failed: {e}")
            self.log(f"[ERROR] Add step: {e}")

    def on_delete_step(self) -> None:
        try:
            sel = self.lst_steps.curselection()
            if not sel:
                return
            index = sel[0]
            self.lst_steps.delete(index)
            del self.protocol_steps[index]
            self.log(f"Deleted step #{index + 1}")
        except Exception as e:
            messagebox.showerror(self._l("Error", "错误"), f"Delete step failed: {e}")
            self.log(f"[ERROR] Delete step: {e}")

    def on_save_protocol(self) -> None:
        try:
            filename = filedialog.asksaveasfilename(
                title=self._l("Save Protocol", "保存协议"),
                defaultextension=".json",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            )
            if not filename:
                return
            with open(filename, "w", encoding="utf-8") as f:
                # 保留中文，不转义
                json.dump(self.protocol_steps, f, indent=2, ensure_ascii=False)
            self.log(f"Protocol saved to {filename}")
        except Exception as e:
            messagebox.showerror(self._l("Error", "错误"), f"Save protocol failed: {e}")
            self.log(f"[ERROR] Save protocol: {e}")

    def on_load_protocol(self) -> None:
        try:
            filename = filedialog.askopenfilename(
                title=self._l("Load Protocol", "载入协议"),
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            )
            if not filename:
                return
            with open(filename, "r", encoding="utf-8") as f:
                self.protocol_steps = json.load(f)

            # 刷新列表显示
            self.lst_steps.delete(0, "end")
            for i, step in enumerate(self.protocol_steps, start=1):
                self.lst_steps.insert(
                    "end", f"{i:02d}. {step.get('type')} {step.get('params')}"
                )

            self.log(f"Protocol loaded from {filename}")
        except Exception as e:
            messagebox.showerror(self._l("Error", "错误"), f"Load protocol failed: {e}")
            self.log(f"[ERROR] Load protocol: {e}")

    def _run_single_step(self, step: dict) -> None:
        """
        执行单个协议步骤。

        支持的 step type:
        - home_xyz
        - pick_tip
        - drop_tip
        - transfer
        - aspirate
        - dispense
        - dwell
        """
        robot = self.require_robot()
        step_type = step.get("type")
        params = step.get("params", {}) or {}

        if step_type == "home_xyz":
            robot.home("XYZ", timeout=9999.0)

        elif step_type == "pick_tip":
            slot = params["slot"]
            well = params["well"]
            robot.pick_up_tip(self.deck, slot_id=slot, well=well)

        elif step_type == "drop_tip":
            slot = params["slot"]
            edge = params.get("edge", "left")
            robot.drop_tip_scrape(self.deck, slot_id=slot, edge=edge)

        elif step_type == "transfer":
            p = params
            syringe_name = p.get("syringe", self.var_syringe.get())
            robot.transfer_volume(
                self.deck,
                src_slot=p["src_slot"],
                src_well=p["src_well"],
                dst_slot=p["dst_slot"],
                dst_well=p["dst_well"],
                volume_ul=float(p["volume_ul"]),
                syringe=syringe_name,
            )

        elif step_type == "aspirate":
            p = params
            syringe_name = p.get("syringe", self.var_syringe.get())
            volume_ul = float(p["volume_ul"])

            slot = p.get("slot")
            well = p.get("well")
        
            if slot is None:
                raise ValueError("aspirate 步骤需要提供 slot。")

            if well is not None:
                # 情况 1：slot + well → 使用 48wells
                robot.aspirate(
                    volume_ul=volume_ul,
                    syringe=syringe_name,
                    deck=self.deck,
                    slot_id=slot,
                    well=well,
                    # labware_type=默认 48 wells
                )
            else:
                # 情况 2：slot + 无 well → 视为 beaker
                    robot.aspirate_from_beaker(
                    deck=self.deck,
                    slot_id=slot,
                    volume_ul=volume_ul,
                    syringe=syringe_name,
                )

        elif step_type == "dispense":
            p = params
            syringe_name = p.get("syringe", self.var_syringe.get())
            volume_ul = float(p["volume_ul"])

            slot = p.get("slot")
            well = p.get("well")

            if slot is None:
                raise ValueError("dispense 步骤需要提供 slot。")

            if well is not None:
                # 情况 1：slot + well → 使用 48wells
                robot.dispense(
                    volume_ul=volume_ul,
                    syringe=syringe_name,
                    deck=self.deck,
                    slot_id=slot,
                    well=well,
                    # labware_type=默认 48 wells
                )
            else:
                # 情况 2：slot + 无 well → 视为 beaker
                    robot.dispense_to_beaker(
                    deck=self.deck,
                    slot_id=slot,
                    volume_ul=volume_ul,
                    syringe=syringe_name,
                )

        elif step_type == "dwell":
            seconds = float(params.get("seconds", 1.0))
            robot.dwell(seconds)

        else:
            raise ValueError(f"Unknown step type: {step_type}")

    def on_run_protocol(self) -> None:
        try:
            self.require_robot()
            self.log("Running protocol...")
            for idx, step in enumerate(self.protocol_steps, start=1):
                self.log(f"Step {idx}: {step}")
                self._run_single_step(step)
            self.log("Protocol finished.")
        except Exception as e:
            messagebox.showerror(self._l("Error", "错误"), f"Run protocol failed: {e}")
            self.log(f"[ERROR] Run protocol: {e}")

    def _build_tab_gpt_chat(self, nb: ttk.Notebook) -> None:
        """GPT 对话标签页：输入一段描述，调用云端 GPT 接口返回结果。"""
        frm = ttk.Frame(nb)
        nb.add(frm, text=self._l("GPT Helper", "GPT 助手"))

        # 输入框
        lbl_in = ttk.Label(frm, text=self._l("Input:", "输入："))
        lbl_in.grid(row=0, column=0, padx=4, pady=4, sticky="nw")

        self.txt_gpt_in = tk.Text(frm, height=4, width=60, wrap="word")
        self.txt_gpt_in.grid(row=0, column=1, padx=4, pady=4, sticky="nsew")

        # 输出框
        lbl_out = ttk.Label(frm, text=self._l("Output:", "输出："))
        lbl_out.grid(row=1, column=0, padx=4, pady=4, sticky="nw")

        self.txt_gpt_out = tk.Text(frm, height=10, width=60, wrap="word", state="disabled")
        self.txt_gpt_out.grid(row=1, column=1, padx=4, pady=4, sticky="nsew")

        # 发送按钮
        btn = ttk.Button(
            frm,
            text=self._l("Send to GPT", "发送到 GPT"),
            command=self.on_gpt_send,
        )
        btn.grid(row=2, column=1, padx=4, pady=6, sticky="e")

        # 让文本框自动拉伸
        frm.rowconfigure(0, weight=1)
        frm.rowconfigure(1, weight=3)
        frm.columnconfigure(1, weight=1)

    def on_gpt_send(self) -> None:
        """读取输入框内容，调用云端 GPT 接口，将结果显示在输出框。"""
        text = self.txt_gpt_in.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning(
                self._l("Warning", "提示"),
                self._l("Please enter text to send to GPT.", "请输入要发送给 GPT 的内容。"),
            )
            return

        try:
            self.log(self._l(f"[GPT] Request: {text}", f"[GPT] 请求：{text}"))
            resp = requests.post(
                GPT_API_URL,
                json={"description": text},
                timeout=300,
            )
            resp.raise_for_status()
            data = resp.json()
            answer = data.get(
                "result",
                self._l("(no 'result' field)", "(无 result 字段)"),
            )
        except Exception as e:
            answer =  self._l(
                f"[ERROR] Call GPT failed: {e}",
                f"[ERROR] 调用 GPT 失败: {e}",
            )
            self.log(answer)

        # 显示到输出框
        self.txt_gpt_out.configure(state="normal")
        self.txt_gpt_out.delete("1.0", "end")
        self.txt_gpt_out.insert("end", answer)
        self.txt_gpt_out.configure(state="disabled")


def main() -> None:
    root = tk.Tk()
    app = PipetteGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
