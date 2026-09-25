"""
main.py
-------
Punkt wejścia aplikacji SoundCore - AI SoundSystem.

Uruchomienie:
    python main.py

Wymagania:
    pip install -r requirements.txt

Przy pierwszym uruchomieniu funkcji syntezy mowy pobierany jest model
Coqui XTTS-v2 (ok. 1.5-2 GB) - wymagane jest wtedy połączenie z internetem.
"""

from gui.app import run

if __name__ == "__main__":
    run()
