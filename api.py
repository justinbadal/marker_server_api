import os
import subprocess
import asyncio
import shutil
import tempfile
import uuid
import json
import re
from pathlib import Path, PurePosixPath
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
import paramiko

# Configuration
API_PORT = int(os.getenv("MARKER_API_PORT", "8336"))
MARKER_OUTPUT_DIR = os.getenv("MARKER_OUTPUT_DIR", r"C:\coding\marker_output")
API_BEARER_TOKEN = os.getenv("MARKER_API_TOKEN", "my-secret-token")  # Change token in production!
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://localhost:8020/v1")
SYNOLOGY_SSH_HOST = os.getenv("SYNOLOGY_SSH_HOST", "")
SYNOLOGY_SSH_PORT = int(os.getenv("SYNOLOGY_SSH_PORT", "22"))
SYNOLOGY_SSH_USER = os.getenv("SYNOLOGY_SSH_USER", "")
SYNOLOGY_SSH_KEY_PATH = os.getenv("SYNOLOGY_SSH_KEY_PATH", "")
SYNOLOGY_SSH_KEY_PASSPHRASE = os.getenv("SYNOLOGY_SSH_KEY_PASSPHRASE")
SYNOLOGY_SSH_REMOTE_BASE_PATH = os.getenv("SYNOLOGY_SSH_REMOTE_BASE_PATH", "/homes/justin/RAG/Marker")
SYNOLOGY_SSH_KNOWN_HOSTS_PATH = os.getenv("SYNOLOGY_SSH_KNOWN_HOSTS_PATH", "")


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


SYNOLOGY_SSH_AUTO_ADD_HOST_KEY = env_flag("SYNOLOGY_SSH_AUTO_ADD_HOST_KEY", False)

# Ensure the base output directory exists on startup
os.makedirs(MARKER_OUTPUT_DIR, exist_ok=True)

app = FastAPI(title="Marker PDF Conversion API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if credentials.credentials != API_BEARER_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")
    return credentials.credentials

@app.get("/health")
async def health_check():
    import shutil as _shutil
    marker_available = bool(_shutil.which("marker_single"))
    return {
        "status": "ok",
        "marker_available": marker_available,
        "output_dir": MARKER_OUTPUT_DIR,
        "llm_url": OPENAI_BASE_URL,
        "synology_ssh_enabled": synology_ssh_enabled(),
        "synology_ssh_host": SYNOLOGY_SSH_HOST,
        "synology_ssh_port": SYNOLOGY_SSH_PORT,
        "synology_ssh_remote_base_path": SYNOLOGY_SSH_REMOTE_BASE_PATH,
    }


def synology_ssh_enabled() -> bool:
    required = [SYNOLOGY_SSH_HOST, SYNOLOGY_SSH_USER, SYNOLOGY_SSH_KEY_PATH]
    return all(required)


def sanitize_folder_name(name: str) -> str:
    safe_name = re.sub(r'[<>:"/\\\\|?*]+', "_", name).strip().strip(".")
    return safe_name or "untitled"


def build_synology_target_dir(original_base_name: str) -> str:
    base = SYNOLOGY_SSH_REMOTE_BASE_PATH.rstrip("/")
    folder_name = sanitize_folder_name(original_base_name)
    return f"{base}/{folder_name}"


def append_job_log(log_file_path: str, message: str):
    print(message)
    with open(log_file_path, "a", encoding="utf-8") as log_file:
        log_file.write(f"{message}\n")


def collect_generated_files(job_dir: str) -> list[str]:
    internal_names = {"status.json", "output.log"}
    generated_files = []
    for path in sorted(Path(job_dir).rglob("*")):
        if not path.is_file():
            continue
        if path.name in internal_names:
            continue
        if path.suffix.lower() == ".pdf":
            continue
        generated_files.append(str(path))
    return generated_files


