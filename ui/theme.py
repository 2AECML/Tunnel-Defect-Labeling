# ui/theme.py
"""
主题系统：夜间模式 / 白天模式
统一管理所有颜色 token，主窗口和编辑面板都从这里取色。
"""

THEMES = {
    "dark": {
        # 背景层级
        "bg_root":      "#141414",
        "bg_bar":       "#1c1c1c",
        "bg_bar_border":"#2e2e2e",
        "bg_card":      "#1e1e1e",
        "bg_input":     "#252525",
        "bg_hover":     "#2d2d2d",
        "bg_panel":     "#1a1a1a",
        "bg_title_bar": "#202020",

        # 文字
        "text_primary":   "#e8e8e8",
        "text_secondary": "#9a9a9a",
        "text_muted":     "#555555",
        "text_accent":    "#5ba3e0",
        "text_green":     "#6ecf6e",
        "text_red":       "#d46a6a",
        "text_orange":    "#e0a060",
        "text_hint":      "#7a7a7a",

        # 边框
        "border":         "#333333",
        "border_hover":   "#555555",
        "border_accent":  "#4a7aac",
        "border_green":   "#3a7a3a",
        "border_red":     "#7a3a3a",

        # 按钮
        "btn_nav_bg":     "#242424",
        "btn_nav_text":   "#c0c0c0",
        "btn_folder_bg":  "#1e2c3e",
        "btn_folder_text":"#7ab8e8",
        "btn_edit_bg":    "#1e3520",
        "btn_edit_text":  "#70d070",
        "btn_edit_active_bg":  "#245a24",
        "btn_edit_active_text":"#90ee90",
        "btn_delete_bg":  "#2e1c1c",
        "btn_delete_text":"#d46a6a",
        "btn_mask_bg":    "#1e1e32",
        "btn_mask_text":  "#8888cc",

        # 工具面板
        "tool_btn_bg":    "#262626",
        "tool_btn_text":  "#c0c0c0",
        "tool_btn_checked_bg":   "#1a3a60",
        "tool_btn_checked_text": "#60aaff",
        "tool_btn_checked_border":"#4090e0",

        # 滑块
        "slider_groove":  "#333333",
        "slider_handle":  "#4a7aac",

        # 状态
        "status_ok":      "#5ab05a",
        "status_warn":    "#d4a030",

        # SpinBox
        "spin_bg":        "#242424",
        "spin_text":      "#c8c8c8",
        "spin_border":    "#3a3a3a",
        "input_selection_bg": "#1f5f9f",

        # Section label
        "section_label":  "#5090c0",

        # Separator
        "sep":            "#2e2e2e",

        # ComboBox
        "combo_bg":       "#242424",
        "combo_text":     "#d0d0d0",
        "combo_border":   "#3a3a3a",
        "scroll_handle":  "#454b53",
        "scroll_hover":   "#626c77",

        # Checkbox
        "chk_indicator_bg":      "#242424",
        "chk_indicator_checked": "#1a3a60",
        "chk_indicator_border":  "#4a4a4a",
        "chk_indicator_checked_border": "#4090e0",
        "chk_text":       "#c0c0c0",

        "theme_btn_text": "☀  日间模式",
    },

    "light": {
        "bg_root":      "#f0f0f0",
        "bg_bar":       "#ffffff",
        "bg_bar_border":"#d8d8d8",
        "bg_card":      "#f8f8f8",
        "bg_input":     "#ffffff",
        "bg_hover":     "#ebebeb",
        "bg_panel":     "#f4f4f4",
        "bg_title_bar": "#e8e8e8",

        "text_primary":   "#1a1a1a",
        "text_secondary": "#555555",
        "text_muted":     "#999999",
        "text_accent":    "#1a6aaa",
        "text_green":     "#1a7a1a",
        "text_red":       "#aa2222",
        "text_orange":    "#b06010",
        "text_hint":      "#777777",

        "border":         "#d0d0d0",
        "border_hover":   "#aaaaaa",
        "border_accent":  "#1a6aaa",
        "border_green":   "#1a7a1a",
        "border_red":     "#aa2222",

        "btn_nav_bg":     "#e8e8e8",
        "btn_nav_text":   "#333333",
        "btn_folder_bg":  "#e0edf8",
        "btn_folder_text":"#1a5a9a",
        "btn_edit_bg":    "#e0f0e0",
        "btn_edit_text":  "#1a6a1a",
        "btn_edit_active_bg":  "#c8e8c8",
        "btn_edit_active_text":"#145a14",
        "btn_delete_bg":  "#f5e0e0",
        "btn_delete_text":"#aa2222",
        "btn_mask_bg":    "#e8e8f8",
        "btn_mask_text":  "#444488",

        "tool_btn_bg":    "#ebebeb",
        "tool_btn_text":  "#333333",
        "tool_btn_checked_bg":   "#cce0f8",
        "tool_btn_checked_text": "#1a5aaa",
        "tool_btn_checked_border":"#1a6acc",

        "slider_groove":  "#d0d0d0",
        "slider_handle":  "#1a6aaa",

        "status_ok":      "#1a7a1a",
        "status_warn":    "#b06010",

        "spin_bg":        "#ffffff",
        "spin_text":      "#1a1a1a",
        "spin_border":    "#c0c0c0",
        "input_selection_bg": "#195ba8",

        "section_label":  "#1a5a9a",
        "sep":            "#d8d8d8",

        "combo_bg":       "#ffffff",
        "combo_text":     "#1a1a1a",
        "combo_border":   "#c0c0c0",
        "scroll_handle":  "#c3cbd4",
        "scroll_hover":   "#9ba9b8",

        "chk_indicator_bg":      "#ffffff",
        "chk_indicator_checked": "#d0e8ff",
        "chk_indicator_border":  "#aaaaaa",
        "chk_indicator_checked_border": "#1a6acc",
        "chk_text":       "#333333",

        "theme_btn_text": "🌙  夜间模式",
    }
}


