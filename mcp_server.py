import base64
import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP


API_BASE_URL = os.getenv("MARKER_API_BASE_URL", "http://marker-api:8336").rstrip("/")
API_TOKEN = os.getenv("MARKER_API_TOKEN", "my-secret-token")
MCP_HOST = os.getenv("MARKER_MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.getenv("MARKER_MCP_PORT", "8337"))
MCP_PATH = os.getenv("MARKER_MCP_PATH", "/mcp")

mcp = FastMCP(
    "Marker MCP",
    host=MCP_HOST,
    port=MCP_PORT,
    streamable_http_path=MCP_PATH,
    stateless_http=True,
    json_response=True,
)


def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {API_TOKEN}"}


def compact_status(status: dict[str, Any]) -> dict[str, Any]:
    logs = status.get("logs")
    if isinstance(logs, list) and len(logs) > 20:
        status["logs"] = logs[-20:]
    return status


async def submit_file(
    filename: str,
    file_bytes: bytes,
    page_range: str | None = None,
    force_ocr: bool = False,
    disable_image_extraction: bool = False,
    paginate_output: bool = False,
    keep_pageheader_in_output: bool = False,
    html_tables_in_markdown: bool = False,
    disable_links: bool = False,
    strip_existing_ocr: bool = False,
    max_concurrency: int = 4,
    highres_image_dpi: int = 192,
) -> dict[str, Any]:
    data = {
        "force_ocr": str(force_ocr).lower(),
        "disable_image_extraction": str(disable_image_extraction).lower(),
        "paginate_output": str(paginate_output).lower(),
        "keep_pageheader_in_output": str(keep_pageheader_in_output).lower(),
        "html_tables_in_markdown": str(html_tables_in_markdown).lower(),
        "disable_links": str(disable_links).lower(),
        "strip_existing_ocr": str(strip_existing_ocr).lower(),
        "max_concurrency": str(max_concurrency),
        "highres_image_dpi": str(highres_image_dpi),
    }
    if page_range:
        data["page_range"] = page_range

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            f"{API_BASE_URL}/convert/async",
            headers=auth_headers(),
            data=data,
            files={"file": (filename, file_bytes, "application/octet-stream")},
        )
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def marker_health() -> dict[str, Any]:
    """Check whether the Marker API is healthy and marker_single is available."""
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"{API_BASE_URL}/health")
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def marker_convert_base64(
    filename: str,
    content_base64: str,
    page_range: str | None = None,
    force_ocr: bool = False,
    disable_image_extraction: bool = False,
    paginate_output: bool = False,
    keep_pageheader_in_output: bool = False,
    html_tables_in_markdown: bool = False,
    disable_links: bool = False,
    strip_existing_ocr: bool = False,
    max_concurrency: int = 4,
    highres_image_dpi: int = 192,
) -> dict[str, Any]:
    """Submit a document for async Marker conversion from base64-encoded file content."""
    file_bytes = base64.b64decode(content_base64)
    return await submit_file(
        filename=filename,
        file_bytes=file_bytes,
        page_range=page_range,
        force_ocr=force_ocr,
        disable_image_extraction=disable_image_extraction,
        paginate_output=paginate_output,
        keep_pageheader_in_output=keep_pageheader_in_output,
        html_tables_in_markdown=html_tables_in_markdown,
        disable_links=disable_links,
        strip_existing_ocr=strip_existing_ocr,
        max_concurrency=max_concurrency,
        highres_image_dpi=highres_image_dpi,
    )


@mcp.tool()
async def marker_convert_url(
    file_url: str,
    filename: str | None = None,
    page_range: str | None = None,
    force_ocr: bool = False,
    disable_image_extraction: bool = False,
    paginate_output: bool = False,
    keep_pageheader_in_output: bool = False,
    html_tables_in_markdown: bool = False,
    disable_links: bool = False,
    strip_existing_ocr: bool = False,
    max_concurrency: int = 4,
    highres_image_dpi: int = 192,
) -> dict[str, Any]:
    """Download a document from a URL and submit it for async Marker conversion."""
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        source = await client.get(file_url)
        source.raise_for_status()

    inferred_name = filename or file_url.rstrip("/").split("/")[-1] or "document.pdf"
    return await submit_file(
        filename=inferred_name,
        file_bytes=source.content,
        page_range=page_range,
        force_ocr=force_ocr,
        disable_image_extraction=disable_image_extraction,
        paginate_output=paginate_output,
        keep_pageheader_in_output=keep_pageheader_in_output,
        html_tables_in_markdown=html_tables_in_markdown,
        disable_links=disable_links,
        strip_existing_ocr=strip_existing_ocr,
        max_concurrency=max_concurrency,
        highres_image_dpi=highres_image_dpi,
    )


@mcp.tool()
async def marker_job_status(job_id: str) -> dict[str, Any]:
    """Return status, recent logs, and artifact metadata for a Marker conversion job."""
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{API_BASE_URL}/status/{job_id}",
            headers=auth_headers(),
        )
        response.raise_for_status()
        return compact_status(response.json())


@mcp.tool()
async def marker_list_files(job_id: str) -> dict[str, Any]:
    """List generated files for a completed or in-progress Marker conversion job."""
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{API_BASE_URL}/files/{job_id}",
            headers=auth_headers(),
        )
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def marker_download_markdown(job_id: str) -> str:
    """Download the generated markdown for a completed Marker conversion job."""
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{API_BASE_URL}/download/{job_id}",
            headers=auth_headers(),
        )
        response.raise_for_status()
        return response.text


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
