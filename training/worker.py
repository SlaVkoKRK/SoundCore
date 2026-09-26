from __future__ import annotations

import csv
import json
import os
import sys
import traceback
import threading
from datetime import datetime
from pathlib import Path


_status_lock = threading.Lock()
_status_cache = {}

def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")

def write_status(path: str, **payload) -> None:
    global _status_cache
    with _status_lock:
        merged = dict(_status_cache)
        merged.update(payload)
        merged["last_activity"] = datetime.now().isoformat(timespec="seconds")
        _status_cache = merged
        tmp = Path(path + ".tmp")
        tmp.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

def append_event(path: str, message: str, level: str = "info", **extra) -> None:
    events = list(_status_cache.get("events", []))[-199:]
    item = {"time": _now(), "message": str(message), "level": level}
    item.update(extra)
    events.append(item)
    write_status(path, events=events, **extra)

def _scalar(v):
    try:
        if hasattr(v, "detach"):
            return float(v.detach().cpu().item())
        return float(v)
    except Exception:
        return None


def main(job_path: str) -> None:
    job = json.loads(Path(job_path).read_text(encoding="utf-8"))
    status_path = job["status_path"]
    profile_folder = Path(job["profile_folder"])
    dataset_dir = profile_folder / "dataset"
    metadata = dataset_dir / "metadata.csv"
    reference = profile_folder / "reference.wav"
    out_path = profile_folder / "model" / "xtts_gpt"
    out_path.mkdir(parents=True, exist_ok=True)
    log_path = Path(job.get("log_path") or (profile_folder / "training.log"))
    write_status(status_path, events=[], loss_history=[], log_path=str(log_path), step=0, epoch=0, loss=None, learning_rate=None)
    append_event(status_path, "Worker treningowy uruchomiony.")

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
    append_event(status_path, f"Dataset gotowy: {sample_count} próbek; eval split {eval_split_size:.3f}.")

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
    append_event(status_path, f"Urządzenie treningu: {actual_device.upper()}.")

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
        append_event(status_path, "Pobieranie brakujących plików bazowego XTTS v2…")
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
    append_event(status_path, f"Start GPTTrainer: {len(train_samples)} train / {len(eval_samples)} eval, {epochs} epok, batch {batch}.")
    def on_train_epoch_start(trainer):
        ep = int(getattr(trainer, "epochs_done", 0)) + 1
        write_status(status_path, epoch=ep, epochs=epochs, message=f"Epoka {ep}/{epochs} — trening…")
        append_event(status_path, f"Rozpoczęto epokę {ep}/{epochs}.", epoch=ep)

    def on_train_step_end(trainer):
        step = int(getattr(trainer, "total_steps_done", 0))
        ep0 = int(getattr(trainer, "epochs_done", 0))
        ep = ep0 + 1
        avg = getattr(getattr(trainer, "keep_avg_train", None), "avg_values", {}) or {}
        loss = _scalar(avg.get("avg_loss"))
        if loss is None:
            candidates = [_scalar(v) for k, v in avg.items() if "loss" in str(k).lower()]
            candidates = [v for v in candidates if v is not None]
            loss = candidates[0] if candidates else None
        lr = None
        try:
            opt = trainer.optimizer
            if isinstance(opt, list): opt = opt[0]
            if isinstance(opt, dict): opt = next(iter(opt.values()))
            lr = float(opt.param_groups[0].get("lr", 0.0))
        except Exception:
            pass
        try:
            steps_per_epoch = max(1, len(trainer.train_loader))
            step_in_epoch = step % steps_per_epoch
            frac = min(1.0, max(0.0, (ep0 + step_in_epoch / steps_per_epoch) / max(1, epochs)))
        except Exception:
            frac = min(1.0, max(0.0, ep0 / max(1, epochs)))
        progress = round(12 + 85 * frac, 1)
        hist = list(_status_cache.get("loss_history", []))
        if loss is not None:
            hist.append({"step": step, "epoch": ep, "loss": round(loss, 6)})
            hist = hist[-300:]
        write_status(status_path, state="training", progress=progress, step=step, epoch=ep, epochs=epochs, loss=loss, learning_rate=lr, loss_history=hist, message=f"Epoka {ep}/{epochs} · krok {step}" + (f" · loss {loss:.5f}" if loss is not None else ""))
        if step <= 3 or step % 10 == 0:
            append_event(status_path, f"Epoka {ep}/{epochs}, krok {step}" + (f", loss={loss:.6f}" if loss is not None else "") + (f", lr={lr:.2e}" if lr is not None else ""), step=step, epoch=ep, loss=loss, learning_rate=lr)

    def on_train_epoch_end(trainer):
        ep = int(getattr(trainer, "epochs_done", 0)) + 1
        avg = getattr(getattr(trainer, "keep_avg_train", None), "avg_values", {}) or {}
        loss = _scalar(avg.get("avg_loss"))
        append_event(status_path, f"Zakończono epokę {ep}/{epochs}" + (f"; średni loss={loss:.6f}." if loss is not None else "."), epoch=ep, loss=loss)

    callbacks = {
        "on_train_epoch_start": on_train_epoch_start,
        "on_train_step_end": on_train_step_end,
        "on_train_epoch_end": on_train_epoch_end,
    }
    trainer = Trainer(
        TrainerArgs(restore_path=None, skip_train_epoch=False, start_with_eval=False, grad_accum_steps=grad_accum),
        config,
        output_path=str(out_path),
        model=model,
        train_samples=train_samples,
        eval_samples=eval_samples,
        callbacks=callbacks,
    )
    # Coqui additionally writes its native trainer log into the run directory.
    trainer.fit()
    run_path = Path(getattr(trainer, "output_path", out_path))
    best = run_path / "best_model.pth"
    if not best.exists():
        ckpts = sorted(run_path.glob("checkpoint_*.pth"), key=lambda x: x.stat().st_mtime)
        best = ckpts[-1] if ckpts else best
    cfg = run_path / "config.json"
    vocab = checkpoints / "vocab.json"
    trained_model = None
    if best.exists() and cfg.exists() and vocab.exists():
        trained_model = {"checkpoint_path":str(best),"config_path":str(cfg),"vocab_path":str(vocab),"checkpoint_name":best.name}
    append_event(status_path, "Trening zakończony. Checkpoint zapisany.", level="success")
    write_status(status_path, state="completed", progress=100, device=actual_device, message="Trening zakończony. Model jest gotowy do podpięcia pod profil.", output_path=str(run_path), trained_model=trained_model)


if __name__ == "__main__":
    try:
        main(sys.argv[1])
    except Exception as exc:
        try:
            job = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
            append_event(job["status_path"], f"BŁĄD: {exc}", level="error")
            write_status(job["status_path"], state="error", progress=0, message=str(exc), traceback=traceback.format_exc())
        finally:
            raise