def build_control_style(t: dict) -> str:
    """主窗口、设置和编辑面板共用的滚动条及下拉选择样式。"""
    return f"""
QScrollBar:vertical {{
    background: transparent; border: none; width: 12px; margin: 4px 2px;
}}
QScrollBar:horizontal {{
    background: transparent; border: none; height: 12px; margin: 2px 4px;
}}
QScrollBar::handle:vertical {{
    background: {t['scroll_handle']}; border: none; border-radius: 4px; min-height: 28px;
}}
QScrollBar::handle:horizontal {{
    background: {t['scroll_handle']}; border: none; border-radius: 4px; min-width: 28px;
}}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
    background: {t['scroll_hover']};
}}
QScrollBar::handle:vertical:pressed, QScrollBar::handle:horizontal:pressed {{
    background: {t['text_accent']};
}}
QScrollBar::handle:vertical:disabled, QScrollBar::handle:horizontal:disabled {{
    background: {t['sep']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0; width: 0; border: none; background: transparent;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0; height: 0; border: none; background: transparent;
}}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; border: none; }}
QScrollBar::up-arrow, QScrollBar::down-arrow,
QScrollBar::left-arrow, QScrollBar::right-arrow {{ image: none; width: 0; height: 0; }}
QAbstractScrollArea::corner {{ background: {t['bg_root']}; border: none; }}
QComboBox {{
    combobox-popup: 0;
    background: {t['combo_bg']}; color: {t['combo_text']};
    border: 1px solid {t['combo_border']}; border-radius: 6px;
    padding: 6px 32px 6px 10px; min-height: 18px;
    font-family: 'Microsoft YaHei', 'Segoe UI'; font-size: 12px;
}}
QComboBox:hover {{ border-color: {t['border_hover']}; background: {t['bg_hover']}; }}
QComboBox:focus, QComboBox:on {{ border-color: {t['text_accent']}; }}
QComboBox:disabled {{
    background: {t['bg_root']}; color: {t['text_muted']}; border-color: {t['sep']};
}}
QComboBox::drop-down {{
    subcontrol-origin: padding; subcontrol-position: top right;
    width: 28px; border: none; background: transparent;
}}
QComboBox::down-arrow {{ image: none; width: 0; height: 0; }}
QFrame#comboPopup {{ background: transparent; border: none; }}
QComboBox QAbstractItemView {{
    background: {t['bg_bar']}; color: {t['text_primary']};
    border: 1px solid {t['border']}; border-radius: 6px;
    padding: 4px; outline: 0;
    selection-background-color: {t['tool_btn_checked_bg']};
    selection-color: {t['tool_btn_checked_text']};
    font-family: 'Microsoft YaHei', 'Segoe UI'; font-size: 12px;
}}
QComboBox QAbstractItemView::item {{
    min-height: 24px; padding: 4px 8px; border: none; border-radius: 4px;
}}
QComboBox QAbstractItemView::item:hover {{
    background: {t['bg_hover']}; color: {t['text_primary']};
}}
QComboBox QAbstractItemView::item:selected {{
    background: {t['tool_btn_checked_bg']}; color: {t['tool_btn_checked_text']};
}}
QComboBox QAbstractItemView::item:disabled {{ color: {t['text_muted']}; }}
QSpinBox#stepperSpinBox {{ padding: 3px 24px 3px 6px; }}
QSpinBox#stepperSpinBox, QSpinBox#stepperSpinBox QLineEdit {{
    selection-background-color: {t['input_selection_bg']}; selection-color: #ffffff;
}}
QSpinBox#stepperSpinBox:focus {{ border-color: {t['text_accent']}; }}
QSpinBox#stepperSpinBox::up-button {{
    subcontrol-origin: border; subcontrol-position: top right;
    width: 22px; height: 15px; background: transparent;
    border: none; border-left: 1px solid {t['sep']}; border-top-right-radius: 4px;
}}
QSpinBox#stepperSpinBox::down-button {{
    subcontrol-origin: border; subcontrol-position: bottom right;
    width: 22px; height: 15px; background: transparent;
    border: none; border-left: 1px solid {t['sep']}; border-bottom-right-radius: 4px;
}}
QSpinBox#stepperSpinBox::up-button:hover, QSpinBox#stepperSpinBox::down-button:hover {{
    background: {t['bg_hover']};
}}
QSpinBox#stepperSpinBox::up-button:pressed, QSpinBox#stepperSpinBox::down-button:pressed {{
    background: {t['btn_folder_bg']};
}}
QSpinBox#stepperSpinBox::up-button:disabled, QSpinBox#stepperSpinBox::down-button:disabled {{
    background: transparent;
}}
QSpinBox#stepperSpinBox::up-arrow, QSpinBox#stepperSpinBox::down-arrow {{
    image: none; width: 0; height: 0;
}}
"""


