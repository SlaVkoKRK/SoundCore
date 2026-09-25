"""
app.py
------
Graficzny interfejs użytkownika (Tkinter) dla aplikacji SoundCore.

Trzy zakładki:
    1. Nagrywanie      - nagranie próbki głosu z mikrofonu i zapis jako profil.
    2. Profile głosowe - lista zapisanych profili, odtwarzanie próbki, usuwanie.
    3. Synteza mowy    - wpisanie tekstu i wygenerowanie mowy w wybranym głosie.

Operacje czasochłonne (nagrywanie z paskiem postępu, ładowanie modelu TTS,
generowanie mowy) są wykonywane w osobnych wątkach, aby nie blokować GUI.
"""

from __future__ import annotations

import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from recorder.recorder import list_input_devices, record_audio, play_wav, DEFAULT_SAMPLERATE
from preprocessing.audio_utils import preprocess_pipeline
from storage.profile_manager import ProfileManager
from voice_engine.tts_engine import get_engine
from voice_engine.rvc_engine import get_rvc_engine
from training.dataset import append_sample, get_stats, load_prompts
from training.manager import TrainingProcess, available_devices
from updater.update_manager import check_for_update, read_release_notes, download_and_stage, launch_apply_update
from version import __version__

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

LANGUAGES = {
    "Polski": "pl",
    "Angielski": "en",
    "Niemiecki": "de",
    "Francuski": "fr",
    "Hiszpański": "es",
}


