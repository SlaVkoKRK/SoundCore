from __future__ import annotations

import csv
import json
import os
import sys
import traceback
from pathlib import Path


def write_status(path: str, **payload) -> None:
    tmp = Path(path + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def main(job_path: str) -> None:
    job = json.loads(Path(job_path).read_text(encoding="utf-8"))
    status_path = job["status_path"]
    profile_folder = Path(job["profile_folder"])
    dataset_dir = profile_folder / "dataset"
    metadata = dataset_dir / "metadata.csv"
    reference = profile_folder / "reference.wav"
    out_path = profile_folder / "model" / "xtts_gpt"
    out_path.mkdir(parents=True, exist_ok=True)

    if not metadata.exists():
        raise RuntimeError("Brak dataset/metadata.csv. Dodaj próbki treningowe.")

    with metadata.open("r", encoding="utf-8", newline="") as f:
        dataset_rows = [row for row in csv.reader(f, delimiter="|") if row and row[0].strip()]
    sample_count = len(dataset_rows)
    if sample_count < 3:
        raise RuntimeError(f"Do treningu potrzebne są co najmniej 3 próbki. Aktualnie: {sample_count}.")
    # Coqui rejects its tiny default eval split on very small datasets.
    # Keep exactly one validation sample for datasets below 10 samples, then 10%.
    eval_split_size = (1.0 / sample_count) if sample_count < 10 else 0.10

    write_status(status_path, state="preparing", progress=2, message=f"Przygotowanie XTTS GPTTrainer… Dataset: {sample_count} próbek.")

    import torch
    from trainer import Trainer, TrainerArgs
    from TTS.config.shared_configs import BaseDatasetConfig
    from TTS.tts.datasets import load_tts_samples
    from TTS.tts.layers.xtts.trainer.gpt_trainer import GPTArgs, GPTTrainer, GPTTrainerConfig, XttsAudioConfig
    from TTS.utils.manage import ModelManager

    requested = job.get("device", "auto").lower()
    if requested == "gpu" and not torch.cuda.is_available():
        raise RuntimeError("Wybrano GPU, ale torch.cuda.is_available() == False. Zainstaluj PyTorch z CUDA.")
    use_cuda = torch.cuda.is_available() and requested != "cpu"
    actual_device = "cuda" if use_cuda else "cpu"
    write_status(status_path, state="preparing", progress=5, device=actual_device, message=f"Urządzenie treningu: {actual_device.upper()}")

    checkpoints = out_path / "XTTS_v2_original_model_files"
    checkpoints.mkdir(parents=True, exist_ok=True)
    links = {
        "dvae.pth": "https://coqui.gateway.scarf.sh/hf-coqui/XTTS-v2/main/dvae.pth",
        "mel_stats.pth": "https://coqui.gateway.scarf.sh/hf-coqui/XTTS-v2/main/mel_stats.pth",
        "vocab.json": "https://coqui.gateway.scarf.sh/hf-coqui/XTTS-v2/main/vocab.json",
        "model.pth": "https://coqui.gateway.scarf.sh/hf-coqui/XTTS-v2/main/model.pth",
    }
    missing = [url for name, url in links.items() if not (checkpoints / name).exists()]
    if missing:
        write_status(status_path, state="downloading", progress=8, device=actual_device, message="Pobieranie plików bazowego XTTS v2…")
        ModelManager._download_model_files(missing, str(checkpoints), progress_bar=True)

    dataset_config = BaseDatasetConfig(
        formatter="ljspeech",
        dataset_name=job["profile_name"],
        path=str(dataset_dir),
        meta_file_train=str(metadata),
        language=job.get("language", "pl"),
    )
    model_args = GPTArgs(
        max_conditioning_length=132300,
        min_conditioning_length=66150,
        debug_loading_failures=False,
        max_wav_length=255995,
        max_text_length=200,
        mel_norm_file=str(checkpoints / "mel_stats.pth"),
        dvae_checkpoint=str(checkpoints / "dvae.pth"),
        xtts_checkpoint=str(checkpoints / "model.pth"),
        tokenizer_file=str(checkpoints / "vocab.json"),
        gpt_num_audio_tokens=1026,
        gpt_start_audio_token=1024,
        gpt_stop_audio_token=1025,
        gpt_use_masking_gt_prompt_approach=True,
        gpt_use_perceiver_resampler=True,
    )
    audio_config = XttsAudioConfig(sample_rate=22050, dvae_sample_rate=22050, output_sample_rate=24000)
    batch = max(1, int(job.get("batch_size", 2)))
    epochs = max(1, int(job.get("epochs", 10)))
    grad_accum = max(1, 252 // batch) if use_cuda else 1
    config = GPTTrainerConfig(
        epochs=epochs,
        output_path=str(out_path),
        model_args=model_args,
        run_name=f"SoundCore_{job['profile_name']}",
        project_name="SoundCore_XTTS",
        run_description="SoundCore XTTS v2 GPT fine-tuning",
        dashboard_logger="tensorboard",
        logger_uri=None,
        audio=audio_config,
        batch_size=batch,
        batch_group_size=48 if use_cuda else 0,
        eval_batch_size=1 if not use_cuda else batch,
        num_loader_workers=0 if os.name == "nt" else 2,
        eval_split_max_size=64,
        eval_split_size=eval_split_size,
        print_step=10,
        plot_step=100,
        log_model_step=500,
        save_step=1000,
        save_n_checkpoints=2,
        save_checkpoints=True,
        print_eval=False,
        optimizer="AdamW",
        optimizer_wd_only_on_weights=True,
        optimizer_params={"betas": [0.9, 0.96], "eps": 1e-8, "weight_decay": 1e-2},
        lr=5e-06,
        lr_scheduler="MultiStepLR",
        lr_scheduler_params={"milestones": [50000 * 18, 150000 * 18, 300000 * 18], "gamma": 0.5, "last_epoch": -1},
        test_sentences=[{
            "text": "Witaj, to jest test wytrenowanego modelu SoundCore.",
            "speaker_wav": [str(reference)],
            "language": job.get("language", "pl"),
        }],
    )
    model = GPTTrainer.init_from_config(config)
    train_samples, eval_samples = load_tts_samples(
        [dataset_config],
        eval_split=True,
        eval_split_max_size=config.eval_split_max_size,
        eval_split_size=config.eval_split_size,
    )
    write_status(status_path, state="training", progress=12, device=actual_device, message=f"Start treningu: {len(train_samples)} próbek treningowych, {len(eval_samples)} walidacyjnych.")
    trainer = Trainer(
        TrainerArgs(restore_path=None, skip_train_epoch=False, start_with_eval=True, grad_accum_steps=grad_accum),
        config,
        output_path=str(out_path),
        model=model,
        train_samples=train_samples,
        eval_samples=eval_samples,
    )
    trainer.fit()
    write_status(status_path, state="completed", progress=100, device=actual_device, message="Trening zakończony. Checkpoint zapisano w profilu.", output_path=str(out_path))


if __name__ == "__main__":
    try:
        main(sys.argv[1])
    except Exception as exc:
        try:
            job = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
            write_status(job["status_path"], state="error", progress=0, message=str(exc), traceback=traceback.format_exc())
        finally:
            raise