def build_main_style(t: dict) -> str:
    return f"""
QMainWindow, QWidget#root {{
    background: {t['bg_root']};
}}
QLabel {{
    color: {t['text_primary']};
    font-size: 12px;
}}
QPushButton {{
    border-radius: 5px;
    font-size: 12px;
    padding: 5px 14px;
    color: {t['text_primary']};
    border: 1px solid {t['border']};
    background: {t['bg_input']};
}}
QPushButton:hover {{
    background: {t['bg_hover']};
    border-color: {t['border_hover']};
}}
QPushButton:disabled {{
    color: {t['text_muted']};
    border-color: {t['sep']};
    background: {t['bg_root']};
}}
QLabel#pathLabel {{
    color: {t['text_muted']};
    font-size: 11px;
    padding: 0 4px;
}}
QLabel#pathLabelActive {{
    color: {t['text_accent']};
    font-size: 11px;
    padding: 0 4px;
}}
QLabel#infoLabel {{
    color: {t['text_secondary']};
    font-size: 12px;
    letter-spacing: 0.5px;
}}
QLabel#statusLabel {{
    color: {t['text_muted']};
    font-size: 11px;
    padding: 2px 0;
}}
QPushButton#navBtn {{
    background: {t['btn_nav_bg']};
    color: {t['btn_nav_text']};
    border: 1px solid {t['border']};
    min-width: 80px;
}}
QPushButton#navBtn:hover {{
    background: {t['bg_hover']};
    color: {t['text_primary']};
    border-color: {t['border_hover']};
}}
QPushButton#navBtn:disabled {{
    color: {t['text_muted']};
    border-color: {t['sep']};
    background: {t['bg_root']};
}}
QPushButton#folderBtn {{
    background: {t['btn_folder_bg']};
    color: {t['btn_folder_text']};
    border: 1px solid {t['border_accent']};
    font-size: 11px;
    padding: 5px 10px;
}}
QPushButton#folderBtn:hover {{
    background: {t['bg_hover']};
    border-color: {t['border_hover']};
    color: {t['text_accent']};
}}
QPushButton#deleteBtn {{
    background: {t['btn_delete_bg']};
    color: {t['btn_delete_text']};
    border: 1px solid {t['border_red']};
}}
QPushButton#deleteBtn:hover {{
    background: {t['bg_hover']};
    color: {t['text_red']};
    border-color: {t['border_red']};
}}
QPushButton#deleteBtn:disabled {{
    color: {t['text_muted']};
    border-color: {t['sep']};
    background: {t['bg_root']};
}}
QPushButton#editBtn {{
    background: {t['btn_edit_bg']};
    color: {t['btn_edit_text']};
    border: 1px solid {t['border_green']};
    font-weight: bold;
    min-width: 110px;
}}
QPushButton#editBtn:hover {{
    background: {t['bg_hover']};
    color: {t['text_green']};
    border-color: {t['border_green']};
}}
QPushButton#editBtn:checked {{
    background: {t['btn_edit_active_bg']};
    color: {t['btn_edit_active_text']};
    border: 1.5px solid {t['border_green']};
}}
QPushButton#maskBtn {{
    background: {t['btn_mask_bg']};
    color: {t['btn_mask_text']};
    border: 1px solid {t['border']};
    font-size: 11px;
    padding: 5px 10px;
}}
QPushButton#maskBtn:hover {{
    background: {t['bg_hover']};
}}
QPushButton#maskBtn:checked {{
    border-color: {t['border_accent']};
    color: {t['text_accent']};
}}
QPushButton#themeBtn, QPushButton#settingsBtn {{
    background: transparent;
    color: {t['text_secondary']};
    border: 1px solid {t['border']};
    font-size: 11px;
    padding: 5px 10px;
}}
QPushButton#themeBtn:hover, QPushButton#settingsBtn:hover {{
    background: {t['bg_hover']};
    color: {t['text_primary']};
}}
QSpinBox {{
    background: {t['spin_bg']};
    color: {t['spin_text']};
    border: 1px solid {t['spin_border']};
    border-radius: 4px;
    padding: 3px 6px;
    font-size: 12px;
}}
QSpinBox::up-button, QSpinBox::down-button {{
    background: {t['bg_hover']};
    border: none;
    width: 16px;
}}
QFrame#hline {{
    color: {t['sep']};
    max-height: 1px;
}}
QGraphicsView {{
    border: none;
    background: {t['bg_root']};
}}
""" + build_control_style(t)