def create_ssh_client() -> paramiko.SSHClient:
    ssh = paramiko.SSHClient()
    if SYNOLOGY_SSH_KNOWN_HOSTS_PATH:
        ssh.load_host_keys(SYNOLOGY_SSH_KNOWN_HOSTS_PATH)
    else:
        ssh.load_system_host_keys()

    if SYNOLOGY_SSH_AUTO_ADD_HOST_KEY:
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    else:
        ssh.set_missing_host_key_policy(paramiko.RejectPolicy())

    ssh.connect(
        hostname=SYNOLOGY_SSH_HOST,
        port=SYNOLOGY_SSH_PORT,
        username=SYNOLOGY_SSH_USER,
        key_filename=SYNOLOGY_SSH_KEY_PATH,
        passphrase=SYNOLOGY_SSH_KEY_PASSPHRASE,
        look_for_keys=False,
        allow_agent=False,
        timeout=30,
    )
    return ssh


def ensure_remote_dir(sftp: paramiko.SFTPClient, remote_dir: str):
    current = PurePosixPath("/")
    for part in PurePosixPath(remote_dir).parts[1:]:
        current = current / part
        try:
            sftp.stat(current.as_posix())
        except FileNotFoundError:
            sftp.mkdir(current.as_posix())


def upload_generated_files_to_synology(job_dir: str, original_base_name: str, log_file_path: str) -> dict:
    if not synology_ssh_enabled():
        append_job_log(log_file_path, "[nas] Synology SSH upload skipped: integration is not fully configured.")
        return {"enabled": False, "status": "skipped", "uploaded_files": [], "target_dir": None}

    target_dir = build_synology_target_dir(original_base_name)
    generated_files = collect_generated_files(job_dir)
    if not generated_files:
        append_job_log(log_file_path, "[nas] No generated files found to upload.")
        return {"enabled": True, "status": "skipped", "uploaded_files": [], "target_dir": target_dir}

    uploaded_files = []
    ssh = None
    sftp = None
    try:
        append_job_log(log_file_path, f"[nas] Connecting to Synology over SSH at {SYNOLOGY_SSH_HOST}:{SYNOLOGY_SSH_PORT}")
        ssh = create_ssh_client()
        sftp = ssh.open_sftp()
        ensure_remote_dir(sftp, target_dir)
        append_job_log(log_file_path, f"[nas] Upload target: {target_dir}")

        for local_file_path in generated_files:
            relative_path = Path(local_file_path).relative_to(job_dir).as_posix()
            remote_file_path = PurePosixPath(target_dir) / PurePosixPath(relative_path)
            ensure_remote_dir(sftp, remote_file_path.parent.as_posix())
            append_job_log(log_file_path, f"[nas] Uploading {relative_path} -> {remote_file_path.as_posix()}")
            sftp.put(local_file_path, remote_file_path.as_posix())
            uploaded_files.append(relative_path)

        append_job_log(log_file_path, f"[nas] Uploaded {len(uploaded_files)} file(s) to Synology over SSH.")
        return {
            "enabled": True,
            "status": "uploaded",
            "uploaded_files": uploaded_files,
            "target_dir": target_dir,
        }
    except Exception as exc:
        append_job_log(log_file_path, f"[nas] Upload failed: {exc}")
        return {
            "enabled": True,
            "status": "failed",
            "error": str(exc),
            "uploaded_files": uploaded_files,
            "target_dir": target_dir,
        }
    finally:
        try:
            if sftp is not None:
                sftp.close()
        except Exception:
            pass
        try:
            if ssh is not None:
                ssh.close()
        except Exception:
            pass

