import logging
import sqlite3
import numpy as np
import pandas as pd
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


from widgets.pyqt6_tools import get_btn_style


class UpdateDatabaseInfo(QDialog):
    """Dialog to update animals information in the database."""

    @staticmethod
    def smart_cast(s: str):
        """Try to convert a string to int or float if possible, otherwise
        return the original string."""
        s = s.strip()
        try:
            value = int(s)
        except ValueError:
            try:
                value = float(s)
            except ValueError:
                value = s
        return value

    def __init__(self, parent: QWidget | None, database_path: Path):
        """Initialize the dialog and load database information."""
        super().__init__(parent)
        self.setWindowTitle("LMT-EYE - Analysis Settings - Animals Table")

        self.database_path = database_path
        self.df = self.get_db_df()
        self._init_ui()

    def _init_ui(self):

        # ================ BUTTONS ================
        layout = QVBoxLayout()
        btn_layout = QHBoxLayout()

        btn_style = get_btn_style(txt_color="white", bg_color="black")

        self.validate_btn = QPushButton("Validate")
        self.validate_btn.setStyleSheet(btn_style)
        self.validate_btn.clicked.connect(self.on_validate)
        btn_layout.addWidget(self.validate_btn)

        self.add_col_btn = QPushButton("Add Column")
        self.add_col_btn.setStyleSheet(btn_style)
        self.add_col_btn.clicked.connect(self.on_add_column)
        btn_layout.addWidget(self.add_col_btn)

        self.del_col_btn = QPushButton("Delete Column")
        self.del_col_btn.setStyleSheet(btn_style)
        self.del_col_btn.clicked.connect(self.on_delete_column)
        btn_layout.addWidget(self.del_col_btn)

        btn_layout.addStretch(1)
        layout.addLayout(btn_layout)

        # ================ TABLE ================
        self.table = QTableWidget()
        self.table.setMinimumSize(800, 400)
        self.table.cellChanged.connect(self.on_cell_changed)
        self.build_table_from_df()

        layout.addWidget(self.table)
        self.setLayout(layout)

    def build_table_from_df(self):
        self.table.blockSignals(True)
        self.table.clear()
        self.table.setRowCount(len(self.df))
        self.table.setColumnCount(len(self.df.columns))
        self.table.setHorizontalHeaderLabels(self.df.columns)

        protected = {"ID", "RFID"}

        for row_idx, (_, row) in enumerate(self.df.iterrows()):
            for j, value in enumerate(row):
                item = QTableWidgetItem(str(value))
                self.table.setItem(row_idx, j, item)
                col_name = self.df.columns[j]
                if col_name in protected:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.resizeColumnsToContents()
        self.table.blockSignals(False)

    def on_cell_changed(self, row: int, column: int):
        protected = {"GENOTYPE", "NAME"}
        item = self.table.item(row, column)
        if item is None:
            return

        col_name = self.df.columns[column]
        col_type = self.df[col_name].dtype

        if col_name in protected:
            new_value = item.text()
        else:
            new_value = UpdateDatabaseInfo.smart_cast(item.text())

        correct_value = None

        if col_type == type(new_value):
            correct_value = new_value

        if col_type.kind == "O":  # object, usually string
            if type(new_value) != str:
                correct_value = str(new_value)
            else:
                correct_value = new_value

        if col_type.kind == "f":
            if type(new_value) == int:
                correct_value = float(new_value)
            if type(new_value) == str and new_value == "":
                correct_value = np.nan
                item.setText("nan")

        if col_type.kind == "i":
            if type(new_value) == float and new_value.is_integer():
                correct_value = int(new_value)
            if type(new_value) == str and new_value == "":
                correct_value = 0
                item.setText("0")

        if correct_value is None:
            self.table.blockSignals(True)
            expected_type = "UNKNOWN"
            if col_type.kind == "f":
                expected_type = "REAL (float)"
            if col_type.kind == "i":
                expected_type = "INTEGER (int)"
            if col_type.kind == "O":
                expected_type = "TEXT (str)"
            warning_msg = (
                f"Column '{col_name}' expects a {expected_type}. "
                "Reverting to previous value."
            )
            QMessageBox.warning(
                self,
                "Invalid Input",
                warning_msg,
            )
            old_value = self.df.at[row, col_name]
            item.setText(str(old_value))
            self.table.blockSignals(False)
        else:
            self.df.at[row, col_name] = correct_value

    def on_add_column(self):
        col_name, ok = QInputDialog.getText(self, "Add Column", "Column name:")
        col_name = col_name.strip().upper()
        if not ok:
            return
        if not col_name:
            QMessageBox.information(self, "Cancel", f"Invalid column name.")
            return
        for col in self.df.columns:
            if col_name == col:
                QMessageBox.information(
                    self, "Cancel", f"Column '{col_name}' already exists."
                )
                return

        dlg = SQLTypeDialog(self)
        if not dlg.exec():
            return

        col_type = dlg.get_choosen_type()
        if col_type == "TEXT":
            default = ""
        elif col_type == "REAL":
            default = np.nan
        elif col_type == "INTEGER":
            default = 0
        else:
            default = None
        self.df[col_name] = pd.Series([default] * len(self.df))
        self.build_table_from_df()

    def on_delete_column(self):
        protected = {"ID", "RFID", "GENOTYPE", "NAME"}
        cols = [col for col in self.df.columns if col not in protected]
        if not cols:
            QMessageBox.information(
                self,
                "No Deletable Columns",
                "No columns available for deletion.",
            )
            return
        col_name, ok = QInputDialog.getItem(
            self, "Delete Column", "Select column to delete:", cols, 0, False
        )
        if not ok or not col_name:
            return
        confirm = QMessageBox.question(
            self,
            "Confirm Delete",
            (
                f"Are you sure you want to delete column '{col_name}'? "
                "This cannot be undone."
            ),
        )
        if not confirm:
            return
        self.df.drop(columns=[col_name], inplace=True)
        self.build_table_from_df()

    def get_db_df(self):
        connection = sqlite3.connect(self.database_path)
        c = connection.cursor()
        c.execute("SELECT * FROM ANIMAL")
        data = c.fetchall()
        columns = [description[0] for description in c.description]
        df = pd.DataFrame(data, columns=columns)
        c.close()
        connection.close()
        return df

    def on_validate(self):
        protected = {"ID", "RFID"}
        try:
            connection = sqlite3.connect(self.database_path)
            c = connection.cursor()

            c.execute("PRAGMA table_info(ANIMAL)")
            db_columns = set([row[1] for row in c.fetchall()])
            df_columns = list(self.df.columns)

            # Remove exceeding columns
            # ----------------

            exceeding_cols = [
                col
                for col in db_columns
                if col not in df_columns and col not in protected
            ]
            for col in exceeding_cols:
                alter_sql = f"ALTER TABLE ANIMAL DROP COLUMN {col}"
                c.execute(alter_sql)

            # Add missing columns
            # ----------------

            missing_cols = [
                col
                for col in df_columns
                if col not in db_columns and col not in protected
            ]
            for col in missing_cols:
                dtype_kind = self.df[col].dtype.kind
                if dtype_kind == "i":
                    sql_type = "INTEGER"
                elif dtype_kind == "f":
                    sql_type = "REAL"
                else:
                    sql_type = "TEXT"
                alter_sql = f"ALTER TABLE ANIMAL ADD COLUMN {col} {sql_type}"
                c.execute(alter_sql)

            # Update values in all columns
            # ----------------

            c.execute("PRAGMA table_info(ANIMAL)")
            db_columns = set([row[1] for row in c.fetchall()])
            update_cols = [
                col
                for col in df_columns
                if col in db_columns and col not in protected
            ]
            for _, row in self.df.iterrows():
                match_col = None
                match_val = None
                if "ID" in df_columns and pd.notna(row["ID"]):
                    match_col = "ID"
                    match_val = row["ID"]
                elif "RFID" in df_columns and pd.notna(row["RFID"]):
                    match_col = "RFID"
                    match_val = row["RFID"]
                else:
                    logging.warning(
                        f"Skipping row with no valid ID or RFID: {row}"
                    )
                    continue

                set_clause = ", ".join([f"{col}=?" for col in update_cols])
                values = [row[col] for col in update_cols]
                values.append(match_val)
                c.execute(
                    f"UPDATE ANIMAL SET {set_clause} WHERE {match_col}=?",
                    values,
                )
            connection.commit()
            c.close()
            connection.close()
            QMessageBox.information(self, "Validated", "Database updated.")
            self.accept()
        except Exception as e:
            QMessageBox.critical(
                self, "Error", f"Failed to update database: {e}"
            )


