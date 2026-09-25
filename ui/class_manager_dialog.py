# ui/class_manager_dialog.py
"""
病害类别管理对话框：增删改查、颜色拾取
"""
import copy
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
                             QTableWidget, QTableWidgetItem, QHeaderView,
                             QDialogButtonBox, QColorDialog)
from PyQt5.QtGui import QColor


class ClassManagerDialog(QDialog):
    def __init__(self, classes: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("病害类别管理")
        self.resize(480, 360)
        self.classes = copy.deepcopy(classes)

        layout = QVBoxLayout(self)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["像素值", "类别名称", "显示颜色(BGR)"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setEditTriggers(
            QTableWidget.DoubleClicked | QTableWidget.SelectedClicked)
        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        btn_add   = QPushButton("＋ 添加类别")
        btn_del   = QPushButton("－ 删除选中")
        btn_color = QPushButton("🎨 修改颜色")
        btn_add.clicked.connect(self._add_row)
        btn_del.clicked.connect(self._del_row)
        btn_color.clicked.connect(self._pick_color)
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_del)
        btn_row.addWidget(btn_color)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._refresh_table()

    def _refresh_table(self):
        self.table.setRowCount(0)
        for cls in self.classes:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(cls["value"])))
            self.table.setItem(row, 1, QTableWidgetItem(cls["name"]))
            b, g, r = cls["color"]
            color_item = QTableWidgetItem(f"({b},{g},{r})")
            color_item.setBackground(QColor(r, g, b))
            color_item.setForeground(QColor(255 - r, 255 - g, 255 - b))
            self.table.setItem(row, 2, color_item)

    def _add_row(self):
        used = {c["value"] for c in self.classes}
        new_val = 1
        while new_val in used:
            new_val += 1
        self.classes.append({
            "value": new_val,
            "name": f"新类别{new_val}",
            "color": (128, 128, 128)
        })
        self._refresh_table()

    def _del_row(self):
        row = self.table.currentRow()
        if row >= 0 and len(self.classes) > 1:
            self.classes.pop(row)
            self._refresh_table()

    def _pick_color(self):
        row = self.table.currentRow()
        if row < 0:
            return
        b, g, r = self.classes[row]["color"]
        color = QColorDialog.getColor(QColor(r, g, b), self, "选择颜色")
        if color.isValid():
            self.classes[row]["color"] = (
                color.blue(), color.green(), color.red())
            self._refresh_table()

    def get_classes(self) -> list:
        result = []
        for i, cls in enumerate(self.classes):
            try:
                val_item  = self.table.item(i, 0)
                name_item = self.table.item(i, 1)
                val  = int(val_item.text())  if val_item  else cls["value"]
                name = name_item.text()       if name_item else cls["name"]
                result.append({"value": val, "name": name, "color": cls["color"]})
            except Exception:
                pass
        return result
