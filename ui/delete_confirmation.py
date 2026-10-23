"""文件删除确认；两类删除的免提示选项独立且只在当前应用进程内生效。"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QCheckBox, QMessageBox


_SKIP_PROPERTY_PREFIX = "mask_annotator_skip_delete_confirmation_"


def confirm_delete(parent, operation: str, title: str, text: str) -> bool:
    app = QApplication.instance()
    property_name = _SKIP_PROPERTY_PREFIX + operation
    if app.property(property_name):
        return True

    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Warning)
    box.setWindowTitle(title)
    box.setTextFormat(Qt.PlainText)
    box.setText(text)
    checkbox = QCheckBox("此次运行中不再提示", box)
    checkbox.setToolTip("仅对本类删除操作生效，重启软件后恢复提示。")
    box.setCheckBox(checkbox)
    delete_button = box.addButton("删除", QMessageBox.DestructiveRole)
    cancel_button = box.addButton("取消", QMessageBox.RejectRole)
    box.setDefaultButton(cancel_button)
    box.setEscapeButton(cancel_button)
    box.exec_()
    confirmed = box.clickedButton() == delete_button
    if confirmed and checkbox.isChecked():
        app.setProperty(property_name, True)
    box.deleteLater()
    return confirmed
