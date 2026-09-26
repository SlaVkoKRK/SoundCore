# SoundCore 0.3.9

Fast Start: interfejs pojawia siÄ™ natychmiast, a ciÄ™ĹĽkie komponenty sÄ… inicjalizowane poza krytycznÄ… Ĺ›cieĹĽkÄ… uruchamiania.

## Zmiany
- usuniÄ™to import NumPy / SciPy / sounddevice / Torch / XTTS / RVC z krytycznej Ĺ›cieĹĽki startu
- GPU i CUDA sÄ… wykrywane w tle po pokazaniu WebUI
- mikrofony sÄ… wykrywane w tle
- peĹ‚ne statystyki datasetĂłw profili sÄ… odĹ›wieĹĽane w tle
- XTTS jest tworzony dopiero przy pierwszej syntezie
- RVC jest tworzony dopiero po faktycznym wĹ‚Ä…czeniu RVC
- ostatni wykryty sprzÄ™t jest cache'owany w `cache/hardware.json`, dziÄ™ki czemu dashboard moĹĽe od razu pokazaÄ‡ poprzedni stan
- nowy pasek statusĂłw usĹ‚ug: Interfejs / GPU / Audio / Profile / XTTS / RVC
- dashboard aktualizuje siÄ™ automatycznie, kiedy usĹ‚ugi tĹ‚a koĹ„czÄ… inicjalizacjÄ™
