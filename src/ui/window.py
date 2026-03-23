"""Main application window for the package manager."""

import gi
import logging
import subprocess
from typing import List

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, GLib

try:
    from src.core import DistroboxManager, PackageManager, Container, Package
except ImportError:
    from core import DistroboxManager, PackageManager, Container, Package

logger = logging.getLogger(__name__)


class PackageManagerApp(Adw.ApplicationWindow):
    """Unified package manager window."""

    def __init__(self, app):
        super().__init__(application=app)
        self.set_title("DistroBox Package Manager")
        self.set_default_size(1000, 700)

        self.distrobox_manager = DistroboxManager()
        self.package_manager = PackageManager()
        self.containers: List[Container] = []

        self._filter = "all"  # "all" or "installed"

        self._build_ui()
        self.connect("show", self._on_show)

    def _build_ui(self):
        header_bar = Adw.HeaderBar()

        self.refresh_button = Gtk.Button(label="Refresh")
        self.refresh_button.connect("clicked", self._on_refresh_clicked)
        header_bar.pack_end(self.refresh_button)

        self.update_button = Gtk.Button(label="Update All")
        self.update_button.connect("clicked", self._on_update_clicked)
        header_bar.pack_end(self.update_button)

        # Filter dropdown (Select between all packages and installed packages)
        self.filter_dropdown = Gtk.DropDown.new_from_strings([
            "All Packages",
            "Installed"
        ])
        self.filter_dropdown.connect("notify::selected", self._on_filter_changed)
        header_bar.pack_end(self.filter_dropdown)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main_box.append(header_bar)

        right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        right_box.set_margin_start(10)
        right_box.set_margin_end(10)
        right_box.set_margin_top(10)
        right_box.set_margin_bottom(10)

        # Search box
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Search packages...")
        #search on enter with "activate" signal or live search with "search-changed" signal
        self.search_entry.connect("search-changed", self._on_search_changed)
        right_box.append(self.search_entry)

        # Package info frame
        package_info_frame = Gtk.Frame()
        package_info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        package_info_box.set_margin_start(5)
        package_info_box.set_margin_end(5)
        package_info_box.set_margin_top(5)
        package_info_box.set_margin_bottom(5)

        self.package_name_label = Gtk.Label()
        self.package_name_label.set_markup("<b>Select a package</b>")
        self.package_name_label.set_xalign(0)
        package_info_box.append(self.package_name_label)

        self.package_desc_label = Gtk.Label()
        self.package_desc_label.set_wrap(True)
        self.package_desc_label.set_xalign(0)
        package_info_box.append(self.package_desc_label)

        package_info_frame.set_child(package_info_box)
        right_box.append(package_info_frame)

        # Shared package/app list
        self.packages_list = Gtk.ListBox()
        self.packages_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.packages_list.connect("row-selected", self._on_row_selected)

        packages_scroll = Gtk.ScrolledWindow()
        packages_scroll.set_child(self.packages_list)
        packages_scroll.set_vexpand(True)
        right_box.append(packages_scroll)

        # Action buttons
        action_box = Gtk.Box(spacing=10)

        self.install_button = Gtk.Button(label="Install")
        self.install_button.set_sensitive(False)
        self.install_button.connect("clicked", self._on_install_clicked)
        action_box.append(self.install_button)

        self.remove_button = Gtk.Button(label="Remove")
        self.remove_button.set_sensitive(False)
        self.remove_button.connect("clicked", self._on_remove_clicked)
        action_box.append(self.remove_button)

        # Export toggle button — only visible in apps mode
        self.export_button = Gtk.Button(label="Add to host")
        self.export_button.set_sensitive(False)
        self.export_button.set_visible(False)
        self.export_button.connect("clicked", self._on_export_clicked)
        action_box.append(self.export_button)

        right_box.append(action_box)

        main_box.append(right_box)
        self.set_content(main_box)

    # ------------------------------------------------------------------ #
    #  Initialisation                                                       #
    # ------------------------------------------------------------------ #

    def _on_show(self, widget):
        logger.info("Application window shown, initializing...")
        self._initialize_containers()

    def _initialize_containers(self):
        self.refresh_button.set_sensitive(False)

        def initialize():
            try:
                logger.info("Ensuring default containers exist...")
                self.distrobox_manager.ensure_default_containers()
                self.containers = self.distrobox_manager.list_containers()
                logger.info(f"Found {len(self.containers)} containers")
                GLib.idle_add(self._refresh_containers_list)
            except Exception as e:
                logger.error(f"Error initializing containers: {e}")
                GLib.idle_add(self._show_error_dialog, str(e))
                GLib.idle_add(lambda: self.refresh_button.set_sensitive(True))

        import threading
        threading.Thread(target=initialize, daemon=True).start()

    def _refresh_containers_list(self):
        if self.containers:
            logger.info(f"Loaded {len(self.containers)} containers")
            GLib.idle_add(self.search_entry.set_text, "")
            GLib.idle_add(self._clear_list)
            GLib.idle_add(self._update_package_info, None)
        self.refresh_button.set_sensitive(True)

    # ------------------------------------------------------------------ #
    #  Header bar actions                                                   #
    # ------------------------------------------------------------------ #

    def _on_refresh_clicked(self, button):
        self.refresh_button.set_sensitive(False)

        def refresh():
            try:
                self.containers = self.distrobox_manager.list_containers()
                GLib.idle_add(self._refresh_containers_list)
            except Exception as e:
                logger.error(f"Error refreshing: {e}")

        import threading
        threading.Thread(target=refresh, daemon=True).start()

    def _on_update_clicked(self, button):
        button.set_sensitive(False)
        self.refresh_button.set_sensitive(False)

        def update():
            errors = []
            try:
                for container in self.containers:
                    logger.info(f"Upgrading {container.name}...")
                    result = subprocess.run(
                        ["distrobox", "upgrade", container.name],
                        capture_output=True,
                        text=True,
                        timeout=1200,
                    )
                    if result.returncode != 0:
                        errors.append(f"{container.name}: {result.stderr.strip()}")
                    else:
                        logger.info(f"Successfully upgraded {container.name}")
            except Exception as e:
                errors.append(str(e))
            finally:
                if errors:
                    GLib.idle_add(
                        self._show_error_dialog,
                        "Some containers failed to update:\n" + "\n".join(errors)
                    )
                else:
                    GLib.idle_add(self._show_info_dialog, "All containers updated successfully")
                GLib.idle_add(lambda: button.set_sensitive(True))
                GLib.idle_add(lambda: self.refresh_button.set_sensitive(True))

        import threading
        threading.Thread(target=update, daemon=True).start()

    # ------------------------------------------------------------------ #
    #  Search mode + filter                                                 #
    # ------------------------------------------------------------------ #
    
    def _on_filter_changed(self, dropdown, _):
        self._filter = "installed" if dropdown.get_selected() == 1 else "all"
        self._clear_list()
        self._update_package_info(None)

        if self._filter == "installed":
            self._load_installed()

    def _load_installed(self):
        def load():
            try:
                results = self.package_manager.get_apps_all_containers(
                    [{"name": c.name, "distro": c.distro} for c in self.containers]
                )
                
                GLib.idle_add(self._display_packages, results)
            except Exception as e:
                logger.error(e)

        import threading
        threading.Thread(target=load, daemon=True).start()

    def _on_search_changed(self, entry):
        query = entry.get_text()

        def search():
            try:
                if self._filter == "installed":
                    results = self.package_manager.get_apps_all_containers(
                        [{"name": c.name, "distro": c.distro} for c in self.containers]
                    )
                    results = [r for r in results if query.lower() in r.name.lower()]
                else:
                    if len(query) < 2:
                        GLib.idle_add(self._clear_list)
                        return
                    results = self.package_manager.search_packages_all_containers(
                        query,
                        [{"name": c.name, "distro": c.distro} for c in self.containers]
                    )

                GLib.idle_add(self._display_packages, results)

            except Exception as e:
                logger.error(e)

        import threading
        threading.Thread(target=search, daemon=True).start()

    def _display_packages(self, packages: List[Package]):
        #used for packages and "apps"
        self._clear_list()
        for pkg in packages:
            row = Adw.ActionRow()
            row.set_title(pkg.name)
            
            #the idea is good, will be implemented as in the packages view, maybe as a color
            #subtitle = pkg.container
            #if getattr(pkg, "is_installed", False):
            #    subtitle += " · Installed"

            row.set_subtitle(pkg.distro)
            row.pkg = pkg
            self.packages_list.append(row)

    # ------------------------------------------------------------------ #
    #  Shared row selection                                                 #
    # ------------------------------------------------------------------ #

    def _on_row_selected(self, listbox, row, dropdown):
        if not row:
            return

        pkg = row.pkg

        self._filter = "installed" if dropdown.get_selected() == 1 else "all"

        self.package_name_label.set_markup(
            f"<b>{pkg.name}</b> ({pkg.distro})"
        )

        if self._filter == "installed":
            self.package_desc_label.set_text(f"Exec: {app.exec_name}")
            # Install is always grayed out in apps mode
            self.install_button.set_sensitive(False)
            # Remove uninstalls from the container
            self.remove_button.set_sensitive(True)
            # Export button label reflects current state
            if app.is_on_host:
                self.export_button.set_label("Remove from host")
                self.export_button.remove_css_class("suggested-action")
                self.export_button.add_css_class("destructive-action")
            else:
                self.export_button.set_label("Add to host")
                self.export_button.add_css_class("suggested-action")
                self.export_button.remove_css_class("destructive-action")
            self.export_button.set_sensitive(True)
        else:
            self.package_desc_label.set_text("Loading details...")
            self.install_button.set_sensitive(False)
            self.remove_button.set_sensitive(False)

            def fetch_info():
                detailed = self.package_manager.get_package_info(
                    package.name, package.container, package.distro
                )
                GLib.idle_add(self._update_package_info, detailed or package)
                GLib.idle_add(lambda: self.install_button.set_sensitive(True))
                GLib.idle_add(lambda: self.remove_button.set_sensitive(True))

            import threading
            threading.Thread(target=fetch_info, daemon=True).start()

    # ------------------------------------------------------------------ #
    #  Install / Remove / Export actions                                    #
    # ------------------------------------------------------------------ #

    def _on_install_clicked(self, button):
        row = self.packages_list.get_selected_row()
        if row is None or not row.pkg:
            return
        package = row.pkg
        button.set_sensitive(False)

        def install():
            try:
                success = self.package_manager.install_package(
                    package.name, package.container, package.distro
                )
                if success:
                    GLib.idle_add(self._show_info_dialog, "Package installed successfully")
                    GLib.idle_add(self._refresh_current_view)
                else:
                    GLib.idle_add(self._show_error_dialog, "Failed to install package")
            except Exception as e:
                logger.error(f"Error installing package: {e}")
                GLib.idle_add(self._show_error_dialog, str(e))
            finally:
                GLib.idle_add(lambda: button.set_sensitive(True))

        import threading
        threading.Thread(target=install, daemon=True).start()

    def _on_remove_clicked(self, button, dropdown):
        row = self.packages_list.get_selected_row()
        if row is None:
            return
        button.set_sensitive(False)

        pkg = row.pkg
        self._filter = "installed" if dropdown.get_selected() == 1 else "all"

        def remove():
            try:
                if self._filter == "installed":
                    success = self.package_manager.remove_app(pkg) #pkg is app type 
                else:
                    success = self.package_manager.remove_package(
                        pkg.name, pkg.container, package.distro                    
                    )
                if success:
                    GLib.idle_add(self._show_info_dialog, "App removed successfully")
                    GLib.idle_add(self._refresh_current_view)  # refresh list
                else:
                    GLib.idle_add(self._show_error_dialog, "Failed to remove app")
            except Exception as e:
                logger.error(f"Error removing app: {e}")
                GLib.idle_add(self._show_error_dialog, str(e))
            finally:
                GLib.idle_add(lambda: button.set_sensitive(True))

            import threading
            threading.Thread(target=remove, daemon=True).start()

    def _on_export_clicked(self, button):
        row = self.packages_list.get_selected_row()
        if not row:
            return
        pkg = row.pkg
        button.set_sensitive(False)

        def do_export():
            if getattr(pkg, "is_on_host", False):
                self.package_manager._unexport_package(pkg.desktop_file, pkg.container)
            else:
                self.package_manager._export_package(pkg.desktop_file, pkg.container)
            # Flip the state and refresh the row subtitle and button
            pkg.is_on_host = not pkg.is_on_host
            GLib.idle_add(self._on_app_row_selected, row)
            GLib.idle_add(lambda: row.set_subtitle(
                f"{pkg.container} · {'On host' if pkg.is_on_host else 'Not on host'}"
            ))

        import threading
        threading.Thread(target=do_export, daemon=True).start()

    # ------------------------------------------------------------------ #
    #  Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _refresh_current_view(self):
        self._clear_list()
        self._update_package_info(None)

        if self._filter == "installed":
            self._load_installed()
        else:
            # re-trigger search with current query
            query = self.search_entry.get_text()
            if len(query) >= 2:
                self._on_search_changed(self.search_entry)

    def _clear_list(self):
        while True:
            row = self.packages_list.get_first_child()
            if row is None:
                break
            self.packages_list.remove(row)
        self.install_button.set_sensitive(False)
        self.remove_button.set_sensitive(False)
        self.export_button.set_sensitive(False)

    def _update_package_info(self, package):
        if package is None:
            self.package_name_label.set_markup("<b>Select a package</b>")
            self.package_desc_label.set_text("")
        else:
            self.package_name_label.set_markup(
                f"<b>{package.name}</b> ({package.distro})"
            )
            self.package_desc_label.set_text(
                f"{package.description}\nVersion: {package.version}\nSize: {package.size}"
            )

    def _show_error_dialog(self, message: str):
        dialog = Adw.MessageDialog(transient_for=self, heading="Error", body=message)
        dialog.add_response("ok", "OK")
        dialog.present()

    def _show_info_dialog(self, message: str):
        dialog = Adw.MessageDialog(transient_for=self, heading="Success", body=message)
        dialog.add_response("ok", "OK")
        dialog.present()
