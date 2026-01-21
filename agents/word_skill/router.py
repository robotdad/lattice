"""
Module: API Router - API Recommendation Engine

Decision tree logic to guide users to the appropriate API level based on
their requirements. Analyzes task descriptions and provides recommendations
with reasoning and example code.

Public Interface:
    - recommend_api: Get API recommendation from task description
    - should_use_simple_api: Check if Simple API is sufficient
    - should_use_advanced_api: Check if Advanced API is needed
    - should_use_ooxml_api: Check if Raw OOXML is required
    - Recommendation: Dataclass with recommendation details

Example:
    >>> from docx_skill.router import recommend_api
    >>> 
    >>> # Get recommendation
    >>> rec = recommend_api("Create a report with title and paragraphs")
    >>> print(rec.api_level)  # "simple"
    >>> print(rec.reasoning)
    >>> print(rec.example_code)
    >>> 
    >>> # Check requirements dict
    >>> from docx_skill.router import should_use_simple_api
    >>> requirements = {"custom_styles": False, "basic_formatting": True}
    >>> if should_use_simple_api(requirements):
    ...     print("Use Simple API")
"""

from dataclasses import dataclass
from typing import Literal, List, Dict, Any
import re


@dataclass
class Recommendation:
    """API recommendation with reasoning.
    
    Attributes:
        api_level: Recommended API level ("simple", "advanced", or "ooxml")
        reasoning: Explanation of why this API was recommended
        example_code: Python code example using recommended API
        alternatives: List of alternative approaches or considerations
    
    Example:
        >>> rec = recommend_api("Create document with table")
        >>> print(f"Use: {rec.api_level}")
        >>> print(f"Why: {rec.reasoning}")
        >>> print(f"Example:\n{rec.example_code}")
    """
    api_level: Literal["simple", "advanced", "ooxml"]
    reasoning: str
    example_code: str
    alternatives: List[str]


def recommend_api(task_description: str) -> Recommendation:
    """Recommend API level for task.
    
    Analyzes the task description using keyword matching and heuristics to
    determine which API level is most appropriate.
    
    Args:
        task_description: Natural language description of what user wants to do
    
    Returns:
        Recommendation with reasoning and example code
    
    Example:
        >>> # Simple task
        >>> rec = recommend_api("Create a document with heading and text")
        >>> assert rec.api_level == "simple"
        >>> 
        >>> # Advanced task
        >>> rec = recommend_api("Create custom paragraph style with specific font")
        >>> assert rec.api_level == "advanced"
        >>> 
        >>> # Complex task
        >>> rec = recommend_api("Modify XML structure of document body")
        >>> assert rec.api_level == "ooxml"
    """
    task_lower = task_description.lower()
    
    # Extract requirements from description
    requirements = _extract_requirements(task_lower)
    
    # Decision tree
    if should_use_ooxml_api(requirements):
        return _ooxml_recommendation(task_description, requirements)
    elif should_use_advanced_api(requirements):
        return _advanced_recommendation(task_description, requirements)
    else:
        return _simple_recommendation(task_description, requirements)


def should_use_simple_api(requirements: Dict[str, Any]) -> bool:
    """Check if Simple API is sufficient.
    
    Simple API is suitable for:
    - Basic document structure (headings, paragraphs, lists)
    - Simple tables without complex styling
    - Images with basic sizing
    - Basic text formatting (bold, italic, font size)
    - No custom styles or complex page layout
    
    Args:
        requirements: Dictionary of extracted requirements
    
    Returns:
        True if Simple API is sufficient
    
    Example:
        >>> requirements = {
        ...     "headings": True,
        ...     "paragraphs": True,
        ...     "lists": True,
        ...     "custom_styles": False,
        ...     "page_layout": False
        ... }
        >>> assert should_use_simple_api(requirements) == True
    """
    # Simple API NOT sufficient if any of these are true
    complex_features = [
        requirements.get("custom_styles"),
        requirements.get("custom_page_layout"),
        requirements.get("headers_footers"),
        requirements.get("advanced_tables"),
        requirements.get("xml_manipulation"),
        requirements.get("complex_sections"),
    ]
    
    return not any(complex_features)


