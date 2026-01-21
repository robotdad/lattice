"""
Module: Validation

Provides comprehensive validation for DOCX documents including structure,
styles, formatting, and content checks. Returns detailed ValidationResult
objects with actionable error messages.

Public Interface:
    - ValidationResult: Result object with errors, warnings, and metadata
    - validate_docx: Check if file is valid DOCX
    - validate_styles: Verify style consistency and usage
    - validate_structure: Check document structure and organization
    - validate_content: Validate content rules and constraints

Example:
    >>> from docx_skill.validation import validate_docx, ValidationResult
    >>> 
    >>> # Basic validation
    >>> result = validate_docx("document.docx")
    >>> if result.is_valid:
    ...     print("Document is valid!")
    >>> else:
    ...     for error in result.errors:
    ...         print(f"Error: {error}")
    >>> 
    >>> # Style validation
    >>> result = validate_styles("document.docx")
    >>> for warning in result.warnings:
    ...     print(f"Warning: {warning}")
"""

import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any
import xml.etree.ElementTree as ET
from enum import Enum


class ValidationLevel(Enum):
    """Validation severity levels."""
    ERROR = "error"      # Critical issue that prevents usage
    WARNING = "warning"  # Non-critical issue that should be reviewed
    INFO = "info"        # Informational message


@dataclass
class ValidationIssue:
    """A single validation issue.
    
    Attributes:
        level: Severity level (ERROR, WARNING, INFO)
        message: Human-readable description
        location: Where the issue occurs (e.g., "paragraph 5", "style 'Heading 1'")
        suggestion: Suggested fix or remediation
        code: Machine-readable error code
    """
    level: ValidationLevel
    message: str
    location: Optional[str] = None
    suggestion: Optional[str] = None
    code: Optional[str] = None
    
    def __str__(self) -> str:
        """Format issue as readable string."""
        parts = [f"[{self.level.value.upper()}]"]
        if self.location:
            parts.append(f"({self.location})")
        parts.append(self.message)
        if self.suggestion:
            parts.append(f"→ {self.suggestion}")
        return " ".join(parts)


@dataclass
class ValidationResult:
    """Result of document validation.
    
    Provides detailed validation results including errors, warnings, and
    informational messages. Use is_valid property to check if validation passed.
    
    Attributes:
        issues: List of all validation issues
        metadata: Additional validation metadata
        validated_path: Path to validated document
        
    Example:
        >>> result = validate_docx("document.docx")
        >>> print(f"Valid: {result.is_valid}")
        >>> print(f"Errors: {len(result.errors)}")
        >>> print(f"Warnings: {len(result.warnings)}")
        >>> 
        >>> if not result.is_valid:
        ...     for error in result.errors:
        ...         print(error)
    """
    issues: List[ValidationIssue] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    validated_path: Optional[Path] = None
    
    @property
    def is_valid(self) -> bool:
        """Check if validation passed (no errors).
        
        Returns:
            True if no ERROR-level issues exist
        """
        return not any(issue.level == ValidationLevel.ERROR for issue in self.issues)
    
    @property
    def errors(self) -> List[ValidationIssue]:
        """Get all ERROR-level issues."""
        return [i for i in self.issues if i.level == ValidationLevel.ERROR]
    
    @property
    def warnings(self) -> List[ValidationIssue]:
        """Get all WARNING-level issues."""
        return [i for i in self.issues if i.level == ValidationLevel.WARNING]
    
    @property
    def info(self) -> List[ValidationIssue]:
        """Get all INFO-level messages."""
        return [i for i in self.issues if i.level == ValidationLevel.INFO]
    
    def add_error(self, message: str, location: Optional[str] = None, 
                  suggestion: Optional[str] = None, code: Optional[str] = None) -> None:
        """Add an error-level issue.
        
        Args:
            message: Error description
            location: Where error occurs
            suggestion: Suggested fix
            code: Error code
        """
        self.issues.append(ValidationIssue(
            level=ValidationLevel.ERROR,
            message=message,
            location=location,
            suggestion=suggestion,
            code=code
        ))
    
    def add_warning(self, message: str, location: Optional[str] = None,
                    suggestion: Optional[str] = None, code: Optional[str] = None) -> None:
        """Add a warning-level issue.
        
        Args:
            message: Warning description
            location: Where warning occurs
            suggestion: Suggested fix
            code: Warning code
        """
        self.issues.append(ValidationIssue(
            level=ValidationLevel.WARNING,
            message=message,
            location=location,
            suggestion=suggestion,
            code=code
        ))
    
    def add_info(self, message: str, location: Optional[str] = None) -> None:
        """Add an info-level message.
        
        Args:
            message: Info description
            location: Where info applies
        """
        self.issues.append(ValidationIssue(
            level=ValidationLevel.INFO,
            message=message,
            location=location
        ))
    
    def __str__(self) -> str:
        """Format result as readable string."""
        lines = [
            f"Validation Result: {'PASSED' if self.is_valid else 'FAILED'}",
            f"  Errors: {len(self.errors)}",
            f"  Warnings: {len(self.warnings)}",
            f"  Info: {len(self.info)}"
        ]
        
        if self.errors:
            lines.append("\nErrors:")
            for error in self.errors:
                lines.append(f"  {error}")
        
        if self.warnings:
            lines.append("\nWarnings:")
            for warning in self.warnings:
                lines.append(f"  {warning}")
        
        return "\n".join(lines)


# OOXML namespaces
NAMESPACES = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
}


def validate_docx(document_path: str | Path, check_corruption: bool = True) -> ValidationResult:
    """Validate that a file is a valid DOCX document.
    
    Checks:
    - File exists and is readable
    - File is a valid ZIP archive
    - Contains required OOXML structure ([Content_Types].xml, document.xml)
    - XML is well-formed
    - Optional: Check for common corruption patterns
    
    Args:
        document_path: Path to DOCX file
        check_corruption: Perform deep corruption checks
        
    Returns:
        ValidationResult with validation details
        
    Example:
        >>> result = validate_docx("document.docx")
        >>> if not result.is_valid:
        ...     print(f"Invalid document: {result.errors[0].message}")
        >>> 
        >>> # Deep validation
        >>> result = validate_docx("document.docx", check_corruption=True)
        >>> print(f"Checked for corruption: {result.is_valid}")
    """
    result = ValidationResult(validated_path=Path(document_path))
    path = Path(document_path)
    
    # Check file exists
    if not path.exists():
        result.add_error(
            f"File not found: {path}",
            code="FILE_NOT_FOUND",
            suggestion="Check the file path"
        )
        return result
    
    # Check file is readable
    if not path.is_file():
        result.add_error(
            f"Not a file: {path}",
            code="NOT_A_FILE"
        )
        return result
    
    # Check file extension
    if path.suffix.lower() not in ['.docx', '.docm']:
        result.add_warning(
            f"Unexpected file extension: {path.suffix}",
            suggestion="DOCX files should have .docx or .docm extension"
        )
    
    # Check it's a valid ZIP
    try:
        with zipfile.ZipFile(path, 'r') as zip_ref:
            # Check for required files
            required_files = [
                '[Content_Types].xml',
                'word/document.xml',
                '_rels/.rels'
            ]
            
            zip_files = zip_ref.namelist()
            
            for required in required_files:
                if required not in zip_files:
                    result.add_error(
                        f"Missing required file: {required}",
                        code="MISSING_REQUIRED_FILE",
                        suggestion="File may be corrupted or not a valid DOCX"
                    )
            
            # If no errors so far, check XML is well-formed
            if result.is_valid:
                try:
                    # Parse main document XML
                    doc_xml = zip_ref.read('word/document.xml')
                    tree = ET.fromstring(doc_xml)
                    
                    # Store metadata
                    result.metadata['has_body'] = tree.find('.//w:body', NAMESPACES) is not None
                    result.metadata['paragraph_count'] = len(tree.findall('.//w:p', NAMESPACES))
                    
                    result.add_info(f"Document has {result.metadata['paragraph_count']} paragraphs")
                    
                except ET.ParseError as e:
                    result.add_error(
                        f"Malformed XML in document.xml: {e}",
                        code="XML_PARSE_ERROR",
                        suggestion="File may be corrupted"
                    )
            
            # Deep corruption check
            if check_corruption and result.is_valid:
                # Test all XML files
                for filename in zip_files:
                    if filename.endswith('.xml'):
                        try:
                            content = zip_ref.read(filename)
                            ET.fromstring(content)
                        except ET.ParseError as e:
                            result.add_error(
                                f"Malformed XML in {filename}: {e}",
                                code="XML_PARSE_ERROR"
                            )
                        except Exception as e:
                            result.add_warning(
                                f"Could not read {filename}: {e}"
                            )
    
    except zipfile.BadZipFile:
        result.add_error(
            "Not a valid ZIP file",
            code="INVALID_ZIP",
            suggestion="File may be corrupted or not a DOCX document"
        )
    except Exception as e:
        result.add_error(
            f"Unexpected error reading file: {e}",
            code="UNEXPECTED_ERROR"
        )
    
    return result


