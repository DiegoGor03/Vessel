"""Main application entry point."""

import gi
import logging
import sys

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, Gio

try:
    from src.ui.window import PackageManagerApp
except ImportError:
    # Running from src directory
    from ui.window import PackageManagerApp

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


class PackageManagerApplication(Adw.Application):
    """Main application class."""
    
    def __init__(self):
        """Initialize the application."""
        super().__init__(
            application_id='com.example.distrobox-packagemanager',
            flags=0
        )
        self.window = None
    
    def do_activate(self):
        """Activate the application."""
        if self.window is None:
            self.window = PackageManagerApp(self)
        
        self.window.present()
    
    def do_startup(self):
        """Startup the application."""
        Adw.Application.do_startup(self)
        
        # Add quit action
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda a, p: self.quit())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<Ctrl>q"])


def main():
    """Main entry point."""
    try:
        app = PackageManagerApplication()
        return app.run(sys.argv)
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
        return 0
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