def should_use_advanced_api(requirements: Dict[str, Any]) -> bool:
    """Check if Advanced API is needed.
    
    Advanced API is needed for:
    - Custom paragraph or character styles
    - Page layout control (margins, orientation, sections)
    - Headers and footers
    - Advanced table styling
    - Multiple sections with different layouts
    
    Args:
        requirements: Dictionary of extracted requirements
    
    Returns:
        True if Advanced API is needed
    
    Example:
        >>> requirements = {
        ...     "custom_styles": True,
        ...     "page_layout": True,
        ...     "xml_manipulation": False
        ... }
        >>> assert should_use_advanced_api(requirements) == True
    """
    advanced_features = [
        requirements.get("custom_styles"),
        requirements.get("custom_page_layout"),
        requirements.get("headers_footers"),
        requirements.get("advanced_tables"),
        requirements.get("complex_sections"),
    ]
    
    # Need Advanced if any advanced features present but no XML manipulation
    has_advanced = any(advanced_features)
    needs_xml = requirements.get("xml_manipulation", False)
    
    return has_advanced and not needs_xml


def should_use_ooxml_api(requirements: Dict[str, Any]) -> bool:
    """Check if Raw OOXML is required.
    
    OOXML API is required for:
    - Direct XML manipulation
    - Custom XML elements
    - Low-level document structure changes
    - Features not exposed by higher-level APIs
    
    Args:
        requirements: Dictionary of extracted requirements
    
    Returns:
        True if OOXML API is required
    
    Example:
        >>> requirements = {
        ...     "xml_manipulation": True
        ... }
        >>> assert should_use_ooxml_api(requirements) == True
    """
    return requirements.get("xml_manipulation", False)


def _extract_requirements(task_description: str) -> Dict[str, Any]:
    """Extract requirements from task description using keyword matching.
    
    Args:
        task_description: Lowercase task description
    
    Returns:
        Dictionary of boolean requirements
    """
    requirements = {
        "headings": False,
        "paragraphs": False,
        "lists": False,
        "tables": False,
        "images": False,
        "custom_styles": False,
        "custom_page_layout": False,
        "headers_footers": False,
        "advanced_tables": False,
        "xml_manipulation": False,
        "complex_sections": False,
    }
    
    # Simple features
    if any(word in task_description for word in ["heading", "title", "chapter"]):
        requirements["headings"] = True
    
    if any(word in task_description for word in ["paragraph", "text", "content", "body"]):
        requirements["paragraphs"] = True
    
    if any(word in task_description for word in ["list", "bullet", "numbered", "items"]):
        requirements["lists"] = True
    
    if "table" in task_description:
        requirements["tables"] = True
    
    if any(word in task_description for word in ["image", "picture", "photo", "graphic"]):
        requirements["images"] = True
    
    # Advanced features
    if any(word in task_description for word in ["custom style", "create style", "define style", "paragraph style", "character style"]):
        requirements["custom_styles"] = True
    
    if any(word in task_description for word in ["margin", "orientation", "landscape", "portrait", "page size"]):
        requirements["custom_page_layout"] = True
    
    if any(word in task_description for word in ["header", "footer"]):
        requirements["headers_footers"] = True
    
    if any(word in task_description for word in ["table style", "merge cell", "table format"]):
        requirements["advanced_tables"] = True
    
    if any(word in task_description for word in ["section", "different layout", "multi-section"]):
        requirements["complex_sections"] = True
    
    # OOXML features
    if any(word in task_description for word in ["xml", "ooxml", "low-level", "direct manipulation", "custom element"]):
        requirements["xml_manipulation"] = True
    
    return requirements


