import shutil
import sys
import re
import ctypes
import json
import os
import traceback
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

from PIL import Image, ImageTk

try:
    import customtkinter as ctk

    CTK_AVAILABLE = True
except ImportError:
    ctk = None
    CTK_AVAILABLE = False

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False
    DND_FILES = None
    TkinterDnD = None


try:
    RESAMPLE_FILTER = Image.Resampling.LANCZOS
except AttributeError:
    RESAMPLE_FILTER = Image.LANCZOS


# === caminhos principais ===
SCRIPT_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
LOG_FILE = APP_DIR / "launcher_error.log"
USER_HOME = Path.home()
CONFIG_DIR = USER_HOME / "AppData" / "Local" / "SoeCharacterLauncher"
CONFIG_FILE = CONFIG_DIR / "settings.json"

DEFAULT_BASE_PATH = (
    USER_HOME
    / "AppData"
    / "Local"
    / "WildLifeC"
    / "Saved"
    / "SandboxSaveGames"
)

ICON_PATH = SCRIPT_DIR / "ICO"


def load_saved_base_path():
    try:
        if CONFIG_FILE.exists():
            with CONFIG_FILE.open("r", encoding="utf-8") as config_file:
                config = json.load(config_file)

            save_folder = config.get("save_folder")

            if save_folder:
                return Path(save_folder)
    except Exception:
        pass

    return DEFAULT_BASE_PATH


def save_base_path(base_path):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    with CONFIG_FILE.open("w", encoding="utf-8") as config_file:
        json.dump({"save_folder": str(base_path)}, config_file, indent=2)


def apply_base_path(base_path):
    global BASE_PATH, COLLECTIONS_PATH, CUSTOMASSETS_PATH, AUTOIMPORT_PATH

    BASE_PATH = Path(base_path)
    COLLECTIONS_PATH = BASE_PATH / "Collections"
    CUSTOMASSETS_PATH = BASE_PATH / "CustomAssets"
    AUTOIMPORT_PATH = BASE_PATH / "AutoImport"


apply_base_path(load_saved_base_path())

if CTK_AVAILABLE:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")

if CTK_AVAILABLE and DND_AVAILABLE and hasattr(TkinterDnD, "DnDWrapper"):
    class CTkDnD(ctk.CTk, TkinterDnD.DnDWrapper):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.TkdndVersion = TkinterDnD._require(self)
else:
    CTkDnD = None


def write_error_log_file(context, error_type=None, error=None, trace=None):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "",
        f"[{timestamp}] {context}",
    ]

    if error_type and error:
        lines.append("".join(traceback.format_exception(error_type, error, trace)).rstrip())

    content = "\n".join(lines) + "\n"
    fallback_log_file = Path.home() / "SoeCharacterLauncher_error.log"

    for log_file in (LOG_FILE, fallback_log_file):
        try:
            with log_file.open("a", encoding="utf-8") as log:
                log.write(content)
            return log_file
        except Exception:
            continue

    return LOG_FILE


def show_startup_error_window(log_file):
    try:
        error_root = tk.Tk()
        error_root.title("SCM")
        error_root.geometry("560x190")
        error_root.resizable(False, False)
        error_root.configure(bg="#0f1117")

        title = tk.Label(
            error_root,
            text="SCM could not finish loading.",
            font=("Arial", 13, "bold"),
            bg="#0f1117",
            fg="#f4f4f5",
        )
        title.pack(pady=(24, 8))

        details = tk.Label(
            error_root,
            text=f"Details were saved to:\n{log_file}",
            font=("Arial", 10),
            bg="#0f1117",
            fg="#a6adbb",
            wraplength=500,
            justify="center",
        )
        details.pack(pady=(0, 18))

        close_button = tk.Button(error_root, text="Close", command=error_root.destroy)
        close_button.pack()

        error_root.mainloop()
    except Exception:
        pass


