from __future__ import annotations

import json
import sys
from pathlib import Path


def main(job_path: str) -> None:
    job = json.loads(Path(job_path).read_text(encoding="utf-8"))
    import torch
    import soundfile as sf
    from qwen_tts import Qwen3TTSModel

    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if torch.cuda.is_available() else torch.float32
    model = Qwen3TTSModel.from_pretrained(
        job.get("model", "Qwen/Qwen3-TTS-12Hz-0.6B-Base"),
        device_map=device,
        dtype=dtype,
        attn_implementation="sdpa",
    )
    wavs, sr = model.generate_voice_clone(
        text=job["text"],
        language=job.get("language", "Auto"),
        ref_audio=job["ref_audio"],
        ref_text=None,
        x_vector_only_mode=True,
        non_streaming_mode=True,
    )
    Path(job["output"]).parent.mkdir(parents=True, exist_ok=True)
    sf.write(job["output"], wavs[0], sr)


if __name__ == "__main__":
    main(sys.argv[1])
