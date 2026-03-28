import os
import subprocess
import asyncio
import shutil
import tempfile
import uuid
import json
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware

# Configuration
API_PORT = int(os.getenv("MARKER_API_PORT", "8335"))
MARKER_OUTPUT_DIR = os.getenv("MARKER_OUTPUT_DIR", r"C:\coding\marker_output")
API_BEARER_TOKEN = os.getenv("MARKER_API_TOKEN", "my-secret-token")  # Change token in production!
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://localhost:8020/v1")

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

def get_marker_cmd(pdf_path: str, output_dir: str):
    return [
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
        "--keep_pagefooter_in_output",
        "--debug"
    ]

def get_run_env():
    run_env = os.environ.copy()
    run_env["TORCH_DEVICE"] = "cuda"
    run_env["CUDA_VISIBLE_DEVICES"] = "0"
    return run_env

def update_job_status(job_dir: str, status: str, error: str = None):
    status_file = os.path.join(job_dir, "status.json")
    data = {"status": status}
    if error:
        data["error"] = error
    with open(status_file, "w") as f:
        json.dump(data, f)

def background_conversion(job_id: str, original_base_name: str, pdf_path: str, job_dir: str):
    cmd = get_marker_cmd(pdf_path, MARKER_OUTPUT_DIR)
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
    token: str = Depends(verify_token)
):
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
        
    background_tasks.add_task(background_conversion, job_id, original_base_name, pdf_path, job_dir)
    
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
            if os.path.exists(hit_output_dir):
                for file_name in os.listdir(hit_output_dir):
                    if file_name.endswith(".md"):
                        md_file_path = os.path.join(hit_output_dir, file_name)
                        break
                        
            if md_file_path and os.path.exists(md_file_path):
                with open(md_file_path, "r", encoding="utf-8") as rf:
                    content = rf.read()
                yield f"data: {json.dumps({'status': 'completed', 'markdown': content})}\n\n"
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
