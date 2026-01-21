"""Test SharePoint integration."""

import json
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agents.integrations.sharepoint import SharePointIntegration
from agents.integrations.documents import DocumentCreator

# Known app registration values
CLIENT_ID = "760968bf-bbb6-423f-bff0-837057851664"
TENANT_ID = "16f9353b-6b50-4fc6-b228-70870adaf580"


def main():
    # Load credentials
    creds_path = Path(__file__).parent.parent / "credentials.json"
    with open(creds_path) as f:
        creds = json.load(f)
    
    client_secret = creds["_app"]["client_secret"]
    bud_password = creds["bud"]["password"]
    
    # Create SharePoint client as Bud
    sp = SharePointIntegration(
        client_id=CLIENT_ID,
        client_secret=client_secret,
        tenant_id=TENANT_ID,
        username="Bud@M365x93789909.onmicrosoft.com",
        password=bud_password,
    )
    
    print("=== Testing SharePoint Integration ===\n")
    
    # 1. Find The Lot site
    print("1. Finding 'The Lot' site...")
    site = sp.get_site("lot")
    print(f"   Found: {site['displayName']}")
    print(f"   ID: {site['id']}")
    site_id = site["id"]
    
    # 2. Get the drive
    print("\n2. Getting document library...")
    drive = sp.get_drive(site_id)
    print(f"   Drive: {drive['name']}")
    
    # 3. List files
    print("\n3. Listing files in root...")
    files = sp.list_files(site_id)
    if files:
        for f in files[:5]:
            print(f"   - {f['name']}")
    else:
        print("   (empty)")
    
    # 4. Create a test document
    print("\n4. Creating test document...")
    doc_creator = DocumentCreator(output_dir="./test_docs")
    doc_path = doc_creator.create_simple_document(
        title="Test Document from Bud",
        body="This is a test document created by Bud.\n\nIt was uploaded to SharePoint via the Graph API.",
        filename="test_from_bud.docx",
    )
    print(f"   Created: {doc_path}")
    
    # 5. Upload to SharePoint
    print("\n5. Uploading to SharePoint...")
    result = sp.upload_file(site_id, doc_path, "test_from_bud.docx")
    print(f"   Uploaded: {result['name']}")
    print(f"   URL: {result['webUrl']}")
    
    # 6. Create sharing link
    print("\n6. Creating sharing link...")
    share_url = sp.create_sharing_link(site_id, result["id"])
    print(f"   Share URL: {share_url}")
    
    print("\n=== Test Complete ===")
    
    sp.close()


if __name__ == "__main__":
    main()
