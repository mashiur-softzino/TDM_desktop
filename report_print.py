"""
Print / PDF report widget for TDM Report
"""

import base64
from io import BytesIO
from html import escape
import matplotlib
matplotlib.use("Agg")
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from scipy.interpolate import CubicSpline
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from datetime import datetime


def build_report_widget(patient, pk, interp, times, concs):
    w = QWidget()
    w.setFixedWidth(680)
    lay = QVBoxLayout(w)
    lay.setContentsMargins(48, 40, 48, 40)
    lay.setSpacing(10)

    def h(text, size=13, bold=True, align=Qt.AlignmentFlag.AlignLeft, color='#1A1A2E'):
        lbl = QLabel(text)
        lbl.setFont(QFont("Arial", size, QFont.Weight.Bold if bold else QFont.Weight.Normal))
        lbl.setAlignment(align)
        lbl.setStyleSheet(f"color: {color};")
        lay.addWidget(lbl)

    def row(label, value, color='#1A1A2E'):
        r = QHBoxLayout()
        l = QLabel(f"<b>{label}</b>")
        l.setFixedWidth(210)
        l.setStyleSheet("color: #546E7A; font-size: 12px;")
        v = QLabel(str(value))
        v.setStyleSheet(f"font-size: 13px; color: {color};")
        r.addWidget(l); r.addWidget(v); r.addStretch()
        lay.addLayout(r)

    def sep():
        f = QFrame(); f.setFrameShape(QFrame.Shape.HLine)
        f.setStyleSheet("background: #E8ECF0; max-height: 1px;")
        lay.addWidget(f)

    h("THERAPEUTIC DRUG MONITORING REPORT", 15, align=Qt.AlignmentFlag.AlignCenter)
    sep()
    lay.addSpacing(4)

    h("Patient Details", 12)
    row("Patient Name:",    patient.get('name', 'N/A'))
    row("Age:",             f"{patient.get('age', 'N/A')} years")
    row("Weight:",          f"{patient.get('weight', 'N/A')} kg")
    row("Hospital ID:",     patient.get('hosp_id', 'N/A'))
    row("Ward / Dept:",     patient.get('ward', 'N/A'))
    row("Diagnosis:",       patient.get('diag', 'N/A'))
    row("Date of Transplant:", patient.get('tx_date', 'N/A'))
    row("Medications:",     patient.get('med', 'N/A'))

    lay.addSpacing(6); sep(); lay.addSpacing(4)
    h("Drug & Sampling", 12)
    row("Requested Drug:",            patient.get('drug', 'N/A'))
    row("MPA Preparation:",           patient.get('preparation', 'N/A'))
    row("Dose of Requested Drug:",    patient.get('dose', 'N/A'))
    row("Dose Date & Time:",          patient.get('dose_dt', 'N/A'))
    row("Sample Collection Date:",    patient.get('sample_collection_date', 'N/A'))
    times_str = "Trough, " + ", ".join(str(t) for t in times[1:]) + " hours post dose." if len(times) > 1 else "Trough"
    row("Time of samples:", times_str)

    lay.addSpacing(6); sep(); lay.addSpacing(4)
    h("Results", 12)

    def fmt(v, d=3):
        return f"{v:.{d}f}" if v is not None else "N/A"

    row("Trough Concentration:", f"{fmt(pk['c_trough'], 2)} μg/mL")
    row("Last Sample Concentration:", f"{fmt(pk['c_last'], 2)} μg/mL")
    row("AUC (0 → last sample):", f"{fmt(pk['auc_0_last'])} mg·h/L")
    row("AUC (0 → 12 hr, extrap.):", f"{fmt(pk['auc_0_12'])} mg·h/L")
    if pk.get('t_half'):
        row("Terminal t½:", f"{fmt(pk['t_half'], 2)} hours")
    if pk.get('lambda_z'):
        row("λz:", f"{fmt(pk['lambda_z'], 4)} h⁻¹")

    interp_color = '#E53935' if interp in ('Low', 'High') else '#2E7D32'
    row("Interpretation:", interp, color=interp_color)
    row("Therapeutic Range (MPA):", "30–60 mg·h/L (AUC₀₋₁₂)")

    lay.addSpacing(6); sep()
    lay.addStretch()

    footer = QLabel(f"Generated: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
    footer.setStyleSheet("color: #9E9E9E; font-size: 10px;")
    lay.addWidget(footer)

    return w


def build_report_html(patient, pk, interp, times, concs, graph_uri=None):
    def fmt(v, d=3):
        return f"{v:.{d}f}" if v is not None else "N/A"

    def result_row(left_label, left_value, right_label=None, right_value=None):
        right_html = ""
        if right_label and right_value is not None:
            right_html = (
                f'<div class="result-col"><span class="r-label">{escape(left_or_empty(right_label))}</span>'
                f'<span class="r-value">{escape(str(right_value))}</span></div>'
            )
        return (
            f'<div class="result-line">'
            f'<div class="result-col"><span class="r-label">{escape(left_or_empty(left_label))}</span>'
            f'<span class="r-value">{escape(str(left_value))}</span></div>'
            f'{right_html}</div>'
        )

    def left_or_empty(text):
        return f"{text} ="

    def detail_row(left_label, left_value, right_label=None, right_value=None):
        right = ""
        if right_label:
            right = (
                f'<div class="grid-row"><div class="grid-label">{escape(right_label)}</div>'
                f'<div class="grid-value">{escape(str(right_value))}</div></div>'
            )
        return (
            '<div class="grid-pair">'
            f'<div class="grid-row"><div class="grid-label">{escape(left_label)}</div>'
            f'<div class="grid-value">{escape(str(left_value))}</div></div>'
            f'{right}'
            '</div>'
        )

    def graph_data_uri():
        fig, ax = plt.subplots(figsize=(6.8, 4.6), dpi=170)
        plot_times = np.array(times, dtype=float)
        plot_concs = np.array(concs, dtype=float)
        ax.set_facecolor("white")
        ax.grid(True, linestyle='--', color='#EEEEEE', alpha=0.9, zorder=0)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#E8ECF0")
        ax.spines["bottom"].set_color("#E8ECF0")

        if len(plot_times) >= 3:
            cs = CubicSpline(plot_times, plot_concs)
            t_fine = np.linspace(plot_times[0], plot_times[-1], 500)
            c_fine = np.clip(cs(t_fine), 0, None)
        else:
            t_fine = plot_times
            c_fine = plot_concs

        points = np.array([t_fine, c_fine]).T.reshape(-1, 1, 2)
        segs = np.concatenate([points[:-1], points[1:]], axis=1)
        norm = plt.Normalize(t_fine[0], t_fine[-1])
        lc = LineCollection(segs, cmap='rainbow', norm=norm, linewidth=2.8, zorder=3)
        lc.set_array(t_fine)
        ax.add_collection(lc)

        n_fill = 80
        t_segs = np.linspace(t_fine[0], t_fine[-1], n_fill + 1)
        for i in range(n_fill):
            ts = t_segs[i:i + 2]
            cs_seg = np.clip(cs(ts), 0, None) if len(plot_times) >= 3 else np.interp(ts, plot_times, plot_concs)
            col = plt.cm.rainbow(norm(t_segs[i]))
            ax.fill_between(ts, 0, cs_seg, color=col, alpha=0.18, zorder=1)

        dot_colors = plt.cm.rainbow(np.linspace(0, 1, len(plot_times)))
        for t, c, col in zip(plot_times, plot_concs, dot_colors):
            ax.scatter(t, c, color=col, s=60, zorder=5, edgecolors='white', linewidth=1.8)

        ax.annotate(
            'Trough', (plot_times[0], plot_concs[0]),
            xytext=(8, 12), textcoords='offset points',
            color='#E53935', fontsize=9, fontweight='bold',
            arrowprops=dict(arrowstyle='-', color='#E53935', lw=1)
        )

        ax.set_xlim(left=max(-0.15, plot_times[0] - 0.2), right=max(plot_times[-1], 7))
        ax.set_ylim(bottom=0)
        ax.set_xlabel("Time (hrs)", fontsize=10, fontweight="bold")
        ax.set_ylabel("Conc.(μg/ml)", fontsize=10, fontweight="bold")
        ax.set_title("Concentration-Time Curve", fontsize=12, fontweight='bold', pad=12)
        fig.tight_layout()
        buf = BytesIO()
        fig.savefig(buf, format="png", facecolor="white", bbox_inches="tight")
        plt.close(fig)
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")

    interp_color = '#E53935' if interp in ('Low', 'High') else '#2E7D32'
    has_data = bool(times and concs)
    if has_data:
        times_str = "Trough, " + ", ".join(str(t) for t in times[1:]) + " hours post dose." if len(times) > 1 else "Trough"
    else:
        times_str = "Direct AUC input"
    generated = datetime.now().strftime('%d.%m.%Y %H:%M')
    last_hr = int(pk['t_last']) if pk.get('t_last') is not None and float(pk['t_last']).is_integer() else (pk.get('t_last') or 0)
    # Only generate graph when there are actual data points
    if has_data:
        graph_uri = graph_uri or graph_data_uri()
    else:
        graph_uri = None

    sections = [
        '<div class="report-shell">',
        '<div class="header-box">',
        '<div class="header-top">CLINICAL PHARMACOLOGY UNIT</div>',
        '<div class="header-subline">Therapeutic Drug Monitoring Report</div>',
        '</div>',
        '<div class="patient-box">',
        '<div class="meta-grid">',
        detail_row("Patient Name", patient.get('name', 'N/A'), "Hospital Number", patient.get('hosp_id', 'N/A')),
        detail_row("Age (years)", patient.get('age', 'N/A'), "Ward", patient.get('ward', 'N/A')),
        detail_row("Sex", patient.get('sex', 'N/A'), "Dept / Unit", patient.get('dept', 'N/A')),
        detail_row("Weight (Kg)", patient.get('weight', 'N/A'), "Date of Transplant", patient.get('tx_date', 'N/A')),
        '</div>',
        f'<div class="single-row"><span class="grid-label">Diagnosis</span><span class="grid-value">{escape(patient.get("diag", "N/A"))}</span></div>',
        f'<div class="single-row"><span class="grid-label">Medication</span><span class="grid-value">{escape(patient.get("med", "N/A"))}</span></div>',
        '</div>',
        '<div class="section-block">',
        '<div class="section-title">Drug & Sampling</div>',
        detail_row("Requested Drug", patient.get('drug', 'N/A'), "Requested Drug Preparation", patient.get('preparation', 'N/A')),
        detail_row("Dose of Requested Drug", patient.get('dose', 'N/A')),
        detail_row("Date and Time of Dose", patient.get('dose_dt', 'N/A')),
        detail_row("Date of Sample Collection", patient.get('sample_collection_date', 'N/A')),
        f'<div class="single-row full-row"><span class="grid-label">Time of sample(s)</span><span class="grid-value">{escape(times_str)}</span></div>',
        '</div>',
        '<div class="section-block">',
        '<div class="section-title result-title">Result:</div>',
    ]
    # Direct AUC mode: only show AUC and interpretation
    if has_data:
        sections += [
            result_row("Trough Concentration", f"{fmt(pk['c_trough'], 2)} μg/mL",
                       f"{last_hr} hour extrapolated to 12 hr MPA AUC", f"{fmt(pk['auc_0_12'])} mg.h/L"),
            result_row(f"{last_hr} hr Concentration", f"{fmt(pk['c_last'], 2)} μg/mL"),
        ]
    else:
        sections += [
            result_row("MPA AUC₀₋₁₂", f"{fmt(pk['auc_0_12'])} mg.h/L"),
        ]
    sections += [
        f'<div class="result-line result-line-interpretation">'
        f'<div class="result-col result-interpretation"><strong>Interpretation:</strong> <span style="color:{interp_color}; font-weight:700;">{escape(interp)}</span></div>'
        f'<div></div>'
        f'</div>',
    ]
    if graph_uri:
        sections.append(f'<div class="graph-wrap"><img src="{graph_uri}" alt="Concentration Time Curve"></div>')
    sections += [
        f'<div class="range-note"><strong>Therapeutic Range:</strong> At present the literature aims at an AUC for MPA of 30 - 60 mg.h/L as being effective with less side effects.</div>',
        '</div>',
        f'<div class="footer">Generated: {escape(generated)}</div>',
        '</div>',
    ]

    body = "\n".join(sections)
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>TDM Report</title>
  <style>
    body {{ font-family: "Times New Roman", Georgia, serif; color:#111; margin:0; background:white; }}
    .page {{ width:860px; margin:0 auto; padding:28px 32px 28px; }}
    .report-shell {{ padding:0; }}
    .header-box {{ margin-bottom:12px; }}
    .header-top {{ text-align:center; font-size:24px; font-weight:700; letter-spacing:.2px; }}
    .header-subline {{ text-align:left; font-size:17px; font-weight:700; margin-top:12px; }}
    .patient-box {{ border:2px solid #111; border-radius:14px; padding:12px 16px 12px; margin-bottom:14px; }}
    .section-block {{ margin-top:10px; }}
    .meta-grid {{ display:flex; flex-direction:column; gap:3px; }}
    .grid-pair {{ display:grid; grid-template-columns: 1fr 1fr; gap:14px; }}
    .grid-row, .single-row {{ display:flex; gap:5px; align-items:flex-start; line-height:1.22; font-size:15px; }}
    .grid-label {{ min-width:150px; font-weight:700; white-space:nowrap; }}
    .grid-value {{ flex:1; }}
    .single-row {{ margin-top:6px; }}
    .full-row .grid-value {{ white-space: nowrap; }}
    .section-title {{ font-size:16px; font-weight:700; margin:12px 0 6px; }}
    .result-title {{ margin-top:8px; }}
    .result-line {{ display:grid; grid-template-columns: 1fr 1fr; gap:14px; margin:2px 0; align-items:start; }}
    .result-col {{ display:flex; align-items:flex-start; gap:4px; font-size:15px; white-space:nowrap; }}
    .r-label {{ font-weight:700; white-space:nowrap; }}
    .r-value {{ font-weight:700; white-space:nowrap; }}
    .result-line-interpretation {{ margin-top:0; }}
    .result-interpretation {{ font-size:15px; }}
    .graph-wrap {{ margin:18px auto 14px; text-align:center; border-top:1px solid #DDD; padding-top:12px; }}
    .graph-wrap img {{ width:650px; max-width:100%; height:auto; }}
    .range-note {{ margin-top:14px; font-size:15px; line-height:1.4; }}
    .footer {{ margin-top:18px; text-align:center; color:#555; font-size:12px; }}
    @media print {{
      body {{ margin:0; }}
      .page {{ width:auto; margin:0; padding:12px 12px; }}
      .patient-box {{ border-width:1.5px; }}
      .result-line {{ grid-template-columns: 1fr 1fr; gap:12px; }}
      .result-col {{ display:flex; gap:4px; }}
      .r-label, .r-value {{ white-space:nowrap; }}
    }}
  </style>
</head>
<body onload="setTimeout(() => window.print(), 250)">
  <div class="page">{body}</div>
</body>
</html>"""
