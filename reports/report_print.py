"""
Print / PDF report widget for TDM Report
"""

import base64
from io import BytesIO
from html import escape
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from datetime import datetime
from pathlib import Path
from core.graph_utils import draw_concentration_time_graph


def build_report_widget(patient, pk, interp, times, concs, report_comment=""):
    w = QWidget()
    w.setFixedWidth(680)
    lay = QVBoxLayout(w)
    lay.setContentsMargins(48, 40, 48, 40)
    lay.setSpacing(10)

    def h(text, size=13, bold=True, align=Qt.AlignmentFlag.AlignLeft, color='#000000'):
        lbl = QLabel(text)
        lbl.setFont(QFont("Calibri", size, QFont.Weight.Bold if bold else QFont.Weight.Normal))
        lbl.setAlignment(align)
        lbl.setStyleSheet(f"color: {color};")
        lay.addWidget(lbl)

    def label_with_colon(label):
        return f"{str(label).rstrip(':').strip()} :"

    def row(label, value, color='#000000'):
        r = QHBoxLayout()
        l = QLabel(label_with_colon(label))
        l.setFixedWidth(210)
        l.setStyleSheet("color: #000000; font-size: 13px; font-family: Calibri;")
        v = QLabel(str(value))
        v.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {color}; font-family: Calibri;")
        r.addWidget(l); r.addWidget(v); r.addStretch()
        lay.addLayout(r)

    def sep():
        f = QFrame(); f.setFrameShape(QFrame.Shape.HLine)
        f.setStyleSheet("background: #E8ECF0; max-height: 1px;")
        lay.addWidget(f)

    h("THERAPEUTIC DRUG MONITORING REPORT", 17, align=Qt.AlignmentFlag.AlignCenter)
    sep()
    lay.addSpacing(4)

    h("Patient Details", 14)
    row("Invoice Number:",  patient.get('invoice_number', 'N/A'))
    row("Invoice Date:",    patient.get('invoice_date', 'N/A'))
    row("Delivery Date:",   patient.get('delivery_date', 'N/A'))
    row("Report Number:",   patient.get('report_number', 'N/A'))
    row("Patient Name:",    patient.get('name', 'N/A'))
    row("Age:",             f"{patient.get('age', 'N/A')} years")
    row("Gender:",          patient.get('sex', 'N/A'))
    row("Referred By:",     patient.get('ref_by', 'N/A'))
    row("Diagnosis:",       patient.get('diag', 'N/A'))
    row("Date of Transplant:", patient.get('tx_date', 'N/A'))
    row("Sample:",          patient.get('test', 'Serum') or 'Serum')
    row("Lab Number:",      patient.get('lab_no', 'N/A'))
    row("Test Name:",       patient.get('drug', 'MPA') or 'MPA')
    row("Medications:",     patient.get('med', 'N/A'))

    lay.addSpacing(6); sep(); lay.addSpacing(4)
    h("Drug & Sampling", 14)
    row("MPA Preparation:",           patient.get('preparation', 'N/A'))
    row("Dose of Requested Drug:",    patient.get('dose', 'N/A'))
    row("Date & Time of Dose:",          patient.get('dose_dt', 'N/A'))
    row("Sample Collection Date:",    patient.get('sample_collection_date', 'N/A'))
    times_str = "Trough, " + ", ".join(str(t) for t in times[1:]) + " hours post dose." if len(times) > 1 else "Trough"
    row("Time of samples:", times_str)

    lay.addSpacing(6); sep(); lay.addSpacing(4)
    h("Results", 14)

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

    if report_comment:
        row("Comment:", report_comment)

    lay.addSpacing(6); sep()
    lay.addStretch()

    footer = QLabel(f"Generated: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
    footer.setStyleSheet("color: #000000; font-size: 12px; font-family: Calibri;")
    lay.addWidget(footer)

    return w


def build_report_html(patient, pk, interp, times, concs, prepared_by=None, checked_by=None,
                      graph_uri=None, title="TDM Report", print_config=None, report_comment=""):
    def fmt(v, d=3):
        return f"{v:.{d}f}" if v is not None else "N/A"

    def label_with_colon(label):
        return f"{str(label).rstrip(':').strip()} :"

    def result_row(left_label, left_value, right_label=None, right_value=None, right_value_html=None):
        right_html = ""
        if right_label and (right_value is not None or right_value_html is not None):
            value_html = right_value_html if right_value_html is not None else escape(str(right_value))
            right_html = (
                f'<div class="result-col"><span class="r-label">{escape(label_with_colon(right_label))}</span>'
                f'<span class="r-value">{value_html}</span></div>'
            )
        left_html = ""
        if left_label or left_value:
            left_html = (
                f'<div class="result-col"><span class="r-label">{escape(label_with_colon(left_label))}</span>'
                f'<span class="r-value">{escape(str(left_value))}</span></div>'
            )
        return f'<div class="result-line">{left_html or "<div></div>"}{right_html or "<div></div>"}</div>'

    def detail_row(left_label, left_value, right_label=None, right_value=None):
        right = ""
        if right_label:
            right = (
                f'<div class="grid-row"><div class="grid-label">{escape(label_with_colon(right_label))}</div>'
                f'<div class="grid-value">{escape(str(right_value))}</div></div>'
            )
        return (
            '<div class="grid-pair">'
            f'<div class="grid-row"><div class="grid-label">{escape(label_with_colon(left_label))}</div>'
            f'<div class="grid-value">{escape(str(left_value))}</div></div>'
            f'{right}'
            '</div>'
        )

    def triple_row(items):
        cols = []
        for label, value in items:
            cols.append(
                f'<div class="triple-col"><span class="grid-label">{escape(label_with_colon(label))}</span>'
                f'<span class="grid-value">{escape(str(value))}</span></div>'
            )
        while len(cols) < 3:
            cols.append('<div class="triple-col"></div>')
        return f'<div class="triple-row">{"".join(cols)}</div>'

    def img_to_base64(path_str=None, image_data=None, mime_type=None):
        if image_data:
            try:
                raw = bytes(image_data)
                mime = mime_type or "image/png"
                return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")
            except Exception:
                return None
        if not path_str:
            return None
        path = Path(path_str)
        if not path.exists(): return None
        try:
            with open(path, "rb") as f:
                return "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")
        except Exception:
            return None

    def graph_data_uri():
        fig, ax = plt.subplots(figsize=(7.6, 2.8), dpi=170)
        draw_concentration_time_graph(ax, times, concs, patient.get("drug", "MPA"))
        fig.subplots_adjust(left=0.08, right=0.99, top=0.82, bottom=0.24)
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
        '<div class="header-top">Department of Biochemistry</div>',
        '</div>',
        '<div class="patient-box">',
        '<div class="meta-grid">',
        triple_row([
            ("Invoice Number", patient.get('invoice_number', 'N/A')),
            ("Invoice Date", patient.get('invoice_date', 'N/A')),
            ("Delivery Date", patient.get('delivery_date', 'N/A')),
        ]),
        triple_row([
            ("Report Number", patient.get('report_number', 'N/A')),
            ("Patient Name", patient.get('name', 'N/A')),
            ("Age (years)", patient.get('age', 'N/A')),
        ]),
        triple_row([
            ("Gender", patient.get('sex', 'N/A')),
            ("Referred By", patient.get('ref_by', 'N/A')),
        ]),
        '<div class="patient-divider"></div>',
        triple_row([
            ("Sample", patient.get('test', 'Serum') or 'Serum'),
            ("Lab Number", patient.get('lab_no', 'N/A')),
            ("Test Name", patient.get('drug', 'MPA') or 'MPA'),
        ]),
        triple_row([
            ("Date of Transplant", patient.get('tx_date', 'N/A')),
            ("Diagnosis", patient.get('diag', 'N/A')),
        ]),
        f'<div class="single-row full-row patient-full-row compact-row"><span class="grid-label">{escape(label_with_colon("Medication"))}</span><span class="grid-value">{escape(str(patient.get("med", "N/A")))}</span></div>',
        '</div>',
        '</div>',
        '<div class="section-block drug-section">',
        '<div class="section-title">Drug &amp; Sampling</div>',
        detail_row("Requested Drug Preparation", patient.get('preparation', 'N/A'), "Dose of Requested Drug", patient.get('dose', 'N/A')),
        detail_row(
            "Date and Time of Dose",
            patient.get('dose_dt', 'N/A'),
            "Date of Sample Collection",
            patient.get('sample_collection_date', 'N/A'),
        ),
        f'<div class="single-row full-row compact-row"><span class="grid-label">{escape(label_with_colon("Time of sample(s)"))}</span><span class="grid-value">{escape(times_str)}</span></div>',
        '</div>',
        '<div class="section-block">',
        '<div class="section-title result-title">Result:</div>',
    ]
    # Use LSS AUC when available (since interpretation is based on it)
    if pk.get('auc_lss') is not None:
        auc_display = fmt(pk['auc_lss'])
        auc_label = "LSS AUC\u2080\u208b\u2081\u2082 (Estimated)"
    else:
        auc_display = fmt(pk['auc_0_12'])
        auc_label = f"{last_hr} hour extrapolated to 12 hr MPA AUC"
    if has_data:
        sections += [
            result_row("Trough Concentration", f"{fmt(pk['c_trough'], 2)} \u03bcg/mL",
                       auc_label, f"{auc_display} mg.h/L"),
            result_row(
                f"{last_hr} hr Concentration",
                f"{fmt(pk['c_last'], 2)} \u03bcg/mL",
                "Interpretation",
                right_value_html=f'<span style="color:{interp_color}; font-weight:700;">{escape(interp)}</span>',
            ),
        ]
    else:
        sections += [
            result_row("MPA AUC\u2080\u208b\u2081\u2082", f"{fmt(pk['auc_0_12'])} mg.h/L"),
            result_row(
                "",
                "",
                "Interpretation",
                right_value_html=f'<span style="color:{interp_color}; font-weight:700;">{escape(interp)}</span>',
            ),
        ]
    if graph_uri:
        sections.append(f'<div class="graph-wrap"><img src="{graph_uri}" alt="Concentration Time Graph"></div>')
    sections += [
        f'<div class="range-note"><span class="note-label">{escape(label_with_colon("Therapeutic Range"))}</span> <span class="note-value">At present the literature aims at an AUC for MPA of 30 - 60 mg.h/L as being effective with less side effects.</span></div>',
    ]
    if report_comment:
        sections.append(
            f'<div class="report-comment"><span class="note-label">{escape(label_with_colon("Comment"))}</span> <span class="note-value">{escape(str(report_comment))}</span></div>'
        )
    sections.append('</div>') # end section-block

    # Signature Section
    sig_html = '<div class="signature-footer"><div class="signature-container">'
    for i, (label, doctor) in enumerate([("Prepared By", prepared_by), ("Checked By", checked_by)]):
        box_class = "sig-box sig-box-right" if i == 1 else "sig-box"
        sig_html += f'<div class="{box_class}">'
        if doctor:
            sig_b64 = img_to_base64(
                doctor.get('signature_path'),
                doctor.get('signature_data'),
                doctor.get('signature_mime'),
            )
            if sig_b64:
                sig_html += f'<div class="sig-img-wrap"><img src="{sig_b64}"></div>'
            else:
                sig_html += '<div class="sig-img-wrap" style="height:50px;"></div>'
            
            sig_html += f'<div class="doc-name">{escape(doctor.get("name", ""))}</div>'
            
            # Designation with line breaks
            desc = escape(doctor.get("designation", "")).replace("\n", "<br>")
            sig_html += f'<div class="doc-desc">{desc}</div>'
        else:
            sig_html += '<div class="sig-img-wrap" style="height:60px;"></div>'
            sig_html += '<div class="doc-name">................................</div>'
            sig_html += f'<div class="doc-desc" style="color:#888;">{escape(label)}</div>'
        sig_html += '</div>'
    sig_html += f'</div><div class="footer">Generated: {escape(generated)}</div></div>'
    sections.append(sig_html)

    sections += [
        '</div>', # end report-shell
    ]

    config = print_config or {}
    mode = config.get("mode", "custom")
    if mode == "custom":
        try:
            print_top_padding = f"{max(0.0, min(float(config.get('custom_top_gap_cm', 2.3)), 10.0)):.2f}cm"
        except (TypeError, ValueError):
            print_top_padding = "2.30cm"
    else:
        print_top_padding = "12px"

    body = "\n".join(sections)
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{escape(title)}</title>
  <style>
    body {{ font-family: Calibri, "Segoe UI", Arial, sans-serif; color:#000; margin:0; background:white; }}
    .page {{ width:860px; min-height:100vh; margin:0 auto; padding:28px 32px 28px; box-sizing:border-box; display:flex; flex-direction:column; }}
    .report-shell {{ padding:0; width:100%; flex:1; display:flex; flex-direction:column; }}
    .header-box {{ margin-bottom:12px; }}
    .header-top {{ text-align:center; font-size:23px; font-weight:700; letter-spacing:0; }}
    .header-subline {{ text-align:left; font-size:16px; font-weight:700; margin-top:12px; }}
    .patient-box {{ border:2px solid #111; border-radius:14px; padding:12px 16px 12px; margin-bottom:14px; }}
    .section-block {{ margin-top:10px; }}
    .meta-grid {{ display:flex; flex-direction:column; gap:3px; }}
    .triple-row {{ display:grid; grid-template-columns: 1.2fr 1fr 1fr; gap:12px; line-height:1.25; font-size:14px; }}
    .triple-col {{ display:flex; gap:6px; align-items:flex-start; min-width:0; }}
    .grid-pair {{ display:grid; grid-template-columns: 1fr 1fr; gap:14px; }}
    .grid-row, .single-row {{ display:flex; gap:8px; align-items:flex-start; line-height:1.25; font-size:14px; }}
    .grid-label {{ width:auto; font-weight:400; white-space:nowrap; }}
    .grid-value {{ flex:1; font-weight:700; }}
    .patient-divider {{ border-top:1px solid #111; margin:5px 0 4px; }}
    .single-row {{ margin-top:6px; }}
    .compact-row {{ margin-top:0; }}
    .full-row .grid-value {{ white-space: nowrap; }}
    .patient-full-row .grid-value {{ white-space: normal; }}
    .section-title {{ font-size:15px; font-weight:700; margin:12px 0 6px; }}
    .drug-section {{ margin-top:0; }}
    .drug-section .section-title {{ margin-top:2px; }}
    .result-title {{ margin-top:8px; }}
    .result-line {{ display:grid; grid-template-columns: 1fr 1fr; gap:14px; margin:2px 0; align-items:start; }}
    .result-col {{ display:flex; align-items:flex-start; gap:4px; font-size:14px; white-space:nowrap; }}
    .r-label {{ font-weight:400; white-space:nowrap; }}
    .r-value {{ font-weight:700; white-space:nowrap; }}
    .result-line-interpretation {{ margin-top:0; }}
    .result-interpretation {{ font-size:14px; }}
    .graph-wrap {{ margin:10px auto 8px; text-align:center; border-top:1px solid #DDD; padding-top:8px; }}
    .graph-wrap img {{ display:block; width:720px; max-width:100%; height:auto; max-height:235px; object-fit:contain; margin:0 auto; }}
    .range-note {{ margin-top:12px; font-size:14px; line-height:1.4; }}
    .report-comment {{ margin-top:6px; font-size:14px; line-height:1.4; }}
    .note-label {{ font-weight:400; }}
    .note-value {{ font-weight:700; }}
    
    .signature-footer {{ margin-top:auto; padding-top:26px; background:white; }}
    .signature-container {{ display:flex; justify-content:space-between; padding:0 10px; }}
    .sig-box {{ text-align:left; width:46%; display:flex; flex-direction:column; align-items:flex-start; }}
    .sig-box-right {{ text-align:right; align-items:flex-end; }}
    .sig-img-wrap {{ height:55px; display:flex; align-items:flex-end; justify-content:flex-start; margin-bottom:4px; }}
    .sig-img-wrap img {{ max-height:55px; max-width:220px; object-fit:contain; }}
    .doc-name {{ font-weight:700; font-size:15px; margin-bottom:2px; color:#000; line-height:1.2; }}
    .doc-desc {{ font-size:13px; color:#000; line-height:1.35; }}
    
    .footer {{ margin-top:8px; text-align:center; color:#000; font-size:12px; border-top:1px solid #111; padding-top:6px; }}
    @media print {{
      body {{ margin:0; }}
      .page {{ width:auto; min-height:100vh; margin:0; padding:{print_top_padding} 12px 12px; }}
      .patient-box {{ border-width:1.5px; }}
      .result-line {{ grid-template-columns: 1fr 1fr; gap:12px; }}
      .result-col {{ display:flex; gap:4px; }}
      .r-label, .r-value {{ white-space:nowrap; }}
      .graph-wrap {{ margin:8px auto 8px; padding-top:8px; }}
      .graph-wrap img {{ width:720px; max-height:220px; }}
      .signature-footer {{ margin-top:auto; padding-top:22px; }}
    }}
  </style>
</head>
<body onload="setTimeout(() => window.print(), 250)">
  <div class="page">{body}</div>
</body>
</html>"""
