# SoundCore 0.5.3

- Naprawiono znany bĹ‚Ä…d Coqui TTS 0.22.0 przy Ĺ‚adowaniu fine-tunowanego XTTS.
- `load_checkpoint()` dostaje teraz jawnie `checkpoint_dir`, dziÄ™ki czemu Coqui nie wykonuje `os.path.join(None, "speakers_xtts.pth")`.
- Zachowano poprawki 0.5.2 dotyczÄ…ce aktywnego XTTS, nieblokujÄ…cego updatera i obsĹ‚ugi `Esc`.