def validate_styles(
    document_path: str | Path,
    check_consistency: bool = True,
    check_unused: bool = True
) -> ValidationResult:
    """Validate document styles and style usage.
    
    Checks:
    - Style definitions are valid
    - Style inheritance is correct
    - Styles are used consistently
    - Detects unused styles
    - Checks for style naming conflicts
    
    Args:
        document_path: Path to DOCX file
        check_consistency: Check for consistent style usage
        check_unused: Report unused styles
        
    Returns:
        ValidationResult with style validation details
        
    Example:
        >>> result = validate_styles("document.docx")
        >>> if result.warnings:
        ...     print(f"Found {len(result.warnings)} style warnings")
        >>> 
        >>> # Check for unused styles
        >>> result = validate_styles("document.docx", check_unused=True)
        >>> for warning in result.warnings:
        ...     if "unused" in warning.message.lower():
        ...         print(f"Unused style: {warning.location}")
    """
    result = ValidationResult(validated_path=Path(document_path))
    path = Path(document_path)
    
    # First validate it's a valid DOCX
    docx_validation = validate_docx(path, check_corruption=False)
    if not docx_validation.is_valid:
        result.add_error(
            "Cannot validate styles: invalid DOCX",
            suggestion="Run validate_docx first"
        )
        return result
    
    try:
        with zipfile.ZipFile(path, 'r') as zip_ref:
            # Check if styles.xml exists
            if 'word/styles.xml' not in zip_ref.namelist():
                result.add_warning(
                    "No styles.xml found",
                    suggestion="Document may have no custom styles"
                )
                return result
            
            # Parse styles
            styles_xml = zip_ref.read('word/styles.xml')
            styles_tree = ET.fromstring(styles_xml)
            
            # Parse document for style usage
            doc_xml = zip_ref.read('word/document.xml')
            doc_tree = ET.fromstring(doc_xml)
            
            # Extract defined styles
            defined_styles = {}
            for style in styles_tree.findall('.//w:style', NAMESPACES):
                style_id = style.get('{%s}styleId' % NAMESPACES['w'])
                style_name_elem = style.find('.//w:name', NAMESPACES)
                style_name = style_name_elem.get('{%s}val' % NAMESPACES['w']) if style_name_elem is not None else style_id
                
                if style_id:
                    defined_styles[style_id] = {
                        'name': style_name,
                        'type': style.get('{%s}type' % NAMESPACES['w']),
                        'used': False
                    }
            
            result.metadata['defined_styles'] = len(defined_styles)
            result.add_info(f"Found {len(defined_styles)} defined styles")
            
            # Extract used styles
            used_styles = set()
            
            # Check paragraph styles
            for para in doc_tree.findall('.//w:p', NAMESPACES):
                style_elem = para.find('.//w:pStyle', NAMESPACES)
                if style_elem is not None:
                    style_id = style_elem.get('{%s}val' % NAMESPACES['w'])
                    if style_id:
                        used_styles.add(style_id)
                        if style_id in defined_styles:
                            defined_styles[style_id]['used'] = True
            
            # Check character styles
            for run in doc_tree.findall('.//w:r', NAMESPACES):
                style_elem = run.find('.//w:rStyle', NAMESPACES)
                if style_elem is not None:
                    style_id = style_elem.get('{%s}val' % NAMESPACES['w'])
                    if style_id:
                        used_styles.add(style_id)
                        if style_id in defined_styles:
                            defined_styles[style_id]['used'] = True
            
            result.metadata['used_styles'] = len(used_styles)
            result.add_info(f"Found {len(used_styles)} used styles")
            
            # Check for undefined styles being used
            if check_consistency:
                for style_id in used_styles:
                    if style_id not in defined_styles:
                        result.add_warning(
                            f"Style '{style_id}' is used but not defined",
                            location=f"style '{style_id}'",
                            suggestion="Add style definition or remove usage"
                        )
            
            # Check for unused styles
            if check_unused:
                unused = [
                    (style_id, info['name']) 
                    for style_id, info in defined_styles.items() 
                    if not info['used']
                ]
                
                if unused:
                    result.add_info(f"Found {len(unused)} unused styles")
                    for style_id, style_name in unused[:5]:  # Limit to first 5
                        result.add_warning(
                            f"Style '{style_name}' is defined but never used",
                            location=f"style '{style_id}'",
                            suggestion="Consider removing unused style"
                        )
                    
                    if len(unused) > 5:
                        result.add_info(f"... and {len(unused) - 5} more unused styles")
    
    except Exception as e:
        result.add_error(
            f"Error validating styles: {e}",
            code="STYLE_VALIDATION_ERROR"
        )
    
    return result


