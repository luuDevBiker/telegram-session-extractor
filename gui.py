"""PyQt6 GUI for Telegram session extractor."""
import asyncio
import json
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QTableWidget, QTableWidgetItem,
    QProgressBar, QStatusBar, QMessageBox, QGroupBox, QRadioButton,
    QButtonGroup, QHeaderView,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor

from extractor import extract_from_zip, extract_from_profile_dir
from probe import probe_sessions_concurrent, ProbeResult


class WorkerThread(QThread):
    """Background thread for extraction and probing."""
    finished = pyqtSignal(list)
    progress = pyqtSignal(int, int)
    error = pyqtSignal(str)

    def __init__(self, path: Path, output_dir: Path, source_type: str):
        super().__init__()
        self.path = path
        self.output_dir = output_dir
        self.source_type = source_type  # "zip" or "dir"

    def run(self):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            if self.source_type == "zip":
                sessions = extract_from_zip(self.path)
            else:
                sess = extract_from_profile_dir(self.path)
                sessions = {"profile": sess} if sess else {}

            if not sessions:
                self.error.emit("Không tìm thấy session nào")
                return

            async def probe():
                return await probe_sessions_concurrent(
                    sessions,
                    self.output_dir,
                    progress_callback=lambda cur, total: self.progress.emit(cur, total),
                )

            results = loop.run_until_complete(probe())
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            loop.close()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Telegram Session Extractor")
        self.resize(1000, 700)

        self.output_dir = Path.home() / "telegram_sessions"
        self.worker: Optional[WorkerThread] = None

        self.init_ui()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Input section
        input_group = QGroupBox("Nguồn dữ liệu")
        input_layout = QVBoxLayout()

        # Source type radio buttons
        source_layout = QHBoxLayout()
        self.rb_zip = QRadioButton("File ZIP")
        self.rb_dir = QRadioButton("Thư mục Chrome profile")
        self.rb_zip.setChecked(True)
        source_layout.addWidget(self.rb_zip)
        source_layout.addWidget(self.rb_dir)
        source_layout.addStretch()
        input_layout.addLayout(source_layout)

        # File/dir selection
        select_layout = QHBoxLayout()
        self.path_label = QLabel("Chưa chọn file/thư mục")
        self.path_label.setStyleSheet("color: gray;")
        select_layout.addWidget(self.path_label)
        btn_browse = QPushButton("Chọn...")
        btn_browse.clicked.connect(self.browse_source)
        select_layout.addWidget(btn_browse)
        input_layout.addLayout(select_layout)

        input_group.setLayout(input_layout)
        layout.addWidget(input_group)

        # Action buttons
        action_layout = QHBoxLayout()
        self.btn_extract = QPushButton("Trích xuất & Probe")
        self.btn_extract.clicked.connect(self.start_extraction)
        self.btn_extract.setEnabled(False)
        action_layout.addWidget(self.btn_extract)

        self.btn_export_excel = QPushButton("Export Excel")
        self.btn_export_excel.clicked.connect(self.export_excel)
        self.btn_export_excel.setEnabled(False)
        action_layout.addWidget(self.btn_export_excel)

        action_layout.addStretch()
        layout.addLayout(action_layout)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Results table
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Phone", "Status", "User ID", "Username",
            "First Name", "Last Name", "Error"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.results: list[ProbeResult] = []

    def browse_source(self):
        if self.rb_zip.isChecked():
            path, _ = QFileDialog.getOpenFileName(
                self, "Chọn file ZIP", "", "ZIP Files (*.zip)"
            )
        else:
            path = QFileDialog.getExistingDirectory(
                self, "Chọn thư mục Chrome profile"
            )

        if path:
            self.source_path = Path(path)
            self.path_label.setText(str(self.source_path))
            self.path_label.setStyleSheet("color: black;")
            self.btn_extract.setEnabled(True)

    def start_extraction(self):
        if not hasattr(self, 'source_path'):
            return

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.btn_extract.setEnabled(False)
        self.table.setRowCount(0)
        self.status_bar.showMessage("Đang trích xuất...")

        source_type = "zip" if self.rb_zip.isChecked() else "dir"
        self.worker = WorkerThread(self.source_path, self.output_dir, source_type)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(self.on_error)
        self.worker.start()

    def update_progress(self, current: int, total: int):
        self.progress_bar.setValue(int(current / total * 100))
        self.status_bar.showMessage(f"Đang probe: {current}/{total}")

    def on_finished(self, results: list[ProbeResult]):
        self.results = results
        self.progress_bar.setVisible(False)
        self.btn_extract.setEnabled(True)
        self.btn_export_excel.setEnabled(True)

        self.populate_table(results)

        alive = sum(1 for r in results if r.status == "alive")
        self.status_bar.showMessage(f"Hoàn tất: {alive}/{len(results)} session còn sống")

    def on_error(self, error_msg: str):
        self.progress_bar.setVisible(False)
        self.btn_extract.setEnabled(True)
        QMessageBox.critical(self, "Lỗi", error_msg)
        self.status_bar.showMessage("Lỗi")

    def populate_table(self, results: list[ProbeResult]):
        self.table.setRowCount(len(results))
        for row, r in enumerate(results):
            self.table.setItem(row, 0, QTableWidgetItem(r.phone))
            self.table.setItem(row, 1, QTableWidgetItem(r.status))
            self.table.setItem(row, 2, QTableWidgetItem(str(r.user_id or "")))
            self.table.setItem(row, 3, QTableWidgetItem(r.username or ""))
            self.table.setItem(row, 4, QTableWidgetItem(r.first_name or ""))
            self.table.setItem(row, 5, QTableWidgetItem(r.last_name or ""))
            self.table.setItem(row, 6, QTableWidgetItem(r.error or ""))

            # Color code status
            status_item = self.table.item(row, 1)
            if r.status == "alive":
                status_item.setBackground(QColor(200, 255, 200))
            elif r.status == "dead":
                status_item.setBackground(QColor(255, 200, 200))
            else:
                status_item.setBackground(QColor(255, 255, 200))

    def export_excel(self):
        if not self.results:
            return

        from openpyxl import Workbook
        from datetime import datetime

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Excel", "", "Excel Files (*.xlsx)"
        )
        if not path:
            return

        wb = Workbook()
        ws = wb.active
        ws.title = "Telegram Sessions"

        headers = [
            "Phone", "Status", "User ID", "Username",
            "First Name", "Last Name", "Error", "Exported At"
        ]
        ws.append(headers)

        for r in self.results:
            ws.append([
                r.phone, r.status, r.user_id, r.username,
                r.first_name, r.last_name, r.error,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ])

        wb.save(path)
        self.status_bar.showMessage(f"Đã export: {path}")


def main():
    app = QApplication([])
    window = MainWindow()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
