# FYP-liquid-handling-robot

This repository contains the complete hardware, firmware, and software implementation for an automated single-channel liquid-handling robot developed as part of an MEng Final Year Project. The system repurposes a decommissioned Raise3D Pro2 Plus motion platform into a programmable syringe-based pipetting robot with a Python control interface and optional GPT-assisted protocol generation.

The project focuses on low-cost laboratory automation, modular mechanical design, and a clear separation between mechanical actuation, firmware-level motion control, and high-level software abstraction.

---

## Repository Structure

The repository is organised into three main directories:

├── `hardware/`

├── `firmware/`

└── `software/`


Each directory corresponds to a major subsystem of the project and can be used independently for replication or further development.

---

## Hardware

**Directory:** `hardware/`

This directory contains the mechanical design files for the syringe pump, experimental deck, and adapters.

### Contents

- `Syringe Pump.f3d`
- `Pump Base.step`
- `Pump Carriage Sled.step`
- `Tips Adapter.f3d`
- `Tips Adapter.step`
- `Experiment Platform.f3d`
- `Experiment Platform.step`

### Description

The syringe pump mechanism used in this project is **adapted from the open-source Poseidon syringe pump project** developed by the Pachter Lab (https://github.com/pachterlab/poseidon), which is released under the **BSD 2-Clause License**.

The original Poseidon design served as a structural and conceptual baseline. The geometry, mounting interfaces, and overall assembly were **modified and reworked** to support integration with a modified Raise3D Pro2 Plus motion platform and to meet the requirements of automated liquid-handling operations in this project.

All CAD files are provided in both Fusion 360 (`.f3d`) and neutral STEP formats to support reuse, inspection, and modification in different CAD environments.

---

## Firmware

**Directory:** `firmware/`

### Contents

- `Marlin-btt/` – Modified Marlin firmware files including configuration files
- `firmware.bin` – Precompiled firmware image for direct flashing

### Description
The firmware is based on the open-source Marlin project (GPLv3).

Motion control is implemented using a BigTreeTech SKR Mini E3 V3.0 controller running a customised version of Marlin firmware. The firmware supports four stepper-driven axes (X, Y, Z, and U), sensorless homing via TMC2209 drivers, and motion constraints adapted for liquid-handling rather than 3D printing.

The provided `firmware.bin` can be flashed directly to the controller via SD card without recompilation. Users wishing to modify axis parameters, homing behaviour, or motion limits may edit the configuration files in `Marlin-btt/` and rebuild the firmware.

---

## Software

**Directory:** `software/`


### Description

The software stack is implemented in Python and follows a layered architecture:

- **robot.py**  
  Implements the command abstraction layer. Low-level G-code transmission and serial communication are wrapped into readable motion and liquid-handling primitives such as homing, point-to-point movement, aspiration, dispensing, and tip handling.

- **deck.py**  
  Defines the physical deck layout and slot coordinates. All labware placement is referenced relative to this model.

- **labware.py**  
  Encodes labware geometry (e.g. plates, tip racks, reservoirs) independently of motion logic, allowing new labware to be added without modifying control code.

- **gui.py**  
  A Tkinter-based graphical user interface providing manual jogging, homing, protocol execution, and real-time feedback, with optional GPT-assisted generation of JSON experiment protocols.

### Standalone Executable

An Windows executable (`PipetteRobot.exe`) included for demonstration purposes. This executable is packaged using PyInstaller and **does not require a Python environment** to run. Launching the executable starts the graphical user interface directly with all dependencies bundled.

---

## Usage Overview

1. Flash the provided firmware to the controller board.
2. Install the syringe, tip rack, and labware onto predefined deck slots.
3. Launch the GUI using either `gui.py` (Python environment) or `PipetteRobot.exe` (standalone).
4. Home the system and execute manual or automated protocols.

Detailed usage scenarios, experimental procedures, and evaluation results are documented in the accompanying project report.

---

## Project Scope and Disclaimer

This project is a research and educational prototype developed for academic purposes. It demonstrates the feasibility of low-cost laboratory automation and software–hardware integration. The system has not been validated for biological, chemical, or clinical use, and no claims are made regarding regulatory compliance.