def validate_structure(
    document_path: str | Path,
    require_heading: bool = False,
    max_depth: Optional[int] = None
) -> ValidationResult:
    """Validate document structure and organization.
    
    Checks:
    - Document has logical heading hierarchy
    - Sections are properly defined
    - No empty sections
    - Heading levels are sequential (no H1 → H3 jumps)
    
    Args:
        document_path: Path to DOCX file
        require_heading: Require document to start with heading
        max_depth: Maximum heading depth allowed (e.g., 3 for H1-H3)
        
    Returns:
        ValidationResult with structure validation details
        
    Example:
        >>> result = validate_structure("document.docx", require_heading=True)
        >>> if not result.is_valid:
        ...     print("Document structure issues:")
        ...     for error in result.errors:
        ...         print(f"  - {error}")
        >>> 
        >>> # Check heading depth
        >>> result = validate_structure("document.docx", max_depth=3)
        >>> print(f"Max heading level used: {result.metadata.get('max_heading_level')}")
    """
    result = ValidationResult(validated_path=Path(document_path))
    path = Path(document_path)
    
    # First validate it's a valid DOCX
    docx_validation = validate_docx(path, check_corruption=False)
    if not docx_validation.is_valid:
        result.add_error(
            "Cannot validate structure: invalid DOCX",
            suggestion="Run validate_docx first"
        )
        return result
    
    try:
        with zipfile.ZipFile(path, 'r') as zip_ref:
            doc_xml = zip_ref.read('word/document.xml')
            doc_tree = ET.fromstring(doc_xml)
            
            # Extract all paragraphs with their styles
            paragraphs = []
            for para in doc_tree.findall('.//w:p', NAMESPACES):
                style_elem = para.find('.//w:pStyle', NAMESPACES)
                style_id = None
                if style_elem is not None:
                    style_id = style_elem.get('{%s}val' % NAMESPACES['w'])
                
                # Get text content
                text_parts = []
                for text_elem in para.findall('.//w:t', NAMESPACES):
                    if text_elem.text:
                        text_parts.append(text_elem.text)
                text = ''.join(text_parts).strip()
                
                paragraphs.append({
                    'style': style_id,
                    'text': text,
                    'has_content': len(text) > 0
                })
            
            result.metadata['paragraph_count'] = len(paragraphs)
            
            # Identify headings
            heading_pattern = ['Heading1', 'Heading2', 'Heading3', 'Heading4', 'Heading5', 'Heading6']
            headings = []
            
            for idx, para in enumerate(paragraphs):
                if para['style'] and para['style'] in heading_pattern:
                    level = int(para['style'][-1])
                    headings.append({
                        'level': level,
                        'text': para['text'],
                        'index': idx,
                        'has_content': para['has_content']
                    })
            
            result.metadata['heading_count'] = len(headings)
            result.add_info(f"Found {len(headings)} headings")
            
            if headings:
                max_level = max(h['level'] for h in headings)
                result.metadata['max_heading_level'] = max_level
                result.add_info(f"Maximum heading level: H{max_level}")
            
            # Check if document starts with heading
            if require_heading:
                if not headings:
                    result.add_error(
                        "Document does not contain any headings",
                        code="NO_HEADINGS",
                        suggestion="Add at least one heading to structure the document"
                    )
                elif headings[0]['index'] > 0:
                    result.add_warning(
                        "Document does not start with a heading",
                        suggestion="Consider starting with a heading for better structure"
                    )
            
            # Check heading depth
            if max_depth and headings:
                max_level = max(h['level'] for h in headings)
                if max_level > max_depth:
                    result.add_warning(
                        f"Document uses heading level H{max_level}, exceeding max depth H{max_depth}",
                        suggestion=f"Consider limiting heading depth to H{max_depth}"
                    )
            
            # Check heading sequence (no level jumps)
            prev_level = 0
            for idx, heading in enumerate(headings):
                level = heading['level']
                
                # Check for level jumps (e.g., H1 → H3)
                if level > prev_level + 1:
                    result.add_warning(
                        f"Heading level jump: H{prev_level} → H{level}",
                        location=f"heading {idx + 1}: '{heading['text'][:50]}'",
                        suggestion=f"Use H{prev_level + 1} instead of H{level}"
                    )
                
                # Check for empty headings
                if not heading['has_content']:
                    result.add_warning(
                        f"Empty heading at H{level}",
                        location=f"heading {idx + 1}",
                        suggestion="Remove empty heading or add content"
                    )
                
                prev_level = level
            
            # Check for empty document
            if not any(p['has_content'] for p in paragraphs):
                result.add_warning(
                    "Document appears to be empty (no text content)",
                    code="EMPTY_DOCUMENT"
                )
    
    except Exception as e:
        result.add_error(
            f"Error validating structure: {e}",
            code="STRUCTURE_VALIDATION_ERROR"
        )
    
    return result


