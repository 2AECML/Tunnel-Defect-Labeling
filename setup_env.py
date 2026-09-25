#!/usr/bin/env python3
# setup_env.py
"""
一键创建虚拟环境并安装所有依赖。

用法：
    python setup_env.py          # 默认在当前目录创建 .venv
    python setup_env.py --name myenv   # 自定义虚拟环境名
    python setup_env.py --check        # 仅检查现有环境，不安装
"""

import sys
import os
import subprocess
import argparse
import platform
from pathlib import Path


# ──────────────────────────────────────────────────────────────────────────────
# 配置
# ──────────────────────────────────────────────────────────────────────────────
MIN_PYTHON = (3, 10)
VENV_DEFAULT = ".venv"
REQUIREMENTS = "requirements.txt"

# 启动脚本模板（Windows bat）
WIN_LAUNCH_SCRIPT = """\
@echo off
call "{venv_dir}\\Scripts\\activate.bat"
python main.py %*
"""

# 启动脚本模板（Unix sh）
UNIX_LAUNCH_SCRIPT = """\
#!/bin/bash
source "{venv_dir}/bin/activate"
python main.py "$@"
"""


# ──────────────────────────────────────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────────────────────────────────────
def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    print(f"  $ {' '.join(str(c) for c in cmd)}")
    return subprocess.run(cmd, check=True, **kwargs)


def _check_python_version():
    v = sys.version_info[:2]
    if v < MIN_PYTHON:
        print(f"[ERROR] 当前 Python {v[0]}.{v[1]} 不满足最低要求 "
              f"{MIN_PYTHON[0]}.{MIN_PYTHON[1]}，请升级 Python 后重试。")
        sys.exit(1)
    print(f"[OK] Python {sys.version.split()[0]}")


def _venv_python(venv_dir: Path) -> Path:
    if platform.system() == "Windows":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _venv_pip(venv_dir: Path) -> Path:
    if platform.system() == "Windows":
        return venv_dir / "Scripts" / "pip.exe"
    return venv_dir / "bin" / "pip"


def create_venv(venv_dir: Path):
    print(f"\n[1/4] 创建虚拟环境 → {venv_dir}")
    _run([sys.executable, "-m", "venv", str(venv_dir)])
    print("      虚拟环境创建完成 ✓")


def upgrade_pip(venv_dir: Path):
    print("\n[2/4] 升级 pip / setuptools / wheel")
    pip = _venv_pip(venv_dir)
    _run([str(pip), "install", "--upgrade", "pip", "setuptools", "wheel"])
    print("      pip 升级完成 ✓")


def install_requirements(venv_dir: Path, req_file: Path):
    print(f"\n[3/4] 安装依赖包 → {req_file}")
    pip = _venv_pip(venv_dir)
    _run([str(pip), "install", "-r", str(req_file)])
    print("      依赖安装完成 ✓")


def verify_imports(venv_dir: Path):
    print("\n[4/4] 验证核心模块可导入")
    python = _venv_python(venv_dir)
    check_script = (
        "import PyQt5.QtWidgets; "
        "import cv2; "
        "import numpy; "
        "print(f'  PyQt5  {PyQt5.QtCore.PYQT_VERSION_STR}'); "
        "print(f'  OpenCV {cv2.__version__}'); "
        "print(f'  NumPy  {numpy.__version__}');"
    )
    _run([str(python), "-c", check_script])
    print("      所有核心模块正常 ✓")


def write_launch_scripts(venv_dir: Path, project_root: Path):
    """生成一键启动脚本（可选，方便双击运行）"""
    if platform.system() == "Windows":
        script_path = project_root / "run.bat"
        script_path.write_text(
            WIN_LAUNCH_SCRIPT.format(venv_dir=venv_dir.resolve()),
            encoding="utf-8"
        )
        print(f"\n  启动脚本已生成 → {script_path.name}  (双击即可运行)")
    else:
        script_path = project_root / "run.sh"
        script_path.write_text(
            UNIX_LAUNCH_SCRIPT.format(venv_dir=venv_dir.resolve()),
            encoding="utf-8"
        )
        script_path.chmod(0o755)
        print(f"\n  启动脚本已生成 → {script_path.name}  (./run.sh 即可运行)")


def check_existing_env(venv_dir: Path):
    """仅检查现有虚拟环境的包版本"""
    python = _venv_python(venv_dir)
    if not python.exists():
        print(f"[ERROR] 未找到虚拟环境：{venv_dir}")
        sys.exit(1)
    pip = _venv_pip(venv_dir)
    _run([str(pip), "list"])


# ──────────────────────────────────────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="掩膜标注系统 — 虚拟环境安装脚本")
    parser.add_argument("--name", default=VENV_DEFAULT,
                        help=f"虚拟环境目录名（默认：{VENV_DEFAULT}）")
    parser.add_argument("--check", action="store_true",
                        help="仅检查现有虚拟环境，不安装")
    args = parser.parse_args()

    project_root = Path(__file__).parent
    venv_dir = project_root / args.name
    req_file = project_root / REQUIREMENTS

    print("=" * 60)
    print("  图像掩膜标注系统 — 环境安装程序")
    print("=" * 60)

    _check_python_version()

    if args.check:
        check_existing_env(venv_dir)
        return

    if not req_file.exists():
        print(f"[ERROR] 找不到 {req_file}，请确认文件存在。")
        sys.exit(1)

    if venv_dir.exists():
        print(f"\n[INFO] 虚拟环境 {venv_dir} 已存在，跳过创建步骤。")
        print("       如需全新安装，请先手动删除该目录后重新运行。")
    else:
        create_venv(venv_dir)

    upgrade_pip(venv_dir)
    install_requirements(venv_dir, req_file)
    verify_imports(venv_dir)
    write_launch_scripts(venv_dir, project_root)

    print("\n" + "=" * 60)
    print("  ✅ 安装完成！")
    print()
    if platform.system() == "Windows":
        activate = f"  {venv_dir}\\Scripts\\activate.bat"
    else:
        activate = f"  source {venv_dir}/bin/activate"
    print(f"  激活虚拟环境：\n{activate}")
    print(f"  启动程序：\n  python main.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
