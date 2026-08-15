"""Marker PDF 2.x runner used by the HTTP wrapper.

Marker 2.0.0's stock marker_single command does not expose every option
advertised in its README, including use_llm.  The wrapper therefore calls the
Python API directly so the configured OpenAI-compatible service is passed
explicitly and configuration is version-stable.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Keep these quiet before importing Marker/Surya.
os.environ.setdefault("GRPC_VERBOSITY", "ERROR")
os.environ.setdefault("GLOG_minloglevel", "2")
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from marker.converters.pdf import PdfConverter
from marker.logger import configure_logging, get_logger
from marker.models import create_model_dict
from marker.output import save_output
from marker.util import parse_range_str


LOGGER = get_logger()


def load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as handle:
        config = json.load(handle)
    page_range = config.get("page_range")
    if isinstance(page_range, str) and page_range.strip():
        config["page_range"] = parse_range_str(page_range)
    return config


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: marker_runner.py INPUT_PATH OUTPUT_DIR CONFIG_PATH", file=sys.stderr)
        return 2

    input_path, output_dir, config_path = sys.argv[1:]
    config = load_config(config_path)
    config["use_llm"] = True
    config.setdefault("mode", "balanced")

    started = time.time()
    print(f"[marker] marker-pdf 2.0.0; mode={config['mode']}; input={Path(input_path).name}", flush=True)
    models = create_model_dict()
    converter = PdfConverter(
        config=config,
        artifact_dict=models,
        renderer="marker.renderers.markdown.MarkdownRenderer",
        llm_service="marker.services.openai.OpenAIService",
    )
    rendered = converter(input_path)

    input_path_obj = Path(input_path)
    output_path = Path(output_dir) / input_path_obj.stem
    output_path.mkdir(parents=True, exist_ok=True)
    save_output(rendered, str(output_path), input_path_obj.stem)
    print(f"[marker] saved output to {output_path}; elapsed={time.time() - started:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    configure_logging()
    try:
        raise SystemExit(main())
    except Exception:
        LOGGER.exception("Marker conversion failed")
        raise
