"""
Document creation for agents using the word skill.

Creates Word documents that agents can then upload to SharePoint.
"""

import sys
import logging
from pathlib import Path
from typing import Any

# Add word skill to path
WORD_SKILL_PATH = Path.home() / ".amplifier" / "skills" / "word"
if WORD_SKILL_PATH.exists():
    sys.path.insert(0, str(WORD_SKILL_PATH))

logger = logging.getLogger(__name__)


class DocumentCreator:
    """
    Creates Word documents for agents.
    
    Wraps the word skill's DocumentBuilder for easy document creation.
    """
    
    def __init__(self, output_dir: str | Path | None = None):
        """
        Initialize document creator.
        
        Args:
            output_dir: Directory for created documents (default: ./documents)
        """
        self.output_dir = Path(output_dir) if output_dir else Path("./documents")
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def create_document(
        self,
        title: str,
        content: list[dict[str, Any]],
        filename: str,
        author: str | None = None,
    ) -> Path:
        """
        Create a Word document from structured content.
        
        Args:
            title: Document title (becomes Heading 1)
            content: List of content blocks, each with:
                - type: "heading", "paragraph", "list", "table"
                - level: For headings (1-9)
                - text: For headings and paragraphs
                - items: For lists
                - bold, italic: For paragraphs
                - headers, data: For tables
            filename: Output filename (without path)
            author: Document author
        
        Returns:
            Path to created document
        """
        try:
            from scripts import DocumentBuilder
        except ImportError:
            logger.warning("Word skill not available, using fallback")
            return self._create_fallback(title, content, filename)
        
        builder = DocumentBuilder()
        builder.add_heading(title, level=1)
        
        for block in content:
            block_type = block.get("type", "paragraph")
            
            if block_type == "heading":
                builder.add_heading(
                    block.get("text", ""),
                    level=block.get("level", 2),
                )
            elif block_type == "paragraph":
                builder.add_paragraph(
                    block.get("text", ""),
                    bold=block.get("bold", False),
                    italic=block.get("italic", False),
                )
            elif block_type == "list":
                builder.add_list(
                    block.get("items", []),
                    numbered=block.get("numbered", False),
                )
            elif block_type == "table":
                builder.add_table(
                    data=block.get("data", []),
                    headers=block.get("headers"),
                )
            elif block_type == "page_break":
                builder.add_page_break()
        
        output_path = self.output_dir / filename
        builder.save(str(output_path), overwrite=True)
        
        logger.info(f"Created document: {output_path}")
        return output_path
    
    def create_simple_document(
        self,
        title: str,
        body: str,
        filename: str,
    ) -> Path:
        """
        Create a simple document with title and body text.
        
        Args:
            title: Document title
            body: Body text (can include multiple paragraphs separated by newlines)
            filename: Output filename
        
        Returns:
            Path to created document
        """
        content = []
        for paragraph in body.split("\n\n"):
            paragraph = paragraph.strip()
            if paragraph:
                content.append({"type": "paragraph", "text": paragraph})
        
        return self.create_document(title, content, filename)
    
    def _create_fallback(self, title: str, content: list, filename: str) -> Path:
        """Fallback to plain text if word skill unavailable."""
        output_path = self.output_dir / filename.replace(".docx", ".txt")
        
        lines = [title, "=" * len(title), ""]
        for block in content:
            if block.get("type") == "heading":
                lines.append(f"\n{block.get('text', '')}")
                lines.append("-" * len(block.get("text", "")))
            elif block.get("type") == "paragraph":
                lines.append(block.get("text", ""))
                lines.append("")
            elif block.get("type") == "list":
                for item in block.get("items", []):
                    lines.append(f"  - {item}")
                lines.append("")
        
        output_path.write_text("\n".join(lines))
        return output_path
