"""Rollback utilities for reverting file changes.

This module provides functionality to backup files before modifications
and restore them to previous states when needed.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class RollbackManager:
    """Manages file backups and rollback operations."""
    
    def __init__(self, backup_dir: Path | None = None) -> None:
        """Initialize the rollback manager.
        
        Args:
            backup_dir: Directory to store backups. Defaults to .harness/rollback/
        """
        if backup_dir is None:
            backup_dir = Path(".harness/rollback")
        self.backup_dir = backup_dir
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self._index_file = self.backup_dir / "index.json"
        self._index = self._load_index()
    
    def _load_index(self) -> dict[str, Any]:
        """Load the rollback index from disk."""
        if self._index_file.exists():
            try:
                with self._index_file.open("r") as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError):
                return {}
        return {}
    
    def _save_index(self) -> None:
        """Save the rollback index to disk."""
        with self._index_file.open("w") as f:
            json.dump(self._index, f, indent=2, default=str)
    
    def _get_file_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of a file."""
        hasher = hashlib.sha256()
        with file_path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    
    def _backup_path(self, file_path: Path, timestamp: str) -> Path:
        """Generate a backup path for a file."""
        # Use relative path from workspace to keep backups organized
        try:
            rel_path = file_path.relative_to(Path.cwd())
        except ValueError:
            # If file is outside workspace, use absolute path
            rel_path = file_path
        
        # Create a safe filename by replacing path separators
        safe_name = str(rel_path).replace("/", "_").replace("\\", "_")
        return self.backup_dir / f"{safe_name}_{timestamp}.bak"
    
    def backup_file(self, file_path: Path) -> dict[str, Any] | None:
        """Create a backup of a file before modification.
        
        Args:
            file_path: Path to the file to backup.
            
        Returns:
            Backup metadata dict, or None if file doesn't exist.
        """
        if not file_path.exists():
            return None
        
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
        backup_path = self._backup_path(file_path, timestamp)
        
        # Copy the file to backup location
        shutil.copy2(file_path, backup_path)
        
        # Calculate hash for verification
        file_hash = self._get_file_hash(file_path)
        
        # Record in index
        backup_info = {
            "original_path": str(file_path),
            "backup_path": str(backup_path),
            "timestamp": timestamp,
            "hash": file_hash,
            "size": file_path.stat().st_size,
        }
        
        # Store in index by original path (keep history)
        if str(file_path) not in self._index:
            self._index[str(file_path)] = []
        self._index[str(file_path)].append(backup_info)
        
        self._save_index()
        return backup_info
    
    def rollback_file(self, file_path: Path, backup_index: int = -1) -> bool:
        """Restore a file from backup.
        
        Args:
            file_path: Path to the file to restore.
            backup_index: Index of backup to use (-1 for most recent).
            
        Returns:
            True if rollback succeeded, False otherwise.
        """
        backups = self._index.get(str(file_path), [])
        if not backups:
            return False
        
        # Get the requested backup
        try:
            backup_info = backups[backup_index]
        except IndexError:
            return False
        
        backup_path = Path(backup_info["backup_path"])
        if not backup_path.exists():
            return False
        
        # Verify hash if possible
        current_hash = self._get_file_hash(backup_path)
        if current_hash != backup_info["hash"]:
            # Hash mismatch - backup may be corrupted
            return False
        
        # Restore the file
        try:
            shutil.copy2(backup_path, file_path)
            return True
        except (OSError, shutil.Error):
            return False
    
    def list_backups(self, file_path: Path) -> list[dict[str, Any]]:
        """List all available backups for a file.
        
        Args:
            file_path: Path to the file.
            
        Returns:
            List of backup metadata dicts.
        """
        return self._index.get(str(file_path), [])
    
    def cleanup_old_backups(self, max_age_days: int = 7, max_per_file: int = 10) -> int:
        """Clean up old backups to save disk space.
        
        Args:
            max_age_days: Maximum age of backups to keep.
            max_per_file: Maximum number of backups per file.
            
        Returns:
            Number of backups removed.
        """
        removed = 0
        cutoff = datetime.now(UTC).timestamp() - (max_age_days * 86400)
        
        for file_path, backups in list(self._index.items()):
            # Remove backups older than max_age_days
            backups[:] = [
                b for b in backups
                if datetime.fromisoformat(b["timestamp"]).timestamp() > cutoff
            ]
            
            # Keep only the most recent max_per_file backups
            if len(backups) > max_per_file:
                old_backups = backups[:-max_per_file]
                for backup in old_backups:
                    backup_path = Path(backup["backup_path"])
                    if backup_path.exists():
                        backup_path.unlink()
                        removed += 1
                backups[:] = backups[-max_per_file:]
            
            # Remove entry if no backups left
            if not backups:
                del self._index[file_path]
        
        self._save_index()
        return removed
    
    def get_backup_size(self) -> int:
        """Get total size of all backups in bytes."""
        total = 0
        for backup_path in self.backup_dir.glob("*.bak"):
            total += backup_path.stat().st_size
        return total
