"""Package discovery and management module."""

import subprocess
import logging
import os
from typing import List, Dict, Optional, Set
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


@dataclass
class Package:
    """Represents a package."""
    name: str
    version: str
    description: str
    container: str
    distro: str
    installed: bool = False
    size: str = "N/A"
    
    def __repr__(self):
        return f"Package({self.name}, v{self.version}, distro={self.distro})"
    
@dataclass
class ContainerApp:
    """Represents a GUI application found inside a container."""
    name: str
    exec_name: str
    icon: str
    desktop_file: str   # basename without .desktop
    container: str
    is_on_host: bool = False  # True if already exported to the host
 
    def __repr__(self):
        return f"ContainerApp({self.name}, container={self.container}, on_host={self.is_on_host})"
    
class PackageManager:
    """Manages package discovery and operations across containers."""
    
    # Package manager commands for each distro.
    # Debian uses apt-cache/apt-get instead of apt to avoid unstable CLI
    # warnings and non-zero exit codes on successful searches.
    PM_COMMANDS = {
        "debian": {
            "list": ["apt-cache", "search", ""],
            "search": ["apt-cache", "search"],
            "info": ["apt-cache", "show"],
            "install": ["sudo", "apt-get", "install", "-y"],
            "remove": ["sudo", "apt-get", "remove", "-y"],
            "update": ["sudo", "apt-get", "update"],
        },
        "fedora": {
            "list": ["dnf", "list", "available"],
            "search": ["dnf", "search"],
            "info": ["dnf", "info"],
            "install": ["sudo", "dnf", "install", "-y"],
            "remove": ["sudo", "dnf", "remove", "-y"],
            "update": ["sudo", "dnf", "check-update"],
        },
        "arch": {
            "list": ["pacman", "-Sl"],
            "search": ["pacman", "-Ss"],
            "info": ["pacman", "-Si"],
            "install": ["sudo", "pacman", "-S", "--noconfirm"],
            "remove": ["sudo", "pacman", "-R", "--noconfirm"],
            "update": ["sudo", "pacman", "-Sy"],
        },
    }
    
    # Architecture suffixes appended by RPM-based package managers (e.g. dnf)
    _ARCH_SUFFIXES = {
        ".x86_64", ".i686", ".aarch64", ".armv7hl", ".ppc64le", ".s390x", ".noarch",
    }

    @staticmethod
    def _strip_arch(name: str) -> str:
        """Remove architecture suffix from a package name (e.g. 'vim.x86_64' → 'vim')."""
        for suffix in PackageManager._ARCH_SUFFIXES:
            if name.endswith(suffix):
                return name[: -len(suffix)]
        return name

    def __init__(self):
        """Initialize package manager."""
        self._package_cache: Dict[str, List[Package]] = {}
        # Timeout settings (in seconds) for various operations
        self.TIMEOUT_SEARCH = 60      # Package search can be slow
        self.TIMEOUT_INFO = 45        # Getting package info
        self.TIMEOUT_INSTALL = 1200   # Installation can take a while
        self.TIMEOUT_REMOVE = 1200     # Removal operation
    
    def _run_in_container(
        self,
        container_name: str,
        command: List[str],
        timeout: int = 30
    ) -> Optional[str]:
        """Execute a command inside a container via distrobox."""
        try:
            result = subprocess.run(
                ["distrobox", "enter", container_name, "--", *command],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False
            )
            # Return stdout if there's any content, regardless of return code.
            # Many package managers (apt, dnf) exit non-zero even on success
            # when they emit warnings to stderr — discarding stdout in that
            # case would silently swallow valid results.
            if result.stdout.strip():
                return result.stdout
            if result.returncode != 0:
                logger.debug(
                    f"Command failed in {container_name} "
                    f"(rc={result.returncode}): {result.stderr.strip()}"
                )
            return None
        except subprocess.TimeoutExpired:
            logger.debug(f"Command timeout in {container_name} after {timeout}s")
            return None
        except Exception as e:
            logger.error(f"Error running command in {container_name}: {e}")
            return None
    
    def search_packages(
        self,
        query: str,
        container_name: str,
        distro: str
    ) -> List[Package]:
        """Search for packages in a container by name only."""
        if distro not in self.PM_COMMANDS:
            logger.error(f"Unknown distro: {distro}")
            return []
        
        search_cmd = self.PM_COMMANDS[distro]["search"]
        command = search_cmd + [query]
        
        logger.info(f"Searching for '{query}' in {container_name}...")
        output = self._run_in_container(container_name, command, timeout=self.TIMEOUT_SEARCH)
        if not output:
            logger.warning(f"No output from search in {container_name}")
            return []
        
        packages = []
        query_lower = query.lower()
        
        # Parse output based on distro format
        if distro == "debian":
            packages = self._parse_debian_search(output, query_lower, container_name)
        elif distro == "fedora":
            packages = self._parse_fedora_search(output, query_lower, container_name)
        elif distro == "arch":
            packages = self._parse_arch_search(output, query_lower, container_name)
        
        logger.info(f"Found {len(packages)} packages matching '{query}' in {container_name}, distro: {distro}")
        return packages
    
    def _parse_debian_search(self, output: str, query_lower: str, container_name: str) -> List[Package]:
        """Parse Debian apt-cache search output.
        
        apt-cache search produces one line per package in the format:
            name - short description
        """
        packages = []
        distro = "debian"

        for line in output.strip().split('\n'):
            line = line.strip()
            if not line:
                continue

            try:
                # Split on the first " - " separator
                if ' - ' in line:
                    pkg_name, description = line.split(' - ', 1)
                    pkg_name = pkg_name.strip()
                    pkg_desc = description.strip()
                else:
                    pkg_name = line
                    description = ""

                # Filter: only include results where the package name matches
                if query_lower not in pkg_name.lower():
                    continue

                packages.append(Package(
                    name=pkg_name,
                    version="N/A",
                    description=pkg_desc,
                    container=container_name,
                    distro=distro,
                    installed=False,
                ))
            except Exception as e:
                logger.debug(f"Error parsing Debian package line: {e}")
                continue

        return packages[:50]  # Limit results
    
    def _parse_fedora_search(self, output: str, query_lower: str, container_name: str) -> List[Package]:
        """Parse Fedora dnf search output."""
        packages = []
        distro = "fedora"
        lines = output.strip().split('\n')
        
        for line in lines:
            if not line.strip():
                continue
            
            try:
                parts = line.split()
                if len(parts) >= 1:
                    # dnf output can include arch suffixes like "vim.x86_64"
                    pkg_name = self._strip_arch(parts[0])
                    
                    # Only include if the package NAME contains the search query
                    if query_lower not in pkg_name.lower():
                        continue
                    
                    pkg_desc = ' '.join(parts[1:]) if len(parts) > 1 else ""
                    
                    packages.append(Package(
                        name=pkg_name,
                        version="N/A",
                        description=pkg_desc,
                        container=container_name,
                        distro=distro,
                        installed=False,
                    ))
            except Exception as e:
                logger.debug(f"Error parsing Fedora package line: {e}")
                continue
        
        return packages[:50]  # Limit results
    
    def _parse_arch_search(self, output: str, query_lower: str, container_name: str) -> List[Package]:
        """Parse Arch pacman search output."""
        packages = []
        distro = "arch"
        lines = output.strip().split('\n')
        
        for line in lines:
            if not line.strip():
                continue
            
            try:
                parts = line.split()
                if len(parts) >= 1:
                    pkg_name = parts[0]
                    
                    # Only include if the package NAME contains the search query
                    if query_lower not in pkg_name.lower():
                        continue
                    
                    pkg_desc = ' '.join(parts[1:]) if len(parts) > 1 else ""
                    
                    packages.append(Package(
                        name=pkg_name,
                        version="N/A",
                        description=pkg_desc,
                        container=container_name,
                        distro=distro,
                        installed=False,
                    ))
            except Exception as e:
                logger.debug(f"Error parsing Arch package line: {e}")
                continue
        
        return packages[:50]  # Limit results
    
    def get_package_info(
        self,
        package_name: str,
        container_name: str,
        distro: str
    ) -> Optional[Package]:
        """Get detailed information about a package."""
        if distro not in self.PM_COMMANDS:
            return None
        
        info_cmd = self.PM_COMMANDS[distro]["info"]
        command = info_cmd + [package_name]
        
        output = self._run_in_container(container_name, command, timeout=self.TIMEOUT_INFO)
        if not output:
            return None
        
        lines = output.strip().split('\n')
        version = "N/A"
        size = "N/A"
        description = ""
        
        # Parse output (format varies by distro)
        for line in lines:
            line_lower = line.lower()
            if 'version' in line_lower:
                version = line.split(':', 1)[-1].strip() if ':' in line else "N/A"
            elif 'size' in line_lower:
                size = line.split(':', 1)[-1].strip() if ':' in line else "N/A"
            elif 'description' in line_lower:
                description = line.split(':', 1)[-1].strip() if ':' in line else ""
        
        return Package(
            name=package_name,
            version=version,
            description=description,
            container=container_name,
            distro=distro,
            size=size
        )
    
    def install_package(
        self,
        package_name: str,
        container_name: str,
        distro: str
    ) -> bool:
        """Install a package in a container."""
        if distro not in self.PM_COMMANDS:
            return False
        
        install_cmd = self.PM_COMMANDS[distro]["install"]
        command = install_cmd + [package_name]
        
        logger.info(f"Installing {package_name} in {container_name}...")
        output = self._run_in_container(
            container_name,
            command,
            timeout=self.TIMEOUT_INSTALL
        )
        
        success = output is not None
        if success:
            logger.info(f"Successfully installed {package_name}")
            self._export_package(package_name, container_name)
        else:
            logger.error(f"Failed to install {package_name}")
        
        return success
    
    def _export_package(self, package_name: str, container_name: str):
        """Export a package's application from inside the container to the host."""
        
        # Try the package name directly first (most cases work fine with it).
        # Only fall back to the full .desktop file path if that fails.
        command = ["distrobox-export", "--app", package_name]
        logger.debug(f"export command: {' '.join(command)}")
        output = self._run_in_container(container_name, command, timeout=30)

        if output is None:
            desktop_file = self._find_desktop_file(package_name, container_name)
            if desktop_file:
                command = ["distrobox-export", "--app", desktop_file]
                logger.debug(f"export command (fallback): {' '.join(command)}")
                output = self._run_in_container(container_name, command, timeout=30)
        if output is not None:
            logger.info(f"Successfully exported {package_name} from {container_name}")
        else:
            logger.warning(
                f"distrobox-export failed for {package_name} — it may be a "
                "CLI-only package with no .desktop entry"
            )

    def _find_desktop_file(self, package_name: str, container_name: str) -> Optional[str]:
        #used for export/unexport if package name not found (e.g. libreoffice-math)
        """Find the .desktop file path inside the container for a given package.
        
        Tries distro package manager queries first (most reliable), then falls
        back to searching the filesystem by name.
        """
        # Ask the package manager which files the package owns — this is the
        # most reliable way to find the right .desktop file even when the
        # package name doesn't match the desktop file name (e.g. libreoffice-math
        # owns /usr/share/applications/libreoffice-math.desktop)
        for cmd in [
            # Debian/Ubuntu
            ["dpkg", "-L", package_name],
            # Fedora
            ["rpm", "-ql", package_name],
            # Arch
            ["pacman", "-Ql", package_name],
        ]:
            output = self._run_in_container(container_name, cmd, timeout=15)
            if output:
                for line in output.splitlines():
                    line = line.strip()
                    # pacman -Ql prefixes lines with "pkgname path"
                    if ' ' in line:
                        line = line.split(' ', 1)[1]
                    if line.endswith(".desktop") and "/applications/" in line:
                        logger.debug(f"Found desktop file via package query: {line}")
                        return line
        
        # Fallback: search the filesystem directly
        output = self._run_in_container(
            container_name,
            ["find", "/usr/share/applications", "/usr/local/share/applications",
            "-name", f"*{package_name}*", "-type", "f"],
            timeout=15
        )
        if output:
            first = output.splitlines()[0].strip()
            logger.debug(f"Found desktop file via filesystem search: {first}")
            return first
        
        return None
 
    def get_package_for_app(
        self,
        app: ContainerApp
    ) -> Optional[str]:
        """Find the package name that owns a ContainerApp's .desktop file."""
        desktop_path = f"/usr/share/applications/{app.desktop_file}.desktop"
        
        #it finds the package given a .desktop file name
        # Each tuple: (distro, command that prints 'pkgname' given a file path)
        owner_cmds = [
            ("debian", ["dpkg", "-S", desktop_path]),
            ("fedora", ["rpm", "-qf", desktop_path]),
            ("arch",   ["pacman", "-Qo", desktop_path]),
        ]

        for target_distro, cmd in owner_cmds:
            if app.distro != target_distro:
                continue
            output = self._run_in_container(app.container, cmd, timeout=15)
            if not output:
                continue

            if app.distro == "debian":
                # Output: "libreoffice-math: /usr/share/applications/libreoffice-math.desktop"
                pkg = output.split(":")[0].strip()
                # Strip any arch qualifier (e.g. "vim:amd64" → "vim")
                pkg = pkg.split(":")[0].strip()
                return pkg

            elif app.distro == "fedora":
                # Output: "libreoffice-math-7.x86_64"
                return self._strip_arch(output.strip().split()[0])

            elif app.distro == "arch":
                # Output: "/usr/share/applications/libreoffice-math.desktop is owned by libreoffice-fresh 24.x"
                parts = output.strip().split("owned by")
                if len(parts) == 2:
                    return parts[1].strip().split()[0]

        return None

    def remove_package(
        self,
        package_name: str,
        container_name: str,
        distro: str
    ) -> bool:
        """Remove a package from a container."""
        if distro not in self.PM_COMMANDS:
            return False
 
        # Unexport before removing so the host desktop entry is cleaned up first
        self._unexport_package(package_name, container_name)
 
        remove_cmd = self.PM_COMMANDS[distro]["remove"]
        command = remove_cmd + [package_name]
        
        logger.info(f"Removing {package_name} from {container_name}...")
        output = self._run_in_container(
            container_name,
            command,
            timeout=self.TIMEOUT_REMOVE
        )
        
        success = output is not None
        if success:
            logger.info(f"Successfully removed {package_name}")
        else:
            logger.error(f"Failed to remove {package_name}")
        
        return success

    def remove_app(self, app: ContainerApp) -> bool:
        """Remove an app by resolving its owning package first."""
        pkg_name = self.get_package_for_app(app)

        if pkg_name is None:
            # Last resort: desktop_file basename is often the package name
            logger.warning(
                f"Could not resolve package for {app.name}, "
                f"falling back to desktop_file name: {app.desktop_file}"
            )
            pkg_name = app.desktop_file

        return self.remove_package(pkg_name, app.container, app.distro)
    
    def _unexport_package(self, package_name: str, container_name: str):
        """Remove the host-side desktop entry for a package before uninstalling it."""
        command = ["distrobox-export", "--app", package_name, "--delete"]
        logger.debug(f"unexport command: {' '.join(command)}")
        output = self._run_in_container(container_name, command, timeout=30)

        if output is None:
            desktop_file = self._find_desktop_file(package_name, container_name)
            if desktop_file:
                command = ["distrobox-export", "--app", desktop_file, "--delete"]
                logger.debug(f"unexport command (fallback): {' '.join(command)}")
                output = self._run_in_container(container_name, command, timeout=30)
        if output is not None:
            logger.info(f"Successfully unexported {package_name} from {container_name}")
        else:
            logger.warning(
                f"distrobox-export --delete failed for {package_name} — "
                "it may not have been exported"
            )
    
    def search_packages_all_containers(
        self,
        query: str,
        containers: List[Dict[str, str]]
    ) -> List[Package]:
        """Search for packages across all containers."""
        all_packages = []
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(
                    self.search_packages,
                    query,
                    container["name"],
                    container["distro"]
                ): container
                for container in containers
            }
            
            for future in as_completed(futures):
                try:
                    packages = future.result()
                    all_packages.extend(packages)
                except Exception as e:
                    logger.error(f"Error searching packages: {e}")
        
        return all_packages

    def get_apps_in_container(self, container_name: str) -> List["Package"]:
        """Return GUI apps installed inside a container by scanning .desktop files.

        Mirrors the Rust get_apps_in_box logic:
        - Lists .desktop files in /usr/share/applications/ that don't set NoDisplay=true
        - Reads Name=, Exec=, Icon= from each file
        - Checks whether the app has already been exported to the host
        """
        # Host-side exported files are named "<container>-<app>.desktop"
        host_app_dir = os.path.expanduser("~/.local/share/applications")
        try:
            host_desktop_files = set(os.listdir(host_app_dir))
        except FileNotFoundError:
            host_desktop_files = set()

        output = self._run_in_container(
            container_name,
            [
                "bash", "-c",
                "grep --files-without-match 'NoDisplay=true' /usr/share/applications/*.desktop",
            ],
            timeout=30,
        )
        if not output:
            logger.warning(f"No .desktop files found in {container_name}")
            return []

        apps = []
        for line in output.splitlines():
            line = line.strip()
            if not line or "No such file" in line or not line.startswith("/usr/share"):
                continue

            contents = self._run_in_container(container_name, ["cat", line], timeout=10)
            if not contents:
                continue

            name = exec_name = icon = ""
            for df_line in contents.splitlines():
                if not name and df_line.startswith("Name="):
                    name = df_line[len("Name="):]
                elif not exec_name and df_line.startswith("Exec="):
                    exec_name = (
                        df_line[len("Exec="):]
                        .replace("%F", "").replace("%U", "").strip()
                    )
                elif not icon and df_line.startswith("Icon="):
                    icon = df_line[len("Icon="):]

            if not name or not exec_name:
                continue

            desktop_file = line.replace("/usr/share/applications/", "").replace(".desktop", "")
            host_desktop_name = f"{container_name}-{desktop_file}.desktop"

            apps.append(Package(
                name=name,
                exec_name=exec_name,
                icon=icon,
                desktop_file=desktop_file,
                container=container_name,
                installed=True,
            ))

        logger.info(f"Found {len(apps)} apps in {container_name}")
        return apps
    
    def get_apps_all_containers(
        self, containers: List[Dict[str, str]]
    ) -> List["Package"]:
        """Fetch installed GUI apps from all containers in parallel."""
        all_apps = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(self.get_apps_in_container, c["name"]): c
                for c in containers
            }
            for future in as_completed(futures):
                try:
                    all_apps.extend(future.result())
                except Exception as e:
                    logger.error(f"Error fetching apps: {e}")
        return sorted(all_apps, key=lambda a: a.name.lower())