def get_marker_cmd(pdf_path: str, output_dir: str, extras: dict = None):
    cmd = [
        "marker_single",
        pdf_path,
        "--output_dir", output_dir,
        "--output_format", "markdown",
        "--use_llm",
        "--llm_service", "marker.services.openai.OpenAIService",
        "--openai_model", "openai/gpt-oss-20b",
        "--openai_base_url", OPENAI_BASE_URL,
        "--openai_api_key", "SK-1234567890HERPDERP",
        "--openai_image_format", "png",
        "--layout_batch_size", "16",
        "--detection_batch_size", "16",
        "--recognition_batch_size", "16",
        "--equation_batch_size", "8",
        "--table_rec_batch_size", "8",
        "--max_concurrency", "4",
        "--redo_inline_math",
        "--keep_pagefooter_in_output"
    ]
    # Append any extra options from the UI
    if extras:
        if extras.get("page_range"): cmd += ["--page_range", extras["page_range"]]
        if extras.get("force_ocr"): cmd += ["--force_ocr"]
        if extras.get("disable_image_extraction"): cmd += ["--disable_image_extraction"]
        if extras.get("paginate_output"): cmd += ["--paginate_output"]
        if extras.get("keep_pageheader_in_output"): cmd += ["--keep_pageheader_in_output"]
        if extras.get("html_tables_in_markdown"): cmd += ["--html_tables_in_markdown"]
        if extras.get("disable_links"): cmd += ["--disable_links"]
        if extras.get("strip_existing_ocr"): cmd += ["--strip_existing_ocr"]
        if extras.get("max_concurrency"): cmd += ["--max_concurrency", str(extras["max_concurrency"])]
        if extras.get("highres_image_dpi"): cmd += ["--highres_image_dpi", str(extras["highres_image_dpi"])]
    return cmd

def get_run_env():
    run_env = os.environ.copy()
    run_env["TORCH_DEVICE"] = "cuda"
    run_env["CUDA_VISIBLE_DEVICES"] = "0"
    
    # AGGRESSIVE CACHE REDIRECTION
    # Point everything to our persistent /root/.cache/huggingface volume
    cache_base = "/root/.cache/huggingface"
    run_env["HF_HOME"] = cache_base
    run_env["HF_HUB_CACHE"] = os.path.join(cache_base, "hub")
    run_env["TRANSFORMERS_CACHE"] = os.path.join(cache_base, "hub")
    run_env["HF_HUB_DISABLE_SYMLINKS"] = "1"
    run_env["XDG_CACHE_HOME"] = "/root/.cache"
    run_env["TORCH_HOME"] = "/root/.cache/torch"
    run_env["SURYA_CACHE_DIR"] = os.path.join(cache_base, "surya")
    return run_env

def update_job_status(job_dir: str, status: str, error: str = None):
    status_file = os.path.join(job_dir, "status.json")
    data = {"status": status}
    if error:
        data["error"] = error
    with open(status_file, "w") as f:
        json.dump(data, f)


def write_job_metadata(job_dir: str, **fields):
    status_file = os.path.join(job_dir, "status.json")
    existing = {}
    if os.path.exists(status_file):
        with open(status_file, "r", encoding="utf-8") as f:
            existing = json.load(f)
    existing.update(fields)
    with open(status_file, "w", encoding="utf-8") as f:
        json.dump(existing, f)

def background_conversion(job_id: str, original_base_name: str, pdf_path: str, job_dir: str, extras: dict = None):
    cmd = get_marker_cmd(pdf_path, MARKER_OUTPUT_DIR, extras)
    env = get_run_env()
    log_file_path = os.path.join(job_dir, "output.log")
    
    try:
        update_job_status(job_dir, "processing")
        with open(log_file_path, "w") as log_file:
            process = subprocess.Popen(
                cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
            )
            for line in process.stdout:
                print(line, end="")  # pipe back to docker logs naturally
                log_file.write(line)
                log_file.flush()
            process.wait()
            
        if process.returncode != 0:
            update_job_status(job_dir, "failed", f"Process exited with code {process.returncode}")
        else:
            update_job_status(job_dir, "completed")
            nas_upload = upload_generated_files_to_synology(job_dir, original_base_name, log_file_path)
            write_job_metadata(job_dir, nas_upload=nas_upload)
            
    except Exception as e:
        update_job_status(job_dir, "failed", str(e))
        print(f"Job {job_id} failed: {e}")

# ---------------------------------------------------------
# OPTION 1: ASYNC POLLING (RECOMMENDED FOR LONG JOBS)
# ---------------------------------------------------------

