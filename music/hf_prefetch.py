from __future__ import annotations
import json, os, sys, time
from pathlib import Path
from huggingface_hub import hf_hub_download

CACHE = Path(sys.argv[1]).resolve()
DURATION = int(sys.argv[2])
CACHE.mkdir(parents=True, exist_ok=True)

# Expected sizes are only UI hints; real transferred bytes are measured from cache growth.
GB = 1024**3
MB = 1024**2
stages = [
    ("CFM", "ASLP-lab/DiffRhythm-1_2" if DURATION == 95 else "ASLP-lab/DiffRhythm-1_2-full", [("cfm_model.pt", 2.22*GB)]),
    ("MUQ_MULAN", "OpenMuQ/MuQ-MuLan-large", [("config.json", 847), ("pytorch_model.bin", 2.65*GB)]),
    ("MUQ_AUDIO", "OpenMuQ/MuQ-large-msd-iter", [("config.json", 4096), ("model.safetensors", 1.25*GB)]),
    ("XLM", "FacebookAI/xlm-roberta-base", [("config.json", 4096), ("model.safetensors", 1.12*GB), ("sentencepiece.bpe.model", 5.1*MB), ("tokenizer.json", 9.2*MB), ("tokenizer_config.json", 4096)]),
    ("VAE", "ASLP-lab/DiffRhythm-vae", [("vae_model.pt", 1.0*GB)]),
]

def emit(obj):
    print("SCSTATUS " + json.dumps(obj, ensure_ascii=False), flush=True)

for name, repo, files in stages:
    expected = int(sum(x[1] for x in files))
    emit({"event":"stage","name":name,"repo":repo,"expected_bytes":expected})
    for filename, _ in files:
        emit({"event":"file","name":name,"repo":repo,"file":filename})
        hf_hub_download(repo_id=repo, filename=filename, cache_dir=str(CACHE), resume_download=True)
    emit({"event":"done","name":name,"repo":repo,"expected_bytes":expected})
emit({"event":"all_done"})
