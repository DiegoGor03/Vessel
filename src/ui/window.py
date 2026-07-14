"""Main application window for the package manager (store-style UI)."""

import gi
import logging
import subprocess
import threading
from typing import List, Optional

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, GLib, Gio

try:
    from src.core import (
        DistroboxManager, PackageManager, Container, Package,
        AppGroup, CATEGORIES, group_packages, category_counts,
    )
except ImportError:
    from core import (
        DistroboxManager, PackageManager, Container, Package,
        AppGroup, CATEGORIES, group_packages, category_counts,
    )

logger = logging.getLogger(__name__)

# Friendly labels for the distro picker / badges
_DISTRO_LABELS = {
    "debian": "Debian",
    "fedora": "Fedora",
    "arch": "Arch",
}


def _distro_label(distro: str) -> str:
    return _DISTRO_LABELS.get(distro, distro.capitalize())


class PackageManagerApp(Adw.ApplicationWindow):
    """Unified package manager window, GNOME Software / Bazaar style."""

    def __init__(self, app):
        super().__init__(application=app)
        self.set_title("Vessel")
        self.set_default_size(1100, 720)

        self.distrobox_manager = DistroboxManager()
        self.package_manager = PackageManager()
        self.containers: List[Container] = []

        self._search_timeout_id = None
        self._filter = "all"          # "all" or "installed"
        self._category_filter = "all"  # "all" or a CATEGORIES key
        self._all_groups: List[AppGroup] = []   # currently loaded catalog
        self._selected_group: Optional[AppGroup] = None

        self._build_ui()
        self.connect("show", self._on_show)

    # ------------------------------------------------------------------ #
    #  UI construction                                                     #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        header_bar = Adw.HeaderBar()

        self.refresh_button = Gtk.Button(icon_name="view-refresh-symbolic")
        self.refresh_button.set_tooltip_text("Refresh container list")
        self.refresh_button.connect("clicked", self._on_refresh_clicked)
        header_bar.pack_end(self.refresh_button)

        self.update_button = Gtk.Button(label="Update all")
        self.update_button.connect("clicked", self._on_update_clicked)
        header_bar.pack_end(self.update_button)

        self.filter_dropdown = Gtk.DropDown.new_from_strings([
            "All packages", "Installed",
        ])
        self.filter_dropdown.connect("notify::selected", self._on_filter_changed)
        header_bar.pack_end(self.filter_dropdown)

        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Search applications...")
        self.search_entry.set_hexpand(True)
        self.search_entry.connect("search-changed", self._on_search_changed)
        header_bar.set_title_widget(self.search_entry)

        root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root_box.append(header_bar)

        # Horizontal split: category sidebar | content stack
        split_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, hexpand=True, vexpand=True)
        split_box.append(self._build_sidebar())
        split_box.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        split_box.append(self._build_content_stack())
        root_box.append(split_box)

        self.set_content(root_box)

    def _build_sidebar(self) -> Gtk.Widget:
        scroller = Gtk.ScrolledWindow()
        scroller.set_size_request(210, -1)
        scroller.set_vexpand(True)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self.category_list = Gtk.ListBox()
        self.category_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.category_list.add_css_class("navigation-sidebar")

        scroller.set_child(self.category_list)
        self._populate_category_sidebar()
        self.category_list.connect("row-selected", self._on_category_selected)
        return scroller

    def _build_content_stack(self) -> Gtk.Widget:
        self.content_stack = Gtk.Stack()
        self.content_stack.set_hexpand(True)
        self.content_stack.set_vexpand(True)
        self.content_stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)

        self.content_stack.add_named(self._build_grid_page(), "grid")
        self.content_stack.add_named(self._build_detail_page(), "detail")
        self.content_stack.add_named(self._build_status_page(), "status")
        self.content_stack.set_visible_child_name("status")
        return self.content_stack

    def _build_grid_page(self) -> Gtk.Widget:
        scroller = Gtk.ScrolledWindow()
        scroller.set_vexpand(True)
        scroller.set_hexpand(True)

        self.flow_box = Gtk.FlowBox()
        self.flow_box.set_valign(Gtk.Align.START)
        self.flow_box.set_max_children_per_line(6)
        self.flow_box.set_min_children_per_line(2)
        self.flow_box.set_row_spacing(12)
        self.flow_box.set_column_spacing(12)
        self.flow_box.set_homogeneous(True)
        self.flow_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.flow_box.set_margin_start(16)
        self.flow_box.set_margin_end(16)
        self.flow_box.set_margin_top(16)
        self.flow_box.set_margin_bottom(16)

        scroller.set_child(self.flow_box)
        return scroller

    def _build_detail_page(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_start(32)
        box.set_margin_end(32)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_valign(Gtk.Align.START)

        back_button = Gtk.Button(label="← Back to list")
        back_button.set_halign(Gtk.Align.START)
        back_button.connect("clicked", lambda b: self.content_stack.set_visible_child_name("grid"))
        box.append(back_button)

        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)

        self.detail_icon = Gtk.Image()
        self.detail_icon.set_pixel_size(96)
        header_box.append(self.detail_icon)

        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        title_box.set_valign(Gtk.Align.CENTER)

        self.detail_name_label = Gtk.Label(xalign=0)
        self.detail_name_label.add_css_class("title-1")
        title_box.append(self.detail_name_label)

        self.detail_category_label = Gtk.Label(xalign=0)
        self.detail_category_label.add_css_class("dim-label")
        title_box.append(self.detail_category_label)

        self.detail_badges_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        title_box.append(self.detail_badges_box)

        header_box.append(title_box)
        box.append(header_box)

        self.detail_desc_label = Gtk.Label(xalign=0)
        self.detail_desc_label.set_wrap(True)
        self.detail_desc_label.set_max_width_chars(70)
        box.append(self.detail_desc_label)

        box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # Action area is rebuilt depending on mode (search vs installed)
        self.detail_action_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.append(self.detail_action_box)

        return box

    def _build_status_page(self) -> Gtk.Widget:
        status = Adw.StatusPage()
        status.set_title("Search for an application")
        status.set_description("Type in the search bar above to get started.")
        status.set_icon_name("system-search-symbolic")
        return status

    def _populate_category_sidebar(self, counts: Optional[dict] = None):
        counts = counts or {}
        # clear
        while True:
            row = self.category_list.get_first_child()
            if row is None:
                break
            self.category_list.remove(row)

        all_row = self._make_category_row("all", "All categories", sum(counts.values()) if counts else None)
        self.category_list.append(all_row)

        for key, (label, icon_name) in CATEGORIES.items():
            row = self._make_category_row(key, label, counts.get(key), icon_name)
            self.category_list.append(row)

        self.category_list.select_row(all_row)

    def _make_category_row(self, key: str, label: str, count: Optional[int], icon_name: Optional[str] = None) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row.category_key = key

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.set_margin_start(8)
        box.set_margin_end(8)
        box.set_margin_top(6)
        box.set_margin_bottom(6)

        icon = Gtk.Image.new_from_icon_name(icon_name or "view-grid-symbolic")
        box.append(icon)

        text = f"{label}" if count is None else f"{label} ({count})"
        name_label = Gtk.Label(label=text, xalign=0)
        name_label.set_hexpand(True)
        box.append(name_label)

        row.set_child(box)
        return row

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

        threading.Thread(target=initialize, daemon=True).start()

    def _refresh_containers_list(self):
        if self.containers:
            logger.info(f"Loaded {len(self.containers)} containers")
            self.search_entry.set_text("")
            self._all_groups = []
            self._clear_grid()
            if self._filter == "installed":
                self._load_installed()
            else:
                self.content_stack.set_visible_child_name("status")
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
                    GLib.idle_add(self._show_info_dialog, "All containers have been updated")
                GLib.idle_add(lambda: button.set_sensitive(True))
                GLib.idle_add(lambda: self.refresh_button.set_sensitive(True))

        threading.Thread(target=update, daemon=True).start()

    # ------------------------------------------------------------------ #
    #  Search mode + filters                                               #
    # ------------------------------------------------------------------ #

    def _on_filter_changed(self, dropdown, _):
        self._filter = "installed" if dropdown.get_selected() == 1 else "all"
        self._all_groups = []
        self._clear_grid()

        if self._filter == "installed":
            self._load_installed()
        else:
            query = self.search_entry.get_text()
            if len(query) >= 2:
                self._do_search(query)
            else:
                self.content_stack.set_visible_child_name("status")

    def _on_category_selected(self, listbox, row):
        if row is None:
            return
        self._category_filter = getattr(row, "category_key", "all")
        self._display_groups(self._all_groups)

    def _load_installed(self):
        self.content_stack.set_visible_child_name("grid")

        def load():
            try:
                results = self.package_manager.get_apps_all_containers(
                    [{"name": c.name, "distro": c.distro} for c in self.containers]
                )
                groups = group_packages(results)
                GLib.idle_add(self._set_catalog, groups)
            except Exception as e:
                logger.error(e)

        threading.Thread(target=load, daemon=True).start()

    def _on_search_changed(self, entry):
        if self._search_timeout_id:
            GLib.source_remove(self._search_timeout_id)
            self._search_timeout_id = None

        query = entry.get_text()
        self._search_timeout_id = GLib.timeout_add(600, self._do_search, query)

    def _do_search(self, query: str):
        self._search_timeout_id = None

        if self._filter == "installed":
            # Filter the already-loaded installed catalog locally
            filtered = [g for g in self._all_groups if query.lower() in g.display_name.lower()]
            self._display_groups(filtered if query else self._all_groups)
            return GLib.SOURCE_REMOVE

        if len(query) < 2:
            self.content_stack.set_visible_child_name("status")
            return GLib.SOURCE_REMOVE

        self.content_stack.set_visible_child_name("grid")

        def search():
            try:
                results = self.package_manager.search_packages_all_containers(
                    query,
                    [{"name": c.name, "distro": c.distro} for c in self.containers]
                )
                groups = group_packages(results)
                GLib.idle_add(self._set_catalog, groups)
            except Exception as e:
                logger.error(e)

        threading.Thread(target=search, daemon=True).start()
        return GLib.SOURCE_REMOVE

    # ------------------------------------------------------------------ #
    #  Catalog display (grid of AppGroup cards)                            #
    # ------------------------------------------------------------------ #

    def _set_catalog(self, groups: List[AppGroup]):
        self._all_groups = groups
        self._populate_category_sidebar(category_counts(groups))
        self._display_groups(groups)

    def _display_groups(self, groups: List[AppGroup]):
        self._clear_grid()

        if self._category_filter != "all":
            groups = [g for g in groups if g.category == self._category_filter]

        if not groups:
            self.content_stack.set_visible_child_name("status")
            return

        self.content_stack.set_visible_child_name("grid")
        for group in groups:
            self.flow_box.insert(self._make_app_card(group), -1)

    def _make_app_card(self, group: AppGroup) -> Gtk.Widget:
        button = Gtk.Button()
        button.add_css_class("card")
        button.add_css_class("flat")
        button.set_size_request(150, 130)
        button.connect("clicked", lambda b, g=group: self._show_detail(g))

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        content.set_margin_start(10)
        content.set_margin_end(10)
        content.set_margin_top(14)
        content.set_margin_bottom(10)
        content.set_valign(Gtk.Align.CENTER)

        icon = Gtk.Image.new_from_icon_name(group.icon_name)
        icon.set_pixel_size(48)
        icon.set_halign(Gtk.Align.CENTER)
        content.append(icon)

        name_label = Gtk.Label(label=group.display_name)
        name_label.set_wrap(True)
        name_label.set_justify(Gtk.Justification.CENTER)
        name_label.set_lines(2)
        name_label.set_ellipsize(3)  # Pango.EllipsizeMode.END
        name_label.add_css_class("heading")
        content.append(name_label)

        if group.is_multi_distro:
            badge = Gtk.Label(label=f"{len(group.distros)} distros")
        else:
            badge = Gtk.Label(label=_distro_label(group.distros[0]))
        badge.add_css_class("caption")
        badge.add_css_class("dim-label")
        content.append(badge)

        button.set_child(content)
        return button

    def _clear_grid(self):
        if not hasattr(self, "flow_box"):
            return

        while True:
            child = self.flow_box.get_first_child()
            if child is None:
                break
            self.flow_box.remove(child)

    # ------------------------------------------------------------------ #
    #  Detail page                                                          #
    # ------------------------------------------------------------------ #

    def _show_detail(self, group: AppGroup):
        self._selected_group = group

        self.detail_icon.set_from_icon_name(group.icon_name)
        self.detail_name_label.set_label(group.display_name)
        self.detail_category_label.set_label(group.category_label)
        self.detail_desc_label.set_label(group.description or "No description available.")

        # distro badges
        while True:
            child = self.detail_badges_box.get_first_child()
            if child is None:
                break
            self.detail_badges_box.remove(child)
        for distro in group.distros:
            chip = Gtk.Label(label=_distro_label(distro))
            chip.add_css_class("pill")
            chip.add_css_class("caption")
            self.detail_badges_box.append(chip)

        # action area rebuilt for the current mode
        while True:
            child = self.detail_action_box.get_first_child()
            if child is None:
                break
            self.detail_action_box.remove(child)

        if self._filter == "installed":
            self._build_installed_actions(group)
        else:
            self._build_search_actions(group)

        self.content_stack.set_visible_child_name("detail")

    def _build_search_actions(self, group: AppGroup):
        """Search mode: a single Install action; asks which distro if needed."""
        install_button = Gtk.Button(label="Install")
        install_button.add_css_class("suggested-action")
        install_button.set_halign(Gtk.Align.START)

        if group.is_multi_distro:
            install_button.connect("clicked", lambda b: self._open_distro_picker(b, group))
        else:
            candidate = group.candidates[0]
            install_button.connect(
                "clicked",
                lambda b, pkg=candidate: self._start_install(pkg, install_button)
            )

        self.detail_action_box.append(install_button)

    def _open_distro_picker(self, anchor_widget: Gtk.Widget, group: AppGroup):
        popover = Gtk.Popover()
        popover.set_parent(anchor_widget)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_start(8)
        box.set_margin_end(8)
        box.set_margin_top(8)
        box.set_margin_bottom(8)

        title = Gtk.Label(label="Install from:")
        title.add_css_class("heading")
        title.set_xalign(0)
        box.append(title)

        for distro in group.distros:
            candidate = group.candidate_for(distro)
            if candidate is None:
                continue

            row_button = Gtk.Button(label=_distro_label(distro))
            row_button.set_halign(Gtk.Align.FILL)

            def on_pick(b, pkg=candidate, pop=popover):
                pop.popdown()
                self._start_install(pkg, None)

            row_button.connect("clicked", on_pick)
            box.append(row_button)

        popover.set_child(box)
        popover.popup()

    def _start_install(self, package: Package, button: Optional[Gtk.Button]):
        if button:
            button.set_sensitive(False)

        def install():
            try:
                success = self.package_manager.install_package(
                    package.name, package.container, package.distro
                )
                if success:
                    GLib.idle_add(
                        self._show_info_dialog,
                        f"{package.name} installed on {_distro_label(package.distro)}"
                    )
                else:
                    GLib.idle_add(self._show_error_dialog, f"Installation of {package.name} failed")
            except Exception as e:
                logger.error(f"Error installing package: {e}")
                GLib.idle_add(self._show_error_dialog, str(e))
            finally:
                if button:
                    GLib.idle_add(lambda: button.set_sensitive(True))

        threading.Thread(target=install, daemon=True).start()

    def _build_installed_actions(self, group: AppGroup):
        """Installed mode: list each container instance with its own
        Remove / host-export controls, since these differ per instance."""
        for app in group.candidates:
            row = Adw.ActionRow()
            row.set_title(_distro_label(app.distro))
            row.set_subtitle("On host" if app.is_on_host else "Not exported to host")

            export_button = Gtk.Button(
                label="Remove from host" if app.is_on_host else "Add to host"
            )
            export_button.add_css_class(
                "destructive-action" if app.is_on_host else "suggested-action"
            )
            export_button.connect("clicked", lambda b, a=app, r=row: self._toggle_export(a, r, b))
            row.add_suffix(export_button)

            remove_button = Gtk.Button(label="Uninstall")
            remove_button.add_css_class("destructive-action")
            remove_button.connect("clicked", lambda b, a=app: self._start_remove(a, b))
            row.add_suffix(remove_button)

            self.detail_action_box.append(row)

    def _toggle_export(self, app, row: Adw.ActionRow, button: Gtk.Button):
        button.set_sensitive(False)

        def do_export():
            if app.is_on_host:
                self.package_manager._unexport_package(app.desktop_file, app.container)
            else:
                self.package_manager._export_package(app.desktop_file, app.container)
            app.is_on_host = not app.is_on_host

            def refresh_row():
                row.set_subtitle("On host" if app.is_on_host else "Not exported to host")
                button.set_label("Remove from host" if app.is_on_host else "Add to host")
                button.remove_css_class("destructive-action")
                button.remove_css_class("suggested-action")
                button.add_css_class("destructive-action" if app.is_on_host else "suggested-action")
                button.set_sensitive(True)

            GLib.idle_add(refresh_row)

        threading.Thread(target=do_export, daemon=True).start()

    def _start_remove(self, app, button: Gtk.Button):
        button.set_sensitive(False)

        def remove():
            try:
                success = self.package_manager.remove_app(app)
                if success:
                    GLib.idle_add(self._show_info_dialog, "App removed successfully")
                    GLib.idle_add(self._refresh_current_view)
                    GLib.idle_add(lambda: self.content_stack.set_visible_child_name("grid"))
                else:
                    GLib.idle_add(self._show_error_dialog, "Removal failed")
            except Exception as e:
                logger.error(f"Error removing app: {e}")
                GLib.idle_add(self._show_error_dialog, str(e))
            finally:
                GLib.idle_add(lambda: button.set_sensitive(True))

        threading.Thread(target=remove, daemon=True).start()

    # ------------------------------------------------------------------ #
    #  Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _refresh_current_view(self):
        self._all_groups = []
        self._clear_grid()

        if self._filter == "installed":
            self._load_installed()
        else:
            query = self.search_entry.get_text()
            if len(query) >= 2:
                self._do_search(query)

    def _show_error_dialog(self, message: str):
        dialog = Adw.MessageDialog(transient_for=self, heading="Errore", body=message)
        dialog.add_response("ok", "OK")
        dialog.present()

    def _show_info_dialog(self, message: str):
        dialog = Adw.MessageDialog(transient_for=self, heading="Fatto", body=message)
        dialog.add_response("ok", "OK")
        dialog.present()