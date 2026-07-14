"""Core module."""
from .distrobox import DistroboxManager, Container
from .packages import PackageManager, Package, ContainerApp
from .catalog import (
    AppGroup,
    CATEGORIES,
    categorize,
    category_counts,
    group_packages,
    normalize_name,
)

__all__ = [
    "DistroboxManager",
    "Container",
    "PackageManager",
    "Package",
    "ContainerApp",
    "AppGroup",
    "CATEGORIES",
    "categorize",
    "category_counts",
    "group_packages",
    "normalize_name",
]