@app.post("/convert/async")
async def convert_async(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    page_range: str = Form(None, description="e.g. 0,5-10,20"),
    force_ocr: bool = Form(False),
    disable_image_extraction: bool = Form(False),
    paginate_output: bool = Form(False),
    keep_pageheader_in_output: bool = Form(False),
    html_tables_in_markdown: bool = Form(False),
    disable_links: bool = Form(False),
    strip_existing_ocr: bool = Form(False),
    max_concurrency: int = Form(4),
    highres_image_dpi: int = Form(192),
    token: str = Depends(verify_token)
):
    extras = {
        "page_range": page_range,
        "force_ocr": force_ocr,
        "disable_image_extraction": disable_image_extraction,
        "paginate_output": paginate_output,
        "keep_pageheader_in_output": keep_pageheader_in_output,
        "html_tables_in_markdown": html_tables_in_markdown,
        "disable_links": disable_links,
        "strip_existing_ocr": strip_existing_ocr,
        "max_concurrency": max_concurrency,
        "highres_image_dpi": highres_image_dpi,
    }

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
        
    job_id = str(uuid.uuid4())[:8]
    original_base_name = os.path.splitext(file.filename)[0]
    unique_name = f"{original_base_name}_{job_id}"
    
    job_dir = os.path.join(MARKER_OUTPUT_DIR, unique_name)
    os.makedirs(job_dir, exist_ok=True)
    
    pdf_path = os.path.join(job_dir, f"{unique_name}.pdf")
    with open(pdf_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    update_job_status(job_dir, "pending")
    with open(os.path.join(job_dir, "output.log"), "w") as f:
        pass
        
    background_tasks.add_task(background_conversion, job_id, original_base_name, pdf_path, job_dir, extras)
    
    return {"job_id": unique_name, "status": "pending", "message": "Conversion started. Poll /status/{job_id}"}


@app.get("/status/{job_id}")
async def get_status(job_id: str, token: str = Depends(verify_token)):
    job_dir = os.path.join(MARKER_OUTPUT_DIR, job_id)
    status_file = os.path.join(job_dir, "status.json")
    
    if not os.path.exists(status_file):
        raise HTTPException(status_code=404, detail="Job not found.")
        
    with open(status_file, "r") as f:
        status_data = json.load(f)
        
    log_file = os.path.join(job_dir, "output.log")
    logs = []
    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            lines = f.readlines()
            logs = [line.strip() for line in lines[-50:] if line.strip()]  # return tail logs 
            
    status_data["logs"] = logs
    return status_data


@app.get("/download/{job_id}")
async def download_result(job_id: str, token: str = Depends(verify_token)):
    job_dir = os.path.join(MARKER_OUTPUT_DIR, job_id)
    status_file = os.path.join(job_dir, "status.json")
    
    if not os.path.exists(status_file):
        raise HTTPException(status_code=404, detail="Job not found.")
        
    with open(status_file, "r") as f:
        status_data = json.load(f)
        
    if status_data.get("status") != "completed":
        raise HTTPException(status_code=400, detail="Job is not completed yet.")
        
    md_file_path = None
    for file_name in os.listdir(job_dir):
        if file_name.endswith(".md"):
            md_file_path = os.path.join(job_dir, file_name)
            break
            
    if not md_file_path or not os.path.exists(md_file_path):
        raise HTTPException(status_code=500, detail="Generated markdown file not found.")
        
    return FileResponse(path=md_file_path, filename=os.path.basename(md_file_path), media_type="text/markdown")


@app.get("/files/{job_id}")
async def list_job_files(job_id: str, token: str = Depends(verify_token)):
    job_dir = os.path.join(MARKER_OUTPUT_DIR, job_id)
    if not os.path.exists(job_dir):
        raise HTTPException(status_code=404, detail="Job not found.")
    files = []
    for fname in sorted(os.listdir(job_dir)):
        # Skip internal tracking files
        if fname in ("status.json", "output.log"):
            continue
        fpath = os.path.join(job_dir, fname)
        fsize = os.path.getsize(fpath) if os.path.isfile(fpath) else 0
        files.append({"name": fname, "size": fsize})
    return {"job_id": job_id, "files": files}


# ---------------------------------------------------------
# OPTION 2: REAL-TIME SSE STREAMING (SERVER SENT EVENTS)
# ---------------------------------------------------------

@app.post("/convert/stream")
async def convert_stream(
    file: UploadFile = File(...),
    token: str = Depends(verify_token)
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
        
    job_id = str(uuid.uuid4())[:8]
    original_base_name = os.path.splitext(file.filename)[0]
    unique_name = f"{original_base_name}_{job_id}"
    
    temp_dir = tempfile.mkdtemp(prefix="marker_api_stream_")
    temp_pdf_path = os.path.join(temp_dir, f"{unique_name}.pdf")
    
    with open(temp_pdf_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    cmd = get_marker_cmd(temp_pdf_path, MARKER_OUTPUT_DIR)
    env = get_run_env()

    async def event_generator():
        yield f"data: {json.dumps({'status': 'starting', 'job_id': unique_name})}\n\n"
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env
        )
        
        while True:
            line = await process.stdout.readline()
            if not line:
                break
                
            log_str = line.decode().strip()
            print(log_str) # To docker logs too
            if log_str:
                yield f"data: {json.dumps({'log': log_str})}\n\n"
            
        await process.wait()
        
        if process.returncode != 0:
            yield f"data: {json.dumps({'status': 'failed', 'error': 'Background process failed'})}\n\n"
        else:
            hit_output_dir = os.path.join(MARKER_OUTPUT_DIR, unique_name)
            md_file_path = None
            nas_upload = None
            if os.path.exists(hit_output_dir):
                log_file_path = os.path.join(hit_output_dir, "output.log")
                with open(log_file_path, "a", encoding="utf-8"):
                    pass
                nas_upload = upload_generated_files_to_synology(hit_output_dir, original_base_name, log_file_path)
                for file_name in os.listdir(hit_output_dir):
                    if file_name.endswith(".md"):
                        md_file_path = os.path.join(hit_output_dir, file_name)
                        break
                        
            if md_file_path and os.path.exists(md_file_path):
                with open(md_file_path, "r", encoding="utf-8") as rf:
                    content = rf.read()
                yield f"data: {json.dumps({'status': 'completed', 'markdown': content, 'nas_upload': nas_upload})}\n\n"
            else:
                yield f"data: {json.dumps({'status': 'failed', 'error': 'Markdown file missing'})}\n\n"
                
        shutil.rmtree(temp_dir, ignore_errors=True)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ---------------------------------------------------------
# BACKWARD COMPATIBILITY: ORIGINAL SYNCHRONOUS ROUTE
# ---------------------------------------------------------

@app.post("/convert")
async def convert_pdf(
    file: UploadFile = File(...),
    token: str = Depends(verify_token)
):
    # Backward compatible synchronous run
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
        
    hit_id = str(uuid.uuid4())[:8]
    original_base_name = os.path.splitext(file.filename)[0]
    unique_name = f"{original_base_name}_{hit_id}"
    
    temp_dir = tempfile.mkdtemp(prefix="marker_api_in_")
    temp_pdf_path = os.path.join(temp_dir, f"{unique_name}.pdf")
    
    try:
        with open(temp_pdf_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        cmd = get_marker_cmd(temp_pdf_path, MARKER_OUTPUT_DIR)
        result = subprocess.run(cmd, env=get_run_env())
        
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail="Conversion failed. Check docker logs.")
            
        hit_output_dir = os.path.join(MARKER_OUTPUT_DIR, unique_name)
        log_file_path = os.path.join(hit_output_dir, "output.log")
        if os.path.exists(hit_output_dir):
            with open(log_file_path, "a", encoding="utf-8"):
                pass
            upload_generated_files_to_synology(hit_output_dir, original_base_name, log_file_path)
        
        md_file_path = None
        if os.path.exists(hit_output_dir):
            for file_name in os.listdir(hit_output_dir):
                if file_name.endswith(".md"):
                    md_file_path = os.path.join(hit_output_dir, file_name)
                    break
                    
        if not md_file_path or not os.path.exists(md_file_path):
            raise HTTPException(status_code=500, detail="Generated markdown file not found.")
            
        return FileResponse(path=md_file_path, filename=f"{original_base_name}.md", media_type="text/markdown")
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=API_PORT, reload=True)
