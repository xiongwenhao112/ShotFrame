# -*- coding: utf-8 -*-
"""ShotFrame 入口：带参数走命令行，双击（无参数）打开图形界面。"""
import sys


def main():
    if len(sys.argv) > 1:
        from shotframe.cli import main as cli_main
        sys.exit(cli_main())
    from shotframe.gui import main as gui_main
    gui_main()


if __name__ == "__main__":
    main()