class SQLTypeDialog(QDialog):
    """Dialog to select a type for a new column in the database."""

    INFOS = {
        "TEXT": "Any text string.",
        "INTEGER": "Whole numbers (int).",
        "REAL": "Floating point numbers (float).",
    }

    def __init__(self, parent: QWidget | None):
        """Initialize the type selection dialog."""
        super().__init__(parent)
        self.setWindowTitle("LMT-EYE - Analysis Settings - Select Column Type")
        layout = QVBoxLayout()
        self.combo = QComboBox()
        self.combo.addItems(self.INFOS.keys())
        layout.addWidget(self.combo)
        self.desc = QLabel()
        layout.addWidget(self.desc)
        self.combo.currentTextChanged.connect(self.update_type_description)
        self.update_type_description(self.combo.currentText())
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
        self.setLayout(layout)

    def update_type_description(self, t):
        """Update the description label based on the selected type."""
        self.desc.setText(f"<i>{self.INFOS[t]}</i>")

    def get_choosen_type(self):
        """Return the selected SQL type as a string."""
        return self.combo.currentText()


if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication

    app = QApplication([])
    db_path = Path.home() / "Desktop" / "APP_TEST" / "example_dataset.sqlite"

    dlg = UpdateDatabaseInfo(None, db_path)

    if dlg.exec():
        print("Database updated:")
        print(dlg.df)
