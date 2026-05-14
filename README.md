# TDM Report — Therapeutic Drug Monitoring Software

A desktop application for generating Therapeutic Drug Monitoring (TDM) reports for renal transplant patients. Supports MPA (Mycophenolic Acid), Tacrolimus, Cyclosporine, and Sirolimus.

---

## Features

- Patient information form
- Configurable sampling schemes: 4, 6, or 10 post-dose time points
- AUC calculation using Linear-Up / Log-Down trapezoidal method (FDA standard)
- Automatic extrapolation from AUC₀₋ₜ to AUC₀₋₁₂
- Live concentration–time curve with rainbow gradient
- Interpretation against therapeutic range (MPA: 30–60 mg·h/L)
- Print / PDF export

---

## Requirements

| Requirement | Minimum Version |
|-------------|----------------|
| Python      | 3.10 or higher |
| PyQt6       | 6.4.0          |
| qtawesome   | 1.3.0          |
| matplotlib  | 3.7.0          |
| numpy       | 1.24.0         |
| scipy       | 1.10.0         |
| reportlab   | 4.0.0          |

---

## Installation

### Step 1 — Install Python

Download and install Python 3.10 or higher from:
**https://www.python.org/downloads/**

During installation on Windows, make sure to check:
☑ **Add Python to PATH**

Verify installation:
```bash
python3 --version
```

---

### Step 2 — Download the project

Download or copy the project folder to your machine. The folder should contain:

```
AUC-sampler/
├── main.py
├── app/
├── core/
├── ui/
├── reports/
├── assets/
│   └── signatures/
├── requirements.txt
└── seed_signatories.json
```

---

### Step 3 — Install dependencies

Open a terminal (or Command Prompt on Windows), navigate to the project folder, and run:

```bash
pip3 install -r requirements.txt
```

Or install packages one by one:

```bash
pip3 install PyQt6 qtawesome matplotlib numpy scipy reportlab
```

---

### Step 4 — Run the application

```bash
python3 main.py
```

On Windows you can also double-click `main.py` if Python is associated with `.py` files.

---

## Platform-specific Notes

### macOS
No extra steps needed. If you get a security warning the first time, go to:
**System Settings → Privacy & Security → Open Anyway**

### Windows
If `python3` is not recognized, try `python` instead:
```
python main.py
```

### Linux (Ubuntu/Debian)
You may need to install `python3-pip` first:
```bash
sudo apt install python3-pip
pip3 install -r requirements.txt
python3 main.py
```

---

## Usage

1. Fill in **Patient Information** (name, age, weight, hospital details)
2. Fill in **Drug & Dose** (drug name, preparation, dose amount, dose date/time)
3. Enter the **Trough** (pre-dose) concentration
4. Select sampling scheme: **2h**, **3h**, or **6h**
5. Enter measured **concentrations** for each time point
6. Click **Calculate AUC & Generate Report**
7. View results and graph, then click **Print / Export PDF**

---

## Sampling Time Points

| Scheme | Post-dose times (hours) |
|--------|------------------------|
| 2h     | 0.5, 2.0 |
| 3h     | 0.5, 1.0, 1.5 |
| 6h     | 0.5, 1.0, 1.5, 2.0, 2.5, 3.0 |

Trough (pre-dose) is always collected and entered separately.
All time values in the table are editable.

---

## AUC Calculation Method

- **Method:** Linear-Up / Log-Down mixed trapezoidal rule (FDA/EMA standard)
  - Rising segments → linear trapezoid
  - Falling segments → log-linear trapezoid
- **Extrapolation:** Terminal log-linear regression (last 3 points) to estimate λz, then extrapolate to 12-hour dosing interval
- **Therapeutic range for MPA:** 30–60 mg·h/L (AUC₀₋₁₂)
  - Source: Le Meur Y et al., *Am J Transplant* 2007

---

## File Structure

| File | Purpose |
|------|---------|
| `main.py` | Entry point — launches the application |
| `app/` | Main window and report workflow orchestration |
| `core/` | Database, PK calculations, logging, app paths, validation |
| `ui/` | Reusable PyQt widgets, pages, dialogs, and form controls |
| `reports/` | Print/PDF report rendering |
| `requirements.txt` | Python package dependencies |
