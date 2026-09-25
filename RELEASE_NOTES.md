# SoundCore 0.3.0

Pierwszy release w nowym modelu aktualizacji GitHub-only.

## Najważniejsze zmiany
- całkowicie nowy jasny WebUI oparty o HTML/CSS w WebView2,
- ostre logo i nowa identyfikacja SoundCore,
- działający użytkownik systemowy i panel powiadomień z dzwonkiem,
- realne autowykrywanie NVIDIA GPU przez `nvidia-smi` oraz osobny status CUDA w PyTorch,
- panel nagrywania profili i datasetu treningowego,
- realny worker XTTS v2 `GPTTrainer` uruchamiany w osobnym procesie,
- wybór AUTO / GPU / CPU dla treningu,
- system aktualizacji z GitHuba: `channel.json`, SHA256, bezpieczne rozpakowanie, restart,
- aktualizacje zachowują `voice_profiles`, `output`, `venv/.venv` i `.git`.

## Ważne o GPU
Sama karta NVIDIA może być poprawnie wykryta, ale trening GPU wymaga wersji PyTorch z CUDA. SoundCore pokazuje oba statusy osobno.
