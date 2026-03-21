"""Distrobox container management module."""

import subprocess
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Container:
    """Represents a distrobox container."""
    name: str
    distro: str
    is_running: bool = False
    
    def __repr__(self):
        status = "running" if self.is_running else "stopped"
        return f"Container(name={self.name}, distro={self.distro}, status={status})"


class DistroboxManager:
    """Manages distrobox containers and operations."""
    
    # Prefix for containers managed by this application
    CONTAINER_PREFIX = "distrobox-"
    
    DISTROS = {
        "debian": "debian:latest",
        "fedora": "fedora:latest",
        "arch": "archlinux:latest"
    }
    
    def __init__(self):
        """Initialize the distrobox manager."""
        self._check_distrobox_installed()
    
    def _check_distrobox_installed(self) -> bool:
        """Check if distrobox is installed."""
        try:
            subprocess.run(
                ["distrobox", "--version"],
                capture_output=True,
                check=True
            )
            logger.info("distrobox is installed")
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.error("distrobox is not installed or not in PATH")
            raise RuntimeError(
                "distrobox is not installed. Please install it first.\n"
                "See: https://distrobox.it/"
            )
    
    def list_containers(self) -> List[Container]:
        """List all distrobox containers managed by this application."""
        try:
            result = subprocess.run(
                ["distrobox", "list"],
                capture_output=True,
                text=True,
                check=True
            )
            
            containers = []
            # Parse distrobox list output
            # Format: ID | NAME | STATUS | IMAGE
            for line in result.stdout.strip().split('\n')[1:]:  # Skip header
                if not line.strip():
                    continue
                
                parts = line.split('|')
                if len(parts) >= 4:
                    # Columns: ID | NAME | STATUS | IMAGE
                    container_id = parts[0].strip()
                    name = parts[1].strip()
                    status = parts[2].strip()
                    
                    # Only include containers managed by this application
                    if not name.startswith(self.CONTAINER_PREFIX):
                        continue
                    
                    is_running = 'Up' in status or 'running' in status.lower()
                    
                    # Determine distro from name
                    distro = self._get_distro_from_name(name)
                    containers.append(Container(
                        name=name,
                        distro=distro,
                        is_running=is_running
                    ))
            
            return containers
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to list containers: {e.stderr}")
            return []
    
    def _get_distro_from_name(self, name: str) -> str:
        """Infer distro from container name."""
        name_lower = name.lower()
        for distro in self.DISTROS.keys():
            if distro in name_lower:
                return distro
        return "unknown"
    
    def create_container(self, name: str, distro: str) -> bool:
        """Create a new distrobox container."""
        if distro not in self.DISTROS:
            logger.error(f"Unknown distro: {distro}")
            return False
        
        image = self.DISTROS[distro]
        
        try:
            logger.info(f"Creating container: {name} from {image}")
            subprocess.run(
                [
                    "distrobox", "create",
                    "-n", name,
                    "-i", image,
                    "--yes"
                ],
                check=True,
                capture_output=True
            )
            logger.info(f"Container {name} created successfully")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create container {name}: {e.stderr}")
            return False
    
    def start_container(self, name: str) -> bool:
        """Start a container."""
        try:
            subprocess.run(
                ["distrobox", "start", name],
                check=True,
                capture_output=True
            )
            logger.info(f"Container {name} started")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to start container {name}: {e.stderr}")
            return False
    
    def stop_container(self, name: str) -> bool:
        """Stop a container."""
        try:
            subprocess.run(
                ["distrobox", "stop", name],
                check=True,
                capture_output=True
            )
            logger.info(f"Container {name} stopped")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to stop container {name}: {e.stderr}")
            return False
    
    def remove_container(self, name: str) -> bool:
        """Remove a container."""
        try:
            subprocess.run(
                ["distrobox", "remove", "-n", name, "--yes"],
                check=True,
                capture_output=True
            )
            logger.info(f"Container {name} removed")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to remove container {name}: {e.stderr}")
            return False
    
    def ensure_default_containers(self) -> Dict[str, bool]:
        """Ensure default containers exist (debian, fedora, arch)."""
        results = {}
        containers = self.list_containers()
        existing_names = {c.name for c in containers}
        
        for distro in self.DISTROS.keys():
            container_name = f"distrobox-{distro}"
            
            if container_name not in existing_names:
                logger.info(f"Creating default {distro} container...")
                results[distro] = self.create_container(
                    container_name, distro
                )
            else:
                logger.info(f"Container {container_name} already exists")
                results[distro] = True
        
        return results
