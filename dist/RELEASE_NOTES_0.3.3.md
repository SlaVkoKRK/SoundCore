# SoundCore 0.3.3

Hotfix mostu WebUI / CUDA / logo.

- caĹ‚kowicie usuniÄ™to przekazywanie obiektu `js_api` do pywebview
- JavaScript otrzymuje wyĹ‚Ä…cznie jawnÄ… biaĹ‚Ä… listÄ™ metod przez `window.expose(...)`
- brak jakiejkolwiek referencji z API do `window.native`, WinForms i WebView2 COM
- poprawiono wywoĹ‚anie `Napraw CUDA` i status instalacji PyTorch CUDA
- logo SoundCore jest osadzone bezpoĹ›rednio w HTML jako data URI, wiÄ™c nie zaleĹĽy od lokalnych Ĺ›cieĹĽek assetĂłw
- zachowano trening XTTS/GPTTrainer, powiadomienia, profile i aktualizacje GitHub
