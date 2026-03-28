import os
import subprocess
import shutil
import tempfile
import uuid
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Configuration (These can be controlled via Environment Variables)
API_PORT = int(os.getenv("MARKER_API_PORT", "8335"))
MARKER_OUTPUT_DIR = os.getenv("MARKER_OUTPUT_DIR", r"C:\coding\marker_output")
API_BEARER_TOKEN = os.getenv("MARKER_API_TOKEN", "my-secret-token")  # Change token in production!
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://localhost:8020/v1")

# Ensure the base output directory exists on startup
os.makedirs(MARKER_OUTPUT_DIR, exist_ok=True)

app = FastAPI(title="Marker PDF Conversion API")
security = HTTPBearer()

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if credentials.credentials != API_BEARER_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")
    return credentials.credentials

@app.post("/convert")
async def convert_pdf(
    file: UploadFile = File(...),
    token: str = Depends(verify_token)
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
        
    # Generate a unique name for this API hit
    hit_id = str(uuid.uuid4())[:8]
    original_base_name = os.path.splitext(file.filename)[0]
    unique_name = f"{original_base_name}_{hit_id}"
    
    # We will save the input PDF temporarily with this unique name
    # so that marker_single inherently creates an isolated output folder named exactly this
    temp_dir = tempfile.mkdtemp(prefix="marker_api_in_")
    temp_pdf_path = os.path.join(temp_dir, f"{unique_name}.pdf")
    
    try:
        # Save the uploaded file
        with open(temp_pdf_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # Build the exact command mimicking marker-pdf.bat
        cmd = [
            "marker_single",
            temp_pdf_path,
            "--output_dir", MARKER_OUTPUT_DIR,
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
        
        # Maintain your GPU environment variables
        run_env = os.environ.copy()
        run_env["TORCH_DEVICE"] = "cuda"
        run_env["CUDA_VISIBLE_DEVICES"] = "0"
        
        # Execute the marker system and let its logs dump dynamically directly to the Docker terminal
        result = subprocess.run(cmd, env=run_env)
        
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail="Conversion failed. Please check the marker-api docker logs for the raw stack trace.")
            
        # Marker_single creates the output directory based on the unique filename
        # example: C:\coding\marker_output\<unique_name>
        hit_output_dir = os.path.join(MARKER_OUTPUT_DIR, unique_name)
        
        if not os.path.exists(hit_output_dir):
            # Fallback in case marker dumps directly to output dir
            hit_output_dir = MARKER_OUTPUT_DIR
            
        # Find the generated .md file
        md_file_path = None
        for file_name in os.listdir(hit_output_dir):
            if file_name.endswith(".md"):
                md_file_path = os.path.join(hit_output_dir, file_name)
                break
                
        if not md_file_path or not os.path.exists(md_file_path):
            raise HTTPException(status_code=500, detail="Failed to find the generated markdown file.")
            
        # Return JUST the markdown file to the caller
        return FileResponse(
            path=md_file_path,
            filename=f"{original_base_name}.md",
            media_type="text/markdown"
        )
        
    finally:
        # Clean up ONLY the temporary input file. 
        # Output artifacts remain at C:\coding\marker_output\<unique_name>
        shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=API_PORT, reload=True)