class SoundCoreApp(ttk.Frame):
    def __init__(self, master: tk.Tk) -> None:
        super().__init__(master)
        self.master = master
        self.profile_manager = ProfileManager()
        self.engine = get_engine()
        self.rvc_engine = get_rvc_engine()
        self.training_process = TrainingProcess()
        self._training_log_lines = []
        self._last_update_info = None

        self._recorded_audio = None
        self._recorded_samplerate = DEFAULT_SAMPLERATE

        self.pack(fill="both", expand=True)
        self._build_ui()
        self._refresh_profile_list()

    # ------------------------------------------------------------------
    # Budowa interfejsu
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.tab_record = ttk.Frame(notebook)
        self.tab_profiles = ttk.Frame(notebook)
        self.tab_speak = ttk.Frame(notebook)
        self.tab_train = ttk.Frame(notebook)
        self.tab_updates = ttk.Frame(notebook)

        notebook.add(self.tab_record, text="🎙️ Nagrywanie")
        notebook.add(self.tab_profiles, text="👤 Profile głosowe")
        notebook.add(self.tab_speak, text="🔊 Synteza mowy")
        notebook.add(self.tab_train, text="🧠 Trening modelu")
        notebook.add(self.tab_updates, text="⬆ Aktualizacje")

        self._build_record_tab()
        self._build_profiles_tab()
        self._build_speak_tab()
        self._build_train_tab()
        self._build_updates_tab()

        # Pasek statusu na dole okna
        self.status_var = tk.StringVar(value=f"SoundCore {__version__} · TTS: {self.engine.device.upper()}")
        status_bar = ttk.Label(self.master, textvariable=self.status_var, anchor="w", relief="sunken")
        status_bar.pack(fill="x", side="bottom")

    # ---------------------- Zakładka: Nagrywanie ----------------------
    def _build_record_tab(self) -> None:
        frame = self.tab_record
        pad = {"padx": 10, "pady": 6}

        ttk.Label(frame, text="Urządzenie wejściowe (mikrofon):").grid(row=0, column=0, sticky="w", **pad)
        self.device_combo = ttk.Combobox(frame, state="readonly", width=50)
        self.device_combo.grid(row=0, column=1, columnspan=2, sticky="w", **pad)
        self._populate_devices()

        ttk.Button(frame, text="🔄 Odśwież listę", command=self._populate_devices).grid(
            row=0, column=3, **pad
        )

        ttk.Label(frame, text="Długość nagrania (sekundy):").grid(row=1, column=0, sticky="w", **pad)
        self.duration_var = tk.IntVar(value=20)
        ttk.Spinbox(frame, from_=5, to=120, textvariable=self.duration_var, width=10).grid(
            row=1, column=1, sticky="w", **pad
        )

        ttk.Label(
            frame,
            text="Wskazówka: mów naturalnie, wyraźnie, przez min. 15-20 sekund,\n"
                 "aby model mógł dobrze uchwycić barwę głosu i dykcję.",
            foreground="gray",
        ).grid(row=2, column=0, columnspan=4, sticky="w", **pad)

        self.record_button = ttk.Button(frame, text="⏺ Rozpocznij nagrywanie", command=self._start_recording)
        self.record_button.grid(row=3, column=0, sticky="w", **pad)

        self.progress = ttk.Progressbar(frame, length=300, mode="determinate", maximum=100)
        self.progress.grid(row=3, column=1, columnspan=2, sticky="w", **pad)

        ttk.Separator(frame, orient="horizontal").grid(row=4, column=0, columnspan=4, sticky="ew", pady=10)

        ttk.Label(frame, text="Nazwa profilu głosowego:").grid(row=5, column=0, sticky="w", **pad)
        self.profile_name_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.profile_name_var, width=30).grid(row=5, column=1, sticky="w", **pad)

        self.save_button = ttk.Button(
            frame, text="💾 Zapisz jako profil głosowy", command=self._save_profile, state="disabled"
        )
        self.save_button.grid(row=5, column=2, sticky="w", **pad)

        self.play_recorded_button = ttk.Button(
            frame, text="▶ Odsłuchaj nagranie", command=self._play_recorded, state="disabled"
        )
        self.play_recorded_button.grid(row=5, column=3, sticky="w", **pad)

    def _populate_devices(self) -> None:
        devices = list_input_devices()
        self._devices = devices
        self.device_combo["values"] = [str(d) for d in devices]
        if devices:
            self.device_combo.current(0)

    def _start_recording(self) -> None:
        if not self._devices:
            messagebox.showerror("Błąd", "Nie znaleziono żadnego urządzenia wejściowego (mikrofonu).")
            return

        device_index = self._devices[self.device_combo.current()].index
        duration = self.duration_var.get()

        self.record_button.config(state="disabled")
        self.save_button.config(state="disabled")
        self.play_recorded_button.config(state="disabled")
        self.progress["value"] = 0
        self.status_var.set("Nagrywanie w toku... mów teraz.")

        def on_progress(p: float) -> None:
            self.master.after(0, lambda: self.progress.config(value=p * 100))

        def worker() -> None:
            try:
                audio = record_audio(
                    duration=duration,
                    device=device_index,
                    on_progress=on_progress,
                )
                cleaned = preprocess_pipeline(audio, DEFAULT_SAMPLERATE)
                self._recorded_audio = cleaned
                self._recorded_samplerate = DEFAULT_SAMPLERATE
                self.master.after(0, self._on_recording_finished)
            except Exception as exc:  # noqa: BLE001
                error_message = str(exc)
                self.master.after(0, lambda: self._on_recording_error(error_message))

        threading.Thread(target=worker, daemon=True).start()

    def _on_recording_finished(self) -> None:
        self.status_var.set("Nagranie zakończone. Możesz je odsłuchać lub zapisać jako profil.")
        self.record_button.config(state="normal")
        self.save_button.config(state="normal")
        self.play_recorded_button.config(state="normal")

    def _on_recording_error(self, message: str) -> None:
        self.status_var.set("Błąd podczas nagrywania.")
        self.record_button.config(state="normal")
        messagebox.showerror("Błąd nagrywania", message)

    def _play_recorded(self) -> None:
        if self._recorded_audio is None:
            return
        tmp_path = os.path.join(OUTPUT_DIR, "_preview.wav")
        import soundfile as sf

        sf.write(tmp_path, self._recorded_audio, self._recorded_samplerate)

        def worker() -> None:
            play_wav(tmp_path)

        threading.Thread(target=worker, daemon=True).start()

    def _save_profile(self) -> None:
        if self._recorded_audio is None:
            return
        name = self.profile_name_var.get().strip()
        if not name:
            messagebox.showwarning("Brak nazwy", "Podaj nazwę profilu głosowego.")
            return
        try:
            self.profile_manager.save_profile(
                name, self._recorded_audio, self._recorded_samplerate, overwrite=True
            )
            messagebox.showinfo("Zapisano", f"Profil '{name}' został zapisany.")
            self._refresh_profile_list()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Błąd zapisu", str(exc))

    # ---------------------- Zakładka: Profile głosowe ----------------------
    def _build_profiles_tab(self) -> None:
        frame = self.tab_profiles
        pad = {"padx": 10, "pady": 6}

        self.profiles_listbox = tk.Listbox(frame, width=60, height=12)
        self.profiles_listbox.grid(row=0, column=0, columnspan=3, sticky="nsew", **pad)

        ttk.Button(frame, text="🔄 Odśwież", command=self._refresh_profile_list).grid(
            row=1, column=0, sticky="w", **pad
        )
        ttk.Button(frame, text="▶ Odtwórz próbkę", command=self._play_selected_profile).grid(
            row=1, column=1, sticky="w", **pad
        )
        ttk.Button(frame, text="🗑 Usuń profil", command=self._delete_selected_profile).grid(
            row=1, column=2, sticky="w", **pad
        )
        ttk.Button(frame, text="🎚 Podepnij model RVC", command=self._attach_rvc_model).grid(
            row=1, column=3, sticky="w", **pad
        )

        ttk.Label(
            frame,
            text="Model RVC to opcjonalny, dodatkowy krok poprawiający wierność barwy głosu.\n"
                 "Trenuje się go osobno (patrz README.md), a tutaj tylko podpinasz gotowy plik .pth\n"
                 "(i opcjonalnie .index) do wybranego profilu.",
            foreground="gray",
            justify="left",
        ).grid(row=2, column=0, columnspan=4, sticky="w", **pad)

    def _refresh_profile_list(self) -> None:
        self.profiles_listbox.delete(0, tk.END)
        self._profiles = self.profile_manager.list_profiles()
        for p in self._profiles:
            rvc_marker = "  🎚RVC" if p.has_rvc_model else ""
            trained_marker = "  🧠XTTS-FT" if p.has_trained_model else ""
            self.profiles_listbox.insert(
                tk.END, f"{p.name}  —  {p.duration_seconds}s  —  utworzono {p.created_at}{trained_marker}{rvc_marker}"
            )
        # odśwież też listę w zakładce syntezy mowy
        names = [p.name for p in self._profiles]
        if hasattr(self, "speak_profile_combo"):
            self.speak_profile_combo["values"] = names
            if names and not self.speak_profile_combo.get():
                self.speak_profile_combo.current(0)
        if hasattr(self, "train_profile_combo"):
            self.train_profile_combo["values"] = names
            if names and not self.train_profile_combo.get():
                self.train_profile_combo.current(0)
                self._refresh_training_dataset()

    def _attach_rvc_model(self) -> None:
        profile = self._get_selected_profile()
        if not profile:
            messagebox.showinfo("Info", "Wybierz najpierw profil z listy.")
            return

        model_path = filedialog.askopenfilename(
            title="Wybierz plik modelu RVC (.pth)",
            filetypes=[("Model RVC", "*.pth"), ("Wszystkie pliki", "*.*")],
        )
        if not model_path:
            return

        index_path = filedialog.askopenfilename(
            title="Wybierz plik indeksu .index (opcjonalne - Anuluj, aby pominąć)",
            filetypes=[("Plik indeksu RVC", "*.index"), ("Wszystkie pliki", "*.*")],
        )
        index_path = index_path or None

        try:
            self.profile_manager.set_rvc_model(profile.name, model_path, index_path)
            messagebox.showinfo(
                "Podpięto model RVC",
                f"Model RVC został podpięty do profilu '{profile.name}'.\n"
                "Pamiętaj, aby zaznaczyć opcję konwersji RVC w zakładce 'Synteza mowy'.",
            )
            self._refresh_profile_list()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Błąd", str(exc))

    def _get_selected_profile(self):
        selection = self.profiles_listbox.curselection()
        if not selection:
            return None
        return self._profiles[selection[0]]

    def _play_selected_profile(self) -> None:
        profile = self._get_selected_profile()
        if not profile:
            messagebox.showinfo("Info", "Wybierz profil z listy.")
            return
        threading.Thread(target=lambda: play_wav(profile.wav_path), daemon=True).start()

    def _delete_selected_profile(self) -> None:
        profile = self._get_selected_profile()
        if not profile:
            return
        if messagebox.askyesno("Potwierdzenie", f"Usunąć profil '{profile.name}'?"):
            self.profile_manager.delete_profile(profile.name)
            self._refresh_profile_list()

    # ---------------------- Zakładka: Synteza mowy ----------------------
    def _build_speak_tab(self) -> None:
        frame = self.tab_speak
        pad = {"padx": 10, "pady": 6}

        ttk.Label(frame, text="Profil głosowy:").grid(row=0, column=0, sticky="w", **pad)
        self.speak_profile_combo = ttk.Combobox(frame, state="readonly", width=30)
        self.speak_profile_combo.grid(row=0, column=1, sticky="w", **pad)

        ttk.Label(frame, text="Język:").grid(row=0, column=2, sticky="w", **pad)
        self.language_combo = ttk.Combobox(
            frame, state="readonly", width=15, values=list(LANGUAGES.keys())
        )
        self.language_combo.current(0)
        self.language_combo.grid(row=0, column=3, sticky="w", **pad)

        ttk.Label(frame, text="Tekst do wypowiedzenia:").grid(row=1, column=0, sticky="nw", **pad)
        self.text_input = tk.Text(frame, width=60, height=8, wrap="word")
        self.text_input.grid(row=1, column=1, columnspan=3, sticky="w", **pad)
        self.text_input.insert("1.0", "Witaj, to jest przykładowy tekst wypowiedziany moim własnym głosem.")

        self.generate_button = ttk.Button(
            frame, text="🎧 Generuj i odtwórz", command=self._generate_speech
        )
        self.generate_button.grid(row=2, column=1, sticky="w", **pad)

        self.speak_progress = ttk.Progressbar(frame, length=250, mode="indeterminate")
        self.speak_progress.grid(row=2, column=2, columnspan=2, sticky="w", **pad)

        self.use_trained_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            frame,
            text="🧠 Użyj wytrenowanego modelu XTTS, jeśli profil go posiada",
            variable=self.use_trained_var,
        ).grid(row=3, column=0, columnspan=4, sticky="w", padx=10, pady=(0, 4))

        self.use_rvc_var = tk.BooleanVar(value=False)
        self.rvc_checkbox = ttk.Checkbutton(
            frame,
            text="🎚 Popraw barwę głosu przez RVC (wymaga podpiętego modelu w zakładce Profile)",
            variable=self.use_rvc_var,
        )
        self.rvc_checkbox.grid(row=4, column=0, columnspan=4, sticky="w", padx=10, pady=(0, 6))

    def _generate_speech(self) -> None:
        profile_name = self.speak_profile_combo.get()
        if not profile_name:
            messagebox.showwarning("Brak profilu", "Najpierw nagraj i zapisz profil głosowy.")
            return

        profile = self.profile_manager.get_profile(profile_name)
        if profile is None:
            messagebox.showerror("Błąd", "Nie znaleziono wybranego profilu.")
            return

        text = self.text_input.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("Brak tekstu", "Wpisz tekst do wypowiedzenia.")
            return

        language_label = self.language_combo.get() or "Polski"
        language_code = LANGUAGES.get(language_label, "pl")
        use_rvc = self.use_rvc_var.get()
        use_trained = self.use_trained_var.get() and profile.has_trained_model

        if use_rvc and not profile.has_rvc_model:
            messagebox.showwarning(
                "Brak modelu RVC",
                f"Profil '{profile_name}' nie ma podpiętego modelu RVC. "
                "Podepnij go w zakładce 'Profile głosowe' albo odznacz opcję RVC.",
            )
            return

        self.generate_button.config(state="disabled")
        self.speak_progress.start(10)
        self.status_var.set(
            f"Ładowanie modelu i generowanie mowy (urządzenie: {self.engine.device.upper()})... "
            "to może potrwać dłużej przy pierwszym uruchomieniu."
        )

        def worker() -> None:
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                raw_path = os.path.join(OUTPUT_DIR, f"speech_{profile_name}_{timestamp}_raw.wav")
                if use_trained:
                    self.master.after(0, lambda: self.status_var.set("Generowanie przez wytrenowany model XTTS..."))
                    self.engine.finetuned_speak(
                        text=text,
                        speaker_wav_path=profile.wav_path,
                        output_path=raw_path,
                        model_info=profile.trained_model_info,
                        language=language_code,
                    )
                else:
                    self.engine.clone_and_speak(
                        text=text,
                        speaker_wav_path=profile.wav_path,
                        output_path=raw_path,
                        language=language_code,
                    )

                final_path = raw_path
                if use_rvc:
                    self.master.after(
                        0, lambda: self.status_var.set("Poprawianie barwy głosu przez RVC...")
                    )
                    rvc_path = os.path.join(OUTPUT_DIR, f"speech_{profile_name}_{timestamp}_rvc.wav")
                    self.rvc_engine.load_model(profile.rvc_model_path, profile.rvc_index_path)
                    self.rvc_engine.convert(raw_path, rvc_path)
                    final_path = rvc_path

                self.master.after(0, lambda: self._on_speech_ready(final_path))
            except Exception as exc:  # noqa: BLE001
                error_message = str(exc)
                self.master.after(0, lambda: self._on_speech_error(error_message))

        threading.Thread(target=worker, daemon=True).start()

    def _on_speech_ready(self, path: str) -> None:
        self.speak_progress.stop()
        self.generate_button.config(state="normal")
        self.status_var.set(f"Gotowe. Zapisano: {path}")
        threading.Thread(target=lambda: play_wav(path), daemon=True).start()

    def _on_speech_error(self, message: str) -> None:
        self.speak_progress.stop()
        self.generate_button.config(state="normal")
        self.status_var.set("Błąd podczas generowania mowy.")
        messagebox.showerror("Błąd syntezy mowy", message)

    # ---------------------- Zakładka: Trening modelu ----------------------
    def _build_train_tab(self) -> None:
        frame = self.tab_train
        pad = {"padx": 10, "pady": 5}

        ttk.Label(frame, text="Profil do trenowania:").grid(row=0, column=0, sticky="w", **pad)
        self.train_profile_combo = ttk.Combobox(frame, state="readonly", width=28)
        self.train_profile_combo.grid(row=0, column=1, sticky="w", **pad)
        self.train_profile_combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_training_dataset())

        ttk.Label(frame, text="Urządzenie:").grid(row=0, column=2, sticky="w", **pad)
        self.train_device_combo = ttk.Combobox(frame, state="readonly", width=28)
        self._train_devices = available_devices()
        self.train_device_combo["values"] = [d.label for d in self._train_devices]
        if self._train_devices:
            self.train_device_combo.current(0)
        self.train_device_combo.grid(row=0, column=3, sticky="w", **pad)

        ttk.Label(frame, text="Epoki:").grid(row=1, column=0, sticky="w", **pad)
        self.train_epochs_var = tk.IntVar(value=20)
        ttk.Spinbox(frame, from_=1, to=200, textvariable=self.train_epochs_var, width=8).grid(row=1, column=1, sticky="w", **pad)
        self.train_stats_var = tk.StringVar(value="Dataset: wybierz profil")
        ttk.Label(frame, textvariable=self.train_stats_var).grid(row=1, column=2, columnspan=2, sticky="w", **pad)

        data_box = ttk.LabelFrame(frame, text="Zbieranie datasetu")
        data_box.grid(row=2, column=0, columnspan=4, sticky="ew", padx=10, pady=8)
        self.train_prompt_var = tk.StringVar(value="Wybierz profil, aby rozpocząć zbieranie danych.")
        ttk.Label(data_box, textvariable=self.train_prompt_var, wraplength=690, font=("TkDefaultFont", 11)).grid(row=0, column=0, columnspan=4, sticky="w", padx=8, pady=8)
        self.dataset_duration_var = tk.IntVar(value=8)
        ttk.Label(data_box, text="Czas nagrania:").grid(row=1, column=0, sticky="w", padx=8, pady=5)
        ttk.Spinbox(data_box, from_=3, to=20, textvariable=self.dataset_duration_var, width=6).grid(row=1, column=1, sticky="w", padx=8, pady=5)
        self.dataset_record_btn = ttk.Button(data_box, text="⏺ Nagraj to zdanie", command=self._record_training_sample)
        self.dataset_record_btn.grid(row=1, column=2, padx=8, pady=5)
        ttk.Button(data_box, text="Następne zdanie", command=self._next_training_prompt).grid(row=1, column=3, padx=8, pady=5)

        controls = ttk.Frame(frame)
        controls.grid(row=3, column=0, columnspan=4, sticky="ew", padx=10, pady=5)
        self.train_start_btn = ttk.Button(controls, text="▶ Rozpocznij GPTTrainer", command=self._start_training)
        self.train_start_btn.pack(side="left", padx=(0, 8))
        self.train_stop_btn = ttk.Button(controls, text="■ Zatrzymaj", command=self._stop_training, state="disabled")
        self.train_stop_btn.pack(side="left")
        self.train_progress = ttk.Progressbar(controls, mode="indeterminate", length=240)
        self.train_progress.pack(side="left", padx=15)

        self.train_log = tk.Text(frame, height=13, width=92, wrap="word")
        self.train_log.grid(row=4, column=0, columnspan=4, sticky="nsew", padx=10, pady=6)
        frame.rowconfigure(4, weight=1)
        frame.columnconfigure(3, weight=1)

        ttk.Label(frame, text="CPU jest obsługiwane, ale trening XTTS będzie na nim bardzo wolny. GPU/CUDA jest zalecane.", foreground="gray").grid(row=5, column=0, columnspan=4, sticky="w", padx=10, pady=4)

    def _refresh_training_dataset(self) -> None:
        name = self.train_profile_combo.get()
        if not name:
            return
        profile = self.profile_manager.get_profile(name)
        if not profile:
            return
        stats = get_stats(profile.folder)
        self.train_stats_var.set(f"Dataset: {stats.samples} próbek · {stats.seconds/60:.1f} min")
        prompts = load_prompts(profile.folder)
        self._training_prompts = prompts
        self._training_prompt_index = stats.samples % len(prompts) if prompts else 0
        if prompts:
            self.train_prompt_var.set(prompts[self._training_prompt_index])

    def _next_training_prompt(self) -> None:
        prompts = getattr(self, "_training_prompts", [])
        if not prompts:
            self._refresh_training_dataset()
            prompts = getattr(self, "_training_prompts", [])
        if prompts:
            self._training_prompt_index = (getattr(self, "_training_prompt_index", 0) + 1) % len(prompts)
            self.train_prompt_var.set(prompts[self._training_prompt_index])

    def _record_training_sample(self) -> None:
        profile = self.profile_manager.get_profile(self.train_profile_combo.get())
        if not profile:
            messagebox.showwarning("Trening", "Wybierz profil głosowy.")
            return
        if not getattr(self, "_devices", None):
            messagebox.showerror("Mikrofon", "Brak urządzenia wejściowego. Odśwież listę w zakładce Nagrywanie.")
            return
        prompt = self.train_prompt_var.get().strip()
        device_index = self._devices[self.device_combo.current()].index if self.device_combo.current() >= 0 else self._devices[0].index
        duration = self.dataset_duration_var.get()
        self.dataset_record_btn.config(state="disabled")
        self.status_var.set("Nagrywanie próbki treningowej...")

        def worker():
            try:
                audio = record_audio(duration=duration, device=device_index)
                cleaned = preprocess_pipeline(audio, DEFAULT_SAMPLERATE)
                append_sample(profile.folder, cleaned, DEFAULT_SAMPLERATE, prompt)
                self.master.after(0, self._on_training_sample_saved)
            except Exception as exc:
                self.master.after(0, lambda: (self.dataset_record_btn.config(state="normal"), messagebox.showerror("Dataset", str(exc))))
        threading.Thread(target=worker, daemon=True).start()

    def _on_training_sample_saved(self) -> None:
        self.dataset_record_btn.config(state="normal")
        self.status_var.set("Próbka treningowa zapisana.")
        self._refresh_training_dataset()

    def _append_train_log(self, line: str) -> None:
        self.train_log.insert(tk.END, line + "\n")
        self.train_log.see(tk.END)

    def _start_training(self) -> None:
        profile = self.profile_manager.get_profile(self.train_profile_combo.get())
        if not profile:
            messagebox.showwarning("Trening", "Wybierz profil głosowy.")
            return
        stats = get_stats(profile.folder)
        if stats.samples < 5:
            messagebox.showwarning("Za mało danych", "Nagraj co najmniej 5 zdań. Do sensownego modelu zalecam 30+ i co najmniej kilka-kilkanaście minut audio.")
            return
        idx = self.train_device_combo.current()
        if idx < 0:
            idx = 0
        device = self._train_devices[idx].code
        epochs = self.train_epochs_var.get()
        self.train_log.delete("1.0", tk.END)
        self.train_start_btn.config(state="disabled")
        self.train_stop_btn.config(state="normal")
        self.train_progress.start(10)
        self.status_var.set(f"Trening XTTS GPT na {device.upper()}...")
        try:
            self.training_process.start(
                profile.folder, device, epochs,
                on_line=lambda line: self.master.after(0, lambda l=line: self._append_train_log(l)),
                on_done=lambda code: self.master.after(0, lambda c=code: self._on_training_done(c)),
            )
        except Exception as exc:
            self._on_training_done(1)
            messagebox.showerror("Trening", str(exc))

    def _stop_training(self) -> None:
        self.training_process.stop()
        self.status_var.set("Zatrzymywanie treningu...")

    def _on_training_done(self, code: int) -> None:
        self.train_progress.stop()
        self.train_start_btn.config(state="normal")
        self.train_stop_btn.config(state="disabled")
        if code == 0:
            self.status_var.set("Trening zakończony poprawnie.")
            messagebox.showinfo("Trening", "Trening zakończony. Checkpointy są zapisane w profilu: model/training.")
        else:
            self.status_var.set(f"Trening zakończył się kodem {code}.")

    # ---------------------- Zakładka: Aktualizacje ----------------------
    def _build_updates_tab(self) -> None:
        frame = self.tab_updates
        pad = {"padx": 12, "pady": 7}
        ttk.Label(frame, text="SoundCore", font=("TkDefaultFont", 16, "bold")).grid(row=0, column=0, sticky="w", **pad)
        ttk.Label(frame, text=f"Zainstalowana wersja: {__version__}").grid(row=1, column=0, sticky="w", **pad)
        self.update_status_var = tk.StringVar(value="Nie sprawdzano aktualizacji.")
        ttk.Label(frame, textvariable=self.update_status_var).grid(row=2, column=0, columnspan=2, sticky="w", **pad)
        self.update_check_btn = ttk.Button(frame, text="Sprawdź aktualizacje", command=self._check_updates)
        self.update_check_btn.grid(row=3, column=0, sticky="w", **pad)
        self.update_install_btn = ttk.Button(frame, text="Pobierz i zainstaluj", command=self._install_update, state="disabled")
        self.update_install_btn.grid(row=3, column=1, sticky="w", **pad)
        self.update_progress = ttk.Progressbar(frame, length=400, mode="determinate", maximum=100)
        self.update_progress.grid(row=4, column=0, columnspan=2, sticky="w", **pad)
        ttk.Label(frame, text="Informacje o wydaniu:").grid(row=5, column=0, sticky="w", **pad)
        self.update_notes = tk.Text(frame, width=80, height=14, wrap="word")
        self.update_notes.grid(row=6, column=0, columnspan=2, sticky="nsew", **pad)
        frame.rowconfigure(6, weight=1)
        frame.columnconfigure(1, weight=1)

    def _check_updates(self) -> None:
        self.update_check_btn.config(state="disabled")
        self.update_status_var.set("Sprawdzanie kanału aktualizacji...")
        def worker():
            try:
                info = check_for_update()
                notes = read_release_notes(info) if info.release_notes_url else ""
                self.master.after(0, lambda: self._on_update_checked(info, notes))
            except Exception as exc:
                self.master.after(0, lambda: self._on_update_error(str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def _on_update_checked(self, info, notes: str) -> None:
        self.update_check_btn.config(state="normal")
        self._last_update_info = info
        self.update_notes.delete("1.0", tk.END)
        self.update_notes.insert("1.0", notes or "Brak informacji o wydaniu.")
        if info.newer:
            self.update_status_var.set(f"Dostępna nowa wersja: {info.version}")
            self.update_install_btn.config(state="normal")
        else:
            self.update_status_var.set(f"Masz aktualną wersję ({__version__}).")
            self.update_install_btn.config(state="disabled")

    def _install_update(self) -> None:
        info = self._last_update_info
        if not info or not info.newer:
            return
        if not messagebox.askyesno("Aktualizacja SoundCore", f"Pobrać i zainstalować SoundCore {info.version}?\nProgram uruchomi się ponownie."):
            return
        self.update_install_btn.config(state="disabled")
        self.update_check_btn.config(state="disabled")
        self.update_status_var.set("Pobieranie i weryfikacja SHA256...")
        self.update_progress["value"] = 0
        def worker():
            try:
                staged = download_and_stage(info, progress=lambda p: self.master.after(0, lambda v=p: self.update_progress.config(value=v*100)))
                app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                self.master.after(0, lambda: self._apply_staged_update(staged, app_root))
            except Exception as exc:
                self.master.after(0, lambda: self._on_update_error(str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def _apply_staged_update(self, staged: str, app_root: str) -> None:
        self.update_status_var.set("Aktualizacja zweryfikowana. Restart SoundCore...")
        launch_apply_update(staged, app_root)
        self.master.destroy()

    def _on_update_error(self, message: str) -> None:
        self.update_check_btn.config(state="normal")
        self.update_install_btn.config(state="disabled")
        self.update_status_var.set("Błąd aktualizacji.")
        messagebox.showerror("Aktualizacje", message)


def run() -> None:
    root = tk.Tk()
    root.title(f"SoundCore {__version__} - AI SoundSystem")
    root.geometry("860x650")
    SoundCoreApp(root)
    root.mainloop()


if __name__ == "__main__":
    run()
