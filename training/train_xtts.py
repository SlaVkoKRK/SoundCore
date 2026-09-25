from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def parse_args():
    p = argparse.ArgumentParser(description="SoundCore XTTS-v2 GPT fine-tuning")
    p.add_argument("--profile", required=True)
    p.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    p.add_argument("--epochs", type=int, default=20)
    p.add_argument("--batch-size", type=int, default=0, help="0=auto")
    p.add_argument("--grad-accum", type=int, default=0, help="0=auto")
    p.add_argument("--max-audio-seconds", type=float, default=12.0)
    return p.parse_args()


def main():
    args = parse_args()
    if args.device == "cpu":
        # Must happen before importing torch/Trainer.
        os.environ["CUDA_VISIBLE_DEVICES"] = ""

    import torch
    if args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("Wybrano GPU, ale PyTorch nie widzi CUDA. Zainstaluj build PyTorch z CUDA.")

    from trainer import Trainer, TrainerArgs
    from TTS.config.shared_configs import BaseDatasetConfig
    from TTS.tts.datasets import load_tts_samples
    from TTS.tts.layers.xtts.trainer.gpt_trainer import GPTArgs, GPTTrainer, GPTTrainerConfig, XttsAudioConfig
    from TTS.utils.manage import ModelManager

    from training.dataset import build_ljspeech_metadata, dataset_dir

    profile = Path(args.profile).resolve()
    if not profile.is_dir():
        raise FileNotFoundError(profile)
    ref = profile / "reference.wav"
    if not ref.is_file():
        raise FileNotFoundError(f"Brak reference.wav: {ref}")

    train_meta, eval_meta = build_ljspeech_metadata(str(profile))
    ds_root = Path(dataset_dir(str(profile)))
    out_root = profile / "model" / "training"
    base_root = profile / "model" / "base_xtts_v2"
    out_root.mkdir(parents=True, exist_ok=True)
    base_root.mkdir(parents=True, exist_ok=True)

    links = {
        "dvae.pth": "https://coqui.gateway.scarf.sh/hf-coqui/XTTS-v2/main/dvae.pth",
        "mel_stats.pth": "https://coqui.gateway.scarf.sh/hf-coqui/XTTS-v2/main/mel_stats.pth",
        "vocab.json": "https://coqui.gateway.scarf.sh/hf-coqui/XTTS-v2/main/vocab.json",
        "model.pth": "https://coqui.gateway.scarf.sh/hf-coqui/XTTS-v2/main/model.pth",
    }
    missing_urls = [url for name, url in links.items() if not (base_root / name).is_file()]
    if missing_urls:
        print("[SOUNDCORE] Pobieranie bazowych plików XTTS-v2...", flush=True)
        ModelManager._download_model_files(missing_urls, str(base_root), progress_bar=True)

    batch = args.batch_size or (2 if args.device == "cuda" else 1)
    grad_accum = args.grad_accum or max(1, 252 // batch)
    max_wav_len = int(args.max_audio_seconds * 22050)

    dataset_cfg = BaseDatasetConfig(
        formatter="ljspeech",
        dataset_name="soundcore",
        path=str(ds_root),
        meta_file_train=str(train_meta),
        meta_file_val=str(eval_meta),
        language="pl",
    )

    model_args = GPTArgs(
        max_conditioning_length=132300,
        min_conditioning_length=66150,
        max_wav_length=max_wav_len,
        max_text_length=200,
        mel_norm_file=str(base_root / "mel_stats.pth"),
        dvae_checkpoint=str(base_root / "dvae.pth"),
        xtts_checkpoint=str(base_root / "model.pth"),
        tokenizer_file=str(base_root / "vocab.json"),
        gpt_num_audio_tokens=1026,
        gpt_start_audio_token=1024,
        gpt_stop_audio_token=1025,
        gpt_use_masking_gt_prompt_approach=True,
        gpt_use_perceiver_resampler=True,
    )
    audio_cfg = XttsAudioConfig(sample_rate=22050, dvae_sample_rate=22050, output_sample_rate=24000)
    config = GPTTrainerConfig(
        epochs=args.epochs,
        output_path=str(out_root),
        model_args=model_args,
        run_name="SoundCore_XTTS_FT",
        project_name="SoundCore",
        run_description="SoundCore local XTTS-v2 GPT fine-tuning",
        dashboard_logger="tensorboard",
        logger_uri=None,
        audio=audio_cfg,
        batch_size=batch,
        batch_group_size=48,
        eval_batch_size=batch,
        num_loader_workers=0 if os.name == "nt" else min(4, os.cpu_count() or 1),
        eval_split_max_size=256,
        print_step=1,
        plot_step=100,
        log_model_step=1000,
        save_step=max(50, 200),
        save_n_checkpoints=2,
        save_checkpoints=True,
        print_eval=True,
        optimizer="AdamW",
        optimizer_wd_only_on_weights=True,
        optimizer_params={"betas": [0.9, 0.96], "eps": 1e-8, "weight_decay": 1e-2},
        lr=5e-6,
        lr_scheduler="MultiStepLR",
        lr_scheduler_params={"milestones": [50000 * 18, 150000 * 18, 300000 * 18], "gamma": 0.5, "last_epoch": -1},
        test_sentences=[{"text": "To jest test mojego wytrenowanego głosu w SoundCore.", "speaker_wav": [str(ref)], "language": "pl"}],
    )

    model = GPTTrainer.init_from_config(config)
    train_samples, eval_samples = load_tts_samples([dataset_cfg], eval_split=True, eval_split_max_size=config.eval_split_max_size, eval_split_size=config.eval_split_size)
    # load_tts_samples with explicit meta_file_val returns both sets in supported TTS releases.
    if not eval_samples:
        raise RuntimeError("Nie udało się wczytać zbioru walidacyjnego.")

    print(f"[SOUNDCORE] device={args.device} batch={batch} grad_accum={grad_accum} epochs={args.epochs}", flush=True)
    trainer = Trainer(
        TrainerArgs(start_with_eval=True, grad_accum_steps=grad_accum, gpu=0 if args.device == "cuda" else None),
        config,
        output_path=str(out_root),
        model=model,
        train_samples=train_samples,
        eval_samples=eval_samples,
        parse_command_line_args=False,
        gpu=0 if args.device == "cuda" else None,
    )
    trainer.fit()

    checkpoints = sorted(out_root.rglob("best_model.pth"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not checkpoints:
        checkpoints = sorted(out_root.rglob("checkpoint_*.pth"), key=lambda p: p.stat().st_mtime, reverse=True)
    checkpoint = checkpoints[0] if checkpoints else None
    config_candidates = sorted(out_root.rglob("config.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    trained_config = config_candidates[0] if config_candidates else None
    result = {
        "device": args.device,
        "epochs": args.epochs,
        "training_root": str(out_root),
        "checkpoint": str(checkpoint) if checkpoint else "",
        "config": str(trained_config) if trained_config else "",
        "vocab": str(base_root / "vocab.json"),
        "speaker_reference": str(ref),
    }
    with open(profile / "model" / "training_result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("[SOUNDCORE] TRAINING_FINISHED", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[SOUNDCORE_ERROR] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise
