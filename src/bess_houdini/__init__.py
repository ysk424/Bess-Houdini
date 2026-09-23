"""Bess — Houdini 内で使う Codex。import だけでは通信を開始しない。"""
__version__ = "0.1.0"


def show():
    import hou
    pane = hou.ui.curDesktop().createFloatingPaneTab(hou.paneTabType.PythonPanel)
    pane.setActiveInterface(hou.pypanel.interfaces()["bess_houdini"])
    return pane
