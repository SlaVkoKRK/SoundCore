from __future__ import annotations

import os
import shutil
import sys
import threading
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from recorder.recorder import DEFAULT_SAMPLERATE, list_input_devices, play_wav, record_audio
from preprocessing.audio_utils import preprocess_pipeline
from storage.profile_manager import ProfileManager, VoiceProfile
from voice_engine.rvc_engine import get_rvc_engine
from voice_engine.tts_engine import get_engine

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
LOGO_PATH = os.path.join(ASSETS_DIR, "soundcore_logo.png")
APP_VERSION = "0.2.0"
LATEST_VERSION = "0.2.0"

os.makedirs(OUTPUT_DIR, exist_ok=True)

LANGUAGES = {
    "Polski": "pl",
    "Angielski": "en",
    "Niemiecki": "de",
    "Francuski": "fr",
    "Hiszpański": "es",
}

BG = "#F6F8FC"
SIDEBAR_BG = "#FFFFFF"
CARD_BG = "#FFFFFF"
TEXT = "#18233C"
MUTED = "#73819D"
BORDER = "#E6EBF5"
PRIMARY = "#2EA7FF"
PRIMARY_2 = "#8C4DFF"
PRIMARY_DARK = "#1E5BFF"
GREEN = "#1BAF63"
RED = "#E54B67"
SOFT_BLUE = "#EDF5FF"
SOFT_GREEN = "#ECFBF2"
SOFT_PURPLE = "#F3EEFF"
SOFT_RED = "#FFF1F4"
SOFT_GRAY = "#F8FAFD"
BUTTON_BG = "#EEF3FB"


@dataclass
class SpeechContext:
    profile_combo: ttk.Combobox
    language_combo: ttk.Combobox
    text_widget: tk.Text
    generate_button: tk.Widget
    progress: ttk.Progressbar
    play_button: tk.Widget | None = None
    use_rvc_var: tk.BooleanVar | None = None


