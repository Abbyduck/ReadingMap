"""Pure, reusable structure extraction from a rendered page or human-supplied evidence."""
from .parser import PageSnapshot, extract_structure, extract_url_list

__all__ = ["PageSnapshot", "extract_structure", "extract_url_list"]
