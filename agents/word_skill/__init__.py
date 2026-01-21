"""
DOCX Skill - Comprehensive Microsoft Word Document Manipulation

A three-tier API for working with DOCX documents:

1. **Simple API** (simple.py) - High-level builder pattern for common tasks
   - Quick document creation
   - Minimal code for common operations
   - Recommended for most use cases

2. **Advanced API** (advanced.py) - Detailed control over formatting and structure
   - Style management
   - Section control
   - Table and image handling
   - Complex formatting

3. **OOXML API** (ooxml.py) - Direct XML manipulation for power users
   - Full control over document structure
   - Custom XML elements
   - Advanced OOXML operations

Core Infrastructure (Phase 1 - Available):
    - Safety mechanisms (temp files, transactions, overwrite protection)
    - Validation (document structure, styles, content)
    - OOXML foundation layer

High-Level APIs (Phase 2 - Available):
    - Simple API (DocumentBuilder) - For 80% of use cases
    - Advanced API (AdvancedDocument, StyleManager, etc.) - For fine-grained control
    - Router (API recommendation engine) - Guides you to the right API

Phase 3 (Available):
    - Conversion utilities (DOCX → Markdown, text extraction)

Example Usage:
    >>> # Simple API - Quick document creation
    >>> from docx_skill.simple import DocumentBuilder
    >>> 
    >>> doc = DocumentBuilder()
    >>> doc.add_heading("Report Title", level=1)
    >>> doc.add_paragraph("Introduction", bold=True)
    >>> doc.add_list(["Item 1", "Item 2", "Item 3"])
    >>> doc.save("report.docx")
    >>> 
    >>> # Advanced API - Full control
    >>> from docx_skill.advanced import AdvancedDocument
    >>> 
    >>> doc = AdvancedDocument()
    >>> doc.styles.add_paragraph_style("Emphasis", font_size=14, bold=True)
    >>> doc.sections.set_margins(1.0, 1.0, 1.5, 1.5)
    >>> doc.add_paragraph("Styled text", style="Emphasis")
    >>> doc.save("advanced.docx")
    >>> 
    >>> # Router - Get API recommendation
    >>> from docx_skill.router import recommend_api
    >>> 
    >>> rec = recommend_api("Create document with custom styles")
    >>> print(rec.api_level)  # "advanced"
    >>> print(rec.example_code)
    >>> 
    >>> # Conversion - DOCX to Markdown for LLMs
    >>> from docx_skill.conversion import docx_to_markdown
    >>> 
    >>> markdown = docx_to_markdown("contract.docx", "contract.md")
    >>> # Now use markdown in your LLM workflow

Version: 0.3.0
"""

# Phase 1: Core Infrastructure
from .safety import (
    TempFileManager,
    SafeFileOperations,
    DocumentTransaction,
    TempFileInfo,
)

from .validation import (
    ValidationResult,
    ValidationIssue,
    ValidationLevel,
    validate_docx,
    validate_styles,
    validate_structure,
    validate_content,
)

from .ooxml import (
    OOXMLDocument,
    NAMESPACES,
    qualified_name,
    get_xml_element,
    get_xml_elements,
    set_xml_property,
)

# Phase 2: High-Level APIs
from .simple import (
    DocumentBuilder,
)

from .advanced import (
    AdvancedDocument,
    StyleManager,
    SectionManager,
    TableBuilder,
    ImageManager,
)

from .router import (
    recommend_api,
    should_use_simple_api,
    should_use_advanced_api,
    should_use_ooxml_api,
    Recommendation,
)

# Phase 3: Conversion Utilities
from .conversion import (
    docx_to_markdown,
    extract_text,
    is_markitdown_available,
)

# Public API exports
__all__ = [
    # Safety
    'TempFileManager',
    'SafeFileOperations',
    'DocumentTransaction',
    'TempFileInfo',
    
    # Validation
    'ValidationResult',
    'ValidationIssue',
    'ValidationLevel',
    'validate_docx',
    'validate_styles',
    'validate_structure',
    'validate_content',
    
    # OOXML
    'OOXMLDocument',
    'NAMESPACES',
    'qualified_name',
    'get_xml_element',
    'get_xml_elements',
    'set_xml_property',
    
    # Simple API
    'DocumentBuilder',
    
    # Advanced API
    'AdvancedDocument',
    'StyleManager',
    'SectionManager',
    'TableBuilder',
    'ImageManager',
    
    # Router
    'recommend_api',
    'should_use_simple_api',
    'should_use_advanced_api',
    'should_use_ooxml_api',
    'Recommendation',
    
    # Conversion
    'docx_to_markdown',
    'extract_text',
    'is_markitdown_available',
]

__version__ = '0.3.0'
__author__ = 'Amplifier AI'
__license__ = 'MIT'
