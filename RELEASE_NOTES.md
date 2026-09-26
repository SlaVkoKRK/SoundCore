# SoundCore 0.4.6

- Naprawiono konflikt zależności instalatora: TTS 0.22.0 wymaga scipy>=1.11.2.
- Ustawiono zgodny stos Python 3.10: numpy==1.22.0, scipy==1.11.4, TTS==0.22.0.
- Usunięto końcowe wymuszanie scipy==1.10.1, które psuło instalację.
- TTS jest przypięte do 0.22.0, aby przyszłe wydania nie zmieniały zależności instalatora.
