"""
OUI Lookup - MAC Address Vendor Identification
Uses IEEE OUI database stored persistently for offline operation
"""

import os
import re
import urllib.request
from typing import Dict, Optional
from pathlib import Path


class OUILookup:
    """
    MAC address vendor lookup using IEEE OUI database.
    
    The database is stored persistently in data/oui.txt so it works offline.
    """
    
    # URL for IEEE OUI database
    OUI_URL = "https://standards-oui.ieee.org/oui/oui.txt"
    
    def __init__(self, data_dir: str = None):
        """
        Initialize OUI lookup.
        
        Args:
            data_dir: Directory containing oui.txt (defaults to project data/ folder)
        """
        if data_dir is None:
            # Default to project_root/data/
            project_root = Path(__file__).parent.parent
            data_dir = project_root / "data"
        
        self.data_dir = Path(data_dir)
        self.oui_file = self.data_dir / "oui.txt"
        self.oui_db: Dict[str, str] = {}
        
        self._load_database()
    
    def _load_database(self) -> None:
        """Load OUI database from persistent file."""
        if not self.oui_file.exists():
            print(f"[OUILookup] Database not found at {self.oui_file}")
            print("[OUILookup] Run update_database() to download, or lookups will return 'Unknown'")
            return
        
        try:
            with open(self.oui_file, 'r', encoding='utf-8', errors='ignore') as f:
                # Parse oui.txt format:
                # XX-XX-XX   (hex)    Vendor Name
                # Example: 00-00-00   (hex)		XEROX CORPORATION
                pattern = re.compile(r'^([0-9A-F]{2}-[0-9A-F]{2}-[0-9A-F]{2})\s+\(hex\)\s+(.+)$')
                
                for line in f:
                    match = pattern.match(line.strip())
                    if match:
                        prefix = match.group(1)
                        vendor = match.group(2).strip()
                        self.oui_db[prefix] = vendor
            
            print(f"[OUILookup] Loaded {len(self.oui_db)} vendor entries")
        except Exception as e:
            print(f"[OUILookup] Error loading database: {e}")
    
    def lookup(self, mac: str) -> str:
        """
        Lookup vendor by MAC address.
        
        Args:
            mac: MAC address in any common format (AA:BB:CC:DD:EE:FF, AA-BB-CC-DD-EE-FF, etc.)
        
        Returns:
            Vendor name or "Unknown" if not found
        """
        if not mac:
            return "Unknown"
        
        # Normalize MAC address to XX-XX-XX format (first 3 octets)
        mac_clean = mac.upper().replace(":", "-").replace(".", "-")
        
        # Handle different formats
        if len(mac_clean) >= 8:
            # Standard format: XX-XX-XX-XX-XX-XX
            prefix = mac_clean[:8]
        elif len(mac_clean) >= 6 and "-" not in mac_clean:
            # Compact format: XXXXXXXXXXXX
            prefix = f"{mac_clean[0:2]}-{mac_clean[2:4]}-{mac_clean[4:6]}"
        else:
            return "Unknown"
        
        return self.oui_db.get(prefix, "Unknown")
    
    def update_database(self) -> bool:
        """
        Download latest OUI database from IEEE.
        
        Returns:
            True if successful, False otherwise
        """
        print(f"[OUILookup] Downloading OUI database from {self.OUI_URL}...")
        
        try:
            # Ensure data directory exists
            self.data_dir.mkdir(parents=True, exist_ok=True)
            
            # Download with timeout
            request = urllib.request.Request(
                self.OUI_URL,
                headers={'User-Agent': 'Protosuit-Engine/1.0'}
            )
            
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read()
            
            # Write to file
            with open(self.oui_file, 'wb') as f:
                f.write(data)
            
            print(f"[OUILookup] Downloaded {len(data)} bytes to {self.oui_file}")
            
            # Reload database
            self.oui_db.clear()
            self._load_database()
            
            return True
            
        except urllib.error.URLError as e:
            print(f"[OUILookup] Network error downloading database: {e}")
            return False
        except Exception as e:
            print(f"[OUILookup] Error updating database: {e}")
            return False
    
    def get_database_info(self) -> Dict:
        """
        Get information about the OUI database.
        
        Returns:
            Dict with database status information
        """
        info = {
            "exists": self.oui_file.exists(),
            "path": str(self.oui_file),
            "entries": len(self.oui_db),
            "size_bytes": 0,
            "modified": None
        }
        
        if self.oui_file.exists():
            stat = self.oui_file.stat()
            info["size_bytes"] = stat.st_size
            info["modified"] = stat.st_mtime
        
        return info


# Singleton instance for shared use
_oui_lookup: Optional[OUILookup] = None


def get_oui_lookup() -> OUILookup:
    """Get shared OUI lookup instance."""
    global _oui_lookup
    if _oui_lookup is None:
        _oui_lookup = OUILookup()
    return _oui_lookup