def _simple_recommendation(task: str, req: Dict[str, Any]) -> Recommendation:
    """Generate recommendation for Simple API."""
    
    reasoning = (
        "Simple API is recommended because your task involves basic document "
        "creation with standard elements (headings, paragraphs, lists, tables, images). "
        "The Simple API provides a fluent interface with method chaining for quick "
        "document creation."
    )
    
    example_code = '''from docx_skill.simple import DocumentBuilder

# Create document with method chaining
doc = DocumentBuilder()
doc.add_heading("Report Title", level=1)
doc.add_paragraph("Introduction text", bold=True)
doc.add_list(["Point 1", "Point 2", "Point 3"])

# Add table with headers
doc.add_table(
    data=[
        ["John", "Doe", "30"],
        ["Jane", "Smith", "25"]
    ],
    headers=["First", "Last", "Age"]
)

# Save document
doc.save("output.docx")'''
    
    alternatives = [
        "If you need custom styles or page layout, consider Advanced API",
        "All Simple API methods support method chaining for cleaner code",
        "Use overwrite=True in save() to allow file overwrites",
    ]
    
    return Recommendation(
        api_level="simple",
        reasoning=reasoning,
        example_code=example_code,
        alternatives=alternatives
    )


def _advanced_recommendation(task: str, req: Dict[str, Any]) -> Recommendation:
    """Generate recommendation for Advanced API."""
    
    features = []
    if req.get("custom_styles"):
        features.append("custom styles")
    if req.get("custom_page_layout"):
        features.append("page layout control")
    if req.get("headers_footers"):
        features.append("headers/footers")
    if req.get("advanced_tables"):
        features.append("advanced table styling")
    if req.get("complex_sections"):
        features.append("multiple sections")
    
    feature_str = ", ".join(features) if features else "advanced formatting"
    
    reasoning = (
        f"Advanced API is recommended because your task requires {feature_str}. "
        "The Advanced API provides specialized managers (StyleManager, SectionManager, "
        "TableBuilder, ImageManager) for fine-grained control over document structure "
        "and formatting."
    )
    
    example_code = '''from docx_skill.advanced import AdvancedDocument

# Create document with advanced features
doc = AdvancedDocument()

# Create custom style
doc.styles.add_paragraph_style(
    name="Emphasis",
    font_size=14,
    bold=True,
    color=(255, 0, 0)
)

# Set page layout
doc.sections.set_margins(top=1.0, bottom=1.0, left=1.5, right=1.5)
doc.sections.add_header("Confidential Document")

# Add content
doc.add_heading("Introduction", level=1)
doc.add_paragraph("Important text", style="Emphasis")

# Advanced table
table = doc.tables.add_table_from_data(
    data=[["A", "B"], ["C", "D"]],
    headers=["Column 1", "Column 2"],
    style="Light Grid Accent 1"
)

# Save
doc.save("output.docx")'''
    
    alternatives = [
        "If you don't need advanced features, Simple API is easier",
        "Access underlying OOXMLDocument with get_ooxml_document() for raw XML access",
        "All managers are accessible via properties: doc.styles, doc.sections, etc.",
    ]
    
    return Recommendation(
        api_level="advanced",
        reasoning=reasoning,
        example_code=example_code,
        alternatives=alternatives
    )


def _ooxml_recommendation(task: str, req: Dict[str, Any]) -> Recommendation:
    """Generate recommendation for OOXML API."""
    
    reasoning = (
        "OOXML API is recommended because your task requires direct XML manipulation "
        "or low-level control over document structure. This API provides direct access "
        "to the underlying Office Open XML format, allowing you to create custom elements "
        "or modify the document structure in ways not exposed by higher-level APIs."
    )
    
    example_code = '''from docx_skill.ooxml import OOXMLDocument, get_xml_element

# Create document with OOXML access
doc = OOXMLDocument()

# Standard operations
doc.add_heading("Title", level=1)
doc.add_paragraph("Content")

# Direct XML access
body = doc.get_body_element()
paragraphs = doc.find_elements('p')  # Find all paragraph elements

# Get document properties
props = doc.get_core_properties()
props.author = "Your Name"
props.title = "Document Title"

# Access python-docx Document directly
docx_obj = doc.document

# Save
doc.save("output.docx")'''
    
    alternatives = [
        "Only use OOXML API if higher-level APIs don't meet your needs",
        "Consider Simple or Advanced APIs first - they're easier and safer",
        "Direct XML manipulation requires knowledge of OOXML specification",
        "Use doc.document to access underlying python-docx Document object",
    ]
    
    return Recommendation(
        api_level="ooxml",
        reasoning=reasoning,
        example_code=example_code,
        alternatives=alternatives
    )
