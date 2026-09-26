# SoundCore 0.3.3

Hotfix mostu WebUI / CUDA / logo.

- całkowicie usunięto przekazywanie obiektu `js_api` do pywebview
- JavaScript otrzymuje wyłącznie jawną białą listę metod przez `window.expose(...)`
- brak jakiejkolwiek referencji z API do `window.native`, WinForms i WebView2 COM
- poprawiono wywołanie `Napraw CUDA` i status instalacji PyTorch CUDA
- logo SoundCore jest osadzone bezpośrednio w HTML jako data URI, więc nie zależy od lokalnych ścieżek assetów
- zachowano trening XTTS/GPTTrainer, powiadomienia, profile i aktualizacje GitHub
