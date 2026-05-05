import base64
import re
import webbrowser
from datetime import datetime
from io import BytesIO
from pathlib import Path

from PyQt6.QtCore import QDate, QDateTime, Qt
from PyQt6.QtWidgets import QDialog, QMessageBox

from app_logger import (
    log_draft_saved,
    log_error,
    log_record_deleted,
    log_record_loaded,
    log_report_generated,
    log_report_printed,
)
from calculations import calculate_auc_full, calculate_lss_auc, canonical_drug_name, interpret_result
from database import delete_record, get_signatory_by_id, load_all, save_record
from tdm_validators import is_valid_direct_auc, is_valid_phone
from ui_constants import DEFAULT_DURATION_OPTIONS
from ui_patients import PatientRow, ResultsDialog
from ui_widgets import ConfirmActionModal


class TDMWorkflowMixin:
    _LIST_PAGE_SIZE = 10

    def _load_saved_patients(self):
        try:
            self._saved_patients, self._drafts = load_all()
        except Exception:
            self._saved_patients = []
            self._drafts = []

    def _patient_payload(self):
        d_del = self.f_delivery_date.date()
        d_sam = self.f_sample_collection_date.date()
        d_tx = self.f_tx_date.date()

        return {
            "name": self.f_name.text().strip() or "N/A",
            "age": self.f_age.text().strip() or "N/A",
            "sex": "" if self.f_sex.currentText() == "Choose a gender" else self.f_sex.currentText(),
            "invoice_date": self.f_invoice_date.date().toString("dd.MM.yyyy"),
            "invoice_number": self.f_hosp_no.text().strip() or "N/A",
            "report_number": self.f_report_no.text().strip() or "N/A",
            "dept": self.f_referred_by.text().strip() or "N/A",
            "delivery_date": d_del.toString("dd.MM.yyyy") if d_del else "N/A",
            "drug": self.f_drug.text().strip(),
            "preparation": self.f_preparation.text().strip(),
            "dose": self.f_dose.text().strip(),
            "dose_dt": self.f_dose_dt.dateTime().toString("dd.MM.yyyy 'at' hh:mmAP"),
            "sample_collection_date": d_sam.toString("dd.MM.yyyy") if d_sam else "N/A",
            "diag": self.f_diag.text().strip() or "N/A",
            "tx_date": d_tx.toString("dd.MM.yyyy") if d_tx else "N/A",
            "med": self.f_med.get_text() or "N/A",
            "phone": self.f_phone.text().strip() or "N/A",
        }

    def _form_signature(self):
        return {
            "patient": self._patient_payload(),
            "sampling_mode": getattr(self, "_sampling_mode", "multi"),
            "direct_auc": self._direct_auc_edit.text().strip() if hasattr(self, "_direct_auc_edit") else "",
            "scheme": getattr(self, "_current_scheme", 4),
            "duration_options": list(getattr(self, "_duration_options", DEFAULT_DURATION_OPTIONS)),
            "trough": self.trough_edit.text().strip(),
            "sample_rows": self.sample_table.get_rows_payload(),
            "prepared_by_id": self.prep_by_combo.currentData() if hasattr(self, "prep_by_combo") else None,
            "checked_by_id": self.checked_by_combo.currentData() if hasattr(self, "checked_by_combo") else None,
        }

    def _snapshot_payload(self):
        mode = getattr(self, "_sampling_mode", "multi")
        if mode == "direct":
            times, concs = [], []
        else:
            times, concs = self._read_table(skip_empty=True)
        data = {
            "saved_at": datetime.now().strftime("%d/%m/%Y"),
            "report_path": "",
            "patient": self._patient_payload(),
            "sampling_mode": mode,
            "direct_auc": self._direct_auc_edit.text().strip() if hasattr(self, "_direct_auc_edit") else "",
            "scheme": getattr(self, "_current_scheme", 4),
            "duration_options": list(getattr(self, "_duration_options", DEFAULT_DURATION_OPTIONS)),
            "trough": self.trough_edit.text().strip(),
            "sample_rows": self.sample_table.get_rows_payload(),
            "times": times,
            "concs": concs,
            "prepared_by_id": self.prep_by_combo.currentData(),
            "checked_by_id": self.checked_by_combo.currentData(),
        }
        if hasattr(self, "_last_pk"):
            data["pk"] = self._last_pk
            data["interp"] = getattr(self, "_last_interp", "N/A")
        return data

    def _has_any_concentration_input(self):
        if self.trough_edit.text().strip():
            return True
        return any(row.has_concentration() for row in self.sample_table._rows)

    def _has_required_sampling_fields(self):
        if not hasattr(self, "f_drug"):
            return False
        if getattr(self, "_sampling_mode", "multi") == "direct":
            return is_valid_direct_auc(self._direct_auc_edit.text()) and bool(self.f_dose.text().strip())
        return all(
            [
                self.f_drug.text().strip(),
                self.f_preparation.text().strip(),
                self.f_dose.text().strip(),
            ]
        )

    def _can_generate_or_save(self):
        if not self.f_name.text().strip() or not self._has_required_sampling_fields():
            return False
        if getattr(self, "_sampling_mode", "multi") == "direct":
            return True
        times, concs = self._read_table(skip_empty=False)
        return times is not None and len(times) >= 3

    def _can_save_draft(self):
        return bool(self.f_name.text().strip())

    def _update_action_buttons(self):
        enabled = self._can_generate_or_save()
        draft_enabled = self._can_save_draft()
        is_editing_saved_sample = (
            getattr(self, "_active_record_source", None) == "sample"
            and bool(getattr(self, "_active_record_id", None))
        )
        is_editing_draft = (
            getattr(self, "_active_record_source", None) == "draft"
            and bool(getattr(self, "_active_record_id", None))
        )
        self.calc_btn.setText("Update Report" if is_editing_saved_sample else "Generate Report")
        if is_editing_saved_sample:
            enabled = enabled and self._form_signature() != getattr(self, "_loaded_form_signature", None)
        if is_editing_draft:
            draft_enabled = draft_enabled and self._form_signature() != getattr(self, "_loaded_form_signature", None)
        self.calc_btn.setEnabled(enabled)
        self.calc_btn.setCursor(Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ForbiddenCursor)
        for button in [self.draft_btn, getattr(self, "sampling_draft_btn", None)]:
            if button is None:
                continue
            button.setVisible(not is_editing_saved_sample)
            button.setEnabled(draft_enabled)
            button.setCursor(Qt.CursorShape.PointingHandCursor if draft_enabled else Qt.CursorShape.ForbiddenCursor)

    def _reset_list_view(self, card):
        if card is None:
            return
        card.set_page_index(0)
        card.clear_search()

    def _refresh_patients_list(self):
        if not hasattr(self, "sample_list_card"):
            return

        def sort_key(snapshot):
            snapshot_id = int(snapshot.get("id") or 0)
            saved_at = str(snapshot.get("saved_at", "") or "")
            patient = snapshot.get("patient", {})
            invoice_number = str(patient.get("invoice_number") or "")
            try:
                saved_dt = datetime.strptime(saved_at, "%d/%m/%Y")
            except ValueError:
                saved_dt = datetime.min
            return (saved_dt, snapshot_id, invoice_number)

        def matches_search(snapshot, query):
            if not query:
                return True
            patient = snapshot.get("patient", {})
            return (
                query in (patient.get("name") or "").lower()
                or query in (patient.get("pid") or "").lower()
                or query in (patient.get("phone") or "").lower()
                or query in (patient.get("invoice_number") or "").lower()
            )

        def populate(card, items, edit_cb, delete_cb, row_type="sample", view_cb=None, print_cb=None):
            query = card.search_text()
            filtered = [snapshot for snapshot in items if matches_search(snapshot, query)]
            visible = sorted(filtered, key=sort_key, reverse=True)

            rows_layout = card._rows_lay
            while rows_layout.count():
                item = rows_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

            if not visible:
                card.set_empty_text("No data found" if query else None)
                card.set_empty_visible(True)
                return

            card.set_empty_text()
            card.set_empty_visible(False)
            page_count = (len(visible) + self._LIST_PAGE_SIZE - 1) // self._LIST_PAGE_SIZE
            card.clamp_page_index(page_count)
            page_index = card.page_index()
            start = page_index * self._LIST_PAGE_SIZE
            page = visible[start:start + self._LIST_PAGE_SIZE]

            for offset, snapshot in enumerate(page, start=start + 1):
                row = PatientRow(snapshot, row_type=row_type, serial_no=offset)
                row.edit_requested.connect(edit_cb)
                if view_cb is not None:
                    row.view_requested.connect(view_cb)
                if print_cb is not None:
                    row.print_requested.connect(print_cb)
                row.delete_requested.connect(delete_cb)
                rows_layout.addWidget(row)

            rows_layout.addStretch()
            card.set_pagination(page_index, page_count, len(visible), self._LIST_PAGE_SIZE)

        populate(
            self.sample_list_card,
            self._saved_patients,
            self._load_saved_sample,
            self._delete_saved_patient,
            row_type="sample",
            view_cb=self._view_saved_sample_result,
            print_cb=self._print_saved_sample,
        )
        if hasattr(self, "draft_list_card"):
            populate(self.draft_list_card, self._drafts, self._load_draft, self._delete_draft, row_type="draft")
        self.sample_list_card.set_count(len(self._saved_patients))
        if hasattr(self, "draft_list_card"):
            self.draft_list_card.set_count(len(self._drafts))

    def _save_draft(self):
        phone = self.f_phone.text().strip()
        if phone and not is_valid_phone(phone):
            self._show_toast("Invalid Phone", "Please enter a valid 11-digit phone number.", tone="warning")
            return
        snapshot = self._snapshot_payload()
        snapshot.pop("pk", None)
        snapshot.pop("interp", None)
        existing_id = getattr(self, "_active_record_id", None)
        if getattr(self, "_active_record_source", None) == "draft" and existing_id is not None:
            snapshot["id"] = existing_id
        save_record(snapshot, "draft")
        patient = snapshot.get("patient", {})
        log_draft_saved(patient.get("pid", "N/A"), patient.get("name", "N/A"))
        self._load_saved_patients()
        self._reset_list_view(getattr(self, "draft_list_card", None))
        self._refresh_patients_list()
        self._clear_form_state()
        self._switch_page(2)
        self._main_scroll.verticalScrollBar().setValue(0)
        self._show_toast("Draft saved successfully", "Sample moved to Draft List.")

    def _load_saved_sample(self, patient_id):
        snapshot = next((item for item in self._saved_patients if item["id"] == patient_id), None)
        if snapshot:
            patient = snapshot.get("patient", {})
            log_record_loaded(patient_id, patient.get("pid", "N/A"), patient.get("name", "N/A"), "sample")
            self._load_snapshot(snapshot)

    def _view_saved_sample_result(self, patient_id):
        snapshot = next((item for item in self._saved_patients if item["id"] == patient_id), None)
        if snapshot:
            patient = snapshot.get("patient", {})
            log_record_loaded(patient_id, patient.get("pid", "N/A"), patient.get("name", "N/A"), "view_result")
            self._show_snapshot_result(snapshot)

    def _print_saved_sample(self, patient_id):
        snapshot = next((item for item in self._saved_patients if item["id"] == patient_id), None)
        if snapshot:
            patient = snapshot.get("patient", {})
            log_report_printed(patient.get("pid", "N/A"), patient.get("name", "N/A"))
            self._open_report_in_browser(snapshot)

    def _load_draft(self, patient_id):
        snapshot = next((item for item in self._drafts if item["id"] == patient_id), None)
        if not snapshot:
            return
        patient = snapshot.get("patient", {})
        log_record_loaded(patient_id, patient.get("pid", "N/A"), patient.get("name", "N/A"), "draft")
        self._load_snapshot(snapshot)

    def _load_snapshot(self, snapshot):
        if hasattr(self, "_report_snapshot"):
            delattr(self, "_report_snapshot")
        self._active_record_id = snapshot.get("id")
        self._active_record_source = snapshot.get("record_type", "sample")
        self._scheme_rows_cache = {}
        saved_mode = snapshot.get("sampling_mode", "multi")
        self._switch_sampling_mode(saved_mode)
        if saved_mode == "direct":
            self._toggle_direct.setChecked(True)
            self._direct_auc_edit.setText(snapshot.get("direct_auc", ""))
        else:
            self._toggle_multi.setChecked(True)
        self._set_duration_options(snapshot.get("duration_options", self._global_duration_options), selected=snapshot.get("scheme", 4))
        patient = snapshot.get("patient", {})
        self.f_name.setText(patient.get("name", "") if patient.get("name") != "N/A" else "")
        self.f_age.setText(patient.get("age", "") if patient.get("age") != "N/A" else "")
        self.f_hosp_no.setText(patient.get("invoice_number", "") if patient.get("invoice_number") != "N/A" else "")
        self.f_report_no.setText(patient.get("report_number", "") if patient.get("report_number") != "N/A" else "")
        self.f_referred_by.setText(patient.get("dept", "") if patient.get("dept") != "N/A" else "")
        self.f_phone.setText(patient.get("phone", "") if patient.get("phone") != "N/A" else "")

        invoice_date = QDate.fromString(patient.get("invoice_date", ""), "dd.MM.yyyy")
        if invoice_date.isValid():
            self.f_invoice_date.setDate(invoice_date)
        delivery_date = QDate.fromString(patient.get("delivery_date", ""), "dd.MM.yyyy")
        if delivery_date.isValid():
            self.f_delivery_date.setDate(delivery_date)

        sex_value = patient.get("sex", "").strip()
        sex_index = self.f_sex.findText(sex_value) if sex_value else 0
        self.f_sex.setCurrentIndex(sex_index if sex_index >= 0 else 0)
        self.f_diag.setText(patient.get("diag", "Post Renal Transplant") if patient.get("diag") != "N/A" else "Post Renal Transplant")
        self.f_drug.setText(patient.get("drug", "MPA") or "MPA")
        self.f_preparation.setText(patient.get("preparation", "Mycophenolate Mofetil (MMF)"))
        self.f_dose.setText(patient.get("dose", "540mg - 720mg") if patient.get("dose") != "N/A" else "")
        tx_date = QDate.fromString(patient.get("tx_date", ""), "dd.MM.yyyy")
        self.f_tx_date.setDate(tx_date if tx_date.isValid() else None)
        self._update_tx_duration()
        dose_dt_text = patient.get("dose_dt", "")
        dose_dt = QDateTime.fromString(dose_dt_text, "dd.MM.yyyy 'at' hh:mmAP")
        if not dose_dt.isValid():
            dose_dt = QDateTime.fromString(dose_dt_text, "dd.MM.yy 'at' hh:mmAP")
        if dose_dt.isValid():
            self.f_dose_dt.setDateTime(dose_dt)
        sample_date_text = patient.get("sample_collection_date", "")
        sample_dt = QDate.fromString(sample_date_text, "dd.MM.yyyy")
        if not sample_dt.isValid():
            sample_dt = QDate.fromString(sample_date_text, "dd.MM.yy")
        if sample_dt.isValid():
            self.f_sample_collection_date.setDate(sample_dt)

        self.f_med.clear_selection()
        meds = patient.get("med", "")
        if meds and meds != "N/A":
            for med in [item.strip() for item in meds.split(",") if item.strip()]:
                self.f_med.select_med(med)

        prep_id = snapshot.get("prepared_by_id")
        check_id = snapshot.get("checked_by_id")
        self._refresh_signatory_combos(select_prep_id=prep_id, select_check_id=check_id)

        scheme = snapshot.get("scheme", 4)
        rows_payload = snapshot.get("sample_rows")
        if rows_payload:
            self._current_scheme = scheme
            self.sample_table.set_rows_payload(rows_payload)
            self._scheme_rows_cache[scheme] = rows_payload
            self.trough_edit.setText(snapshot.get("trough", ""))
        else:
            times = snapshot.get("times", [])
            concs = snapshot.get("concs", [])
            if times:
                if times[0] == 0 and concs:
                    self.trough_edit.setText("" if concs[0] is None else str(concs[0]))
                    self.sample_table.set_data(times[1:], concs[1:])
                    self._scheme_rows_cache[scheme] = self.sample_table.get_rows_payload()
                else:
                    self.trough_edit.clear()
                    self.sample_table.set_data(times, concs)
                    self._scheme_rows_cache[scheme] = self.sample_table.get_rows_payload()
            else:
                self.trough_edit.clear()
                self._populate_table(scheme)

        if snapshot.get("pk"):
            self._last_pk = snapshot["pk"]
            self._last_times = snapshot.get("times", [])
            self._last_concs = snapshot.get("concs", [])
            self._last_interp = snapshot.get("interp", "N/A")
            self._last_drug = canonical_drug_name(patient.get("drug", "MPA"))
        else:
            for attr in ["_last_pk", "_last_times", "_last_concs", "_last_interp", "_last_drug"]:
                if hasattr(self, attr):
                    delattr(self, attr)
        self._loaded_form_signature = self._form_signature()
        self._update_action_buttons()
        self._switch_page(0)
        self._switch_report_step(1)

    def _delete_saved_patient(self, patient_id):
        snapshot = next((item for item in self._saved_patients if item["id"] == patient_id), None)
        dlg = ConfirmActionModal(
            "Delete Sample",
            "Are you sure you want to delete this sample from the Sample List?",
            confirm_label="Yes",
            cancel_label="No",
            parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        if snapshot:
            patient = snapshot.get("patient", {})
            log_record_deleted(patient_id, patient.get("pid", "N/A"), patient.get("name", "N/A"))
        delete_record(patient_id)
        self._load_saved_patients()
        self._refresh_patients_list()
        self._show_toast("Deleted successfully", "Sample removed from Sample List.")

    def _delete_draft(self, patient_id):
        snapshot = next((item for item in self._drafts if item["id"] == patient_id), None)
        dlg = ConfirmActionModal(
            "Delete Draft",
            "Are you sure you want to delete this draft from the Draft List?",
            confirm_label="Yes",
            cancel_label="No",
            parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        if snapshot:
            patient = snapshot.get("patient", {})
            log_record_deleted(patient_id, patient.get("pid", "N/A"), patient.get("name", "N/A"))
        delete_record(patient_id)
        self._load_saved_patients()
        self._refresh_patients_list()
        self._show_toast("Deleted successfully", "Draft removed from Draft List.")

    def _show_snapshot_result(self, snapshot):
        pk = snapshot.get("pk")
        if not pk:
            QMessageBox.information(self, "No Report Yet", "Generate a report for this sample first.")
            return
        self._reset_to_sample_list_on_result_close = False
        self._report_snapshot = snapshot
        self._last_pk = pk
        self._last_times = snapshot.get("times", [])
        self._last_concs = snapshot.get("concs", [])
        self._last_interp = snapshot.get("interp", "N/A")
        self._last_drug = canonical_drug_name(snapshot.get("patient", {}).get("drug", "MPA"))
        self._apply_results(pk, self._last_interp)

    def _capture_report_graph_uri(self):
        if self._results_dialog is None:
            return None
        buf = BytesIO()
        self._results_dialog.canvas.fig.savefig(buf, format="png", facecolor="white", bbox_inches="tight")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")

    def _report_file_stem(self, snapshot):
        patient = snapshot.get("patient", {})
        pid = str(patient.get("pid") or "").strip()
        if pid and pid != "N/A":
            stem = f"TDM_{pid}"
        else:
            stem = f"TDM_Report_{snapshot.get('id', datetime.now().strftime('%y%m%d%H%M%S'))}"
        return re.sub(r'[<>:"/\\|?*]+', "_", stem).strip(" .") or "TDM_Report"

    def _expected_report_path(self, snapshot):
        from app_paths import reports_dir

        return reports_dir() / f"{self._report_file_stem(snapshot)}.html"

    def _save_report_file(self, snapshot, graph_uri=None):
        try:
            from report_print import build_report_html

            report_path = self._expected_report_path(snapshot)
            prep_id = snapshot.get("prepared_by_id")
            check_id = snapshot.get("checked_by_id")
            prepared_by = get_signatory_by_id(prep_id) if prep_id else None
            checked_by = get_signatory_by_id(check_id) if check_id else None

            html = build_report_html(
                patient=snapshot.get("patient", {}),
                pk=snapshot.get("pk", {}),
                interp=snapshot.get("interp", "N/A"),
                times=snapshot.get("times", []),
                concs=snapshot.get("concs", []),
                prepared_by=prepared_by,
                checked_by=checked_by,
                graph_uri=graph_uri,
                title=self._report_file_stem(snapshot),
            )
            report_path.write_text(html, encoding="utf-8")
            snapshot["report_path"] = str(report_path)
            return str(report_path)
        except Exception as exc:
            log_error("_save_report_file", exc)
            self._show_toast(
                "Report file not saved",
                "Result is saved to the database but the print file could not be written.",
                tone="error",
            )
            return None

    def _open_report_in_browser(self, snapshot):
        pk = snapshot.get("pk")
        if not pk:
            QMessageBox.information(self, "No Report Yet", "Generate a report for this sample first.")
            return
        report_path = snapshot.get("report_path")
        expected_path = self._expected_report_path(snapshot)
        if not report_path or not Path(report_path).exists() or Path(report_path).name != expected_path.name:
            from report_print import build_report_html

            prep_id = snapshot.get("prepared_by_id")
            check_id = snapshot.get("checked_by_id")
            prepared_by = get_signatory_by_id(prep_id) if prep_id else None
            checked_by = get_signatory_by_id(check_id) if check_id else None
            html = build_report_html(
                patient=snapshot.get("patient", {}),
                pk=snapshot.get("pk", {}),
                interp=snapshot.get("interp", "N/A"),
                times=snapshot.get("times", []),
                concs=snapshot.get("concs", []),
                prepared_by=prepared_by,
                checked_by=checked_by,
                graph_uri=None,
                title=self._report_file_stem(snapshot),
            )
            report_path = str(expected_path)
            snapshot["report_path"] = report_path
            try:
                Path(report_path).write_text(html, encoding="utf-8")
                if snapshot.get("id"):
                    save_record(snapshot, snapshot.get("record_type", "sample"))
            except Exception:
                pass

        if report_path and Path(report_path).exists():
            webbrowser.open(f"file://{Path(report_path).absolute()}")
        else:
            self._show_toast("Error", "Report file not found and could not be regenerated.", tone="error")

    def _apply_results(self, pk, interp):
        if self._results_dialog is None:
            self._results_dialog = ResultsDialog(self, print_handler=self._print_report)
            self._results_dialog.finished.connect(self._on_results_dialog_closed)
        times = getattr(self, "_last_times", None)
        concs = getattr(self, "_last_concs", None)
        self._results_dialog.apply_results(pk, interp, times=times, concs=concs)
        has_data = bool(times and concs)
        self._results_dialog.set_graph_visible(has_data)
        if has_data:
            drug_name = getattr(self, "_last_drug", "MPA")
            self._results_dialog.plot_data(times, concs, drug=drug_name)
        self._results_dialog.show()
        self._results_dialog.raise_()
        self._results_dialog.activateWindow()

    def _on_results_dialog_closed(self, _result):
        self._results_dialog = None
        if not getattr(self, "_reset_to_sample_list_on_result_close", False):
            return
        self._clear_form_state(close_results=False)
        if hasattr(self, "_report_snapshot"):
            delattr(self, "_report_snapshot")
        for attr in ["_last_pk", "_last_times", "_last_concs", "_last_interp", "_last_drug"]:
            if hasattr(self, attr):
                delattr(self, attr)
        self._switch_page(1)
        if hasattr(self, "_main_scroll"):
            self._main_scroll.verticalScrollBar().setValue(0)
        self._reset_to_sample_list_on_result_close = False

    def _calculate(self):
        phone = self.f_phone.text().strip()
        if phone and not is_valid_phone(phone):
            self._show_toast("Invalid Phone", "Please enter a valid 11-digit phone number.", tone="warning")
            return

        if hasattr(self, "_report_snapshot"):
            delattr(self, "_report_snapshot")

        drug = canonical_drug_name(self.f_drug.text().strip() or "MPA")

        if getattr(self, "_sampling_mode", "multi") == "direct":
            try:
                auc_val = float(self._direct_auc_edit.text().strip())
                if auc_val <= 0:
                    raise ValueError
            except ValueError:
                QMessageBox.warning(self, "Invalid Value", "Please enter a valid AUC value (mg·h/L).")
                return
            pk = {
                "auc_0_last": auc_val,
                "auc_0_12": auc_val,
                "auc_lss": auc_val,
                "lss_equation": "Direct input (mg·h/L)",
                "lambda_z": None,
                "t_half": None,
                "r_squared": None,
                "t_last": 0.0,
                "c_trough": None,
                "c_last": None,
            }
            interp, _ = interpret_result(drug, auc_val)
            self._last_pk = pk
            self._last_times = []
            self._last_concs = []
            self._last_interp = interp
            self._last_drug = drug
            patient = self._patient_payload()
            log_report_generated(patient.get("pid", "N/A"), patient.get("name", "N/A"), drug, auc_val)
            self._apply_results(pk, interp)
            snapshot = self._snapshot_payload()
            existing_id = getattr(self, "_active_record_id", None)
            if getattr(self, "_active_record_source", None) == "sample" and existing_id is not None:
                snapshot["id"] = existing_id
            if getattr(self, "_active_record_source", None) == "draft" and existing_id:
                delete_record(existing_id)
            save_record(snapshot, "sample")
            saved_path = self._save_report_file(snapshot, graph_uri=None)
            snapshot["report_path"] = saved_path or ""
            save_record(snapshot, "sample")
            self._report_snapshot = snapshot
            self._active_record_id = snapshot["id"]
            self._active_record_source = "sample"
            self._loaded_form_signature = self._form_signature()
            self._load_saved_patients()
            self._reset_list_view(getattr(self, "sample_list_card", None))
            self._refresh_patients_list()
            self._reset_to_sample_list_on_result_close = True
            return

        times, concs = self._read_table(skip_empty=False)
        if times is None or len(times) < 3:
            QMessageBox.warning(self, "Insufficient Data", "Please enter at least the trough + 2 post-dose concentrations.")
            return
        if any(b <= a for a, b in zip(times, times[1:])):
            QMessageBox.warning(self, "Invalid Sample Times", "Sample times must be strictly increasing without duplicates.")
            return
        pk = calculate_auc_full(times, concs)

        lss = None
        if len(times) == 3:
            rounded_times = set(round(t, 1) for t in times)
            if rounded_times == {0.0, 0.5, 2.0}:
                lss = calculate_lss_auc(times, concs, cni=drug)

        if lss and drug.upper() in lss["equation_label"].upper():
            pk["auc_lss"] = lss["auc_lss"]
            pk["lss_equation"] = lss["equation_label"]
            pk["lss_r2"] = lss["r2"]

        interp_value = pk.get("auc_lss") if pk.get("auc_lss") is not None else pk["auc_0_12"]
        interp, _ = interpret_result(drug, interp_value)
        self._last_pk = pk
        self._last_times = times
        self._last_concs = concs
        self._last_interp = interp
        self._last_drug = drug
        patient = self._patient_payload()
        log_report_generated(patient.get("pid", "N/A"), patient.get("name", "N/A"), drug, pk.get("auc_0_12"))
        self._apply_results(pk, interp)

        snapshot = self._snapshot_payload()
        existing_id = getattr(self, "_active_record_id", None)
        was_updating = getattr(self, "_active_record_source", None) == "sample" and bool(existing_id)
        if getattr(self, "_active_record_source", None) == "sample" and existing_id is not None:
            snapshot["id"] = existing_id
        if getattr(self, "_active_record_source", None) == "draft" and existing_id:
            delete_record(existing_id)
        save_record(snapshot, "sample")
        saved_path = self._save_report_file(snapshot, graph_uri=self._capture_report_graph_uri())
        snapshot["report_path"] = saved_path or ""
        save_record(snapshot, "sample")
        self._report_snapshot = snapshot
        self._active_record_id = snapshot["id"]
        self._active_record_source = "sample"
        self._loaded_form_signature = self._form_signature()
        self._load_saved_patients()
        self._reset_list_view(getattr(self, "sample_list_card", None))
        self._refresh_patients_list()
        if self._results_dialog is not None:
            if was_updating:
                self._results_dialog.show_toast("Report updated", "Generated result has been updated successfully.")
            else:
                self._results_dialog.show_toast("Report generated", "Generated result has been saved successfully.")
        self._reset_to_sample_list_on_result_close = True

    def _print_report(self):
        if not hasattr(self, "_last_pk"):
            return
        if hasattr(self, "_report_snapshot"):
            self._open_report_in_browser(self._report_snapshot)
            self._switch_page(1)
            if hasattr(self, "_main_scroll"):
                self._main_scroll.verticalScrollBar().setValue(0)
            return
        snapshot = self._snapshot_payload()
        existing_id = getattr(self, "_active_record_id", None)
        if existing_id:
            snapshot["id"] = existing_id
        report_path = self._save_report_file(snapshot, graph_uri=self._capture_report_graph_uri())
        webbrowser.open(Path(report_path).as_uri())
        self._switch_page(1)
        if hasattr(self, "_main_scroll"):
            self._main_scroll.verticalScrollBar().setValue(0)

    def _clear_form_state(self, close_results=True):
        self._active_record_id = None
        self._active_record_source = None
        self._loaded_form_signature = None
        self._reset_to_sample_list_on_result_close = False
        self._current_scheme = None
        self._scheme_rows_cache = {}
        default_duration = self._global_duration_options[0] if self._global_duration_options else 4
        self._set_duration_options(self._global_duration_options, selected=default_duration)
        self._switch_sampling_mode("multi")
        self._toggle_multi.setChecked(True)
        self._direct_auc_edit.clear()
        if close_results and hasattr(self, "_report_snapshot"):
            delattr(self, "_report_snapshot")
        for edit in [
            self.f_name,
            self.f_age,
            self.f_hosp_no,
            self.f_report_no,
            self.f_referred_by,
            self.f_dose,
            self.f_diag,
            self.trough_edit,
            self.f_phone,
        ]:
            edit.clear()
        self.f_drug.setText("MPA")
        self.f_preparation.setText("Mycophenolate Mofetil (MMF)")
        self.f_diag.setText("Post Renal Transplant")
        self.f_sex.setCurrentIndex(0)
        self.f_med.clear_selection()
        self.f_tx_date.setDate(None)
        self.f_invoice_date.setDate(QDate.currentDate())
        self.f_delivery_date.setDate(QDate.currentDate())
        self.f_dose_dt.setDateTime(QDateTime.currentDateTime())
        self.f_sample_collection_date.setDate(QDate.currentDate())
        self._populate_table(default_duration)
        self._scheme_rows_cache[default_duration] = self.sample_table.get_rows_payload()
        self._update_action_buttons()
        self._switch_report_step(0)
        if close_results and self._results_dialog is not None:
            self._results_dialog.close()
        if close_results:
            for attr in ["_last_pk", "_last_times", "_last_concs", "_last_interp", "_last_drug"]:
                if hasattr(self, attr):
                    delattr(self, attr)

    def _reset(self):
        self._clear_form_state()
        self._switch_page(0)
        if hasattr(self, "_main_scroll"):
            self._main_scroll.verticalScrollBar().setValue(0)