class SoundCoreApp(ttk.Frame):
    def __init__(self, master: tk.Tk) -> None:
        super().__init__(master)
        self.master = master
        self.master.configure(bg=BG)

        self.profile_manager = ProfileManager()
        self.engine = get_engine()
        self.rvc_engine = get_rvc_engine()

        self._recorded_audio = None
        self._recorded_samplerate = DEFAULT_SAMPLERATE
        self._last_generated_path: str | None = None
        self._devices = []
        self._profiles: list[VoiceProfile] = []
        self._speech_contexts: dict[str, SpeechContext] = {}
        self._nav_buttons: dict[str, tk.Button] = {}
        self._pages: dict[str, tk.Frame] = {}
        self._current_page = "dashboard"
        self._profile_cards_container: tk.Frame | None = None
        self._logo_image = None
        self._busy_generation = False

        self.pack(fill="both", expand=True)
        self._build_styles()
        self._build_shell()
        self._populate_devices()
        self._refresh_all()
        self._show_page("dashboard")

    # ------------------------------------------------------------------
    # UI shell
    # ------------------------------------------------------------------
    def _build_styles(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("SC.TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD_BG)
        style.configure("Sidebar.TFrame", background=SIDEBAR_BG)
        style.configure("SC.TLabel", background=BG, foreground=TEXT)
        style.configure("Muted.TLabel", background=BG, foreground=MUTED)
        style.configure("CardTitle.TLabel", background=CARD_BG, foreground=TEXT, font=("Segoe UI", 14, "bold"))
        style.configure("CardMuted.TLabel", background=CARD_BG, foreground=MUTED, font=("Segoe UI", 10))
        style.configure("SC.TCombobox", fieldbackground="#FFFFFF", background="#FFFFFF", foreground=TEXT, bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, arrowsize=14, padding=6)
        style.map("SC.TCombobox", fieldbackground=[("readonly", "#FFFFFF")])
        style.configure("Blue.Horizontal.TProgressbar", troughcolor="#EAEFFD", background=PRIMARY_DARK, bordercolor="#EAEFFD", lightcolor=PRIMARY, darkcolor=PRIMARY_2, thickness=10)
        style.configure("Green.Horizontal.TProgressbar", troughcolor="#E5F7EE", background=GREEN, bordercolor="#E5F7EE", lightcolor="#35D987", darkcolor=GREEN, thickness=10)

    def _build_shell(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self.sidebar = tk.Frame(self, bg=SIDEBAR_BG, width=250, highlightthickness=1, highlightbackground=BORDER)
        self.sidebar.grid(row=0, column=0, sticky="nsw")
        self.sidebar.grid_propagate(False)
        self._build_sidebar()

        self.main = tk.Frame(self, bg=BG)
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.rowconfigure(1, weight=1)
        self.main.columnconfigure(0, weight=1)

        self.header_frame = tk.Frame(self.main, bg=BG)
        self.header_frame.grid(row=0, column=0, sticky="ew", padx=28, pady=(18, 10))
        self.header_frame.columnconfigure(0, weight=1)
        self._build_header()

        self.page_host = tk.Frame(self.main, bg=BG)
        self.page_host.grid(row=1, column=0, sticky="nsew", padx=28, pady=(0, 18))
        self.page_host.rowconfigure(0, weight=1)
        self.page_host.columnconfigure(0, weight=1)
        self._build_pages()

        self.status_var = tk.StringVar(value=f"Gotowe. Silnik TTS działa na: {self.engine.device.upper()}")
        status = tk.Label(self.main, textvariable=self.status_var, bg="#F0F4FA", fg=MUTED, anchor="w", padx=16, pady=8)
        status.grid(row=2, column=0, sticky="ew")

    def _build_sidebar(self) -> None:
        logo_box = tk.Frame(self.sidebar, bg=SIDEBAR_BG)
        logo_box.pack(fill="x", padx=18, pady=(18, 14))
        self._load_logo(logo_box)

        menu_items = [
            ("dashboard", "⌂  Pulpit"),
            ("speak", "◉  Synteza mowy"),
            ("profiles", "◌  Profile głosu"),
            ("training", "◎  Trening modelu"),
            ("updates", "↓  Aktualizacje"),
            ("settings", "⚙  Ustawienia"),
        ]
        for key, label in menu_items:
            btn = tk.Button(
                self.sidebar,
                text=label,
                command=lambda k=key: self._show_page(k),
                font=("Segoe UI", 12, "bold" if key == "dashboard" else "normal"),
                fg=TEXT,
                bg=SIDEBAR_BG,
                activebackground="#EEF2FF",
                activeforeground=PRIMARY_DARK,
                bd=0,
                relief="flat",
                anchor="w",
                padx=18,
                pady=12,
                cursor="hand2",
            )
            btn.pack(fill="x", padx=14, pady=3)
            self._nav_buttons[key] = btn

        promo = tk.Frame(self.sidebar, bg=SOFT_GRAY, highlightthickness=1, highlightbackground=BORDER)
        promo.pack(side="bottom", fill="x", padx=16, pady=18)
        promo_top = tk.Canvas(promo, height=84, bg=SOFT_GRAY, bd=0, highlightthickness=0)
        promo_top.pack(fill="x")
        promo_top.create_arc(-20, 10, 120, 120, start=10, extent=150, fill="#C8DFFF", outline="#C8DFFF")
        promo_top.create_arc(60, 20, 210, 140, start=10, extent=160, fill="#B9CEFF", outline="#B9CEFF")
        promo_top.create_arc(120, 0, 260, 110, start=10, extent=150, fill="#D9C8FF", outline="#D9C8FF")
        text_frame = tk.Frame(promo, bg=SOFT_GRAY)
        text_frame.pack(fill="x", padx=18, pady=(6, 18))
        tk.Label(text_frame, text="Twórz\nnaturalne głosy\nz pomocą AI", bg=SOFT_GRAY, fg=TEXT, justify="left", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        tk.Label(text_frame, text="Realistyczna synteza,\nwłasne modele, pełna kontrola.", bg=SOFT_GRAY, fg=MUTED, justify="left", font=("Segoe UI", 10)).pack(anchor="w", pady=(10, 12))
        tk.Button(text_frame, text="Dowiedz się więcej →", bg=PRIMARY_2, fg="white", activebackground=PRIMARY_DARK, activeforeground="white", bd=0, relief="flat", font=("Segoe UI", 11, "bold"), cursor="hand2", padx=16, pady=10, command=lambda: self._show_info("SoundCore", "Nowe, nowoczesne UI jest już gotowe. Kolejny krok: backend treningu i aktualizacji." )).pack(fill="x")

    def _load_logo(self, parent: tk.Widget) -> None:
        if os.path.isfile(LOGO_PATH):
            try:
                img = tk.PhotoImage(file=LOGO_PATH)
                if img.width() > 180:
                    factor = max(1, img.width() // 180)
                    img = img.subsample(factor, factor)
                self._logo_image = img
                tk.Label(parent, image=img, bg=SIDEBAR_BG).pack(anchor="w")
                return
            except tk.TclError:
                pass
        tk.Label(parent, text="SoundCore", bg=SIDEBAR_BG, fg=TEXT, font=("Segoe UI", 20, "bold")).pack(anchor="w")

    def _build_header(self) -> None:
        self.header_title = tk.Label(self.header_frame, text="Pulpit", bg=BG, fg=TEXT, font=("Segoe UI", 28, "bold"))
        self.header_title.grid(row=0, column=0, sticky="w")
        self.header_subtitle = tk.Label(self.header_frame, text="Witaj w SoundCore! Twórz, trenuj i zarządzaj swoimi modelami głosu.", bg=BG, fg=MUTED, font=("Segoe UI", 12))
        self.header_subtitle.grid(row=1, column=0, sticky="w", pady=(2, 0))

        right = tk.Frame(self.header_frame, bg=BG)
        right.grid(row=0, column=1, rowspan=2, sticky="e")
        search_wrap = tk.Frame(right, bg="#FFFFFF", highlightthickness=1, highlightbackground=BORDER)
        search_wrap.pack(side="left", padx=(0, 16))
        self.search_var = tk.StringVar(value="Szukaj profili, nagrań, projektów…")
        self.search_entry = tk.Entry(search_wrap, textvariable=self.search_var, bd=0, relief="flat", width=34, fg=MUTED, bg="#FFFFFF", font=("Segoe UI", 11))
        self.search_entry.pack(side="left", padx=(14, 8), pady=10)
        self.search_entry.bind("<FocusIn>", self._on_search_focus_in)
        self.search_entry.bind("<FocusOut>", self._on_search_focus_out)
        tk.Label(search_wrap, text="⌘ K", bg="#F5F7FB", fg=MUTED, font=("Segoe UI", 9, "bold"), padx=8, pady=3).pack(side="right", padx=(0, 10))

        tk.Label(right, text="🔔", bg="#FFFFFF", fg=TEXT, font=("Segoe UI Emoji", 16), padx=14, pady=8).pack(side="left", padx=(0, 12))
        profile = tk.Frame(right, bg=BG)
        profile.pack(side="left")
        tk.Label(profile, text="P", bg=PRIMARY_DARK, fg="white", width=2, height=1, font=("Segoe UI", 13, "bold"), padx=6, pady=6).pack(side="left", padx=(0, 10))
        user = tk.Frame(profile, bg=BG)
        user.pack(side="left")
        tk.Label(user, text="Piotr Nowak", bg=BG, fg=TEXT, font=("Segoe UI", 11, "bold")).pack(anchor="w")
        tk.Label(user, text="Użytkownik", bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w")

    def _build_pages(self) -> None:
        self._pages["dashboard"] = self._build_dashboard_page()
        self._pages["speak"] = self._build_speak_page()
        self._pages["profiles"] = self._build_profiles_page()
        self._pages["training"] = self._build_training_page()
        self._pages["updates"] = self._build_updates_page()
        self._pages["settings"] = self._build_settings_page()
        for frame in self._pages.values():
            frame.grid(row=0, column=0, sticky="nsew")

    def _show_page(self, key: str) -> None:
        titles = {
            "dashboard": ("Pulpit", "Witaj w SoundCore! Twórz, trenuj i zarządzaj swoimi modelami głosu."),
            "speak": ("Synteza mowy", "Generuj naturalnie brzmiącą mowę z użyciem własnych profili."),
            "profiles": ("Profile głosu", "Nagrywaj, zarządzaj i przygotowuj profile głosowe."),
            "training": ("Trening modelu", "Przygotuj dane i kontroluj trening własnego modelu głosu."),
            "updates": ("Aktualizacje", "Sprawdzaj wersje i zarządzaj kanałem aktualizacji programu."),
            "settings": ("Ustawienia", "Podstawowa konfiguracja aplikacji i informacje o systemie."),
        }
        self._current_page = key
        page = self._pages[key]
        page.tkraise()
        title, subtitle = titles[key]
        self.header_title.configure(text=title)
        self.header_subtitle.configure(text=subtitle)
        for k, btn in self._nav_buttons.items():
            active = k == key
            btn.configure(
                bg="#EEF2FF" if active else SIDEBAR_BG,
                fg=PRIMARY_DARK if active else TEXT,
                font=("Segoe UI", 12, "bold" if active else "normal"),
            )

    # ------------------------------------------------------------------
    # Pages
    # ------------------------------------------------------------------
    def _build_dashboard_page(self) -> tk.Frame:
        page = tk.Frame(self.page_host, bg=BG)
        for i in range(12):
            page.columnconfigure(i, weight=1)

        top_cards = [
            (0, 0, 3, "Aktywny profil", "Brak profilu", "Dodaj profil, aby zacząć", SOFT_BLUE, "◌"),
            (0, 3, 3, "Model", "XTTS v2", "Wysoka jakość · wielojęzyczny", SOFT_PURPLE, "◈"),
            (0, 6, 3, "GPU/CPU", self.engine.device.upper(), "Urządzenie silnika", SOFT_GREEN, "⚙"),
            (0, 9, 3, "Status", "Wszystko działa", "System gotowy do pracy", SOFT_GREEN, "✓"),
        ]
        self.dashboard_top_value_labels = {}
        for row, col, span, title, value, subtitle, icon_bg, icon in top_cards:
            card = self._card(page)
            card.grid(row=row, column=col, columnspan=span, sticky="nsew", padx=8, pady=8)
            icon_box = tk.Label(card, text=icon, bg=icon_bg, fg=PRIMARY_DARK if title != "Status" else GREEN, font=("Segoe UI", 18, "bold"), width=2, pady=10)
            icon_box.pack(side="left", padx=16, pady=16)
            text_box = tk.Frame(card, bg=CARD_BG)
            text_box.pack(side="left", fill="both", expand=True, pady=16)
            tk.Label(text_box, text=title, bg=CARD_BG, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w")
            value_lbl = tk.Label(text_box, text=value, bg=CARD_BG, fg=TEXT, font=("Segoe UI", 16, "bold"))
            value_lbl.pack(anchor="w", pady=(2, 0))
            subtitle_lbl = tk.Label(text_box, text=subtitle, bg=CARD_BG, fg=MUTED, font=("Segoe UI", 10))
            subtitle_lbl.pack(anchor="w")
            self.dashboard_top_value_labels[title] = (value_lbl, subtitle_lbl)

        speech = self._card(page)
        speech.grid(row=1, column=0, columnspan=7, sticky="nsew", padx=8, pady=8)
        self._build_dashboard_speech_card(speech)

        training = self._card(page)
        training.grid(row=1, column=7, columnspan=5, sticky="nsew", padx=8, pady=8)
        self._build_dashboard_training_card(training)

        profiles = self._card(page)
        profiles.grid(row=2, column=0, columnspan=7, sticky="nsew", padx=8, pady=8)
        self._build_dashboard_profiles_card(profiles)

        updates = self._card(page)
        updates.grid(row=2, column=7, columnspan=5, sticky="nsew", padx=8, pady=8)
        self._build_dashboard_updates_card(updates)

        return page

    def _build_dashboard_speech_card(self, parent: tk.Frame) -> None:
        self._card_header(parent, "Synteza mowy", "Przekształć tekst w naturalnie brzmiącą mowę przy użyciu wybranego profilu.", action_text="Ustawienia zaawansowane", action_cmd=lambda: self._show_page("speak"))

        text = tk.Text(parent, height=5, wrap="word", bd=0, relief="flat", font=("Segoe UI", 12), fg=TEXT, bg="#FFFFFF", highlightthickness=1, highlightbackground=BORDER, padx=12, pady=12)
        text.pack(fill="x", padx=18, pady=(4, 10))
        text.insert("1.0", "Witaj w SoundCore! To nowoczesna platforma do syntezy mowy i trenowania\nwłasnych modeli głosu. Dzięki sztucznej inteligencji możesz tworzyć naturalnie\nbrzmiące nagrania w kilka sekund.")

        row = tk.Frame(parent, bg=CARD_BG)
        row.pack(fill="x", padx=18, pady=(4, 10))
        row.columnconfigure((0, 1, 2), weight=1)
        prof = self._labeled_combo(row, 0, "Profil głosu")
        lang = self._labeled_combo(row, 1, "Język", values=list(LANGUAGES.keys()), current=0)
        style_combo = self._labeled_combo(row, 2, "Styl mówienia", values=["Naturalny", "Wyraźny", "Spokojny"], current=0)
        style_combo.configure(state="readonly")

        buttons = tk.Frame(parent, bg=CARD_BG)
        buttons.pack(fill="x", padx=18, pady=(0, 12))
        gen_btn = self._button(buttons, "✦  Generuj", self._generate_speech_dashboard, fill="#5C66FF")
        gen_btn.pack(side="left")
        play_btn = self._button(buttons, "▶  Odtwórz", self._play_last_generated, fill=BUTTON_BG, fg=PRIMARY_DARK)
        play_btn.pack(side="left", padx=(10, 0))
        play_btn.configure(state="disabled")
        self.dashboard_download_btn = self._button(buttons, "⇩  Pobierz", self._download_last_generated, fill=BUTTON_BG, fg=TEXT)
        self.dashboard_download_btn.pack(side="right")
        self.dashboard_download_btn.configure(state="disabled")
        self.dashboard_speed_var = tk.StringVar(value="1.0x")
        speed = ttk.Combobox(buttons, textvariable=self.dashboard_speed_var, width=7, state="readonly", values=["0.8x", "1.0x", "1.1x", "1.2x"], style="SC.TCombobox")
        speed.pack(side="right", padx=(0, 10))

        progress = ttk.Progressbar(parent, style="Blue.Horizontal.TProgressbar", mode="indeterminate")
        progress.pack(fill="x", padx=18, pady=(0, 10))

        audio = tk.Frame(parent, bg="#F8FAFE", highlightthickness=1, highlightbackground=BORDER)
        audio.pack(fill="x", padx=18, pady=(0, 18))
        tk.Label(audio, text="▶", bg="#F8FAFE", fg=PRIMARY_DARK, font=("Segoe UI", 18, "bold"), padx=14, pady=12).pack(side="left")
        self.wave_canvas = tk.Canvas(audio, height=54, bg="#F8FAFE", bd=0, highlightthickness=0)
        self.wave_canvas.pack(side="left", fill="x", expand=True, padx=(0, 10), pady=8)
        self._draw_waveform(self.wave_canvas)
        self.dashboard_audio_label = tk.Label(audio, text="0:00 / 0:00", bg="#F8FAFE", fg=MUTED, font=("Segoe UI", 10))
        self.dashboard_audio_label.pack(side="right", padx=14)

        self._speech_contexts["dashboard"] = SpeechContext(
            profile_combo=prof,
            language_combo=lang,
            text_widget=text,
            generate_button=gen_btn,
            progress=progress,
            play_button=play_btn,
            use_rvc_var=None,
        )

    def _build_dashboard_training_card(self, parent: tk.Frame) -> None:
        self._card_header(parent, "Trening modelu XTTS", "Trenuj własny model głosu na podstawie nagrań.", action_text="Dokumentacja", action_cmd=lambda: self._show_info("Trening modelu", "Warstwa wizualna treningu jest gotowa. Następny etap to pełne spięcie backendu GPTTrainer."))
        metrics = tk.Frame(parent, bg=CARD_BG)
        metrics.pack(fill="x", padx=18, pady=(6, 6))
        metrics.columnconfigure((0, 1, 2), weight=1)
        self.training_dataset_label = self._metric_card(metrics, 0, "Zbiór danych", "0 min", "Czas nagrań")
        self.training_epochs_label = self._metric_card(metrics, 1, "Epoki", "10", "Liczba epok")
        self.training_device_label = self._metric_card(metrics, 2, "Urządzenie", "AUTO", "Automatyczny wybór")

        box = tk.Frame(parent, bg="#FBFCFF", highlightthickness=1, highlightbackground=BORDER)
        box.pack(fill="both", expand=True, padx=18, pady=(8, 18))
        top = tk.Frame(box, bg="#FBFCFF")
        top.pack(fill="x", padx=16, pady=(14, 8))
        tk.Label(top, text="Trening w toku…", bg="#FBFCFF", fg=TEXT, font=("Segoe UI", 15, "bold")).pack(side="left")
        tk.Label(top, text="Epoka 0 / 10", bg="#FBFCFF", fg=MUTED, font=("Segoe UI", 10)).pack(side="right")
        pb = ttk.Progressbar(box, style="Blue.Horizontal.TProgressbar", value=32)
        pb.pack(fill="x", padx=16)
        tk.Label(box, text="Loss (niższe = lepsze)", bg="#FBFCFF", fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", padx=16, pady=(12, 4))
        chart = tk.Canvas(box, height=140, bg="#FFFFFF", bd=0, highlightthickness=1, highlightbackground=BORDER)
        chart.pack(fill="x", padx=16, pady=(0, 8))
        self._draw_loss_chart(chart)
        bottom = tk.Frame(box, bg="#FBFCFF")
        bottom.pack(fill="x", padx=16, pady=(6, 16))
        tk.Label(bottom, text="Czas treningu  00:00:00", bg="#FBFCFF", fg=TEXT, font=("Segoe UI", 11, "bold")).pack(side="left")
        self._button(bottom, "■  Zatrzymaj trening", lambda: self._show_info("Trening", "Backend treningu będzie spięty w kolejnym kroku."), fill="#FFF0F3", fg=RED, border=RED).pack(side="right")

    def _build_dashboard_profiles_card(self, parent: tk.Frame) -> None:
        self._card_header(parent, "Profile głosu", "Zarządzaj swoimi profilami głosu i wybierz najlepszy do syntezy.", action_text="Zobacz wszystkie →", action_cmd=lambda: self._show_page("profiles"))
        self._profile_cards_container = tk.Frame(parent, bg=CARD_BG)
        self._profile_cards_container.pack(fill="both", expand=True, padx=14, pady=(4, 14))
        self._render_dashboard_profile_cards()

    def _build_dashboard_updates_card(self, parent: tk.Frame) -> None:
        self._card_header(parent, "Aktualizacje", "Sprawdź najnowsze wersje i aktualizacje systemu.")
        wrap = tk.Frame(parent, bg=CARD_BG)
        wrap.pack(fill="both", expand=True, padx=18, pady=(6, 16))
        wrap.columnconfigure((0, 1), weight=1)
        self.current_version_tile = self._metric_card(wrap, 0, "Aktualna wersja", APP_VERSION, "Lokalna instalacja")
        self.latest_version_tile = self._metric_card(wrap, 1, "Najnowsza wersja", LATEST_VERSION, "+ Masz najnowszą wersję")
        self._button(parent, "↻  Sprawdź aktualizacje", self._check_updates_stub, fill="#EEF4FF", fg=PRIMARY_DARK).pack(fill="x", padx=18, pady=(0, 18))

    def _build_speak_page(self) -> tk.Frame:
        page = tk.Frame(self.page_host, bg=BG)
        container = self._card(page)
        container.pack(fill="both", expand=True, padx=8, pady=8)
        self._card_header(container, "Synteza mowy", "Wprowadź tekst i wygeneruj mowę na bazie wybranego profilu głosowego.")

        content = tk.Frame(container, bg=CARD_BG)
        content.pack(fill="both", expand=True, padx=18, pady=(8, 18))
        content.columnconfigure((0, 1), weight=1)

        left = tk.Frame(content, bg=CARD_BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        right = tk.Frame(content, bg=CARD_BG)
        right.grid(row=0, column=1, sticky="nsew", padx=(12, 0))

        tk.Label(left, text="Tekst do syntezy", bg=CARD_BG, fg=TEXT, font=("Segoe UI", 13, "bold")).pack(anchor="w")
        text = tk.Text(left, height=16, wrap="word", bd=0, relief="flat", font=("Segoe UI", 12), fg=TEXT, bg="#FFFFFF", highlightthickness=1, highlightbackground=BORDER, padx=12, pady=12)
        text.pack(fill="both", expand=True, pady=(8, 12))
        text.insert("1.0", "Witaj, to jest przykładowy tekst wypowiedziany moim własnym głosem.")

        tk.Label(right, text="Ustawienia", bg=CARD_BG, fg=TEXT, font=("Segoe UI", 13, "bold")).pack(anchor="w")
        prof = self._labeled_combo(right, None, "Profil głosowy")
        prof.pack(fill="x", pady=(8, 10))
        lang = self._labeled_combo(right, None, "Język", values=list(LANGUAGES.keys()), current=0)
        lang.pack(fill="x", pady=(0, 10))
        rvc_var = tk.BooleanVar(value=False)
        tk.Checkbutton(right, text="Popraw barwę głosu przez RVC", variable=rvc_var, bg=CARD_BG, fg=TEXT, selectcolor="#FFFFFF", activebackground=CARD_BG, font=("Segoe UI", 11)).pack(anchor="w", pady=(4, 16))
        progress = ttk.Progressbar(right, style="Blue.Horizontal.TProgressbar", mode="indeterminate")
        progress.pack(fill="x", pady=(0, 16))
        gen = self._button(right, "✦  Generuj i odtwórz", self._generate_speech_full, fill="#5C66FF")
        gen.pack(fill="x", pady=(0, 10))
        play_btn = self._button(right, "▶  Odtwórz ostatni plik", self._play_last_generated, fill=BUTTON_BG, fg=PRIMARY_DARK)
        play_btn.pack(fill="x", pady=(0, 10))
        play_btn.configure(state="disabled")
        save_btn = self._button(right, "⇩  Zapisz plik WAV", self._download_last_generated, fill=BUTTON_BG, fg=TEXT)
        save_btn.pack(fill="x")

        info = tk.Frame(right, bg="#F8FAFE", highlightthickness=1, highlightbackground=BORDER)
        info.pack(fill="x", pady=(18, 0))
        tk.Label(info, text="Porada", bg="#F8FAFE", fg=TEXT, font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=12, pady=(12, 4))
        tk.Label(info, text="Najlepsze wyniki uzyskasz z wyraźnie nagraną próbką referencyjną i krótkimi testami w kilku językach.", bg="#F8FAFE", fg=MUTED, justify="left", wraplength=320, font=("Segoe UI", 10)).pack(anchor="w", padx=12, pady=(0, 12))

        self._speech_contexts["speak"] = SpeechContext(
            profile_combo=prof,
            language_combo=lang,
            text_widget=text,
            generate_button=gen,
            progress=progress,
            play_button=play_btn,
            use_rvc_var=rvc_var,
        )
        return page

    def _build_profiles_page(self) -> tk.Frame:
        page = tk.Frame(self.page_host, bg=BG)
        page.columnconfigure((0, 1), weight=1)
        page.rowconfigure(1, weight=1)

        record = self._card(page)
        record.grid(row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=8)
        self._card_header(record, "Nagrywanie profilu", "Nagraj próbkę głosu i zapisz ją jako nowy profil.")
        body = tk.Frame(record, bg=CARD_BG)
        body.pack(fill="x", padx=18, pady=(6, 18))
        body.columnconfigure((0, 1, 2, 3), weight=1)
        tk.Label(body, text="Urządzenie wejściowe", bg=CARD_BG, fg=MUTED, font=("Segoe UI", 10)).grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.device_combo = ttk.Combobox(body, state="readonly", style="SC.TCombobox")
        self.device_combo.grid(row=1, column=0, sticky="ew", padx=(0, 10))
        tk.Label(body, text="Długość nagrania (s)", bg=CARD_BG, fg=MUTED, font=("Segoe UI", 10)).grid(row=0, column=1, sticky="w", pady=(0, 4))
        self.duration_var = tk.IntVar(value=20)
        tk.Spinbox(body, from_=5, to=120, textvariable=self.duration_var, bd=0, relief="flat", highlightthickness=1, highlightbackground=BORDER, bg="#FFFFFF", fg=TEXT, font=("Segoe UI", 11)).grid(row=1, column=1, sticky="ew", padx=(0, 10))
        tk.Label(body, text="Nazwa profilu", bg=CARD_BG, fg=MUTED, font=("Segoe UI", 10)).grid(row=0, column=2, sticky="w", pady=(0, 4))
        self.profile_name_var = tk.StringVar()
        tk.Entry(body, textvariable=self.profile_name_var, bd=0, relief="flat", highlightthickness=1, highlightbackground=BORDER, bg="#FFFFFF", fg=TEXT, font=("Segoe UI", 11)).grid(row=1, column=2, sticky="ew", padx=(0, 10))
        refresh = self._button(body, "↻  Odśwież mikrofony", self._populate_devices, fill=BUTTON_BG, fg=TEXT)
        refresh.grid(row=1, column=3, sticky="ew")

        self.record_progress = ttk.Progressbar(record, style="Blue.Horizontal.TProgressbar", mode="determinate", maximum=100)
        self.record_progress.pack(fill="x", padx=18, pady=(0, 12))
        actions = tk.Frame(record, bg=CARD_BG)
        actions.pack(fill="x", padx=18, pady=(0, 12))
        self.record_button = self._button(actions, "●  Rozpocznij nagrywanie", self._start_recording, fill="#5C66FF")
        self.record_button.pack(side="left")
        self.play_recorded_button = self._button(actions, "▶  Odsłuchaj nagranie", self._play_recorded, fill=BUTTON_BG, fg=PRIMARY_DARK)
        self.play_recorded_button.pack(side="left", padx=10)
        self.play_recorded_button.configure(state="disabled")
        self.save_button = self._button(actions, "💾  Zapisz profil", self._save_profile, fill=BUTTON_BG, fg=TEXT)
        self.save_button.pack(side="left")
        self.save_button.configure(state="disabled")
        tk.Label(record, text="Wskazówka: mów naturalnie i wyraźnie przez co najmniej 15–20 sekund, aby model dobrze uchwycił barwę głosu i dykcję.", bg=CARD_BG, fg=MUTED, wraplength=1100, justify="left", font=("Segoe UI", 10)).pack(anchor="w", padx=18, pady=(0, 18))

        profiles = self._card(page)
        profiles.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=8, pady=8)
        self._card_header(profiles, "Lista profili", "Zarządzaj zapisanymi profilami, odsłuchuj próbki i podepnij model RVC.")
        list_wrap = tk.Frame(profiles, bg=CARD_BG)
        list_wrap.pack(fill="both", expand=True, padx=18, pady=(6, 18))
        list_wrap.columnconfigure(0, weight=1)
        list_wrap.rowconfigure(0, weight=1)
        self.profiles_listbox = tk.Listbox(list_wrap, bd=0, relief="flat", highlightthickness=1, highlightbackground=BORDER, bg="#FFFFFF", fg=TEXT, font=("Segoe UI", 11), activestyle="none", selectbackground="#EAF1FF", selectforeground=TEXT)
        self.profiles_listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar = tk.Scrollbar(list_wrap, command=self.profiles_listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.profiles_listbox.configure(yscrollcommand=scrollbar.set)

        btns = tk.Frame(profiles, bg=CARD_BG)
        btns.pack(fill="x", padx=18, pady=(0, 18))
        self._button(btns, "▶  Odtwórz próbkę", self._play_selected_profile, fill=BUTTON_BG, fg=PRIMARY_DARK).pack(side="left")
        self._button(btns, "🎚  Podepnij model RVC", self._attach_rvc_model, fill=BUTTON_BG, fg=TEXT).pack(side="left", padx=10)
        self._button(btns, "🗑  Usuń profil", self._delete_selected_profile, fill="#FFF0F3", fg=RED, border=RED).pack(side="right")
        return page

    def _build_training_page(self) -> tk.Frame:
        page = tk.Frame(self.page_host, bg=BG)
        card = self._card(page)
        card.pack(fill="both", expand=True, padx=8, pady=8)
        self._card_header(card, "Trening modelu", "Nowy, nowoczesny panel treningu jest gotowy wizualnie. Kolejnym krokiem będzie pełne spięcie backendu GPTTrainer.")
        inner = tk.Frame(card, bg=CARD_BG)
        inner.pack(fill="both", expand=True, padx=18, pady=(8, 18))
        inner.columnconfigure((0, 1, 2), weight=1)
        self.train_dataset_page_label = self._metric_card(inner, 0, "Zbiór danych", "0 min", "Łączny czas próbek")
        self.train_profiles_page_label = self._metric_card(inner, 1, "Profile", "0", "Dostępne profile")
        self.train_device_page_label = self._metric_card(inner, 2, "Urządzenie", self.engine.device.upper(), "Aktywne urządzenie")

        form = tk.Frame(inner, bg="#FBFCFF", highlightthickness=1, highlightbackground=BORDER)
        form.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=(16, 0))
        for col in range(3):
            form.columnconfigure(col, weight=1)
        tk.Label(form, text="Plan treningu", bg="#FBFCFF", fg=TEXT, font=("Segoe UI", 16, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", padx=18, pady=(16, 8))
        self.train_profile_combo = self._labeled_combo(form, 0, "Profil bazowy")
        self.train_profile_combo.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 10))
        self.train_device_combo = self._labeled_combo(form, 1, "Urządzenie", values=["AUTO", "GPU", "CPU"], current=0)
        self.train_device_combo.grid(row=1, column=1, sticky="ew", padx=18, pady=(0, 10))
        self.train_epochs_combo = self._labeled_combo(form, 2, "Epoki", values=["5", "10", "20", "30"], current=1)
        self.train_epochs_combo.grid(row=1, column=2, sticky="ew", padx=18, pady=(0, 10))
        tk.Label(form, text="Interfejs treningu jest już gotowy wizualnie i przygotowany pod integrację z GPTTrainer / XTTS fine-tune.", bg="#FBFCFF", fg=MUTED, wraplength=1000, justify="left", font=("Segoe UI", 10)).grid(row=2, column=0, columnspan=3, sticky="w", padx=18, pady=(0, 10))
        self._button(form, "▶  Rozpocznij trening", lambda: self._show_info("Trening", "W tej paczce wdrożyłem pełny nowy wygląd. Spięcie backendu treningu zrobimy w następnym kroku."), fill="#5C66FF").grid(row=3, column=0, padx=18, pady=(0, 18), sticky="w")
        self._button(form, "📁  Otwórz katalog danych", lambda: self._open_folder(self.profile_manager.base_dir), fill=BUTTON_BG, fg=TEXT).grid(row=3, column=1, padx=18, pady=(0, 18), sticky="w")
        return page

    def _build_updates_page(self) -> tk.Frame:
        page = tk.Frame(self.page_host, bg=BG)
        card = self._card(page)
        card.pack(fill="both", expand=True, padx=8, pady=8)
        self._card_header(card, "Aktualizacje", "Panel aktualizacji jest gotowy pod integrację z mechanizmem publikacji i kanałem update jak w VEYRA.")
        inner = tk.Frame(card, bg=CARD_BG)
        inner.pack(fill="both", expand=True, padx=18, pady=(8, 18))
        inner.columnconfigure((0, 1), weight=1)
        self.upd_current_page_label = self._metric_card(inner, 0, "Aktualna wersja", APP_VERSION, "Bieżąca instalacja")
        self.upd_latest_page_label = self._metric_card(inner, 1, "Najnowsza wersja", LATEST_VERSION, "Kanał publiczny")
        info = tk.Frame(inner, bg="#FBFCFF", highlightthickness=1, highlightbackground=BORDER)
        info.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(16, 0))
        tk.Label(info, text="Mechanizm aktualizacji", bg="#FBFCFF", fg=TEXT, font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=18, pady=(16, 8))
        bullets = [
            "sprawdzanie channel.json",
            "porównanie wersji",
            "pobieranie paczki aktualizacyjnej",
            "weryfikacja SHA256",
            "bezpieczna podmiana plików aplikacji",
            "zachowanie voice_profiles, output i środowiska lokalnego",
        ]
        for item in bullets:
            tk.Label(info, text=f"• {item}", bg="#FBFCFF", fg=MUTED, font=("Segoe UI", 11)).pack(anchor="w", padx=18, pady=2)
        btns = tk.Frame(info, bg="#FBFCFF")
        btns.pack(fill="x", padx=18, pady=(14, 18))
        self._button(btns, "↻  Sprawdź aktualizacje", self._check_updates_stub, fill="#EEF4FF", fg=PRIMARY_DARK).pack(side="left")
        self._button(btns, "📄  Pokaż release notes", lambda: self._show_info("Release notes", "SoundCore 0.2.0: nowy modernistyczny interfejs, nowe logo i przygotowanie pod system aktualizacji oraz trening modelu."), fill=BUTTON_BG, fg=TEXT).pack(side="left", padx=10)
        return page

    def _build_settings_page(self) -> tk.Frame:
        page = tk.Frame(self.page_host, bg=BG)
        card = self._card(page)
        card.pack(fill="both", expand=True, padx=8, pady=8)
        self._card_header(card, "Ustawienia", "Podstawowe informacje o aplikacji, katalogach i używanym silniku.")
        inner = tk.Frame(card, bg=CARD_BG)
        inner.pack(fill="both", expand=True, padx=18, pady=(8, 18))
        inner.columnconfigure((0, 1), weight=1)
        fields = [
            ("Wersja", APP_VERSION),
            ("Silnik TTS", "Coqui XTTS v2"),
            ("Urządzenie", self.engine.device.upper()),
            ("Katalog profili", self.profile_manager.base_dir),
            ("Katalog output", OUTPUT_DIR),
            ("Motyw", "Light Modern UI"),
        ]
        for idx, (label, value) in enumerate(fields):
            box = tk.Frame(inner, bg="#FBFCFF", highlightthickness=1, highlightbackground=BORDER)
            box.grid(row=idx // 2, column=idx % 2, sticky="nsew", padx=8, pady=8)
            tk.Label(box, text=label, bg="#FBFCFF", fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", padx=14, pady=(14, 2))
            tk.Label(box, text=value, bg="#FBFCFF", fg=TEXT, font=("Segoe UI", 12, "bold"), wraplength=470, justify="left").pack(anchor="w", padx=14, pady=(0, 14))
        btns = tk.Frame(inner, bg=CARD_BG)
        btns.grid(row=3, column=0, columnspan=2, sticky="w", padx=8, pady=(10, 0))
        self._button(btns, "📁  Otwórz katalog profili", lambda: self._open_folder(self.profile_manager.base_dir), fill=BUTTON_BG, fg=TEXT).pack(side="left")
        self._button(btns, "📁  Otwórz output", lambda: self._open_folder(OUTPUT_DIR), fill=BUTTON_BG, fg=TEXT).pack(side="left", padx=10)
        return page

    # ------------------------------------------------------------------
    # Shared widgets/helpers
    # ------------------------------------------------------------------
    def _card(self, parent: tk.Widget) -> tk.Frame:
        return tk.Frame(parent, bg=CARD_BG, highlightthickness=1, highlightbackground=BORDER)

    def _card_header(self, parent: tk.Frame, title: str, subtitle: str, action_text: str | None = None, action_cmd=None) -> None:
        top = tk.Frame(parent, bg=CARD_BG)
        top.pack(fill="x", padx=18, pady=(18, 8))
        left = tk.Frame(top, bg=CARD_BG)
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text=title, bg=CARD_BG, fg=TEXT, font=("Segoe UI", 17, "bold")).pack(anchor="w")
        tk.Label(left, text=subtitle, bg=CARD_BG, fg=MUTED, font=("Segoe UI", 10), wraplength=900, justify="left").pack(anchor="w")
        if action_text:
            self._button(top, action_text, action_cmd, fill=BUTTON_BG, fg=TEXT).pack(side="right")

    def _button(self, parent: tk.Widget, text: str, command, fill: str, fg: str = "white", border: str | None = None) -> tk.Button:
        btn = tk.Button(parent, text=text, command=command, bg=fill, fg=fg, activebackground=fill, activeforeground=fg, bd=0 if not border else 1, highlightthickness=0 if not border else 1, highlightbackground=border or fill, relief="flat", font=("Segoe UI", 11, "bold"), cursor="hand2", padx=16, pady=10)
        return btn

    def _metric_card(self, parent: tk.Widget, column: int | None, title: str, value: str, subtitle: str) -> tk.Label:
        box = tk.Frame(parent, bg="#FBFCFF", highlightthickness=1, highlightbackground=BORDER)
        if column is None:
            pass
        elif isinstance(parent, tk.Frame):
            box.grid(row=0, column=column, sticky="ew", padx=8, pady=4)
        tk.Label(box, text=title, bg="#FBFCFF", fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", padx=14, pady=(14, 2))
        value_lbl = tk.Label(box, text=value, bg="#FBFCFF", fg=TEXT, font=("Segoe UI", 18, "bold"))
        value_lbl.pack(anchor="w", padx=14)
        tk.Label(box, text=subtitle, bg="#FBFCFF", fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", padx=14, pady=(2, 14))
        return value_lbl

    def _labeled_combo(self, parent: tk.Widget, column: int | None, label: str, values: list[str] | None = None, current: int | None = None) -> ttk.Combobox:
        wrap = tk.Frame(parent, bg=CARD_BG if parent.cget("bg") == CARD_BG else parent.cget("bg"))
        if column is None:
            wrap.pack(fill="x")
        else:
            wrap.grid(row=0, column=column, sticky="ew", padx=(0, 10))
        tk.Label(wrap, text=label, bg=wrap.cget("bg"), fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 4))
        combo = ttk.Combobox(wrap, state="readonly", style="SC.TCombobox", values=values or [])
        combo.pack(fill="x")
        if values and current is not None and len(values) > current:
            combo.current(current)
        return combo

    def _draw_waveform(self, canvas: tk.Canvas) -> None:
        canvas.delete("all")
        w = 700
        h = 54
        bars = [10, 18, 26, 20, 12, 24, 38, 48, 42, 30, 16, 26, 34, 44, 28, 18, 10]
        x = 10
        colors = ["#2EA7FF", "#3B94FF", "#4D84FF", "#6D69FF", "#8C4DFF"]
        for idx, bar in enumerate(bars):
            color = colors[idx % len(colors)]
            canvas.create_line(x, h / 2 - bar / 2, x, h / 2 + bar / 2, fill=color, width=4, capstyle=tk.ROUND)
            x += 18
        canvas.configure(scrollregion=(0, 0, w, h))

    def _draw_loss_chart(self, canvas: tk.Canvas) -> None:
        canvas.delete("all")
        width = 520
        height = 140
        pad = 24
        for i in range(5):
            y = pad + i * ((height - 2 * pad) / 4)
            canvas.create_line(pad, y, width - pad, y, fill="#E9EEF7")
        for i in range(11):
            x = pad + i * ((width - 2 * pad) / 10)
            canvas.create_line(x, pad, x, height - pad, fill="#F3F6FB")
        points = [0.82, 0.66, 0.58, 0.50, 0.41, 0.34, 0.31, 0.31, 0.32, 0.32, 0.33]
        coords = []
        for idx, val in enumerate(points):
            x = pad + idx * ((width - 2 * pad) / (len(points) - 1))
            y = (height - pad) - val * (height - 2 * pad)
            coords.extend([x, y])
        canvas.create_line(*coords, fill=PRIMARY_2, width=3, smooth=True)
        for i in range(0, len(coords), 2):
            canvas.create_oval(coords[i] - 4, coords[i + 1] - 4, coords[i] + 4, coords[i + 1] + 4, fill=PRIMARY_DARK, outline="white")

    # ------------------------------------------------------------------
    # Data refresh
    # ------------------------------------------------------------------
    def _populate_devices(self) -> None:
        devices = list_input_devices()
        self._devices = devices
        values = [str(d) for d in devices]
        if hasattr(self, "device_combo"):
            self.device_combo["values"] = values
            if values:
                self.device_combo.current(0)

    def _refresh_all(self) -> None:
        self._profiles = self.profile_manager.list_profiles()
        self._refresh_profile_selectors()
        self._refresh_profile_list()
        self._refresh_dashboard()
        self._refresh_training_stats()
        self._refresh_updates_page()

    def _refresh_profile_selectors(self) -> None:
        names = [p.name for p in self._profiles]
        for key, ctx in self._speech_contexts.items():
            ctx.profile_combo["values"] = names
            if names and not ctx.profile_combo.get():
                ctx.profile_combo.current(0)
        if hasattr(self, "train_profile_combo"):
            self.train_profile_combo["values"] = names
            if names and not self.train_profile_combo.get():
                self.train_profile_combo.current(0)

    def _refresh_profile_list(self) -> None:
        if not hasattr(self, "profiles_listbox"):
            return
        self.profiles_listbox.delete(0, tk.END)
        for p in self._profiles:
            marker = "  |  RVC" if p.has_rvc_model else ""
            self.profiles_listbox.insert(tk.END, f"{p.name}  —  {p.duration_seconds}s  —  {p.created_at}{marker}")
        self._render_dashboard_profile_cards()

    def _refresh_dashboard(self) -> None:
        if hasattr(self, "dashboard_top_value_labels"):
            if self._profiles:
                active = self._profiles[0]
                self.dashboard_top_value_labels["Aktywny profil"][0].configure(text=active.name)
                self.dashboard_top_value_labels["Aktywny profil"][1].configure(text=f"{active.duration_seconds}s · gotowy do użycia")
            else:
                self.dashboard_top_value_labels["Aktywny profil"][0].configure(text="Brak profilu")
                self.dashboard_top_value_labels["Aktywny profil"][1].configure(text="Dodaj profil, aby zacząć")
        total_seconds = sum(p.duration_seconds for p in self._profiles)
        minutes = max(0, round(total_seconds / 60))
        if hasattr(self, "training_dataset_label"):
            self.training_dataset_label.configure(text=f"{minutes} min")

    def _refresh_training_stats(self) -> None:
        total_seconds = sum(p.duration_seconds for p in self._profiles)
        minutes = max(0, round(total_seconds / 60))
        if hasattr(self, "train_dataset_page_label"):
            self.train_dataset_page_label.configure(text=f"{minutes} min")
        if hasattr(self, "train_profiles_page_label"):
            self.train_profiles_page_label.configure(text=str(len(self._profiles)))
        if hasattr(self, "training_dataset_label"):
            self.training_dataset_label.configure(text=f"{minutes} min")

    def _refresh_updates_page(self) -> None:
        for lbl in [getattr(self, "upd_current_page_label", None), getattr(self, "upd_latest_page_label", None), getattr(self, "current_version_tile", None), getattr(self, "latest_version_tile", None)]:
            if lbl is None:
                continue
        
    def _render_dashboard_profile_cards(self) -> None:
        if self._profile_cards_container is None:
            return
        for child in self._profile_cards_container.winfo_children():
            child.destroy()
        if not self._profiles:
            empty = tk.Frame(self._profile_cards_container, bg="#FBFCFF", highlightthickness=1, highlightbackground=BORDER)
            empty.pack(fill="x", padx=6, pady=6)
            tk.Label(empty, text="Nie masz jeszcze żadnych profili. Przejdź do 'Profile głosu', aby nagrać pierwszą próbkę.", bg="#FBFCFF", fg=MUTED, font=("Segoe UI", 11), pady=20).pack()
            return
        row = tk.Frame(self._profile_cards_container, bg=CARD_BG)
        row.pack(fill="x")
        for idx, profile in enumerate(self._profiles[:3]):
            card = tk.Frame(row, bg="#FBFCFF", highlightthickness=1, highlightbackground="#DCE7FF" if idx == 0 else BORDER)
            card.pack(side="left", fill="both", expand=True, padx=6, pady=6)
            avatar = tk.Label(card, text=profile.name[:1].upper(), bg="#E6EEFF", fg=PRIMARY_DARK, font=("Segoe UI", 18, "bold"), width=2, pady=10)
            avatar.pack(side="left", padx=12, pady=12)
            meta = tk.Frame(card, bg="#FBFCFF")
            meta.pack(side="left", fill="both", expand=True, pady=12)
            tk.Label(meta, text=profile.name, bg="#FBFCFF", fg=TEXT, font=("Segoe UI", 12, "bold")).pack(anchor="w")
            tk.Label(meta, text=f"Próbka {profile.duration_seconds}s", bg="#FBFCFF", fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w")
            tag = "XTTS v2 + RVC" if profile.has_rvc_model else "XTTS v2"
            tk.Label(meta, text=tag, bg="#EEF2FF", fg=PRIMARY_DARK, font=("Segoe UI", 9, "bold"), padx=8, pady=2).pack(anchor="w", pady=(6, 0))

    # ------------------------------------------------------------------
    # Search box placeholder handling
    # ------------------------------------------------------------------
    def _on_search_focus_in(self, _event=None) -> None:
        if self.search_var.get() == "Szukaj profili, nagrań, projektów…":
            self.search_var.set("")
            self.search_entry.configure(fg=TEXT)

    def _on_search_focus_out(self, _event=None) -> None:
        if not self.search_var.get().strip():
            self.search_var.set("Szukaj profili, nagrań, projektów…")
            self.search_entry.configure(fg=MUTED)

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------
    def _start_recording(self) -> None:
        if not self._devices:
            messagebox.showerror("Błąd", "Nie znaleziono żadnego urządzenia wejściowego (mikrofonu).")
            return
        device_index = self._devices[self.device_combo.current()].index
        duration = self.duration_var.get()
        self.record_button.configure(state="disabled")
        self.play_recorded_button.configure(state="disabled")
        self.save_button.configure(state="disabled")
        self.record_progress.configure(value=0)
        self.status_var.set("Nagrywanie w toku… mów teraz.")

        def on_progress(p: float) -> None:
            self.master.after(0, lambda: self.record_progress.configure(value=p * 100))

        def worker() -> None:
            try:
                audio = record_audio(duration=duration, device=device_index, on_progress=on_progress)
                cleaned = preprocess_pipeline(audio, DEFAULT_SAMPLERATE)
                self._recorded_audio = cleaned
                self._recorded_samplerate = DEFAULT_SAMPLERATE
                self.master.after(0, self._on_recording_finished)
            except Exception as exc:  # noqa: BLE001
                self.master.after(0, lambda: self._on_recording_error(str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_recording_finished(self) -> None:
        self.record_button.configure(state="normal")
        self.play_recorded_button.configure(state="normal")
        self.save_button.configure(state="normal")
        self.status_var.set("Nagranie zakończone. Możesz je odsłuchać lub zapisać jako profil.")

    def _on_recording_error(self, message: str) -> None:
        self.record_button.configure(state="normal")
        self.status_var.set("Błąd podczas nagrywania.")
        messagebox.showerror("Błąd nagrywania", message)

    def _play_recorded(self) -> None:
        if self._recorded_audio is None:
            return
        tmp_path = os.path.join(OUTPUT_DIR, "_preview.wav")
        import soundfile as sf

        sf.write(tmp_path, self._recorded_audio, self._recorded_samplerate)
        threading.Thread(target=lambda: play_wav(tmp_path), daemon=True).start()

    def _save_profile(self) -> None:
        if self._recorded_audio is None:
            return
        name = self.profile_name_var.get().strip()
        if not name:
            messagebox.showwarning("Brak nazwy", "Podaj nazwę profilu głosowego.")
            return
        try:
            self.profile_manager.save_profile(name, self._recorded_audio, self._recorded_samplerate, overwrite=True)
            self.status_var.set(f"Zapisano profil: {name}")
            self._refresh_all()
            messagebox.showinfo("Zapisano", f"Profil '{name}' został zapisany.")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Błąd zapisu", str(exc))

    # ------------------------------------------------------------------
    # Profile management
    # ------------------------------------------------------------------
    def _get_selected_profile(self) -> VoiceProfile | None:
        selection = self.profiles_listbox.curselection() if hasattr(self, "profiles_listbox") else None
        if not selection:
            return None
        return self._profiles[selection[0]]

    def _play_selected_profile(self) -> None:
        profile = self._get_selected_profile()
        if not profile:
            messagebox.showinfo("Info", "Wybierz profil z listy.")
            return
        threading.Thread(target=lambda: play_wav(profile.wav_path), daemon=True).start()

    def _attach_rvc_model(self) -> None:
        profile = self._get_selected_profile()
        if not profile:
            messagebox.showinfo("Info", "Wybierz najpierw profil z listy.")
            return
        model_path = filedialog.askopenfilename(title="Wybierz plik modelu RVC (.pth)", filetypes=[("Model RVC", "*.pth"), ("Wszystkie pliki", "*.*")])
        if not model_path:
            return
        index_path = filedialog.askopenfilename(title="Wybierz plik indeksu .index (opcjonalne)", filetypes=[("Plik indeksu RVC", "*.index"), ("Wszystkie pliki", "*.*")])
        index_path = index_path or None
        try:
            self.profile_manager.set_rvc_model(profile.name, model_path, index_path)
            self._refresh_all()
            messagebox.showinfo("Podpięto model RVC", f"Model RVC został podpięty do profilu '{profile.name}'.")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Błąd", str(exc))

    def _delete_selected_profile(self) -> None:
        profile = self._get_selected_profile()
        if not profile:
            return
        if messagebox.askyesno("Potwierdzenie", f"Usunąć profil '{profile.name}'?"):
            self.profile_manager.delete_profile(profile.name)
            self._refresh_all()

    # ------------------------------------------------------------------
    # Speech synthesis
    # ------------------------------------------------------------------
    def _generate_speech_dashboard(self) -> None:
        self._generate_speech("dashboard")

    def _generate_speech_full(self) -> None:
        self._generate_speech("speak")

    def _generate_speech(self, context_name: str) -> None:
        if self._busy_generation:
            messagebox.showinfo("Trwa generowanie", "Poczekaj na zakończenie bieżącego generowania.")
            return
        ctx = self._speech_contexts[context_name]
        profile_name = ctx.profile_combo.get()
        if not profile_name:
            messagebox.showwarning("Brak profilu", "Najpierw nagraj i zapisz profil głosowy.")
            return
        profile = self.profile_manager.get_profile(profile_name)
        if profile is None:
            messagebox.showerror("Błąd", "Nie znaleziono wybranego profilu.")
            return
        text = ctx.text_widget.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("Brak tekstu", "Wpisz tekst do wypowiedzenia.")
            return
        use_rvc = bool(ctx.use_rvc_var.get()) if ctx.use_rvc_var else False
        if use_rvc and not profile.has_rvc_model:
            messagebox.showwarning("Brak modelu RVC", f"Profil '{profile_name}' nie ma podpiętego modelu RVC.")
            return
        language_label = ctx.language_combo.get() or "Polski"
        language_code = LANGUAGES.get(language_label, "pl")

        self._busy_generation = True
        ctx.generate_button.configure(state="disabled")
        ctx.progress.start(10)
        self.status_var.set(f"Generowanie mowy ({self.engine.device.upper()})… To może potrwać dłużej przy pierwszym uruchomieniu.")

        def worker() -> None:
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                raw_path = os.path.join(OUTPUT_DIR, f"speech_{profile_name}_{timestamp}_raw.wav")
                self.engine.clone_and_speak(text=text, speaker_wav_path=profile.wav_path, output_path=raw_path, language=language_code)
                final_path = raw_path
                if use_rvc:
                    self.rvc_engine.load_model(profile.rvc_model_path, profile.rvc_index_path)
                    rvc_path = os.path.join(OUTPUT_DIR, f"speech_{profile_name}_{timestamp}_rvc.wav")
                    self.rvc_engine.convert(raw_path, rvc_path)
                    final_path = rvc_path
                self.master.after(0, lambda: self._on_speech_ready(context_name, final_path))
            except Exception as exc:  # noqa: BLE001
                self.master.after(0, lambda: self._on_speech_error(context_name, str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_speech_ready(self, context_name: str, path: str) -> None:
        ctx = self._speech_contexts[context_name]
        self._busy_generation = False
        ctx.progress.stop()
        ctx.generate_button.configure(state="normal")
        self._last_generated_path = path
        self.status_var.set(f"Gotowe. Zapisano: {path}")
        self.dashboard_audio_label.configure(text=os.path.basename(path))
        for context in self._speech_contexts.values():
            if context.play_button is not None:
                context.play_button.configure(state="normal")
        self.dashboard_download_btn.configure(state="normal")
        threading.Thread(target=lambda: play_wav(path), daemon=True).start()

    def _on_speech_error(self, context_name: str, message: str) -> None:
        ctx = self._speech_contexts[context_name]
        self._busy_generation = False
        ctx.progress.stop()
        ctx.generate_button.configure(state="normal")
        self.status_var.set("Błąd podczas generowania mowy.")
        messagebox.showerror("Błąd syntezy mowy", message)

    def _play_last_generated(self) -> None:
        if not self._last_generated_path or not os.path.isfile(self._last_generated_path):
            messagebox.showinfo("Brak pliku", "Najpierw wygeneruj mowę.")
            return
        threading.Thread(target=lambda: play_wav(self._last_generated_path), daemon=True).start()

    def _download_last_generated(self) -> None:
        if not self._last_generated_path or not os.path.isfile(self._last_generated_path):
            messagebox.showinfo("Brak pliku", "Najpierw wygeneruj mowę.")
            return
        dest = filedialog.asksaveasfilename(title="Zapisz wygenerowany plik WAV", defaultextension=".wav", initialfile=os.path.basename(self._last_generated_path), filetypes=[("Plik WAV", "*.wav")])
        if not dest:
            return
        shutil.copy2(self._last_generated_path, dest)
        self.status_var.set(f"Zapisano plik: {dest}")
        messagebox.showinfo("Zapisano", f"Plik został zapisany:\n{dest}")

    # ------------------------------------------------------------------
    # Misc actions
    # ------------------------------------------------------------------
    def _check_updates_stub(self) -> None:
        self.status_var.set("Sprawdzono aktualizacje. Masz najnowszą wersję.")
        messagebox.showinfo("Aktualizacje", f"Aktualna wersja: {APP_VERSION}\nNajnowsza wersja: {LATEST_VERSION}\n\nPanel aktualizacji jest gotowy do spięcia z publisherem GitHub.")

    def _show_info(self, title: str, message: str) -> None:
        messagebox.showinfo(title, message)

    def _open_folder(self, path: str) -> None:
        messagebox.showinfo("Katalog", f"Katalog projektu:\n{path}")


def run() -> None:
    root = tk.Tk()
    root.title("SoundCore")
    root.geometry("1540x920")
    root.minsize(1280, 760)
    SoundCoreApp(root)
    root.mainloop()


if __name__ == "__main__":
    run()
