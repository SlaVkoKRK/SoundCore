# SoundCore 0.3.9

Fast Start: interfejs pojawia się natychmiast, a ciężkie komponenty są inicjalizowane poza krytyczną ścieżką uruchamiania.

## Zmiany
- usunięto import NumPy / SciPy / sounddevice / Torch / XTTS / RVC z krytycznej ścieżki startu
- GPU i CUDA są wykrywane w tle po pokazaniu WebUI
- mikrofony są wykrywane w tle
- pełne statystyki datasetów profili są odświeżane w tle
- XTTS jest tworzony dopiero przy pierwszej syntezie
- RVC jest tworzony dopiero po faktycznym włączeniu RVC
- ostatni wykryty sprzęt jest cache'owany w `cache/hardware.json`, dzięki czemu dashboard może od razu pokazać poprzedni stan
- nowy pasek statusów usług: Interfejs / GPU / Audio / Profile / XTTS / RVC
- dashboard aktualizuje się automatycznie, kiedy usługi tła kończą inicjalizację
