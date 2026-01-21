"""
SharePoint integration for agents.

Provides document upload, sharing, and management using ROPC auth.
"""

import json
import logging
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class SharePointIntegration:
    """
    SharePoint client for agent document operations.
    
    Uses ROPC auth to act as the agent user.
    """
    
    GRAPH_BASE = "https://graph.microsoft.com/v1.0"
    
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        tenant_id: str,
        username: str,
        password: str,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.tenant_id = tenant_id
        self.username = username
        self.password = password
        self._token: str | None = None
        self._http: httpx.Client | None = None
    
    def _get_token(self) -> str:
        """Get access token using ROPC flow."""
        if self._token:
            return self._token
        
        response = httpx.post(
            f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token",
            data={
                "client_id": self.client_id,
                "scope": "https://graph.microsoft.com/.default",
                "client_secret": self.client_secret,
                "grant_type": "password",
                "username": self.username,
                "password": self.password,
            },
        )
        
        data = response.json()
        if "access_token" not in data:
            error = data.get("error_description", data.get("error", "Unknown error"))
            raise RuntimeError(f"Token acquisition failed: {error}")
        
        self._token = data["access_token"]
        return self._token
    
    def _get_http(self) -> httpx.Client:
        """Get HTTP client with auth headers."""
        if self._http is None:
            self._http = httpx.Client(timeout=60.0)
        return self._http
    
    def _request(
        self,
        method: str,
        path: str,
        json_data: dict | None = None,
        content: bytes | None = None,
        headers: dict | None = None,
    ) -> httpx.Response:
        """Make authenticated request to Graph API."""
        token = self._get_token()
        http = self._get_http()
        
        url = f"{self.GRAPH_BASE}{path}"
        req_headers = {
            "Authorization": f"Bearer {token}",
        }
        if headers:
            req_headers.update(headers)
        if json_data:
            req_headers["Content-Type"] = "application/json"
        
        return http.request(
            method=method,
            url=url,
            headers=req_headers,
            json=json_data,
            content=content,
        )
    
    def get_site(self, site_name: str) -> dict:
        """Get SharePoint site by name."""
        response = self._request("GET", f"/sites?search={site_name}")
        
        if response.status_code != 200:
            raise RuntimeError(f"Failed to find site: {response.text}")
        
        sites = response.json().get("value", [])
        if not sites:
            raise RuntimeError(f"Site '{site_name}' not found")
        
        return sites[0]
    
    def get_drive(self, site_id: str) -> dict:
        """Get the default document library drive for a site."""
        response = self._request("GET", f"/sites/{site_id}/drive")
        
        if response.status_code != 200:
            raise RuntimeError(f"Failed to get drive: {response.text}")
        
        return response.json()
    
    def list_files(self, site_id: str, folder_path: str = "root") -> list[dict]:
        """List files in a folder."""
        if folder_path == "root":
            path = f"/sites/{site_id}/drive/root/children"
        else:
            path = f"/sites/{site_id}/drive/root:/{folder_path}:/children"
        
        response = self._request("GET", path)
        
        if response.status_code != 200:
            raise RuntimeError(f"Failed to list files: {response.text}")
        
        return response.json().get("value", [])
    
    def upload_file(
        self,
        site_id: str,
        file_path: str | Path,
        destination_path: str,
    ) -> dict:
        """
        Upload a file to SharePoint.
        
        Args:
            site_id: SharePoint site ID
            file_path: Local path to file
            destination_path: Path in SharePoint (e.g., "Documents/report.docx")
        
        Returns:
            File metadata from Graph API
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        content = file_path.read_bytes()
        
        # Use simple upload for small files (<4MB)
        if len(content) < 4 * 1024 * 1024:
            response = self._request(
                "PUT",
                f"/sites/{site_id}/drive/root:/{destination_path}:/content",
                content=content,
                headers={"Content-Type": "application/octet-stream"},
            )
        else:
            # For larger files, would use upload session
            raise NotImplementedError("Large file upload not yet implemented")
        
        if response.status_code not in (200, 201):
            raise RuntimeError(f"Failed to upload file: {response.text}")
        
        return response.json()
    
    def create_sharing_link(
        self,
        site_id: str,
        item_id: str,
        link_type: str = "view",
        scope: str = "organization",
    ) -> str:
        """
        Create a sharing link for a file.
        
        Args:
            site_id: SharePoint site ID
            item_id: File item ID
            link_type: "view" or "edit"
            scope: "anonymous", "organization", or "users"
        
        Returns:
            Sharing URL
        """
        response = self._request(
            "POST",
            f"/sites/{site_id}/drive/items/{item_id}/createLink",
            json_data={
                "type": link_type,
                "scope": scope,
            },
        )
        
        if response.status_code not in (200, 201):
            raise RuntimeError(f"Failed to create sharing link: {response.text}")
        
        return response.json()["link"]["webUrl"]
    
    def get_file_url(self, site_id: str, item_id: str) -> str:
        """Get the web URL for a file."""
        response = self._request("GET", f"/sites/{site_id}/drive/items/{item_id}")
        
        if response.status_code != 200:
            raise RuntimeError(f"Failed to get file: {response.text}")
        
        return response.json()["webUrl"]
    
    def close(self):
        """Close HTTP client."""
        if self._http:
            self._http.close()
            self._http = None
