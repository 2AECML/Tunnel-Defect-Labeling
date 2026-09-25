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

        # Section label
        "section_label":  "#5090c0",

        # Separator
        "sep":            "#2e2e2e",

        # ComboBox
        "combo_bg":       "#242424",
        "combo_text":     "#d0d0d0",
        "combo_border":   "#3a3a3a",

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

        "section_label":  "#1a5a9a",
        "sep":            "#d8d8d8",

        "combo_bg":       "#ffffff",
        "combo_text":     "#1a1a1a",
        "combo_border":   "#c0c0c0",

        "chk_indicator_bg":      "#ffffff",
        "chk_indicator_checked": "#d0e8ff",
        "chk_indicator_border":  "#aaaaaa",
        "chk_indicator_checked_border": "#1a6acc",
        "chk_text":       "#333333",

        "theme_btn_text": "🌙  夜间模式",
    }
}


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
QPushButton#themeBtn {{
    background: transparent;
    color: {t['text_secondary']};
    border: 1px solid {t['border']};
    font-size: 11px;
    padding: 5px 10px;
}}
QPushButton#themeBtn:hover {{
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
"""


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
QComboBox {{
    background: {t['combo_bg']};
    color: {t['combo_text']};
    border: 1px solid {t['combo_border']};
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 12px;
}}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background: {t['combo_bg']};
    color: {t['combo_text']};
    selection-background-color: {t['tool_btn_checked_bg']};
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
"""
