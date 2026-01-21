"""
Module: Safety Mechanisms

Provides safe file operations, temporary file management, and transaction support
for DOCX document manipulation. All file operations should use these safety
mechanisms to prevent data loss and accidental overwrites.

Public Interface:
    - TempFileManager: Context manager for temporary file operations
    - SafeFileOperations: Safe file read/write with overwrite protection
    - DocumentTransaction: Transactional document operations with rollback

Example:
    >>> from docx_skill.safety import TempFileManager, SafeFileOperations
    >>> 
    >>> # Safe temp file operations
    >>> with TempFileManager() as temp_mgr:
    ...     temp_path = temp_mgr.create_temp_file("test.docx")
    ...     # Work with temp file...
    ...     # Automatically cleaned up on exit
    >>> 
    >>> # Safe file operations with overwrite protection
    >>> safe_ops = SafeFileOperations()
    >>> safe_ops.write_file(data, "output.docx", allow_overwrite=False)
"""

import os
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Callable, Any
import uuid


@dataclass
class TempFileInfo:
    """Information about a temporary file.
    
    Attributes:
        path: Absolute path to the temporary file
        original_name: Original filename (e.g., "document.docx")
        created_at: Timestamp when file was created
    """
    path: Path
    original_name: str
    created_at: float


class TempFileManager:
    """Context manager for temporary file operations with automatic cleanup.
    
    Manages temporary files and directories, ensuring proper cleanup even if
    errors occur. All temp files are created in a single temp directory that
    is removed when the context exits.
    
    Example:
        >>> with TempFileManager() as temp_mgr:
        ...     # Create temp file
        ...     temp_path = temp_mgr.create_temp_file("document.docx")
        ...     
        ...     # Copy existing file to temp
        ...     temp_copy = temp_mgr.copy_to_temp("original.docx")
        ...     
        ...     # Work with temp files...
        ...     # All temp files cleaned up automatically
        
        >>> # Preserve temp file on success
        >>> with TempFileManager(cleanup_on_success=False) as temp_mgr:
        ...     temp_path = temp_mgr.create_temp_file("keep.docx")
        ...     # File will NOT be cleaned up
    """
    
    def __init__(self, cleanup_on_success: bool = True, cleanup_on_error: bool = True):
        """Initialize TempFileManager.
        
        Args:
            cleanup_on_success: Remove temp files if context exits normally
            cleanup_on_error: Remove temp files if exception occurs
        """
        self.cleanup_on_success = cleanup_on_success
        self.cleanup_on_error = cleanup_on_error
        self.temp_dir: Optional[Path] = None
        self.temp_files: list[TempFileInfo] = []
    
    def __enter__(self) -> 'TempFileManager':
        """Enter context and create temp directory."""
        self.temp_dir = Path(tempfile.mkdtemp(prefix="docx_skill_"))
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context and cleanup temp files if configured."""
        should_cleanup = (
            (exc_type is None and self.cleanup_on_success) or
            (exc_type is not None and self.cleanup_on_error)
        )
        
        if should_cleanup and self.temp_dir and self.temp_dir.exists():
            try:
                shutil.rmtree(self.temp_dir)
            except Exception as e:
                # Don't let cleanup errors mask original exception
                if exc_type is None:
                    raise RuntimeError(f"Failed to cleanup temp directory: {e}")
        
        return False  # Don't suppress exceptions
    
    def create_temp_file(self, filename: str) -> Path:
        """Create a new temporary file.
        
        Args:
            filename: Name for the temp file (e.g., "document.docx")
        
        Returns:
            Path to the created temp file
            
        Example:
            >>> with TempFileManager() as temp_mgr:
            ...     path = temp_mgr.create_temp_file("test.docx")
            ...     path.write_bytes(b"content")
        """
        if not self.temp_dir:
            raise RuntimeError("TempFileManager not initialized (use with context manager)")
        
        temp_path = self.temp_dir / f"{uuid.uuid4().hex}_{filename}"
        temp_path.touch()
        
        self.temp_files.append(TempFileInfo(
            path=temp_path,
            original_name=filename,
            created_at=temp_path.stat().st_ctime
        ))
        
        return temp_path
    
    def copy_to_temp(self, source_path: str | Path) -> Path:
        """Copy an existing file to temp directory.
        
        Args:
            source_path: Path to file to copy
            
        Returns:
            Path to temp copy
            
        Raises:
            FileNotFoundError: If source file doesn't exist
            
        Example:
            >>> with TempFileManager() as temp_mgr:
            ...     temp_copy = temp_mgr.copy_to_temp("original.docx")
            ...     # Modify temp_copy without affecting original
        """
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(f"Source file not found: {source}")
        
        temp_path = self.create_temp_file(source.name)
        shutil.copy2(source, temp_path)
        
        return temp_path
    
    def get_temp_dir(self) -> Path:
        """Get the temporary directory path.
        
        Returns:
            Path to temp directory
            
        Raises:
            RuntimeError: If manager not initialized
        """
        if not self.temp_dir:
            raise RuntimeError("TempFileManager not initialized (use with context manager)")
        return self.temp_dir
    
    def list_temp_files(self) -> list[TempFileInfo]:
        """List all temporary files created by this manager.
        
        Returns:
            List of TempFileInfo objects
        """
        return self.temp_files.copy()


class SafeFileOperations:
    """Safe file operations with overwrite protection and confirmations.
    
    Provides methods for reading and writing files with safety checks to
    prevent accidental data loss. Can prompt for user confirmation before
    overwriting existing files.
    
    Example:
        >>> ops = SafeFileOperations()
        >>> 
        >>> # Write with overwrite protection
        >>> ops.write_file(data, "output.docx", allow_overwrite=False)
        >>> # Raises error if file exists
        >>> 
        >>> # Write with confirmation callback
        >>> def confirm(path):
        ...     return input(f"Overwrite {path}? (y/n): ").lower() == 'y'
        >>> ops.write_file(data, "output.docx", confirm_callback=confirm)
    """
    
    def __init__(self, default_allow_overwrite: bool = False):
        """Initialize SafeFileOperations.
        
        Args:
            default_allow_overwrite: Default behavior for overwrite protection
        """
        self.default_allow_overwrite = default_allow_overwrite
    
    def write_file(
        self,
        data: bytes,
        target_path: str | Path,
        allow_overwrite: Optional[bool] = None,
        confirm_callback: Optional[Callable[[Path], bool]] = None,
        backup: bool = True
    ) -> Path:
        """Write data to file with overwrite protection.
        
        Args:
            data: Binary data to write
            target_path: Destination file path
            allow_overwrite: Allow overwriting existing file (None = use default)
            confirm_callback: Function to call for overwrite confirmation
                             Should return True to proceed, False to cancel
            backup: Create backup (.bak) if overwriting existing file
            
        Returns:
            Path to written file
            
        Raises:
            FileExistsError: If file exists and overwrite not allowed
            ValueError: If user confirms 'no' via callback
            
        Example:
            >>> ops = SafeFileOperations()
            >>> 
            >>> # Simple write with protection
            >>> ops.write_file(data, "new.docx", allow_overwrite=False)
            >>> 
            >>> # Write with confirmation
            >>> def confirm(path):
            ...     return input(f"Overwrite {path}? ").lower() == 'y'
            >>> ops.write_file(data, "exists.docx", confirm_callback=confirm)
        """
        target = Path(target_path)
        allow = allow_overwrite if allow_overwrite is not None else self.default_allow_overwrite
        
        # Check if file exists
        if target.exists():
            # If callback provided, use it for confirmation
            if confirm_callback:
                if not confirm_callback(target):
                    raise ValueError(f"Overwrite cancelled by user: {target}")
            # Otherwise check allow_overwrite flag
            elif not allow:
                raise FileExistsError(
                    f"File exists and overwrite not allowed: {target}\n"
                    f"Set allow_overwrite=True or provide confirm_callback"
                )
            
            # Create backup if requested
            if backup:
                backup_path = target.with_suffix(target.suffix + '.bak')
                shutil.copy2(target, backup_path)
        
        # Ensure parent directory exists
        target.parent.mkdir(parents=True, exist_ok=True)
        
        # Write file
        target.write_bytes(data)
        
        return target
    
    def read_file(self, source_path: str | Path) -> bytes:
        """Read file with error handling.
        
        Args:
            source_path: Path to file to read
            
        Returns:
            File contents as bytes
            
        Raises:
            FileNotFoundError: If file doesn't exist
            PermissionError: If file not readable
            
        Example:
            >>> ops = SafeFileOperations()
            >>> data = ops.read_file("document.docx")
        """
        source = Path(source_path)
        
        if not source.exists():
            raise FileNotFoundError(f"File not found: {source}")
        
        if not source.is_file():
            raise ValueError(f"Not a file: {source}")
        
        return source.read_bytes()
    
    def copy_file(
        self,
        source_path: str | Path,
        target_path: str | Path,
        allow_overwrite: Optional[bool] = None,
        confirm_callback: Optional[Callable[[Path], bool]] = None
    ) -> Path:
        """Copy file with overwrite protection.
        
        Args:
            source_path: Source file path
            target_path: Destination file path
            allow_overwrite: Allow overwriting existing file
            confirm_callback: Function for overwrite confirmation
            
        Returns:
            Path to copied file
            
        Example:
            >>> ops = SafeFileOperations()
            >>> ops.copy_file("original.docx", "copy.docx", allow_overwrite=False)
        """
        data = self.read_file(source_path)
        return self.write_file(data, target_path, allow_overwrite, confirm_callback)


class DocumentTransaction:
    """Transactional document operations with rollback support.
    
    Provides transaction semantics for document operations. Changes are made
    to a temporary copy and only committed to the original if all operations
    succeed. Supports rollback on error.
    
    Example:
        >>> from docx import Document
        >>> 
        >>> with DocumentTransaction("original.docx") as txn:
        ...     doc = Document(txn.get_working_path())
        ...     doc.add_paragraph("New content")
        ...     doc.save(txn.get_working_path())
        ...     txn.commit()  # Only writes to original if commit called
        >>> 
        >>> # Automatic rollback on error
        >>> try:
        ...     with DocumentTransaction("doc.docx") as txn:
        ...         doc = Document(txn.get_working_path())
        ...         # ... operations that might fail ...
        ...         raise ValueError("Something went wrong")
        ...         txn.commit()  # Never reached
        ... except ValueError:
        ...     pass  # Original file unchanged due to rollback
    """
    
    def __init__(
        self,
        document_path: str | Path,
        backup: bool = True,
        auto_commit: bool = False
    ):
        """Initialize DocumentTransaction.
        
        Args:
            document_path: Path to document to operate on
            backup: Create backup before committing changes
            auto_commit: Automatically commit on successful exit (default: False)
        """
        self.document_path = Path(document_path)
        self.backup = backup
        self.auto_commit = auto_commit
        self.temp_mgr: Optional[TempFileManager] = None
        self.working_path: Optional[Path] = None
        self.committed = False
        self.backup_path: Optional[Path] = None
    
    def __enter__(self) -> 'DocumentTransaction':
        """Enter transaction context."""
        # Create temp file manager
        self.temp_mgr = TempFileManager(cleanup_on_success=True, cleanup_on_error=True)
        self.temp_mgr.__enter__()
        
        # Copy document to temp location
        if self.document_path.exists():
            self.working_path = self.temp_mgr.copy_to_temp(self.document_path)
        else:
            # Create new temp file if original doesn't exist
            self.working_path = self.temp_mgr.create_temp_file(self.document_path.name)
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit transaction context and cleanup."""
        try:
            # Auto-commit if configured and no errors
            if exc_type is None and self.auto_commit and not self.committed:
                self.commit()
            
            # Cleanup temp files
            if self.temp_mgr:
                self.temp_mgr.__exit__(exc_type, exc_val, exc_tb)
        except Exception as cleanup_error:
            # Don't mask original exception
            if exc_type is None:
                raise
        
        return False  # Don't suppress exceptions
    
    def get_working_path(self) -> Path:
        """Get path to working copy of document.
        
        Returns:
            Path to temp working copy
            
        Example:
            >>> with DocumentTransaction("doc.docx") as txn:
            ...     path = txn.get_working_path()
            ...     # Modify file at path...
            ...     txn.commit()
        """
        if not self.working_path:
            raise RuntimeError("Transaction not initialized (use with context manager)")
        return self.working_path
    
    def commit(self) -> None:
        """Commit changes to original document.
        
        Copies working copy back to original location. If backup enabled,
        creates .bak file first.
        
        Raises:
            RuntimeError: If transaction not initialized or already committed
            
        Example:
            >>> with DocumentTransaction("doc.docx") as txn:
            ...     # Make changes...
            ...     txn.commit()  # Writes to original
        """
        if not self.working_path:
            raise RuntimeError("Transaction not initialized")
        
        if self.committed:
            raise RuntimeError("Transaction already committed")
        
        # Create backup if requested and original exists
        if self.backup and self.document_path.exists():
            self.backup_path = self.document_path.with_suffix(self.document_path.suffix + '.bak')
            shutil.copy2(self.document_path, self.backup_path)
        
        # Ensure parent directory exists
        self.document_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Copy working file to original location
        shutil.copy2(self.working_path, self.document_path)
        
        self.committed = True
    
    def rollback(self) -> None:
        """Explicitly rollback transaction.
        
        Discards all changes. Original document unchanged.
        
        Note:
            Rollback happens automatically if commit() not called before
            context exit. This method is for explicit early rollback.
            
        Example:
            >>> with DocumentTransaction("doc.docx") as txn:
            ...     # Make changes...
            ...     if error_condition:
            ...         txn.rollback()  # Explicit rollback
            ...         return
            ...     txn.commit()
        """
        # Rollback is implicit - just don't commit
        # Mark as committed to prevent auto-commit
        self.committed = True
    
    def has_backup(self) -> bool:
        """Check if backup was created.
        
        Returns:
            True if backup exists
        """
        return self.backup_path is not None and self.backup_path.exists()
    
    def restore_backup(self) -> None:
        """Restore from backup.
        
        Restores original document from backup file created during commit.
        Only works if backup was enabled and commit was called.
        
        Raises:
            RuntimeError: If no backup exists
            
        Example:
            >>> with DocumentTransaction("doc.docx", backup=True) as txn:
            ...     # Make changes...
            ...     txn.commit()
            >>> 
            >>> # Later, restore from backup
            >>> with DocumentTransaction("doc.docx") as txn:
            ...     txn.restore_backup()
        """
        if not self.has_backup():
            raise RuntimeError("No backup available to restore")
        
        shutil.copy2(self.backup_path, self.document_path)