class CharacterLauncher:
    PREVIEW_SIZE = 150
    GRID_COLUMNS = 7
    CARD_PAD_X = 13
    CARD_PAD_Y = 13
    CARD_NAME_HEIGHT = 34
    DELETE_ICON_SIZE = 24
    DELETE_ICON_MARGIN_X = 6
    DELETE_ICON_MARGIN_Y = 6
    DELETE_ICON_HITBOX = 32
    OPEN_FOLDER_ICON_SIZE = 24
    OPEN_FOLDER_ICON_MARGIN_X = 6
    OPEN_FOLDER_ICON_MARGIN_Y = 6
    OPEN_FOLDER_ICON_HITBOX = 32
    INITIAL_RENDER_COUNT = 28
    CARD_RENDER_BATCH = 21
    PREVIEW_LOAD_BATCH = 5
    CARD_RENDER_DELAY = 10
    PREVIEW_LOAD_DELAY = 15

    BG_COLOR = "#0f1117"
    SURFACE_COLOR = "#171a21"
    PANEL_COLOR = "#1f232d"
    CARD_COLOR = "#20242e"
    PREVIEW_BG = "#f2f2f2"
    BORDER_COLOR = "#303642"
    ACCENT_COLOR = "#2f80ed"
    TEXT_COLOR = "#f4f4f5"
    MUTED_TEXT_COLOR = "#a6adbb"
    WARNING_COLOR = "#d39b3a"
    BUTTON_COLOR = "#2b2f3a"
    BUTTON_HOVER_COLOR = "#3a4050"
    DANGER_COLOR = "#8f2d35"
    DANGER_HOVER_COLOR = "#b33a45"

    def __init__(self):
        self.dnd_enabled = False
        self.root = self._create_root()
        self.root.report_callback_exception = self.handle_callback_exception

        self.root.title("SCM")
        self.root.geometry("1415x800")
        self.root.resizable(False, False)
        self.safe_set_window_attributes()

        self.selected = set()
        self.character_cards = {}
        self.sort_mode = "alpha"
        self.sort_reverse = False
        self.all_characters = []
        self.empty_message = None
        self.search_after_id = None
        self.card_render_after_id = None
        self.preview_load_after_id = None
        self.current_render_token = 0
        self.preview_queue = []
        self.image_cache = {}
        self.delete_icon = None
        self.delete_icon_pil = None
        self.open_folder_icon = None
        self.open_folder_icon_pil = None
        self.no_image_icon_pil = None
        self.no_image_icon = None
        self.select_icon = None
        self.logo_image = None

        self.search_var = tk.StringVar()

        self._load_icons()
        self._apply_window_icon()
        self._build_ui()
        self._setup_drag_and_drop()
        self.safe_update_idletasks()

        self._show_status_message("Loading characters...")
        self.root.after(120, self.refresh_characters)

    # === inicializacao ===
    def handle_callback_exception(self, error_type, error, trace):
        log_file = self.write_error_log("Unhandled UI callback error", error_type, error, trace)

        try:
            messagebox.showerror(
                "Error",
                f"Something went wrong.\n\nDetails were saved to:\n{log_file}",
            )
        except Exception:
            pass

    def write_error_log(self, context, error_type=None, error=None, trace=None):
        return write_error_log_file(context, error_type, error, trace)

    def write_exception_log(self, context, error):
        return self.write_error_log(context, type(error), error, error.__traceback__)

    def safe_update_idletasks(self):
        try:
            self.root.update_idletasks()
        except Exception:
            pass

    def safe_set_window_attributes(self):
        try:
            self.root.attributes("-toolwindow", False)
        except Exception as error:
            self.write_exception_log("Window attribute setup failed", error)

    def show_logged_error(self, context, error, title="Error", message=None):
        log_file = self.write_exception_log(context, error)
        visible_message = message or str(error)

        messagebox.showerror(
            title,
            f"{visible_message}\n\nDetails were saved to:\n{log_file}",
        )

    def save_folder_exists(self):
        return BASE_PATH.exists() and BASE_PATH.is_dir()

    def normalize_save_folder(self, folder_path):
        folder = Path(folder_path)

        if folder.name.casefold() in {"collections", "customassets", "autoimport"}:
            folder = folder.parent

        sandbox_child = folder / "SandboxSaveGames"

        if sandbox_child.exists() and sandbox_child.is_dir():
            folder = sandbox_child

        return folder

    def is_valid_save_folder(self, folder_path):
        folder = Path(folder_path)

        if not folder.exists() or not folder.is_dir():
            return False

        if folder.name.casefold() == "sandboxsavegames":
            return True

        expected_folders = ("Collections", "CustomAssets", "AutoImport")
        return any((folder / name).exists() for name in expected_folders)

    def choose_save_folder(self):
        initial_dir = BASE_PATH if self.save_folder_exists() else DEFAULT_BASE_PATH.parent

        if not initial_dir.exists():
            initial_dir = USER_HOME

        folder_path = filedialog.askdirectory(
            title="Select your SandboxSaveGames folder",
            initialdir=str(initial_dir),
        )

        if not folder_path:
            return

        selected_folder = self.normalize_save_folder(folder_path)

        if not self.is_valid_save_folder(selected_folder):
            messagebox.showwarning(
                "Save folder not found",
                (
                    "Please select the SandboxSaveGames folder from your save.\n\n"
                    "Example:\n"
                    "E:\\Games\\Wildlife\\Saved\\SandboxSaveGames"
                ),
            )
            return

        try:
            apply_base_path(selected_folder)
            save_base_path(BASE_PATH)
            self.image_cache.clear()
            self.selected.clear()
            self.scroll_to_top()
            self.refresh_characters()
            messagebox.showinfo("Save folder updated", f"Save folder set to:\n{BASE_PATH}")
        except Exception as error:
            self.show_logged_error("Save folder update failed", error)

    def ensure_save_folder_available(self):
        if self.save_folder_exists():
            return True

        messagebox.showwarning(
            "Save folder not found",
            "Save folder not found. Please select the SandboxSaveGames folder from your save.",
        )
        return False

    def _create_root(self):
        if CTK_AVAILABLE and CTkDnD:
            self.dnd_enabled = True
            return CTkDnD()

        if CTK_AVAILABLE:
            return ctk.CTk()

        if DND_AVAILABLE:
            self.dnd_enabled = True
            return TkinterDnD.Tk()

        return tk.Tk()

    def _load_icons(self):
        self.delete_icon_pil = self._load_icon_pil(
            "trash.png",
            (self.DELETE_ICON_SIZE, self.DELETE_ICON_SIZE),
        )

        if self.delete_icon_pil:
            self.delete_icon = self._make_ui_image(
                self.delete_icon_pil.copy(),
                (self.DELETE_ICON_SIZE, self.DELETE_ICON_SIZE),
            )

        self.open_folder_icon_pil = self._load_icon_pil(
            "open-folder.png",
            (self.OPEN_FOLDER_ICON_SIZE, self.OPEN_FOLDER_ICON_SIZE),
        )

        if self.open_folder_icon_pil:
            self.open_folder_icon = self._make_ui_image(
                self.open_folder_icon_pil.copy(),
                (self.OPEN_FOLDER_ICON_SIZE, self.OPEN_FOLDER_ICON_SIZE),
            )

        self.logo_image = self._load_icon("logo.ico", (64, 64))
        self.no_image_icon_pil = self._load_first_available_icon_pil(
            ("No_image.png", "No_image.jpg", "No_image.jpeg", "No_image_ICO.png"),
            (self.PREVIEW_SIZE, self.PREVIEW_SIZE),
        )

        if self.no_image_icon_pil:
            no_image = self._draw_action_icons_on_preview(self.no_image_icon_pil.copy())
            self.no_image_icon = self._make_ui_image(
                no_image,
                (self.PREVIEW_SIZE, self.PREVIEW_SIZE),
            )

    def _load_first_available_icon_pil(self, filenames, size):
        for filename in filenames:
            icon = self._load_icon_pil(filename, size)

            if icon:
                return icon

        return None

    def _load_first_available_icon(self, filenames, size):
        for filename in filenames:
            icon = self._load_icon(filename, size)

            if icon:
                return icon

        return None

    def _load_icon(self, filename, size):
        image = self._load_icon_pil(filename, size)

        if not image:
            return None

        return self._make_ui_image(image, size)

    def _load_icon_pil(self, filename, size):
        icon_file = ICON_PATH / filename

        if not icon_file.exists():
            return None

        try:
            with Image.open(icon_file) as image:
                image = image.convert("RGBA")
                image = image.resize(size, RESAMPLE_FILTER)
                return image.copy()
        except Exception:
            return None

    def _make_ui_image(self, image, size):
        if CTK_AVAILABLE:
            return ctk.CTkImage(light_image=image, dark_image=image, size=size)

        return ImageTk.PhotoImage(image)

    def _apply_window_icon(self):
        icon_file = ICON_PATH / "app.ico"

        if icon_file.exists():
            try:
                self.root.iconbitmap(str(icon_file))
                return
            except Exception:
                pass

    def _build_ui(self):
        if CTK_AVAILABLE:
            self._build_ctk_ui()
        else:
            self._build_tk_ui()

    def _build_ctk_ui(self):
        self.root.configure(fg_color=self.BG_COLOR)

        self.main_frame = ctk.CTkFrame(
            self.root,
            fg_color=self.BG_COLOR,
            corner_radius=0,
        )
        self.main_frame.pack(fill="both", expand=True, padx=18, pady=18)

        self.shell_frame = ctk.CTkFrame(
            self.main_frame,
            fg_color=self.SURFACE_COLOR,
            border_width=1,
            border_color=self.BORDER_COLOR,
            corner_radius=14,
        )
        self.shell_frame.pack(fill="both", expand=True)

        self.header_frame = ctk.CTkFrame(self.shell_frame, fg_color="transparent")
        self.header_frame.pack(fill="x", padx=18, pady=(16, 8))

        self.logo_frame = ctk.CTkFrame(
            self.header_frame,
            width=78,
            height=78,
            fg_color=self.PANEL_COLOR,
            border_width=1,
            border_color=self.BORDER_COLOR,
            corner_radius=14,
        )
        self.logo_frame.pack(side="left", padx=(0, 14))
        self.logo_frame.pack_propagate(False)

        if self.logo_image:
            logo_label = ctk.CTkLabel(self.logo_frame, image=self.logo_image, text="")
        else:
            logo_label = ctk.CTkLabel(
                self.logo_frame,
                text="LOGO",
                font=("Arial", 12, "bold"),
                text_color=self.MUTED_TEXT_COLOR,
            )

        logo_label.pack(expand=True)

        self.title_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        self.title_frame.pack(side="left", fill="both", expand=True)

        self.title_label = ctk.CTkLabel(
            self.title_frame,
            text="SoE Character Manager",
            font=("Arial", 22, "bold"),
            text_color=self.TEXT_COLOR,
            anchor="w",
        )
        self.title_label.pack(anchor="w", pady=(8, 0))

        self.label = ctk.CTkLabel(
            self.title_frame,
            text="drag and drop the .Wlsave file" if self.dnd_enabled else "Select a .wlsave",
            font=("Arial", 13),
            text_color=self.MUTED_TEXT_COLOR,
            anchor="w",
        )
        self.label.pack(anchor="w", pady=(2, 0))

        self.action_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        self.action_frame.pack(side="right", pady=(18, 0))

        self.btn_install = ctk.CTkButton(
            self.action_frame,
            text="Manual install",
            command=self.install_manual,
            width=140,
            height=34,
            corner_radius=8,
            fg_color=self.ACCENT_COLOR,
            hover_color="#3f91ff",
            text_color=self.TEXT_COLOR,
        )
        self.btn_install.pack(side="left", padx=(0, 8))

        self.btn_refresh = ctk.CTkButton(
            self.action_frame,
            text="Refresh characters",
            command=self.refresh_characters,
            width=170,
            height=34,
            corner_radius=8,
            fg_color=self.BUTTON_COLOR,
            hover_color=self.BUTTON_HOVER_COLOR,
            text_color=self.TEXT_COLOR,
        )
        self.btn_refresh.pack(side="left")

        self.btn_cleanup_orphans = ctk.CTkButton(
            self.action_frame,
            text="Clear Custom Assets",
            command=self.cleanup_orphans,
            width=170,
            height=34,
            corner_radius=8,
            fg_color=self.BUTTON_COLOR,
            hover_color=self.BUTTON_HOVER_COLOR,
            text_color=self.TEXT_COLOR,
        )
        self.btn_cleanup_orphans.pack(side="left", padx=(8, 0))

        self.btn_save_folder = ctk.CTkButton(
            self.action_frame,
            text="Save folder",
            command=self.choose_save_folder,
            width=130,
            height=34,
            corner_radius=8,
            fg_color=self.BUTTON_COLOR,
            hover_color=self.BUTTON_HOVER_COLOR,
            text_color=self.TEXT_COLOR,
        )
        self.btn_save_folder.pack(side="left", padx=(8, 0))

        self.top_frame = ctk.CTkFrame(self.shell_frame, fg_color="transparent")
        self.top_frame.pack(fill="x", padx=18, pady=(0, 12))

        self.search_entry = ctk.CTkEntry(
            self.top_frame,
            textvariable=self.search_var,
            width=340,
            height=38,
            placeholder_text="Search character",
            fg_color=self.PANEL_COLOR,
            border_color=self.BORDER_COLOR,
            text_color=self.TEXT_COLOR,
        )
        self.search_entry.pack(side="left", padx=(92, 8), pady=5)

        self.btn_clear_search = ctk.CTkButton(
            self.top_frame,
            text="X",
            command=self.clear_search,
            width=38,
            height=38,
            corner_radius=8,
            fg_color=self.BUTTON_COLOR,
            hover_color=self.BUTTON_HOVER_COLOR,
            text_color=self.TEXT_COLOR,
        )
        self.btn_clear_search.pack(side="left", padx=(0, 12), pady=5)

        self.btn_sort_alpha = ctk.CTkButton(
            self.top_frame,
            text="A-Z Up",
            command=self.set_alpha_sort,
            width=86,
            height=38,
            corner_radius=8,
            fg_color=self.ACCENT_COLOR,
            hover_color="#3f91ff",
            text_color=self.TEXT_COLOR,
        )
        self.btn_sort_alpha.pack(side="left", padx=(0, 8), pady=5)

        self.btn_sort_number = ctk.CTkButton(
            self.top_frame,
            text="0-9",
            command=self.set_number_sort,
            width=86,
            height=38,
            corner_radius=8,
            fg_color=self.BUTTON_COLOR,
            hover_color=self.BUTTON_HOVER_COLOR,
            text_color=self.TEXT_COLOR,
        )
        self.btn_sort_number.pack(side="left", padx=(0, 8), pady=5)

        self.btn_delete_selected = ctk.CTkButton(
            self.top_frame,
            text="Delete selected",
            image=self.delete_icon,
            compound="left",
            font=("Arial", 12, "bold"),
            width=190,
            height=38,
            corner_radius=8,
            fg_color=self.DANGER_COLOR,
            hover_color=self.DANGER_HOVER_COLOR,
            text_color=self.TEXT_COLOR,
            command=self.delete_selected_characters,
        )
        self.btn_delete_selected.pack(side="right", padx=(10, 0), pady=5)

        self.btn_clear_selection = ctk.CTkButton(
            self.top_frame,
            text="Clear selection",
            command=self.clear_selection,
            width=130,
            height=38,
            corner_radius=8,
            fg_color=self.BUTTON_COLOR,
            hover_color=self.BUTTON_HOVER_COLOR,
            text_color=self.TEXT_COLOR,
        )

        if not self.dnd_enabled:
            warning = ctk.CTkLabel(
                self.shell_frame,
                text="tkinterdnd2 is not installed: drag and drop is disabled.",
                font=("Arial", 11),
                text_color=self.WARNING_COLOR,
            )
            warning.pack(fill="x", padx=18, pady=(0, 8))

        self.content_frame = ctk.CTkFrame(
            self.shell_frame,
            fg_color=self.PANEL_COLOR,
            border_width=1,
            border_color=self.BORDER_COLOR,
            corner_radius=12,
        )
        self.content_frame.pack(fill="both", expand=True, padx=18, pady=(0, 18))

        self.list_frame = ctk.CTkScrollableFrame(
            self.content_frame,
            fg_color="transparent",
            scrollbar_button_color=self.BUTTON_COLOR,
            scrollbar_button_hover_color=self.BUTTON_HOVER_COLOR,
        )
        self.list_frame.pack(fill="both", expand=True, padx=8, pady=8)

        self.grid_frame = ctk.CTkFrame(self.list_frame, fg_color="transparent")
        self.grid_frame.pack(anchor="n")
        self.configure_grid_columns()

        self.search_var.trace_add("write", self._on_search_change)

    def _build_tk_ui(self):
        self.root.configure(bg=self.BG_COLOR)

        self.header_frame = tk.Frame(self.root, bg=self.BG_COLOR)
        self.header_frame.pack(fill="x", padx=18, pady=(16, 8))

        self.logo_frame = tk.Frame(
            self.header_frame,
            width=78,
            height=78,
            bg="#1f232d",
            highlightthickness=1,
            highlightbackground="#303642",
        )
        self.logo_frame.pack(side="left", padx=(0, 14))
        self.logo_frame.pack_propagate(False)

        if self.logo_image:
            logo_label = tk.Label(self.logo_frame, image=self.logo_image, bg="#1f232d")
            logo_label.image = self.logo_image
        else:
            logo_label = tk.Label(
                self.logo_frame,
                text="LOGO",
                font=("Arial", 10, "bold"),
                bg="#1f232d",
                fg="#a6adbb",
            )

        logo_label.pack(expand=True)

        self.title_frame = tk.Frame(self.header_frame, bg=self.BG_COLOR)
        self.title_frame.pack(side="left", fill="both", expand=True)

        self.title_label = tk.Label(
            self.title_frame,
            text="Soe Character Launcher",
            font=("Arial", 16, "bold"),
            bg=self.BG_COLOR,
            fg="white",
            anchor="w",
        )
        self.title_label.pack(anchor="w", pady=(8, 0))

        self.label = tk.Label(
            self.title_frame,
            text="drag and drop the .Wlsave file" if DND_AVAILABLE else "Select a .wlsave",
            font=("Arial", 11),
            bg=self.BG_COLOR,
            fg="#a6adbb",
            anchor="w",
        )
        self.label.pack(anchor="w", pady=(2, 0))

        self.action_frame = tk.Frame(self.header_frame, bg=self.BG_COLOR)
        self.action_frame.pack(side="right", pady=(18, 0))

        self.btn_install = tk.Button(
            self.action_frame,
            text="Manual install",
            command=self.install_manual,
        )
        self.btn_install.pack(side="left", padx=(0, 8))

        self.btn_refresh = tk.Button(
            self.action_frame,
            text="Refresh characters",
            command=self.refresh_characters,
        )
        self.btn_refresh.pack(side="left")

        self.btn_cleanup_orphans = tk.Button(
            self.action_frame,
            text="Clear Custom Assets",
            command=self.cleanup_orphans,
        )
        self.btn_cleanup_orphans.pack(side="left", padx=(8, 0))

        self.btn_save_folder = tk.Button(
            self.action_frame,
            text="Save folder",
            command=self.choose_save_folder,
        )
        self.btn_save_folder.pack(side="left", padx=(8, 0))

        self.top_frame = tk.Frame(self.root, bg=self.BG_COLOR)
        self.top_frame.pack(fill="x", padx=18, pady=(0, 12))

        self.search_entry = tk.Entry(
            self.top_frame,
            textvariable=self.search_var,
            width=42,
        )
        self.search_entry.pack(side="left", padx=(92, 8), pady=5)

        self.btn_clear_search = tk.Button(
            self.top_frame,
            text="X",
            command=self.clear_search,
            bd=0,
            bg="#2b2b2b",
            fg="white",
            activebackground="#444444",
            activeforeground="white",
            width=3,
        )
        self.btn_clear_search.pack(side="left", padx=(0, 12), pady=5)

        self.btn_sort_alpha = tk.Button(
            self.top_frame,
            text="A-Z Up",
            command=self.set_alpha_sort,
            bd=0,
            bg="#2f80ed",
            fg="white",
            activebackground="#3f91ff",
            activeforeground="white",
            width=8,
        )
        self.btn_sort_alpha.pack(side="left", padx=(0, 8), pady=5)

        self.btn_sort_number = tk.Button(
            self.top_frame,
            text="0-9",
            command=self.set_number_sort,
            bd=0,
            bg="#2b2b2b",
            fg="white",
            activebackground="#444444",
            activeforeground="white",
            width=8,
        )
        self.btn_sort_number.pack(side="left", padx=(0, 8), pady=5)

        self.btn_delete_selected = tk.Button(
            self.top_frame,
            text=" Delete selected" if self.delete_icon else "Delete selected",
            image=self.delete_icon,
            compound="left",
            font=("Arial", 10, "bold"),
            bg="#2b2b2b",
            fg="white",
            activebackground="#444444",
            activeforeground="white",
            bd=0,
            padx=10,
            pady=5,
            command=self.delete_selected_characters,
        )
        self.btn_delete_selected.pack(side="right", padx=10, pady=5)

        self.btn_clear_selection = tk.Button(
            self.top_frame,
            text="Clear selection",
            command=self.clear_selection,
            bd=0,
            bg="#2b2b2b",
            fg="white",
            activebackground="#444444",
            activeforeground="white",
            padx=10,
            pady=5,
        )

        if not DND_AVAILABLE:
            warning = tk.Label(
                self.root,
                text="tkinterdnd2 is not installed: drag and drop is disabled.",
                font=("Arial", 9),
                fg="#9a5b00",
            )
            warning.pack(pady=(0, 6))

        self.canvas = tk.Canvas(self.root)
        self.scrollbar = tk.Scrollbar(
            self.root,
            orient="vertical",
            command=self.canvas.yview,
        )

        self.list_frame = tk.Frame(self.canvas)
        self.grid_frame = tk.Frame(self.list_frame)
        self.grid_frame.pack(anchor="n")
        self.configure_grid_columns()

        self.canvas_window = self.canvas.create_window(
            (0, 0),
            window=self.list_frame,
            anchor="nw",
        )

        self.list_frame.bind(
            "<Configure>",
            lambda event: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.bind(
            "<Configure>",
            lambda event: self.canvas.itemconfigure(self.canvas_window, width=event.width),
        )
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        self.search_var.trace_add("write", self._on_search_change)

    def _setup_drag_and_drop(self):
        if not self.dnd_enabled:
            return

        try:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>", self.drop_files)
        except Exception as error:
            self.dnd_enabled = False
            self.write_exception_log("Drag and drop setup failed", error)

    def configure_grid_columns(self):
        column_width = self.PREVIEW_SIZE + (self.CARD_PAD_X * 2)

        for column in range(self.GRID_COLUMNS):
            self.grid_frame.grid_columnconfigure(
                column,
                minsize=column_width,
                weight=0,
                uniform="character_cards",
            )

    # === instalacao ===
    def install_character_direct(self, file_path):
        source = Path(str(file_path).strip("{}"))

        if source.suffix.lower() != ".wlsave":
            return

        if not self.ensure_save_folder_available():
            return

        if not source.exists():
            messagebox.showerror("Error", f"File not found:\n{source}")
            return

        try:
            AUTOIMPORT_PATH.mkdir(parents=True, exist_ok=True)

            destination = AUTOIMPORT_PATH / source.name

            if source.resolve() == destination.resolve():
                messagebox.showinfo("Notice", f"{source.name} is already in the AutoImport folder.")
                return

            shutil.copy2(source, destination)
            messagebox.showinfo("Success", f"{source.name} installed!")

        except Exception as error:
            self.show_logged_error("Manual install failed", error)

    def install_manual(self):
        file_path = filedialog.askopenfilename(
            title="Select character",
            filetypes=[("WildLife Save", "*.wlsave")],
        )

        if file_path:
            self.install_character_direct(file_path)

    def drop_files(self, event):
        files = self.root.tk.splitlist(event.data)

        for file_path in files:
            self.install_character_direct(file_path)

    # === listagem ===
    def list_characters(self):
        characters = []

        if not self.save_folder_exists() or not COLLECTIONS_PATH.exists():
            return characters

        json_files = [
            file_path
            for file_path in COLLECTIONS_PATH.iterdir()
            if file_path.is_file() and file_path.suffix.casefold() == ".json"
        ]

        for json_file in sorted(json_files, key=lambda item: item.stem.casefold()):
            preview_file = json_file.with_suffix(".png")

            characters.append(
                {
                    "name": json_file.stem,
                    "preview": preview_file if preview_file.exists() else None,
                }
            )

        return characters

    def get_collection_names(self):
        names = set()

        if not self.save_folder_exists() or not COLLECTIONS_PATH.exists():
            return names

        for file_path in COLLECTIONS_PATH.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in {".json", ".png"}:
                names.add(file_path.stem)

        return names

    def get_customasset_names(self):
        names = set()

        if not self.save_folder_exists() or not CUSTOMASSETS_PATH.exists():
            return names

        for folder_path in CUSTOMASSETS_PATH.iterdir():
            if folder_path.is_dir():
                names.add(folder_path.name)

        return names

    def refresh_characters(self):
        try:
            self.cancel_pending_render_jobs()
            self.all_characters = self.list_characters()
            current_names = {character["name"] for character in self.all_characters}

            for name in list(self.character_cards):
                if name not in current_names:
                    self.safe_destroy_widget(self.character_cards[name].get("frame"))
                    del self.character_cards[name]

            self.render_characters()
        except Exception as error:
            self.show_logged_error(
                "Refresh characters failed",
                error,
                message="Refresh failed.",
            )

    def render_characters(self):
        self.cancel_pending_render_jobs()
        self.current_render_token += 1
        render_token = self.current_render_token
        self._hide_empty_message()
        self._update_selection_button()
        self.preview_queue.clear()

        characters = list(self.all_characters)
        filter_text = self.search_var.get().strip().casefold()

        if filter_text:
            characters = [
                character
                for character in characters
                if filter_text in character["name"].casefold()
            ]

        if not characters:
            for card in self.character_cards.values():
                self.safe_grid_forget(card.get("frame"))

            self._show_empty_message(filter_text)
            return

        characters = self.sort_characters(characters)
        visible_names = {character["name"] for character in characters}

        for name, card in self.character_cards.items():
            if name not in visible_names:
                self.safe_grid_forget(card.get("frame"))

        initial_count = min(len(characters), self.INITIAL_RENDER_COUNT)
        self.render_character_batch(characters, 0, initial_count, render_token)

        if initial_count < len(characters):
            self.card_render_after_id = self.root.after(
                self.CARD_RENDER_DELAY,
                lambda: self.render_remaining_character_batches(
                    characters,
                    initial_count,
                    render_token,
                ),
            )

        self.schedule_preview_loading()

    def cancel_pending_render_jobs(self):
        if self.card_render_after_id:
            self.safe_after_cancel(self.card_render_after_id)
            self.card_render_after_id = None

        if self.preview_load_after_id:
            self.safe_after_cancel(self.preview_load_after_id)
            self.preview_load_after_id = None

    def safe_after_cancel(self, after_id):
        try:
            self.root.after_cancel(after_id)
        except tk.TclError:
            pass
        except Exception as error:
            self.write_exception_log("Failed to cancel scheduled UI job", error)

    def safe_grid_forget(self, widget):
        try:
            if self.widget_exists(widget):
                widget.grid_forget()
        except Exception:
            pass

    def safe_destroy_widget(self, widget):
        try:
            if self.widget_exists(widget):
                widget.destroy()
        except Exception:
            pass

    def widget_exists(self, widget):
        try:
            return bool(widget and widget.winfo_exists())
        except Exception:
            return False

    def render_remaining_character_batches(self, characters, start_index, render_token):
        if render_token != self.current_render_token:
            return

        try:
            end_index = min(start_index + self.CARD_RENDER_BATCH, len(characters))
            self.render_character_batch(characters, start_index, end_index, render_token)

            if end_index < len(characters):
                self.card_render_after_id = self.root.after(
                    self.CARD_RENDER_DELAY,
                    lambda: self.render_remaining_character_batches(
                        characters,
                        end_index,
                        render_token,
                    ),
                )
            else:
                self.card_render_after_id = None
        except Exception as error:
            self.card_render_after_id = None
            self.write_exception_log("Character card batch render failed", error)

    def render_character_batch(self, characters, start_index, end_index, render_token):
        if render_token != self.current_render_token:
            return

        for index in range(start_index, end_index):
            character = characters[index]
            row = index // self.GRID_COLUMNS
            column = index % self.GRID_COLUMNS
            self._show_character_card(character, row, column)

    def _hide_empty_message(self):
        self.safe_destroy_widget(self.empty_message)
        self.empty_message = None

    def _show_character_card(self, character, row, column):
        name = character["name"]
        card = self.character_cards.get(name)

        if card is None:
            self._create_character_card(character, row, column)
            return

        if card.get("preview") != character["preview"]:
            self.safe_destroy_widget(card.get("frame"))
            self.character_cards.pop(name, None)
            self._create_character_card(character, row, column)
            return

        frame = card.get("frame")

        if not self.widget_exists(frame):
            self.character_cards.pop(name, None)
            self._create_character_card(character, row, column)
            return

        frame.grid(row=row, column=column, padx=self.CARD_PAD_X, pady=self.CARD_PAD_Y, sticky="n")
        self._set_card_selected(name, name in self.selected)
        self.queue_preview_load(name)

    def queue_preview_load(self, name):
        card = self.character_cards.get(name)

        if not card or card["preview_loaded"] or not card["preview"]:
            return

        if name not in self.preview_queue:
            self.preview_queue.append(name)

        self.schedule_preview_loading()

    def schedule_preview_loading(self):
        if self.preview_load_after_id or not self.preview_queue:
            return

        self.preview_load_after_id = self.root.after(
            self.PREVIEW_LOAD_DELAY,
            self.load_preview_batch,
        )

    def load_preview_batch(self):
        self.preview_load_after_id = None

        if not self.preview_queue:
            return

        loaded_count = 0

        while self.preview_queue and loaded_count < self.PREVIEW_LOAD_BATCH:
            name = self.preview_queue.pop(0)

            try:
                card = self.character_cards.get(name)

                if not card or card["preview_loaded"] or not card["preview"]:
                    continue

                image_label = card.get("image_label")

                if not self.widget_exists(image_label):
                    continue

                image = self._get_preview_image(card["preview"])
                image_label.configure(image=image, text="")
                image_label.image = image
                card["preview_loaded"] = True
                loaded_count += 1
            except Exception as error:
                self.write_exception_log(f"Preview load failed for {name}", error)

        if self.preview_queue:
            self.schedule_preview_loading()

    # === classificacao ===
    def set_alpha_sort(self):
        if self.sort_mode == "alpha":
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_mode = "alpha"
            self.sort_reverse = False

        self.update_sort_buttons()
        self.render_characters()

    def set_number_sort(self):
        if self.sort_mode == "number":
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_mode = "number"
            self.sort_reverse = False

        self.update_sort_buttons()
        self.render_characters()

    def update_sort_buttons(self):
        direction = "Down" if self.sort_reverse else "Up"
        alpha_text = f"A-Z {direction}" if self.sort_mode == "alpha" else "A-Z"
        number_text = f"0-9 {direction}" if self.sort_mode == "number" else "0-9"

        self.btn_sort_alpha.configure(text=alpha_text)
        self.btn_sort_number.configure(text=number_text)

        if CTK_AVAILABLE:
            self.btn_sort_alpha.configure(
                fg_color=self.ACCENT_COLOR if self.sort_mode == "alpha" else self.BUTTON_COLOR,
                hover_color="#3f91ff" if self.sort_mode == "alpha" else self.BUTTON_HOVER_COLOR,
            )
            self.btn_sort_number.configure(
                fg_color=self.ACCENT_COLOR if self.sort_mode == "number" else self.BUTTON_COLOR,
                hover_color="#3f91ff" if self.sort_mode == "number" else self.BUTTON_HOVER_COLOR,
            )
        else:
            self.btn_sort_alpha.configure(
                bg="#2f80ed" if self.sort_mode == "alpha" else "#2b2b2b",
                activebackground="#3f91ff" if self.sort_mode == "alpha" else "#444444",
            )
            self.btn_sort_number.configure(
                bg="#2f80ed" if self.sort_mode == "number" else "#2b2b2b",
                activebackground="#3f91ff" if self.sort_mode == "number" else "#444444",
            )

    def sort_characters(self, characters):
        if self.sort_mode == "number":
            numbered = []
            without_number = []

            for character in characters:
                number = self.get_first_number(character["name"])

                if number is None:
                    without_number.append(character)
                else:
                    numbered.append((number, character))

            numbered.sort(
                key=lambda item: (item[0], item[1]["name"].casefold()),
                reverse=self.sort_reverse,
            )
            without_number.sort(key=lambda character: character["name"].casefold())

            return [character for _number, character in numbered] + without_number

        return sorted(
            characters,
            key=lambda character: self.get_alpha_sort_key(character["name"]),
            reverse=self.sort_reverse,
        )

    def get_alpha_sort_key(self, name):
        for index, character in enumerate(name):
            if character.isalpha():
                return name[index:].casefold()

        return name.casefold()

    def get_first_number(self, name):
        match = re.search(r"\d+", name)
        return int(match.group()) if match else None

    def _show_empty_message(self, filter_text):
        if filter_text:
            text = "No character found for this search."
        elif not self.save_folder_exists():
            text = "Save folder not found. Please select the SandboxSaveGames folder from your save."
        elif not COLLECTIONS_PATH.exists():
            text = "The Collections folder does not exist yet."
        else:
            text = "No character found."

        self._show_status_message(text)

    def _show_status_message(self, text):
        self._hide_empty_message()

        if CTK_AVAILABLE:
            label = ctk.CTkLabel(
                self.grid_frame,
                text=text,
                font=("Arial", 12),
                text_color=self.MUTED_TEXT_COLOR,
                wraplength=640,
            )
        else:
            label = tk.Label(self.grid_frame, text=text, font=("Arial", 10), wraplength=640)

        label.grid(row=0, column=0, columnspan=self.GRID_COLUMNS, padx=20, pady=20)
        self.empty_message = label

    def _create_character_card(self, character, row, column, parent_frame=None):
        name = character["name"]
        parent = parent_frame or self.grid_frame

        card_height = self.PREVIEW_SIZE + self.CARD_NAME_HEIGHT

        if CTK_AVAILABLE:
            frame = ctk.CTkFrame(
                parent,
                width=self.PREVIEW_SIZE,
                height=card_height,
                fg_color="transparent",
            )
        else:
            frame = tk.Frame(
                parent,
                width=self.PREVIEW_SIZE,
                height=card_height,
            )

        frame.grid(row=row, column=column, padx=self.CARD_PAD_X, pady=self.CARD_PAD_Y, sticky="n")
        frame.grid_propagate(False)

        if CTK_AVAILABLE:
            label_name = ctk.CTkLabel(
                frame,
                text=name,
                font=("Arial", 12, "bold"),
                width=self.PREVIEW_SIZE,
                height=self.CARD_NAME_HEIGHT,
                anchor="w",
                justify="left",
                text_color=self.TEXT_COLOR,
                wraplength=self.PREVIEW_SIZE,
            )
        else:
            label_name = tk.Label(
                frame,
                text=name,
                font=("Arial", 8, "bold"),
                width=20,
                height=2,
                anchor="w",
                justify="left",
                wraplength=self.PREVIEW_SIZE,
            )

        label_name.pack()

        if CTK_AVAILABLE:
            image_frame = ctk.CTkFrame(
                frame,
                width=self.PREVIEW_SIZE,
                height=self.PREVIEW_SIZE,
                fg_color=self.PREVIEW_BG,
                border_width=2 if name in self.selected else 1,
                border_color=self.ACCENT_COLOR if name in self.selected else self.BORDER_COLOR,
                corner_radius=8,
            )
        else:
            image_frame = tk.Frame(
                frame,
                width=self.PREVIEW_SIZE,
                height=self.PREVIEW_SIZE,
                bg="#f2f2f2",
                highlightthickness=2 if name in self.selected else 1,
                highlightbackground="#2f80ed" if name in self.selected else "#cccccc",
            )

        image_frame.pack()
        image_frame.pack_propagate(False)
        self.character_cards[name] = {
            "frame": frame,
            "image_frame": image_frame,
            "overlay": None,
            "preview": character["preview"],
            "preview_loaded": False,
            "image_label": None,
        }

        if character["preview"]:
            if CTK_AVAILABLE:
                image_label = ctk.CTkLabel(
                    image_frame,
                    text="",
                    fg_color=self.PREVIEW_BG,
                )
            else:
                image_label = tk.Label(image_frame, text="", bg="#f2f2f2")

            image_label.pack(expand=True)
            self._bind_preview_actions(image_label, name)
            self.character_cards[name]["image_label"] = image_label
            self.queue_preview_load(name)
        else:
            if self.no_image_icon:
                if CTK_AVAILABLE:
                    image_label = ctk.CTkLabel(
                        image_frame,
                        image=self.no_image_icon,
                        text="",
                        fg_color=self.PREVIEW_BG,
                    )
                else:
                    image_label = tk.Label(image_frame, image=self.no_image_icon, bg="#f2f2f2")

                image_label.image = self.no_image_icon
            elif CTK_AVAILABLE:
                image_label = ctk.CTkLabel(
                    image_frame,
                    text="No image",
                    fg_color=self.PREVIEW_BG,
                    text_color="#666666",
                )
            else:
                image_label = tk.Label(
                    image_frame,
                    text="No image",
                    bg="#f2f2f2",
                    fg="#666666",
                )

            image_label.pack(expand=True)
            if self.no_image_icon:
                self._bind_preview_actions(image_label, name)
            else:
                self._bind_selection(image_label, name)

            self.character_cards[name]["image_label"] = image_label
            self.character_cards[name]["preview_loaded"] = True

        self._bind_selection(frame, name)
        self._bind_selection(image_frame, name)
        self._bind_selection(label_name, name)

        if name in self.selected:
            self.character_cards[name]["overlay"] = self._add_selection_overlay(image_frame, name)

        if not self.has_embedded_action_icon(character, self.delete_icon_pil):
            self._add_delete_button(image_frame, name)

        if not self.has_embedded_action_icon(character, self.open_folder_icon_pil):
            self._add_open_folder_button(image_frame, name)

    def has_embedded_action_icon(self, character, icon):
        if not icon:
            return False

        return bool(character["preview"] or self.no_image_icon)

    def _get_preview_image(self, preview_path):
        preview_path = Path(preview_path)

        if preview_path in self.image_cache:
            return self.image_cache[preview_path]

        try:
            with Image.open(preview_path) as image:
                image = image.convert("RGBA")
                image = image.resize((self.PREVIEW_SIZE, self.PREVIEW_SIZE), RESAMPLE_FILTER)
                image = self._draw_action_icons_on_preview(image)

                photo = self._make_ui_image(image.copy(), (self.PREVIEW_SIZE, self.PREVIEW_SIZE))
                self.image_cache[preview_path] = photo
                return photo

        except Exception:
            image = Image.new("RGBA", (self.PREVIEW_SIZE, self.PREVIEW_SIZE), (242, 242, 242, 255))
            image = self._draw_action_icons_on_preview(image)
            photo = self._make_ui_image(
                image,
                (self.PREVIEW_SIZE, self.PREVIEW_SIZE),
            )
            self.image_cache[preview_path] = photo
            return photo

    def _draw_action_icons_on_preview(self, image):
        image = self._draw_open_folder_icon_on_preview(image)
        image = self._draw_delete_icon_on_preview(image)
        return image

    def _draw_open_folder_icon_on_preview(self, image):
        if not self.open_folder_icon_pil:
            return image

        x = self.OPEN_FOLDER_ICON_MARGIN_X
        y = self.OPEN_FOLDER_ICON_MARGIN_Y
        image.alpha_composite(self.open_folder_icon_pil, (x, y))
        return image

    def _draw_delete_icon_on_preview(self, image):
        if not self.delete_icon_pil:
            return image

        x = self.PREVIEW_SIZE - self.DELETE_ICON_SIZE - self.DELETE_ICON_MARGIN_X
        y = self.DELETE_ICON_MARGIN_Y
        image.alpha_composite(self.delete_icon_pil, (x, y))
        return image

    def _add_selection_overlay(self, image_frame, name):
        if self.select_icon:
            if CTK_AVAILABLE:
                overlay = ctk.CTkLabel(
                    image_frame,
                    image=self.select_icon,
                    text="",
                    fg_color=self.PREVIEW_BG,
                )
            else:
                overlay = tk.Label(image_frame, image=self.select_icon, bd=0, bg="#f2f2f2")

            overlay.image = self.select_icon
        else:
            if CTK_AVAILABLE:
                overlay = ctk.CTkLabel(
                    image_frame,
                    text="Selected",
                    fg_color=self.ACCENT_COLOR,
                    text_color=self.TEXT_COLOR,
                    font=("Arial", 12, "bold"),
                    corner_radius=0,
                    padx=8,
                    pady=4,
                )
            else:
                overlay = tk.Label(
                    image_frame,
                    text="Selected",
                    bd=0,
                    bg="#2f80ed",
                    fg="white",
                    font=("Arial", 9, "bold"),
                    padx=8,
                    pady=4,
                )

        overlay.place(relx=0.5, rely=0.5, anchor="center")
        self._bind_selection(overlay, name)
        return overlay

    def _add_delete_button(self, image_frame, name):
        if CTK_AVAILABLE:
            button = ctk.CTkButton(
                image_frame,
                text="" if self.delete_icon else "X",
                image=self.delete_icon,
                command=lambda character_name=name: self.delete_character(character_name),
                width=26,
                height=26,
                corner_radius=7,
                fg_color="transparent",
                hover_color="#dddddd",
                text_color=self.TEXT_COLOR,
            )
        elif self.delete_icon:
            button = tk.Button(
                image_frame,
                image=self.delete_icon,
                command=lambda character_name=name: self.delete_character(character_name),
                bd=0,
                bg="#f2f2f2",
                activebackground="#dddddd",
            )
        else:
            button = tk.Button(
                image_frame,
                text="X",
                command=lambda character_name=name: self.delete_character(character_name),
                bd=0,
                bg="#2b2b2b",
                fg="white",
                activebackground="#444444",
                activeforeground="white",
                width=2,
            )

        button.place(x=self.PREVIEW_SIZE - 30, y=4)

    def _add_open_folder_button(self, image_frame, name):
        if CTK_AVAILABLE:
            button = ctk.CTkButton(
                image_frame,
                text="" if self.open_folder_icon else "Open",
                image=self.open_folder_icon,
                command=lambda character_name=name: self.open_custom_assets_folder(character_name),
                width=26,
                height=26,
                corner_radius=7,
                fg_color="transparent",
                hover_color="#dddddd",
                text_color=self.TEXT_COLOR,
            )
        elif self.open_folder_icon:
            button = tk.Button(
                image_frame,
                image=self.open_folder_icon,
                command=lambda character_name=name: self.open_custom_assets_folder(character_name),
                bd=0,
                bg="#f2f2f2",
                activebackground="#dddddd",
            )
        else:
            button = tk.Button(
                image_frame,
                text="Open",
                command=lambda character_name=name: self.open_custom_assets_folder(character_name),
                bd=0,
                bg="#2b2b2b",
                fg="white",
                activebackground="#444444",
                activeforeground="white",
                width=5,
            )

        button.place(x=4, y=4)

    # === selecao ===
    def _bind_selection(self, widget, name):
        widget.bind("<Button-1>", lambda event, character_name=name: self.toggle_selection(character_name))
        widget.bind("<Double-Button-1>", lambda event: "break")

    def _bind_preview_actions(self, widget, name):
        widget.bind("<Button-1>", lambda event, character_name=name: self.handle_preview_click(event, character_name))
        widget.bind("<Double-Button-1>", lambda event: "break")

    def handle_preview_click(self, event, name):
        if self.is_open_folder_icon_click(event.x, event.y):
            self.open_custom_assets_folder(name)
        elif self.is_delete_icon_click(event.x, event.y):
            self.delete_character(name)
        else:
            self.toggle_selection(name)

        return "break"

    def is_open_folder_icon_click(self, x, y):
        if not self.open_folder_icon_pil:
            return False

        left = self.OPEN_FOLDER_ICON_MARGIN_X
        right = self.OPEN_FOLDER_ICON_MARGIN_X + self.OPEN_FOLDER_ICON_HITBOX
        top = self.OPEN_FOLDER_ICON_MARGIN_Y
        bottom = self.OPEN_FOLDER_ICON_MARGIN_Y + self.OPEN_FOLDER_ICON_HITBOX

        return left <= x <= right and top <= y <= bottom

    def is_delete_icon_click(self, x, y):
        if not self.delete_icon_pil:
            return False

        left = self.PREVIEW_SIZE - self.DELETE_ICON_HITBOX - self.DELETE_ICON_MARGIN_X
        right = self.PREVIEW_SIZE - self.DELETE_ICON_MARGIN_X
        top = self.DELETE_ICON_MARGIN_Y
        bottom = self.DELETE_ICON_MARGIN_Y + self.DELETE_ICON_HITBOX

        return left <= x <= right and top <= y <= bottom

    def toggle_selection(self, name):
        if name in self.selected:
            self.selected.remove(name)
            is_selected = False
        else:
            self.selected.add(name)
            is_selected = True

        self._set_card_selected(name, is_selected)
        self._update_selection_button()
        return "break"

    def clear_selection(self):
        selected_names = list(self.selected)
        self.selected.clear()

        for name in selected_names:
            self._set_card_selected(name, False)

        self._update_selection_button()

    def _set_card_selected(self, name, is_selected):
        card = self.character_cards.get(name)

        if not card:
            return

        image_frame = card["image_frame"]

        if not self.widget_exists(image_frame):
            return

        if CTK_AVAILABLE:
            image_frame.configure(
                border_width=2 if is_selected else 1,
                border_color=self.ACCENT_COLOR if is_selected else self.BORDER_COLOR,
            )
        else:
            image_frame.configure(
                highlightthickness=2 if is_selected else 1,
                highlightbackground="#2f80ed" if is_selected else "#cccccc",
            )

        overlay = card.get("overlay")

        if is_selected:
            if overlay is None or not overlay.winfo_exists():
                card["overlay"] = self._add_selection_overlay(image_frame, name)
        elif overlay is not None and overlay.winfo_exists():
            overlay.destroy()
            card["overlay"] = None

    def _update_selection_button(self):
        if self.selected:
            self.btn_clear_selection.pack(side="right", padx=(0, 10), pady=5)
        else:
            self.btn_clear_selection.pack_forget()

    # === busca ===
    def clear_search(self):
        if not self.search_var.get():
            self.render_characters()
            return

        self.search_var.set("")

    def _on_search_change(self, *_args):
        if self.search_after_id:
            self.safe_after_cancel(self.search_after_id)

        self.search_after_id = self.root.after(120, self.apply_search)

    def apply_search(self):
        self.search_after_id = None
        self.scroll_to_top()
        self.render_characters()
        self.root.after(1, self.scroll_to_top)

    def scroll_to_top(self):
        if CTK_AVAILABLE:
            try:
                self.list_frame._parent_canvas.yview_moveto(0)
            except Exception:
                pass
        else:
            self.canvas.yview_moveto(0)

    # === abrir pasta ===
    def open_custom_assets_folder(self, name):
        if not self.ensure_save_folder_available():
            return

        assets_folder = CUSTOMASSETS_PATH / name

        if not assets_folder.exists() or not assets_folder.is_dir():
            messagebox.showwarning(
                "Folder not found",
                f"CustomAssets folder not found for '{name}'.\n\n{assets_folder}",
            )
            return

        try:
            if sys.platform != "win32":
                raise RuntimeError("Opening folders is only available on Windows.")

            os.startfile(str(assets_folder))
        except Exception as error:
            self.show_logged_error("Open CustomAssets folder failed", error)

    # === delete ===
    def send_to_recycle_bin(self, path):
        path = Path(path)

        if not path.exists():
            return

        if sys.platform != "win32":
            raise RuntimeError("Recycle Bin is only available on Windows.")

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [
                ("hwnd", ctypes.c_void_p),
                ("wFunc", ctypes.c_uint),
                ("pFrom", ctypes.c_wchar_p),
                ("pTo", ctypes.c_wchar_p),
                ("fFlags", ctypes.c_ushort),
                ("fAnyOperationsAborted", ctypes.c_bool),
                ("hNameMappings", ctypes.c_void_p),
                ("lpszProgressTitle", ctypes.c_wchar_p),
            ]

        fo_delete = 3
        fof_silent = 0x0004
        fof_noconfirmation = 0x0010
        fof_allowundo = 0x0040
        fof_noerrorui = 0x0400

        operation = SHFILEOPSTRUCTW()
        operation.wFunc = fo_delete
        operation.pFrom = str(path.resolve()) + "\0\0"
        operation.fFlags = fof_allowundo | fof_noconfirmation | fof_silent | fof_noerrorui

        result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))

        if result != 0:
            raise RuntimeError(f"Failed to move to Recycle Bin: {path}")

    def remove_character_files(self, name):
        json_file = COLLECTIONS_PATH / f"{name}.json"
        preview_file = COLLECTIONS_PATH / f"{name}.png"
        assets_folder = CUSTOMASSETS_PATH / name

        if json_file.exists():
            self.send_to_recycle_bin(json_file)

        if preview_file.exists():
            self.send_to_recycle_bin(preview_file)

        if assets_folder.exists():
            self.send_to_recycle_bin(assets_folder)

    def delete_character(self, name):
        confirm = messagebox.askyesno(
            "Confirm",
            f"Do you want to move '{name}' to the Recycle Bin?",
        )

        if not confirm:
            return

        try:
            self.remove_character_files(name)
            self.selected.discard(name)
            self.image_cache.clear()

            messagebox.showinfo("Success", f"{name} moved to the Recycle Bin!")
            self.refresh_characters()

        except Exception as error:
            self.show_logged_error("Delete character failed", error)

    def delete_selected_characters(self):
        if not self.selected:
            messagebox.showwarning("Warning", "No character selected!")
            return

        total = len(self.selected)
        confirm = messagebox.askyesno(
            "Confirm",
            f"Do you want to move {total} character(s) to the Recycle Bin?",
        )

        if not confirm:
            return

        try:
            for name in list(self.selected):
                self.remove_character_files(name)

            self.selected.clear()
            self.image_cache.clear()

            messagebox.showinfo("Success", "Characters moved to the Recycle Bin!")
            self.refresh_characters()

        except Exception as error:
            self.show_logged_error("Delete selected characters failed", error)

    # === CustomAssets cleanup ===
    def cleanup_orphans(self):
        if not self.ensure_save_folder_available():
            return

        collection_names = self.get_collection_names()
        asset_names = self.get_customasset_names()

        asset_only = sorted(asset_names - collection_names, key=str.lower)

        if not asset_only:
            messagebox.showinfo("Checkup complete", "No orphan CustomAssets folders found.")
            return

        message = (
            "Orphan CustomAssets folders were found.\n\n"
            f"CustomAssets folders to delete: {len(asset_only)}\n\n"
            "Collections files will not be deleted.\n\n"
            "Do you want to permanently delete these CustomAssets folders?"
        )

        confirm = messagebox.askyesno("Clear Custom Assets", message)

        if not confirm:
            return

        deleted_asset_folders = 0

        try:
            for name in asset_only:
                assets_folder = CUSTOMASSETS_PATH / name

                if assets_folder.exists():
                    shutil.rmtree(assets_folder)
                    deleted_asset_folders += 1

                self.selected.discard(name)

            self.image_cache.clear()
            self.refresh_characters()

            messagebox.showinfo(
                "Cleanup complete",
                (
                    "Orphan CustomAssets folders removed!\n\n"
                    "Collections files were preserved.\n"
                    f"Folders removed from CustomAssets: {deleted_asset_folders}"
                ),
            )

        except Exception as error:
            self.show_logged_error("Clear Custom Assets failed", error)

    # === scroll ===
    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    try:
        app = CharacterLauncher()
        app.run()
    except Exception as error:
        log_file = write_error_log_file("Fatal startup error", type(error), error, error.__traceback__)
        show_startup_error_window(log_file)