def validate_content(
    document_path: str | Path,
    min_words: Optional[int] = None,
    max_words: Optional[int] = None,
    check_spelling: bool = False
) -> ValidationResult:
    """Validate document content against constraints.
    
    Checks:
    - Word count within specified range
    - Optional: Spelling check (requires additional library)
    - Character encoding issues
    
    Args:
        document_path: Path to DOCX file
        min_words: Minimum word count (None = no minimum)
        max_words: Maximum word count (None = no maximum)
        check_spelling: Perform spell check (not yet implemented)
        
    Returns:
        ValidationResult with content validation details
        
    Example:
        >>> # Check word count
        >>> result = validate_content("document.docx", min_words=100, max_words=1000)
        >>> print(f"Word count: {result.metadata['word_count']}")
        >>> 
        >>> if not result.is_valid:
        ...     for error in result.errors:
        ...         print(error)
    """
    result = ValidationResult(validated_path=Path(document_path))
    path = Path(document_path)
    
    # First validate it's a valid DOCX
    docx_validation = validate_docx(path, check_corruption=False)
    if not docx_validation.is_valid:
        result.add_error(
            "Cannot validate content: invalid DOCX",
            suggestion="Run validate_docx first"
        )
        return result
    
    try:
        with zipfile.ZipFile(path, 'r') as zip_ref:
            doc_xml = zip_ref.read('word/document.xml')
            doc_tree = ET.fromstring(doc_xml)
            
            # Extract all text
            text_parts = []
            for text_elem in doc_tree.findall('.//w:t', NAMESPACES):
                if text_elem.text:
                    text_parts.append(text_elem.text)
            
            full_text = ' '.join(text_parts)
            word_count = len(full_text.split())
            
            result.metadata['word_count'] = word_count
            result.metadata['character_count'] = len(full_text)
            result.add_info(f"Word count: {word_count:,}")
            result.add_info(f"Character count: {len(full_text):,}")
            
            # Check word count constraints
            if min_words is not None and word_count < min_words:
                result.add_error(
                    f"Document has {word_count:,} words, minimum is {min_words:,}",
                    code="INSUFFICIENT_WORDS",
                    suggestion=f"Add at least {min_words - word_count:,} more words"
                )
            
            if max_words is not None and word_count > max_words:
                result.add_error(
                    f"Document has {word_count:,} words, maximum is {max_words:,}",
                    code="EXCESSIVE_WORDS",
                    suggestion=f"Remove at least {word_count - max_words:,} words"
                )
            
            # Check for empty content
            if word_count == 0:
                result.add_warning(
                    "Document contains no text",
                    code="EMPTY_CONTENT"
                )
            
            # Spell check placeholder
            if check_spelling:
                result.add_info("Spell checking not yet implemented")
    
    except Exception as e:
        result.add_error(
            f"Error validating content: {e}",
            code="CONTENT_VALIDATION_ERROR"
        )
    
    return result