def build_panel_style(t: dict) -> str:
    return f"""
EditPanel {{
    background: {t['bg_panel']};
    border: 1px solid {t['border']};
    border-radius: 10px;
}}
QWidget#titleBar {{
    background: {t['bg_title_bar']};
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    border-bottom: 1px solid {t['sep']};
}}
QWidget#panelContent {{
    background: {t['bg_panel']};
}}
QLabel {{
    color: {t['text_primary']};
}}
QPushButton#toolBtn {{
    background: {t['tool_btn_bg']};
    color: {t['tool_btn_text']};
    border: 1px solid {t['border']};
    border-radius: 6px;
    font-size: 10px;
    padding: 4px;
}}
QPushButton#toolBtn:hover {{
    background: {t['bg_hover']};
    border-color: {t['border_hover']};
    color: {t['text_primary']};
}}
QPushButton#toolBtn:checked {{
    background: {t['tool_btn_checked_bg']};
    border: 1.5px solid {t['tool_btn_checked_border']};
    color: {t['tool_btn_checked_text']};
    font-weight: bold;
}}
QCheckBox {{
    color: {t['chk_text']};
    font-size: 11px;
    spacing: 5px;
}}
QCheckBox::indicator {{
    width: 14px; height: 14px;
    border: 1px solid {t['chk_indicator_border']};
    border-radius: 3px;
    background: {t['chk_indicator_bg']};
}}
QCheckBox::indicator:checked {{
    background: {t['chk_indicator_checked']};
    border-color: {t['chk_indicator_checked_border']};
}}
QSlider::groove:horizontal {{
    height: 4px;
    background: {t['slider_groove']};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    width: 14px; height: 14px;
    background: {t['slider_handle']};
    border-radius: 7px;
    margin: -5px 0;
}}
QSlider::sub-page:horizontal {{
    background: {t['slider_handle']};
    border-radius: 2px;
}}
""" + build_control_style(t)
