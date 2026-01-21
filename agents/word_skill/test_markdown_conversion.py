#!/usr/bin/env python3
"""
Test markdown conversion of lists to verify the fix works end-to-end.
"""

import sys
from pathlib import Path

def test_markdown_conversion():
    """Test that lists convert correctly to markdown."""
    print("=" * 60)
    print("Testing Markdown Conversion")
    print("=" * 60)
    
    # Import conversion function
    try:
        from conversion import docx_to_markdown, is_markitdown_available
    except ImportError:
        print("✗ Could not import conversion module")
        return False
    
    # Check if markitdown is available
    if not is_markitdown_available():
        print("✗ markitdown not installed")
        print("  Install with: pip install markitdown")
        return False
    
    print("✓ markitdown is available")
    
    # Convert the test document
    docx_path = "/Users/robotdad/guide/test_lists.docx"
    if not Path(docx_path).exists():
        print(f"✗ Test document not found: {docx_path}")
        return False
    
    print(f"\nConverting: {docx_path}")
    
    try:
        markdown = docx_to_markdown(docx_path)
        print(f"✓ Converted to {len(markdown)} characters")
    except Exception as e:
        print(f"✗ Conversion failed: {e}")
        return False
    
    # Verify content
    print("\n" + "-" * 60)
    print("Generated Markdown:")
    print("-" * 60)
    print(markdown)
    print("-" * 60)
    
    # Check for correct list markers
    print("\nVerifying list markers...")
    
    success = True
    
    # Check bullets
    bullet_items = [
        "* First bullet item",
        "* Second bullet item",
        "* Third bullet item"
    ]
    
    for item in bullet_items:
        if item in markdown:
            print(f"  ✓ Found: {item}")
        else:
            print(f"  ✗ Missing: {item}")
            success = False
    
    # Check numbers
    number_items = [
        "1. First numbered item",
        "2. Second numbered item",
        "3. Third numbered item"
    ]
    
    for item in number_items:
        if item in markdown:
            print(f"  ✓ Found: {item}")
        else:
            print(f"  ✗ Missing: {item}")
            success = False
    
    print("\n" + "=" * 60)
    if success:
        print("✓ MARKDOWN CONVERSION SUCCESSFUL")
        print("=" * 60)
        print("\nBoth bullets and numbered lists convert correctly!")
        return True
    else:
        print("✗ MARKDOWN CONVERSION FAILED")
        print("=" * 60)
        return False

if __name__ == "__main__":
    success = test_markdown_conversion()
    sys.exit(0 if success else 1)
