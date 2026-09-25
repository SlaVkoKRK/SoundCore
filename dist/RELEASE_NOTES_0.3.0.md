# SoundCore 0.3.0

Pierwszy release w nowym modelu aktualizacji GitHub-only.

## NajwaĹĽniejsze zmiany
- caĹ‚kowicie nowy jasny WebUI oparty o HTML/CSS w WebView2,
- ostre logo i nowa identyfikacja SoundCore,
- dziaĹ‚ajÄ…cy uĹĽytkownik systemowy i panel powiadomieĹ„ z dzwonkiem,
- realne autowykrywanie NVIDIA GPU przez `nvidia-smi` oraz osobny status CUDA w PyTorch,
- panel nagrywania profili i datasetu treningowego,
- realny worker XTTS v2 `GPTTrainer` uruchamiany w osobnym procesie,
- wybĂłr AUTO / GPU / CPU dla treningu,
- system aktualizacji z GitHuba: `channel.json`, SHA256, bezpieczne rozpakowanie, restart,
- aktualizacje zachowujÄ… `voice_profiles`, `output`, `venv/.venv` i `.git`.

## WaĹĽne o GPU
Sama karta NVIDIA moĹĽe byÄ‡ poprawnie wykryta, ale trening GPU wymaga wersji PyTorch z CUDA. SoundCore pokazuje oba statusy osobno.
