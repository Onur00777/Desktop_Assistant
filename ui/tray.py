"""System tray menu."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from core.workspace_manager import WorkspaceManager


class AssistantTray(QSystemTrayIcon):
    launch_workspace = pyqtSignal(str)
    toggle_widget_requested = pyqtSignal()
    toggle_dashboard_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, icon: QIcon, workspaces: WorkspaceManager) -> None:
        super().__init__(icon)
        self.workspaces = workspaces
        self.available = QSystemTrayIcon.isSystemTrayAvailable()
        self.setToolTip("Desktop Assistant")

        self.menu = QMenu()
        self.toggle_widget_action = self.menu.addAction("Hide Icon")
        self.toggle_widget_action.triggered.connect(self.toggle_widget_requested.emit)
        dashboard_action = self.menu.addAction("Dashboard")
        dashboard_action.triggered.connect(self.toggle_dashboard_requested.emit)
        self.workspace_menu = self.menu.addMenu("Workspaces")
        self.workspace_menu.aboutToShow.connect(self.rebuild_workspaces)
        self.menu.addSeparator()
        quit_action = self.menu.addAction("Quit")
        quit_action.triggered.connect(self.quit_requested.emit)
        self.setContextMenu(self.menu)
        self.activated.connect(self._on_activated)

    def set_widget_visible(self, visible: bool) -> None:
        self.toggle_widget_action.setText("Hide Icon" if visible else "Show Icon")

    def rebuild_workspaces(self) -> None:
        self.workspace_menu.clear()
        try:
            profiles = self.workspaces.list_profiles()
        except ValueError:
            action = self.workspace_menu.addAction("Could not read profiles")
            action.setEnabled(False)
            return
        if not profiles:
            action = self.workspace_menu.addAction("No profiles")
            action.setEnabled(False)
            return
        for profile in profiles:
            name = str(profile.get("name") or "")
            action = self.workspace_menu.addAction(name)
            action.triggered.connect(lambda checked=False, profile_name=name: self.launch_workspace.emit(profile_name))

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_dashboard_requested.emit()
