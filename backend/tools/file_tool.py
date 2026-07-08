"""
tools/file_tool.py — Safe file read/write tool.

Agents can read and write files, but we must NEVER let an agent access
arbitrary paths on the filesystem — that's a security hole.

Path validation strategy:
- All agent file operations are sandboxed to ./agent_workspace/
- Any path that tries to escape (../../../etc/passwd) is rejected
- Max file size on read: 50KB (prevents context flooding)
- Max file size on write: 100KB
"""

from __future__ import annotations

import json
from pathlib import Path

import structlog
from langchain_core.tools import tool

logger = structlog.get_logger(__name__)

# All agent file operations happen inside this directory
WORKSPACE_DIR = Path("./agent_workspace").resolve()
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

MAX_READ_BYTES  = 50_000   # 50KB — larger files would flood the context window
MAX_WRITE_BYTES = 100_000  # 100KB


def _safe_path(filename: str) -> Path | None:
    """
    Resolve a filename to an absolute path inside WORKSPACE_DIR.
    Returns None if the path tries to escape the sandbox.
    
    HOW PATH TRAVERSAL ATTACKS WORK:
        filename = "../../etc/passwd"
        Path(WORKSPACE_DIR / filename).resolve() → /etc/passwd
        That's outside WORKSPACE_DIR → we reject it.
    
    The .resolve() call collapses all ".." components first,
    then we check if the result is still inside WORKSPACE_DIR.
    """
    # Strip any leading slashes — don't allow absolute paths
    clean = filename.lstrip("/").lstrip("\\")
    candidate = (WORKSPACE_DIR / clean).resolve()

    # is_relative_to() checks if candidate is inside WORKSPACE_DIR
    if not candidate.is_relative_to(WORKSPACE_DIR):
        return None  # Path traversal attempt detected

    return candidate


@tool
def read_file(filename: str) -> str:
    """
    Read a file from the agent workspace directory.
    
    Use this tool when you need to read content from a file that was
    previously written in this session or provided as input context.
    
    The workspace is sandboxed — you can only read files inside agent_workspace/.
    Do NOT use absolute paths or path traversal (../). Just use the filename
    or a relative path like 'reports/summary.txt'.
    
    Returns file content as a string, or a JSON error object on failure.
    
    Args:
        filename: Relative path to the file within the workspace directory.
    """
    try:
        safe = _safe_path(filename)

        if safe is None:
            return json.dumps({
                "status": "error",
                "error_type": "security",
                "message": f"Access denied: '{filename}' is outside the allowed workspace."
            })

        if not safe.exists():
            return json.dumps({
                "status": "error",
                "error_type": "not_found",
                "message": f"File '{filename}' does not exist in workspace."
            })

        if safe.stat().st_size > MAX_READ_BYTES:
            return json.dumps({
                "status": "error",
                "error_type": "too_large",
                "message": f"File '{filename}' is too large to read ({safe.stat().st_size} bytes). Max is {MAX_READ_BYTES}."
            })

        content = safe.read_text(encoding="utf-8")
        logger.info("read_file success", filename=filename, size=len(content))

        return json.dumps({
            "status": "success",
            "filename": filename,
            "content": content,
            "size_bytes": len(content.encode("utf-8")),
        })

    except UnicodeDecodeError:
        return json.dumps({
            "status": "error",
            "error_type": "encoding",
            "message": f"File '{filename}' is not valid UTF-8 text (may be binary)."
        })
    except Exception as e:
        logger.error("read_file failed", filename=filename, error=str(e))
        return json.dumps({
            "status": "error",
            "error_type": "read_failed",
            "message": str(e)
        })


@tool
def write_file(filename: str, content: str, append: bool = False) -> str:
    """
    Write content to a file in the agent workspace directory.
    
    Use this tool to save research findings, summaries, or reports
    so they can be retrieved later or included in the final output.
    
    The workspace is sandboxed — you can only write inside agent_workspace/.
    Creates parent directories automatically if they don't exist.
    
    Returns a success confirmation or JSON error object.
    
    Args:
        filename: Relative path for the file (e.g. 'reports/summary.md').
        content: Text content to write to the file.
        append: If True, append to existing file. If False (default), overwrite.
    """
    try:
        if len(content.encode("utf-8")) > MAX_WRITE_BYTES:
            return json.dumps({
                "status": "error",
                "error_type": "too_large",
                "message": f"Content too large ({len(content)} chars). Max is {MAX_WRITE_BYTES} bytes."
            })

        safe = _safe_path(filename)

        if safe is None:
            return json.dumps({
                "status": "error",
                "error_type": "security",
                "message": f"Access denied: '{filename}' is outside the allowed workspace."
            })

        # Create parent directories if needed (e.g. 'reports/' in 'reports/summary.md')
        safe.parent.mkdir(parents=True, exist_ok=True)

        mode = "a" if append else "w"
        safe.write_text(content, encoding="utf-8") if not append else \
            safe.open("a", encoding="utf-8").write(content)

        logger.info("write_file success", filename=filename, size=len(content), append=append)

        return json.dumps({
            "status": "success",
            "message": f"Successfully {'appended to' if append else 'wrote'} '{filename}'",
            "filename": filename,
            "size_bytes": len(content.encode("utf-8")),
        })

    except Exception as e:
        logger.error("write_file failed", filename=filename, error=str(e))
        return json.dumps({
            "status": "error",
            "error_type": "write_failed",
            "message": str(e)
        })

