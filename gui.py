import json
import math
import os
import threading
import webbrowser
import pandas as pd
import requests
import customtkinter as ctk
from tkinter import messagebox, ttk
from data_handler import (
    download_sbti_data, load_cached_data, save_cached_data, merge_sbti_update, needs_refresh,
    save_to_my_list, remove_from_my_list, load_my_list,
    merge_enrichment, get_cache_date_str, validate_website,
    batch_validate_websites,
)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CONFIG_FILE = os.path.join(DATA_DIR, "app_config.json")


def _load_config():
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_config(**kwargs):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        config = _load_config()
        config.update(kwargs)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except Exception:
        pass
from eu_taxonomy import download_eu_taxonomy, merge_eu_taxonomy
from enrichment import enrich_company, batch_enrich
from filters import apply_filters, compute_scores
from scoring import score_color, score_bg, EU_COUNTRIES
from apollo_helper import build_apollo_url, build_apollo_contact_url, build_esg_search_url, build_sbti_profile_url
from exporter import export_to_csv, export_google_sheets_format, export_to_excel

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")

BG = "#0f1117"
CARD = "#1a1f2e"
CARD_LIGHT = "#232838"
ACCENT = "#00d4aa"
TEXT = "#ffffff"
TEXT_SECONDARY = "#8892a4"
DANGER = "#ff4757"
WARNING = "#ffa502"

FONT_FAMILY = "Segoe UI"

ALL_INDUSTRIES = [
    "Food and Beverage", "Agriculture", "Retail", "Manufacturing",
    "Logistics", "Consumer Goods", "Real Estate", "Fashion",
    "Packaging", "Healthcare",
]
DEFAULT_EXCLUDED = ["Financial Services", "Government", "Professional Services", "Oil and Gas"]
ALL_REGIONS = ["Europe", "North America", "Asia Pacific", "Latin America", "Middle East and Africa"]
REGULATORY_OPTIONS = ["CSRD", "SBTi Committed", "SBTi Targets Set", "SEC Registrant", "UK Company", "EU Company"]
LEAD_STATUS_OPTIONS = ["HOT", "WARM", "COLD"]
COMMITMENT_STATUSES = ["All", "Committed", "Targets Set", "Achieved Net Zero"]
ROWS_PER_PAGE = 50

# --- ttk dark theme ---
style = ttk.Style()
style.theme_use("clam")
style.configure("Dark.Treeview",
    background="#ffffff", foreground="#222222", fieldbackground="#ffffff",
    rowheight=36, font=(FONT_FAMILY, 11), borderwidth=0,
)
style.map("Dark.Treeview",
    background=[("selected", "#e8e8e8")],
    foreground=[("selected", "#222222")],
)
style.configure("Dark.Treeview.Heading",
    background="#f5f5f5", foreground="#222222",
    font=(FONT_FAMILY, 10, "bold"), relief="flat", borderwidth=0,
    padding=(8, 6),
)
style.map("Dark.Treeview.Heading",
    background=[("active", "#e8e8e8")],
    foreground=[("active", "#222222")],
    relief=[("pressed", "flat"), ("active", "flat")],
)
style.configure("Vertical.TScrollbar",
    background="#1a1f2e", troughcolor="#0f1117", bordercolor="#0f1117", arrowcolor="#8892a4",
    width=12,
)
style.map("Vertical.TScrollbar",
    background=[("active", "#2a3040")],
)
style.configure("Horizontal.TScrollbar",
    background="#1a1f2e", troughcolor="#0f1117", bordercolor="#0f1117", arrowcolor="#8892a4",
    width=12,
)
style.map("Horizontal.TScrollbar",
    background=[("active", "#2a3040")],
)


class CircularProgress(ctk.CTkCanvas):
    def __init__(self, master, size=120, **kwargs):
        super().__init__(master, width=size, height=size, highlightthickness=0, bg=BG, **kwargs)
        self.size = size
        self.MAX = 90
        self.value = 0
        self.draw(0)

    def draw(self, value):
        self.delete("all")
        self.value = min(max(value, 0), self.MAX)
        cx = cy = self.size / 2
        r = self.size / 2 - 10
        self.create_oval(cx - r, cy - r, cx + r, cy + r, outline="#2a2f3e", width=8)
        if self.value > 0:
            color = score_color(self.value)
            extent = (self.value / self.MAX) * 360
            self.create_arc(cx - r, cy - r, cx + r, cy + r, start=90, extent=-extent, outline=color, width=8, style="arc")
        self.create_text(cx, cy - 8, text=f"{self.value}", fill=TEXT, font=(FONT_FAMILY, 28, "bold"))
        self.create_text(cx, cy + 18, text="ICP Score", fill=TEXT_SECONDARY, font=(FONT_FAMILY, 10))


class FilterDropdown(ctk.CTkFrame):
    def __init__(self, master, label, options, prechecked=None, on_change=None, label_color=None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.options = options
        self.vars = {}
        self._on_change = on_change
        self._open = False

        lc = label_color or TEXT_SECONDARY
        self._header = ctk.CTkFrame(self, fg_color=CARD_LIGHT, corner_radius=6, height=34)
        self._header.pack(fill="x")
        self._header.pack_propagate(False)

        ctk.CTkLabel(self._header, text=label, font=(FONT_FAMILY, 11, "bold"),
                     text_color=lc, anchor="w").pack(side="left", padx=(10, 4))

        self._count_label = ctk.CTkLabel(self._header, text="", font=(FONT_FAMILY, 10),
                                          text_color=ACCENT, anchor="e")
        self._count_label.pack(side="right", padx=(0, 6))

        self._arrow = ctk.CTkLabel(self._header, text="\u25bc", font=(FONT_FAMILY, 9),
                                    text_color=TEXT_SECONDARY, anchor="e")
        self._arrow.pack(side="right", padx=(0, 8))

        self._header.bind("<Button-1>", self._toggle)
        for child in self._header.winfo_children():
            child.bind("<Button-1>", self._toggle)

        self._body = ctk.CTkScrollableFrame(self, fg_color=CARD, corner_radius=6, height=0)
        self._body_packed = False

        self.winfo_toplevel().bind("<Button-1>", self._on_global_click, add="+")

        for opt in options:
            var = ctk.BooleanVar(value=opt in (prechecked or []))
            self.vars[opt] = var
            cb = ctk.CTkCheckBox(
                self._body, text=opt, variable=var,
                fg_color=ACCENT, hover_color=ACCENT,
                text_color=TEXT, font=(FONT_FAMILY, 11),
                corner_radius=4, checkbox_width=18, checkbox_height=18,
            )
            cb.pack(anchor="w", padx=10, pady=2, fill="x")
            if self._on_change:
                var.trace_add("write", lambda *a: self._update_count() or self._on_change())

        self._update_count()

    def _update_count(self):
        sel = len(self.get_selected())
        total = len(self.options)
        self._count_label.configure(text=f"{sel}/{total}" if sel else "")

    def _toggle(self, event=None):
        if self._open:
            self._close()
        else:
            self._open_dropdown()

    def _open_dropdown(self):
        if self._body_packed:
            return
        max_h = min(len(self.options) * 32 + 8, 200)
        self._body.configure(height=max_h)
        self._body.pack(fill="x", pady=(2, 0))
        self._body_packed = True
        self._open = True
        self._arrow.configure(text="\u25b2")

    def _close(self):
        if not self._body_packed:
            return
        self._body.pack_forget()
        self._body.configure(height=0)
        self._body_packed = False
        self._open = False
        self._arrow.configure(text="\u25bc")

    def _on_global_click(self, event):
        if not self._open:
            return
        wx = self.winfo_rootx()
        wy = self.winfo_rooty()
        bw = self.winfo_width()
        body_h = self._body.winfo_height() if self._body_packed else 0
        bh = self._header.winfo_height() + body_h
        if not (wx <= event.x_root <= wx + bw and wy <= event.y_root <= wy + bh):
            self._close()

    def get_selected(self):
        return [opt for opt, var in self.vars.items() if var.get()]

    def set_all(self, state):
        for var in self.vars.values():
            var.set(state)
        self._update_count()


class StatusBar(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=CARD, height=30, **kwargs)
        self.pack_propagate(False)
        self.label = ctk.CTkLabel(
            self, text="Ready", font=(FONT_FAMILY, 11),
            text_color=TEXT_SECONDARY, anchor="w",
        )
        self.label.pack(side="left", padx=12, pady=3)
        self.source_label = ctk.CTkLabel(
            self, text="", font=(FONT_FAMILY, 10),
            text_color=ACCENT, anchor="e",
        )
        self.source_label.pack(side="left", padx=4, pady=3)

        self.counts = ctk.CTkLabel(
            self, text="", font=(FONT_FAMILY, 11),
            text_color=TEXT_SECONDARY, anchor="e",
        )
        self.counts.pack(side="right", padx=12, pady=3)

    def set_status(self, text):
        self.label.configure(text=text)

    def set_source(self, text):
        self.source_label.configure(text=text)

    def set_counts(self, total, filtered, saved):
        self.counts.configure(text=f"\U0001f4ca {total:,}  |  \U0001f50d {filtered:,}  |  \u2b50 {saved}")


class TerrascopeApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Terrascope ICP Lead Finder")
        self.geometry("1680x920")
        self.minsize(1300, 600)
        self.configure(fg_color=BG)

        self.df = None
        self._df_version = 0
        self._wiki_running = False
        self._cb_running = False
        self._apollo_contacts = {}
        self._company_index = {}
        self.filtered_df = None
        self.current_page = 0
        self.total_pages = 0
        self.selected_row_data = None
        self.my_list_count = len(load_my_list())
        self.notes_text = ""
        self.enrichment_results = {}
        self._search_timer = None

        self._build_layout()
        self.clay_url_entry.insert(0, _load_config().get("webhook_url", ""))
        self._check_cache_on_startup()

    # ======================= LAYOUT =======================

    def _build_layout(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self._build_left_panel()
        self._build_center_panel()
        self._build_right_panel()
        self._build_bottom_bar()

    def _build_left_panel(self):
        left = ctk.CTkFrame(self, fg_color=CARD, width=250, corner_radius=0)
        left.grid(row=0, column=0, sticky="nsew")
        left.grid_propagate(False)
        left.grid_rowconfigure(3, weight=1)

        # Header
        hdr = ctk.CTkFrame(left, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 2))
        ctk.CTkLabel(hdr, text="Terrascope Lead Finder",
                     font=(FONT_FAMILY, 16, "bold"), text_color=ACCENT).pack(anchor="w")
        ctk.CTkLabel(hdr, text="ICP-Matched Company Discovery",
                     font=(FONT_FAMILY, 10), text_color=TEXT_SECONDARY).pack(anchor="w")

        # Data source
        ds = ctk.CTkFrame(left, fg_color="transparent")
        ds.grid(row=1, column=0, sticky="ew", padx=14, pady=(8, 0))
        ds.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(ds, text="DATA SOURCE", font=(FONT_FAMILY, 10, "bold"),
                     text_color=TEXT_SECONDARY).grid(row=0, column=0, sticky="w")

        self.dl_status = ctk.CTkLabel(
            ds, text="", font=(FONT_FAMILY, 10), text_color=TEXT_SECONDARY, anchor="w", wraplength=250,
        )
        self.dl_status.grid(row=1, column=0, sticky="ew", pady=(2, 2))

        # Source info label
        self.source_info = ctk.CTkLabel(
            ds, text="", font=(FONT_FAMILY, 10), text_color=ACCENT, anchor="w", wraplength=250,
        )
        self.source_info.grid(row=2, column=0, sticky="ew", pady=(0, 2))

        self.dl_progress = ctk.CTkProgressBar(ds, fg_color="#2a2f3e", progress_color=ACCENT, height=4)
        self.dl_progress.grid(row=3, column=0, sticky="ew", pady=(0, 4))
        self.dl_progress.set(0)

        self.dl_btn = ctk.CTkButton(
            ds, text="Download SBTi Database", command=self._on_download_sbti,
            fg_color=CARD_LIGHT, hover_color="#3a3f4e", text_color=TEXT,
            font=(FONT_FAMILY, 11), corner_radius=6, height=32,
        )
        self.dl_btn.grid(row=4, column=0, sticky="ew", pady=(0, 2))

        self.eu_tax_btn = ctk.CTkButton(
            ds, text="+ EU Taxonomy (190 cos)", command=self._on_download_eu_taxonomy,
            fg_color="#1a3a2a", hover_color="#2a5a3e", text_color=ACCENT,
            font=(FONT_FAMILY, 11), corner_radius=6, height=28,
        )
        self.eu_tax_btn.grid(row=5, column=0, sticky="ew", pady=(0, 4))

        # Filters (scrollable)
        fc = ctk.CTkScrollableFrame(left, fg_color="transparent", corner_radius=0)
        fc.grid(row=3, column=0, sticky="nsew", padx=0, pady=0)
        fc.grid_columnconfigure(0, weight=1)

        r = 0

        self.industry_group = FilterDropdown(fc, "INDUSTRIES", ALL_INDUSTRIES, on_change=self._schedule_refilter)
        self.industry_group.grid(row=r, column=0, sticky="ew", padx=10, pady=(4, 0))
        r += 1

        self.exclude_group = FilterDropdown(fc, "EXCLUDE", DEFAULT_EXCLUDED, prechecked=DEFAULT_EXCLUDED,
                                             on_change=self._schedule_refilter, label_color=DANGER)
        self.exclude_group.grid(row=r, column=0, sticky="ew", padx=10, pady=(4, 0))
        r += 1

        ctk.CTkLabel(fc, text="EMPLOYEES", font=(FONT_FAMILY, 10, "bold"),
                     text_color=TEXT_SECONDARY, anchor="w").grid(row=r, column=0, sticky="ew", padx=14, pady=(6, 0))
        r += 1
        empf = ctk.CTkFrame(fc, fg_color="transparent")
        empf.grid(row=r, column=0, sticky="ew", padx=14, pady=2)
        empf.grid_columnconfigure((0, 1, 2), weight=1)
        ctk.CTkLabel(empf, text="From", font=(FONT_FAMILY, 10), text_color=TEXT_SECONDARY).grid(row=0, column=0, sticky="w", padx=(0, 2))
        self.emp_min_var = ctk.StringVar()
        self.emp_min_var.trace_add("write", self._schedule_refilter)
        ctk.CTkEntry(empf, textvariable=self.emp_min_var, placeholder_text="0",
                     fg_color=CARD_LIGHT, text_color=TEXT, font=(FONT_FAMILY, 11),
                     border_width=0, corner_radius=6, height=30,
                     ).grid(row=0, column=1, sticky="ew", padx=(0, 4))
        ctk.CTkLabel(empf, text="To", font=(FONT_FAMILY, 10), text_color=TEXT_SECONDARY).grid(row=0, column=2, sticky="w", padx=(0, 2))
        self.emp_max_var = ctk.StringVar()
        self.emp_max_var.trace_add("write", self._schedule_refilter)
        ctk.CTkEntry(empf, textvariable=self.emp_max_var, placeholder_text="any",
                     fg_color=CARD_LIGHT, text_color=TEXT, font=(FONT_FAMILY, 11),
                     border_width=0, corner_radius=6, height=30,
                     ).grid(row=0, column=3, sticky="ew")
        r += 1

        self.region_group = FilterDropdown(fc, "REGIONS", ALL_REGIONS, on_change=self._schedule_refilter)
        self.region_group.grid(row=r, column=0, sticky="ew", padx=10, pady=(4, 0))
        r += 1

        # Country filter
        ctk.CTkLabel(fc, text="COUNTRY", font=(FONT_FAMILY, 10, "bold"),
                     text_color=TEXT_SECONDARY, anchor="w").grid(row=r, column=0, sticky="ew", padx=14, pady=(6, 0))
        r += 1
        self.country_var = ctk.StringVar(value="All")
        self.country_var.trace_add("write", self._schedule_refilter)
        self.country_dropdown = ctk.CTkOptionMenu(
            fc, values=["All"], variable=self.country_var,
            fg_color=CARD_LIGHT, button_color="#3a3f4e", button_hover_color=ACCENT,
            text_color=TEXT, font=(FONT_FAMILY, 11),
            dropdown_fg_color=CARD, dropdown_text_color=TEXT, dropdown_font=(FONT_FAMILY, 11),
            corner_radius=6,
        )
        self.country_dropdown.grid(row=r, column=0, sticky="ew", padx=14, pady=2)
        r += 1

        self.regulatory_group = FilterDropdown(fc, "REGULATORY", REGULATORY_OPTIONS, on_change=self._schedule_refilter)
        self.regulatory_group.grid(row=r, column=0, sticky="ew", padx=10, pady=(4, 0))
        r += 1

        ctk.CTkLabel(fc, text="COMMITMENT", font=(FONT_FAMILY, 10, "bold"),
                     text_color=TEXT_SECONDARY, anchor="w").grid(row=r, column=0, sticky="ew", padx=14, pady=(6, 0))
        r += 1
        self.commit_var = ctk.StringVar(value="All")
        self.commit_var.trace_add("write", self._schedule_refilter)
        self.commit_dropdown = ctk.CTkOptionMenu(
            fc, values=COMMITMENT_STATUSES, variable=self.commit_var,
            fg_color=CARD_LIGHT, button_color="#3a3f4e", button_hover_color=ACCENT,
            text_color=TEXT, font=(FONT_FAMILY, 11),
            dropdown_fg_color=CARD, dropdown_text_color=TEXT, dropdown_font=(FONT_FAMILY, 11),
            corner_radius=6,
        )
        self.commit_dropdown.grid(row=r, column=0, sticky="ew", padx=14, pady=2)
        r += 1

        # Target Year range
        ctk.CTkLabel(fc, text="TARGET YEAR", font=(FONT_FAMILY, 10, "bold"),
                     text_color=TEXT_SECONDARY, anchor="w").grid(row=r, column=0, sticky="ew", padx=14, pady=(6, 0))
        r += 1
        tyf = ctk.CTkFrame(fc, fg_color="transparent")
        tyf.grid(row=r, column=0, sticky="ew", padx=14, pady=2)
        tyf.grid_columnconfigure((0, 1, 2), weight=1)
        ctk.CTkLabel(tyf, text="From", font=(FONT_FAMILY, 10), text_color=TEXT_SECONDARY).grid(row=0, column=0, sticky="w", padx=(0, 2))
        self.target_year_min_var = ctk.StringVar()
        self.target_year_min_var.trace_add("write", self._schedule_refilter)
        ctk.CTkEntry(tyf, textvariable=self.target_year_min_var, placeholder_text="2025",
                     fg_color=CARD_LIGHT, text_color=TEXT, font=(FONT_FAMILY, 11),
                     border_width=0, corner_radius=6, height=30,
                     ).grid(row=0, column=1, sticky="ew", padx=(0, 4))
        ctk.CTkLabel(tyf, text="To", font=(FONT_FAMILY, 10), text_color=TEXT_SECONDARY).grid(row=0, column=2, sticky="w", padx=(0, 2))
        self.target_year_max_var = ctk.StringVar()
        self.target_year_max_var.trace_add("write", self._schedule_refilter)
        ctk.CTkEntry(tyf, textvariable=self.target_year_max_var, placeholder_text="2030",
                     fg_color=CARD_LIGHT, text_color=TEXT, font=(FONT_FAMILY, 11),
                     border_width=0, corner_radius=6, height=30,
                     ).grid(row=0, column=3, sticky="ew")
        r += 1

        # ICP Score range
        ctk.CTkLabel(fc, text="ICP SCORE", font=(FONT_FAMILY, 10, "bold"),
                     text_color=TEXT_SECONDARY, anchor="w").grid(row=r, column=0, sticky="ew", padx=14, pady=(6, 0))
        r += 1
        icpf = ctk.CTkFrame(fc, fg_color="transparent")
        icpf.grid(row=r, column=0, sticky="ew", padx=14, pady=2)
        icpf.grid_columnconfigure((0, 1, 2), weight=1)
        ctk.CTkLabel(icpf, text="Min", font=(FONT_FAMILY, 10), text_color=TEXT_SECONDARY).grid(row=0, column=0, sticky="w", padx=(0, 2))
        self.icp_score_min_var = ctk.StringVar()
        self.icp_score_min_var.trace_add("write", self._schedule_refilter)
        ctk.CTkEntry(icpf, textvariable=self.icp_score_min_var, placeholder_text="0",
                     fg_color=CARD_LIGHT, text_color=TEXT, font=(FONT_FAMILY, 11),
                     border_width=0, corner_radius=6, height=30,
                     ).grid(row=0, column=1, sticky="ew", padx=(0, 4))
        ctk.CTkLabel(icpf, text="Max", font=(FONT_FAMILY, 10), text_color=TEXT_SECONDARY).grid(row=0, column=2, sticky="w", padx=(0, 2))
        self.icp_score_max_var = ctk.StringVar()
        self.icp_score_max_var.trace_add("write", self._schedule_refilter)
        ctk.CTkEntry(icpf, textvariable=self.icp_score_max_var, placeholder_text="100",
                     fg_color=CARD_LIGHT, text_color=TEXT, font=(FONT_FAMILY, 11),
                     border_width=0, corner_radius=6, height=30,
                     ).grid(row=0, column=3, sticky="ew")
        r += 1

        self.lead_status_group = FilterDropdown(fc, "LEAD STATUS", LEAD_STATUS_OPTIONS, on_change=self._schedule_refilter)
        self.lead_status_group.grid(row=r, column=0, sticky="ew", padx=10, pady=(4, 0))
        r += 1

        # Last Fetch freshness filter
        ctk.CTkLabel(fc, text="LAST FETCHED", font=(FONT_FAMILY, 10, "bold"),
                     text_color=TEXT_SECONDARY, anchor="w").grid(row=r, column=0, sticky="ew", padx=14, pady=(6, 0))
        r += 1
        lff = ctk.CTkFrame(fc, fg_color="transparent")
        lff.grid(row=r, column=0, sticky="ew", padx=14, pady=2)
        lff.grid_columnconfigure((0, 1, 2), weight=1)
        ctk.CTkLabel(lff, text="From", font=(FONT_FAMILY, 10), text_color=TEXT_SECONDARY).grid(row=0, column=0, sticky="w", padx=(0, 2))
        self.fetch_from_var = ctk.StringVar()
        self.fetch_from_var.trace_add("write", self._schedule_refilter)
        ctk.CTkEntry(lff, textvariable=self.fetch_from_var, placeholder_text="2026-01-01",
                     fg_color=CARD_LIGHT, text_color=TEXT, font=(FONT_FAMILY, 11),
                     border_width=0, corner_radius=6, height=30,
                     ).grid(row=0, column=1, sticky="ew", padx=(0, 4))
        ctk.CTkLabel(lff, text="To", font=(FONT_FAMILY, 10), text_color=TEXT_SECONDARY).grid(row=0, column=2, sticky="w", padx=(0, 2))
        self.fetch_to_var = ctk.StringVar()
        self.fetch_to_var.trace_add("write", self._schedule_refilter)
        ctk.CTkEntry(lff, textvariable=self.fetch_to_var, placeholder_text="2026-12-31",
                     fg_color=CARD_LIGHT, text_color=TEXT, font=(FONT_FAMILY, 11),
                     border_width=0, corner_radius=6, height=30,
                     ).grid(row=0, column=3, sticky="ew")
        r += 1

        # Find button
        btn_row = ctk.CTkFrame(fc, fg_color="transparent")
        btn_row.grid(row=r, column=0, sticky="ew", padx=14, pady=(10, 2))
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=1)

        self.find_btn = ctk.CTkButton(
            btn_row, text="\U0001f50d  Find", command=self._on_find_companies,
            fg_color=ACCENT, hover_color="#00b898", text_color="#0a0a0a",
            font=(FONT_FAMILY, 13, "bold"), height=36, corner_radius=8,
        )
        self.find_btn.grid(row=0, column=0, sticky="ew", padx=(0, 3))

        self.reset_filters_btn = ctk.CTkButton(
            btn_row, text="\u2716  Reset", command=self._on_reset_filters,
            fg_color=CARD_LIGHT, hover_color="#3a3f4e", text_color=TEXT,
            font=(FONT_FAMILY, 13), height=36, corner_radius=8,
        )
        self.reset_filters_btn.grid(row=0, column=1, sticky="ew", padx=(3, 0))

        r += 1

        ctk.CTkFrame(fc, fg_color="#2a2f3e", height=1).grid(row=r, column=0, sticky="ew", padx=14, pady=4)
        r += 1

        ctk.CTkLabel(fc, text="ENRICHMENT", font=(FONT_FAMILY, 10, "bold"),
                     text_color=TEXT_SECONDARY, anchor="w").grid(row=r, column=0, sticky="ew", padx=14, pady=(4, 0))
        r += 1

        self.enrich_status = ctk.CTkLabel(
            fc, text="", font=(FONT_FAMILY, 10), text_color=TEXT_SECONDARY, anchor="w", wraplength=250,
        )
        self.enrich_status.grid(row=r, column=0, sticky="ew", padx=14)
        r += 1

        self.enrich_progress = ctk.CTkProgressBar(fc, fg_color="#2a2f3e", progress_color=ACCENT, height=4)
        self.enrich_progress.grid(row=r, column=0, sticky="ew", padx=14, pady=(2, 4))
        self.enrich_progress.set(0)
        r += 1

        self.enrich_btn = ctk.CTkButton(
            fc, text="\U0001f50e  Enrich All", command=self._on_enrich_all,
            fg_color=CARD_LIGHT, hover_color="#3a3f4e", text_color=TEXT,
            font=(FONT_FAMILY, 11), corner_radius=6, height=32, state="disabled",
        )
        self.enrich_btn.grid(row=r, column=0, sticky="ew", padx=14, pady=2)
        r += 1

        ctk.CTkFrame(fc, fg_color="#2a2f3e", height=1).grid(row=r, column=0, sticky="ew", padx=14, pady=4)
        r += 1

        ctk.CTkLabel(fc, text="BULK ACTIONS", font=(FONT_FAMILY, 10, "bold"),
                     text_color=TEXT_SECONDARY, anchor="w").grid(row=r, column=0, sticky="ew", padx=14, pady=(4, 0))
        r += 1

        self.bulk_add_btn = ctk.CTkButton(
            fc, text="\u2b50 Add Filtered to My List", command=self._on_bulk_add_filtered,
            fg_color="#2e7d32", hover_color="#1b5e20", text_color="#ffffff",
            font=(FONT_FAMILY, 10), corner_radius=6, height=28,
        )
        self.bulk_add_btn.grid(row=r, column=0, sticky="ew", padx=14, pady=2)
        r += 1

        ctk.CTkFrame(fc, fg_color="#2a2f3e", height=1).grid(row=r, column=0, sticky="ew", padx=14, pady=4)
        r += 1

        ctk.CTkLabel(fc, text="WEBSITE VALIDATION", font=(FONT_FAMILY, 10, "bold"),
                     text_color=TEXT_SECONDARY, anchor="w").grid(row=r, column=0, sticky="ew", padx=14, pady=(4, 0))
        r += 1

        self.validate_status = ctk.CTkLabel(
            fc, text="", font=(FONT_FAMILY, 10), text_color=TEXT_SECONDARY, anchor="w", wraplength=220,
        )
        self.validate_status.grid(row=r, column=0, sticky="ew", padx=14)
        r += 1

        self.validate_btn = ctk.CTkButton(
            fc, text="\u2713 Validate Websites", command=self._on_validate_websites,
            fg_color=CARD_LIGHT, hover_color="#3a3f4e", text_color=TEXT,
            font=(FONT_FAMILY, 11), corner_radius=6, height=32,
        )
        self.validate_btn.grid(row=r, column=0, sticky="ew", padx=14, pady=2)
        r += 1

        ctk.CTkFrame(fc, fg_color="#2a2f3e", height=1).grid(row=r, column=0, sticky="ew", padx=14, pady=4)
        r += 1

        ctk.CTkLabel(fc, text="CLEARBIT WEBSITES", font=(FONT_FAMILY, 10, "bold"),
                     text_color=TEXT_SECONDARY, anchor="w").grid(row=r, column=0, sticky="ew", padx=14, pady=(4, 0))
        r += 1

        self.cb_status = ctk.CTkLabel(
            fc, text="", font=(FONT_FAMILY, 10), text_color=TEXT_SECONDARY, anchor="w", wraplength=220,
        )
        self.cb_status.grid(row=r, column=0, sticky="ew", padx=14)
        r += 1

        self.cb_progress = ctk.CTkProgressBar(fc, fg_color="#2a2f3e", progress_color="#e65100", height=4)
        self.cb_progress.grid(row=r, column=0, sticky="ew", padx=14, pady=(2, 4))
        self.cb_progress.set(0)
        r += 1

        self.cb_btn = ctk.CTkButton(
            fc, text="\U0001f310  Run Clearbit Batch", command=self._on_clearbit_batch,
            fg_color="#3a2a1a", hover_color="#5a3a2a", text_color="#ffb74d",
            font=(FONT_FAMILY, 11), corner_radius=6, height=32,
        )
        self.cb_btn.grid(row=r, column=0, sticky="ew", padx=14, pady=2)
        r += 1

        ctk.CTkFrame(fc, fg_color="#2a2f3e", height=1).grid(row=r, column=0, sticky="ew", padx=14, pady=4)
        r += 1

        ctk.CTkLabel(fc, text="WIKIPEDIA EMPLOYEES", font=(FONT_FAMILY, 10, "bold"),
                     text_color=TEXT_SECONDARY, anchor="w").grid(row=r, column=0, sticky="ew", padx=14, pady=(4, 0))
        r += 1

        self.wiki_status = ctk.CTkLabel(
            fc, text="", font=(FONT_FAMILY, 10), text_color=TEXT_SECONDARY, anchor="w", wraplength=220,
        )
        self.wiki_status.grid(row=r, column=0, sticky="ew", padx=14)
        r += 1

        self.wiki_progress = ctk.CTkProgressBar(fc, fg_color="#2a2f3e", progress_color="#42a5f5", height=4)
        self.wiki_progress.grid(row=r, column=0, sticky="ew", padx=14, pady=(2, 4))
        self.wiki_progress.set(0)
        r += 1

        self.wiki_btn = ctk.CTkButton(
            fc, text="\U0001f4cb  Fill Missing Employees", command=self._on_wikipedia_employees,
            fg_color="#1a3a5c", hover_color="#2a5a7c", text_color="#90caf9",
            font=(FONT_FAMILY, 11), corner_radius=6, height=32,
        )
        self.wiki_btn.grid(row=r, column=0, sticky="ew", padx=14, pady=2)
        r += 1

        ctk.CTkFrame(fc, fg_color="#2a2f3e", height=1).grid(row=r, column=0, sticky="ew", padx=14, pady=4)
        r += 1

        ctk.CTkLabel(fc, text="CLAY EXPORT", font=(FONT_FAMILY, 10, "bold"),
                     text_color=TEXT_SECONDARY, anchor="w").grid(row=r, column=0, sticky="ew", padx=14, pady=(4, 0))
        r += 1

        self.clay_status = ctk.CTkLabel(
            fc, text="", font=(FONT_FAMILY, 10), text_color=TEXT_SECONDARY, anchor="w", wraplength=220,
        )
        self.clay_status.grid(row=r, column=0, sticky="ew", padx=14)
        r += 1

        self.clay_url_entry = ctk.CTkEntry(
            fc, placeholder_text="Clay table webhook URL",
            fg_color="#0f1117", border_width=0, text_color=TEXT, font=(FONT_FAMILY, 10),
        )
        self.clay_url_entry.grid(row=r, column=0, sticky="ew", padx=14, pady=2)
        r += 1

        self.clay_btn = ctk.CTkButton(
            fc, text="\U0001f4e4  Push to Clay", command=self._on_push_to_clay,
            fg_color="#1a2a3a", hover_color="#2a4a5a", text_color="#80cbc4",
            font=(FONT_FAMILY, 11), corner_radius=6, height=32,
        )
        self.clay_btn.grid(row=r, column=0, sticky="ew", padx=14, pady=2)
        r += 1

        ctk.CTkFrame(fc, fg_color="#2a2f3e", height=1).grid(row=r, column=0, sticky="ew", padx=14, pady=4)
        r += 1

        ctk.CTkLabel(fc, text="APOLLO API KEY", font=(FONT_FAMILY, 10, "bold"),
                     text_color=TEXT_SECONDARY, anchor="w").grid(row=r, column=0, sticky="ew", padx=14, pady=(4, 0))
        r += 1

        self.apollo_key_entry = ctk.CTkEntry(
            fc, placeholder_text="Apollo API Key (for contact search)",
            fg_color="#0f1117", border_width=0, text_color=TEXT, font=(FONT_FAMILY, 10),
        )
        self.apollo_key_entry.insert(0, _load_config().get("apollo_key", ""))
        self.apollo_key_entry.bind("<KeyRelease>", lambda e: _save_config(apollo_key=self.apollo_key_entry.get().strip()))
        self.apollo_key_entry.grid(row=r, column=0, sticky="ew", padx=14, pady=2)
        r += 1

        self.count_label = ctk.CTkLabel(
            fc, text="0 companies found", font=(FONT_FAMILY, 11), text_color=TEXT_SECONDARY,
        )
        self.count_label.grid(row=r, column=0, pady=(4, 14))
        r += 1

        fc.grid_rowconfigure(r, weight=1)

    def _build_center_panel(self):
        center = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        center.grid(row=0, column=1, sticky="nsew")
        center.grid_rowconfigure(1, weight=1)
        center.grid_columnconfigure(0, weight=1)

        # Search bar
        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *a: self._on_search_debounced())

        sf = ctk.CTkFrame(center, fg_color=CARD, corner_radius=8)
        sf.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))

        ctk.CTkLabel(sf, text="\U0001f50d", font=(FONT_FAMILY, 14), text_color=TEXT_SECONDARY
                     ).pack(side="left", padx=(10, 4), pady=8)

        self.search_entry = ctk.CTkEntry(
            sf, textvariable=self.search_var,
            placeholder_text="Search by name, country, or industry...",
            fg_color="transparent", border_width=0,
            text_color=TEXT, font=(FONT_FAMILY, 12),
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=4, pady=8)

        self.my_list_btn = ctk.CTkButton(
            sf, text=f"\u2b50 My List ({self.my_list_count})", command=self._on_show_my_list,
            fg_color=CARD_LIGHT, hover_color="#3a3f4e", text_color=TEXT,
            font=(FONT_FAMILY, 11), corner_radius=6, width=110,
        )
        self.my_list_btn.pack(side="right", padx=(4, 8), pady=6)

        # Table frame with both scrollbars
        tf = ctk.CTkFrame(center, fg_color=CARD, corner_radius=8)
        tf.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 8))
        tf.grid_rowconfigure(0, weight=1)
        tf.grid_columnconfigure(0, weight=1)

        cols = ("company", "country", "industry", "employees", "revenue", "sbti_status", "region", "target_year", "website", "score", "lead_status")
        self.tree = ttk.Treeview(tf, columns=cols, show="headings", selectmode="extended", style="Dark.Treeview")

        headings = ["Company Name", "Country", "Industry", "Employees", "Revenue", "SBTi Status", "Region", "Target Yr", "Website", "Score", "Lead"]
        col_widths = [200, 110, 130, 80, 90, 130, 80, 65, 140, 70, 60]

        for cid, hdr, w in zip(cols, headings, col_widths):
            self.tree.heading(cid, text=hdr, command=lambda c=cid: self._on_tree_sort(c))
            self.tree.column(cid, width=w, minwidth=50, stretch=(cid == "company"))
        self.tree.column("score", anchor="e")
        self.tree.column("revenue", anchor="e")
        self.tree.column("lead_status", anchor="center")

        # Vertical scrollbar
        vs = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview, style="Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=vs.set)

        # Horizontal scrollbar
        hs = ttk.Scrollbar(tf, orient="horizontal", command=self.tree.xview, style="Horizontal.TScrollbar")
        self.tree.configure(xscrollcommand=hs.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        hs.grid(row=1, column=0, sticky="ew")

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Button-3>", self._on_tree_right_click)

        import tkinter as _tk
        self.tree_context_menu = _tk.Menu(self, tearoff=0, bg="#ffffff", fg="#222222",
                                           activebackground="#e8e8e8", activeforeground="#222222",
                                           font=("Segoe UI", 10))
        self.tree_context_menu.add_command(
            label="Enrich Employees & Revenue via Apollo",
            command=self._on_apollo_enrich_selected,
        )

        # Row indicator tags (subtle)


        # Pagination
        pf = ctk.CTkFrame(center, fg_color="transparent")
        pf.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 8))

        self.prev_btn = ctk.CTkButton(
            pf, text="\u25c0  Previous", command=self._on_prev_page,
            fg_color=CARD_LIGHT, hover_color="#3a3f4e", text_color=TEXT,
            font=(FONT_FAMILY, 11), corner_radius=6, state="disabled", width=100,
        )
        self.prev_btn.pack(side="left", padx=(0, 8))

        self.page_label = ctk.CTkLabel(pf, text="Page 1 of 1",
                                       font=(FONT_FAMILY, 11), text_color=TEXT_SECONDARY)
        self.page_label.pack(side="left")

        self.next_btn = ctk.CTkButton(
            pf, text="Next  \u25b6", command=self._on_next_page,
            fg_color=CARD_LIGHT, hover_color="#3a3f4e", text_color=TEXT,
            font=(FONT_FAMILY, 11), corner_radius=6, state="disabled", width=100,
        )
        self.next_btn.pack(side="left", padx=8)

        ctk.CTkFrame(pf, fg_color="transparent").pack(side="left", fill="x", expand=True)

        self.sort_var = ctk.StringVar(value="Score (High to Low)")
        self.sort_dropdown = ctk.CTkOptionMenu(
            pf, values=["Score (High to Low)", "Score (Low to High)", "Company (A-Z)", "Company (Z-A)"],
            variable=self.sort_var, fg_color=CARD_LIGHT, button_color="#3a3f4e", button_hover_color=ACCENT,
            text_color=TEXT, font=(FONT_FAMILY, 11),
            dropdown_fg_color=CARD, dropdown_text_color=TEXT, dropdown_font=(FONT_FAMILY, 11),
            corner_radius=6, width=160, command=lambda x: self._render_table(),
        )
        self.sort_dropdown.pack(side="right")

    def _build_right_panel(self):
        right = ctk.CTkFrame(self, fg_color=CARD, width=330, corner_radius=0)
        right.grid(row=0, column=2, sticky="nsew")
        right.grid_propagate(False)

        self.right_scroll = ctk.CTkScrollableFrame(right, fg_color="transparent", corner_radius=0)
        self.right_scroll.pack(fill="both", expand=True, padx=0, pady=0)

        self.empty_label = ctk.CTkLabel(
            self.right_scroll, text="Select a company\nto view details",
            font=(FONT_FAMILY, 14), text_color=TEXT_SECONDARY, justify="center",
        )
        self.empty_label.pack(expand=True, pady=100)

    def _build_bottom_bar(self):
        bottom = ctk.CTkFrame(self, fg_color=CARD, height=32, corner_radius=0)
        bottom.grid(row=1, column=0, columnspan=3, sticky="ew")
        bottom.grid_propagate(False)
        bottom.grid_columnconfigure(0, weight=1)

        self.status_bar = StatusBar(bottom)
        self.status_bar.pack(fill="x", expand=True)

        ef = ctk.CTkFrame(bottom, fg_color="transparent")
        ef.pack(side="right", padx=8, pady=2)

        self.export_csv_btn = ctk.CTkButton(
            ef, text="Export CSV", command=self._on_export_csv,
            fg_color=CARD_LIGHT, hover_color="#3a3f4e", text_color=TEXT,
            font=(FONT_FAMILY, 11), corner_radius=6, width=90, state="disabled",
        )
        self.export_csv_btn.pack(side="left", padx=2)

        self.export_sheets_btn = ctk.CTkButton(
            ef, text="Sheets Format", command=self._on_export_sheets,
            fg_color=CARD_LIGHT, hover_color="#3a3f4e", text_color=TEXT,
            font=(FONT_FAMILY, 11), corner_radius=6, width=110, state="disabled",
        )
        self.export_sheets_btn.pack(side="left", padx=2)

        self.export_mylist_btn = ctk.CTkButton(
            ef, text="\u2b50 Export My List", command=self._on_export_my_list,
            fg_color=CARD_LIGHT, hover_color="#3a3f4e", text_color=TEXT,
            font=(FONT_FAMILY, 11), corner_radius=6, width=120,
        )
        self.export_mylist_btn.pack(side="left", padx=2)

        self.export_xlsx_btn = ctk.CTkButton(
            ef, text="Excel (.xlsx)", command=self._on_export_xlsx,
            fg_color=CARD_LIGHT, hover_color="#3a3f4e", text_color=TEXT,
            font=(FONT_FAMILY, 11), corner_radius=6, width=100, state="disabled",
        )
        self.export_xlsx_btn.pack(side="left", padx=2)

    # ======================= DATA SOURCE =======================

    def _init_search_col(self):
        if self.df is not None and not self.df.empty:
            self.df["_search_col"] = (
                self.df["company"].fillna("").str.lower() + " | "
                + self.df["country"].fillna("").str.lower() + " | "
                + self.df["industry"].fillna("").str.lower()
            )
        self._rebuild_company_index()

    def _rebuild_company_index(self):
        idx = self.filtered_df if self.filtered_df is not None else self.df
        if idx is not None and not idx.empty:
            self._company_index = dict(zip(idx["company"].str.lower().str.strip(), idx.index))
        else:
            self._company_index = {}

    def _update_source_display(self):
        n = len(self.df) if self.df is not None else 0
        date_str = get_cache_date_str()
        has_eu_tax = self.df is not None and "EU-Tax" in self.df["source_flags"].values if "source_flags" in self.df.columns else False
        eu_suffix = " + EU-Taxonomy" if has_eu_tax else ""
        if date_str:
            self.source_info.configure(text=f"\U0001f4e1 SBTi{eu_suffix}  \u2022  cached {date_str}")
            self.status_bar.set_source(f"SBTi{eu_suffix} \u2022 {date_str}")
        elif n > 0:
            self.source_info.configure(text=f"\U0001f4e1 SBTi{eu_suffix}")
            self.status_bar.set_source(f"SBTi{eu_suffix}")
        else:
            self.source_info.configure(text="")
            self.status_bar.set_source("")

    def _check_cache_on_startup(self):
        def check():
            cached = load_cached_data()
            if cached is not None:
                self.df = cached
                self._ensure_columns()
                save_cached_data(self.df)
                self._df_version += 1
                self._init_search_col()
                n = len(cached)
                self.after(0, lambda nn=n: self.status_bar.set_status(f"Loaded {nn:,} companies"))
                self.after(0, lambda: self._update_source_display())
                self.after(0, lambda: self._populate_country_dropdown())
                self.after(0, lambda nn=n: self.status_bar.set_counts(nn, 0, self.my_list_count))
                if needs_refresh():
                    self.after(0, lambda: self.dl_status.configure(text="Cache is 7+ days old - refresh recommended."))
                else:
                    self.after(0, lambda: self.dl_status.configure(text="Data loaded from cache."))
                if self.df is not None and not self.df.empty:
                    self.after(0, self._on_find_companies)
            else:
                self.after(0, lambda: self.dl_status.configure(text="No cached data. Download SBTi database to begin."))
                self.after(0, lambda: self._update_source_display())
        threading.Thread(target=check, daemon=True).start()

    def _ensure_columns(self):
        if self.df is None:
            return
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        if "last_sbti_fetch" not in self.df.columns:
            self.df["last_sbti_fetch"] = ""

    def _populate_country_dropdown(self):
        if self.df is None or "country" not in self.df.columns:
            return
        countries = self.df["country"].dropna().unique().tolist()
        countries.sort()
        values = ["All"] + countries
        self.country_dropdown.configure(values=values)
        if self.country_var.get() not in values:
            self.country_var.set("All")

    def _on_download_sbti(self):
        self.dl_btn.configure(state="disabled", text="Downloading...")

        def cb(msg, pct):
            self.after(0, lambda: self.dl_status.configure(text=msg))
            self.after(0, lambda: self.dl_progress.set(max(0, pct / 100)))
            if pct == 100:
                self.after(0, lambda: self.dl_btn.configure(state="normal", text="Download SBTi Database"))
            elif pct < 0:
                self.after(0, lambda: self.dl_btn.configure(state="normal", text="Retry Download"))

        def run():
            try:
                old_df = self.df.copy() if self.df is not None else None
                fresh = download_sbti_data(progress_callback=cb)
                old_count = len(old_df) if old_df is not None else 0
                self.df, updated, new_added = merge_sbti_update(old_df, fresh)
                self._df_version += 1
                self._init_search_col()
                n = len(self.df)
                parts = [f"Loaded {n:,} companies"]
                if updated:
                    parts.append(f"{updated} updated")
                if new_added:
                    parts.append(f"{new_added} new")
                self.after(0, lambda: self.status_bar.set_status(" | ".join(parts)))
                self.after(0, lambda: self.dl_status.configure(text=" | ".join(parts)))
                self.after(0, lambda: self._update_source_display())
                self.after(0, lambda: self._populate_country_dropdown())
                self.after(0, lambda nn=n: self.status_bar.set_counts(nn, 0, self.my_list_count))
                self.after(0, lambda nn=n: self.count_label.configure(text=f"{nn:,} companies loaded"))
                if self.df is not None and not self.df.empty:
                    self.after(0, self._on_find_companies)
            except Exception as e:
                err = str(e)[:60]
                self.after(0, lambda e=err: self.dl_status.configure(text=f"Download failed: {e}..."))
                self.after(0, lambda: self.dl_btn.configure(state="normal", text="Retry Download"))
                self.after(0, lambda: self.status_bar.set_status("Error downloading SBTi data"))
        threading.Thread(target=run, daemon=True).start()

    def _on_download_eu_taxonomy(self):
        self.eu_tax_btn.configure(state="disabled", text="Loading...")
        self.dl_status.configure(text="Downloading EU Taxonomy data...")

        def run():
            try:
                eu_df = download_eu_taxonomy(force=True)
                if eu_df.empty:
                    self.after(0, lambda: self.dl_status.configure(text="EU Taxonomy: no data found"))
                    return
                if self.df is not None and not self.df.empty:
                    self.df = merge_eu_taxonomy(self.df, eu_df)
                else:
                    self.df = eu_df
                self._df_version += 1
                self._init_search_col()
                n_new = len(eu_df)
                n_total = len(self.df) if self.df is not None else 0
                self.after(0, lambda n=n_new, t=n_total: self.dl_status.configure(
                    text=f"EU Taxonomy: {n} companies merged ({t} total)"))
                self.after(0, lambda: self._update_source_display())
                self.after(0, lambda: self._populate_country_dropdown())
                if self.df is not None:
                    total = len(self.df)
                    self.after(0, lambda t=total: self.status_bar.set_counts(t, 0, self.my_list_count))
                    self.after(0, lambda t=total: self.count_label.configure(text=f"{t:,} companies loaded"))
                if self.df is not None and not self.df.empty:
                    self.after(0, self._on_find_companies)
            except Exception as e:
                err = str(e)[:60]
                self.after(0, lambda e=err: self.dl_status.configure(text=f"EU Taxonomy error: {e}"))
            finally:
                self.after(0, lambda: self.eu_tax_btn.configure(state="normal", text="+ EU Taxonomy (190 cos)"))
        threading.Thread(target=run, daemon=True).start()

    # ======================= FILTERS =======================

    def _schedule_refilter(self, *args):
        if hasattr(self, '_refilter_timer') and self._refilter_timer:
            self.after_cancel(self._refilter_timer)
        self._refilter_timer = self.after(300, self._on_find_companies)

    def _on_reset_filters(self):
        self.industry_group.set_all(False)
        self.exclude_group.set_all(False)
        self.region_group.set_all(False)
        self.regulatory_group.set_all(False)
        self.emp_min_var.set("")
        self.emp_max_var.set("")
        self.country_var.set("All")
        self.commit_var.set("All")
        self.target_year_min_var.set("")
        self.target_year_max_var.set("")
        self.icp_score_min_var.set("")
        self.icp_score_max_var.set("")
        self.lead_status_group.set_all(False)
        self.fetch_from_var.set("")
        self.fetch_to_var.set("")
        self.search_var.set("")
        self._on_find_companies()

    def _on_find_companies(self):
        if self.df is None:
            messagebox.showwarning("No Data", "Please download the SBTi database first.")
            return

        if getattr(self, '_filter_running', False):
            return

        def _int_or_none(v):
            try:
                return int(v.strip())
            except:
                return None

        filters = {
            "industries": tuple(sorted(self.industry_group.get_selected())),
            "excluded_industries": tuple(sorted(self.exclude_group.get_selected())),
            "employees_min": _int_or_none(self.emp_min_var.get()),
            "employees_max": _int_or_none(self.emp_max_var.get()),
            "regions": tuple(sorted(self.region_group.get_selected())),
            "regulatory": tuple(sorted(self.regulatory_group.get_selected())),
            "commitment": self.commit_var.get(),
            "countries": tuple([]) if self.country_var.get() == "All" else tuple([self.country_var.get()]),
            "target_year_min": _int_or_none(self.target_year_min_var.get()),
            "target_year_max": _int_or_none(self.target_year_max_var.get()),
            "icp_score_min": _int_or_none(self.icp_score_min_var.get()),
            "icp_score_max": _int_or_none(self.icp_score_max_var.get()),
            "lead_statuses": tuple(sorted(self.lead_status_group.get_selected())),
            "fetch_from": self.fetch_from_var.get().strip(),
            "fetch_to": self.fetch_to_var.get().strip(),
        }

        fhash = hash(tuple(sorted(filters.items())))
        dv = getattr(self, '_df_version', 0)
        if (hasattr(self, '_last_filter_hash') and self._last_filter_hash == fhash
                and self._last_filter_dfv == dv and self.filtered_df is not None):
            self.find_btn.configure(state="normal", text="\U0001f50d  Find Companies")
            return

        self.find_btn.configure(state="disabled", text="\u23f3  Searching...")
        self.status_bar.set_status("Computing scores...")
        self._filter_running = True

        def run():
            try:
                df = self.df.copy()
                for col in ["icp_score", "score_breakdown", "lead_status"]:
                    if col in df.columns:
                        df = df.drop(columns=[col])
                df = compute_scores(df)

                f_dict = {k: list(v) if isinstance(v, tuple) else v for k, v in filters.items()}
                result = apply_filters(df, f_dict)
                if result is not None and not result.empty:
                    c = filters.get("commitment", "All")
                    if c != "All":
                        result = result[result["sbti_status"].str.lower().str.contains(c.lower(), na=False)]

                self._last_filter_hash = fhash
                self._last_filter_dfv = dv + 1
                self.after(0, lambda d=df, r=result: self._on_scores_ready(d, r))
            except Exception as e:
                self.after(0, lambda: self.status_bar.set_status("Computation failed"))
                self.after(0, lambda: messagebox.showerror("Error", str(e)))
                self.after(0, lambda: self.find_btn.configure(state="normal", text="\U0001f50d  Find Companies"))
            finally:
                self.after(0, lambda: setattr(self, '_filter_running', False))
        threading.Thread(target=run, daemon=True).start()

    def _on_scores_ready(self, df, result):
        self.df = df
        self._df_version += 1
        self.status_bar.set_status("Saving...")
        save_cached_data(self.df)
        self._on_filters_applied(result)
        self.find_btn.configure(state="normal", text="\U0001f50d  Find Companies")

    def _on_filters_applied(self, result):
        if result is None or result.empty:
            self.filtered_df = None
            self.current_page = 0
            self.total_pages = 0
            self.count_label.configure(text="0 companies found")
            self.status_bar.set_counts(len(self.df) if self.df is not None else 0, 0, self.my_list_count)
            self._render_empty_table()
            self.export_csv_btn.configure(state="disabled")
            self.export_sheets_btn.configure(state="disabled")
            self.export_xlsx_btn.configure(state="disabled")
            self.enrich_btn.configure(state="disabled")
            self.status_bar.set_status("No companies match your filters.")
            return

        self.filtered_df = result
        self.current_page = 0
        self.total_pages = max(1, (len(result) + ROWS_PER_PAGE - 1) // ROWS_PER_PAGE)
        n = len(result)
        self.count_label.configure(text=f"{n:,} companies found")
        self.status_bar.set_counts(len(self.df) if self.df is not None else 0, n, self.my_list_count)
        self.status_bar.set_status(f"Found {n:,} matching companies")
        self.export_csv_btn.configure(state="normal")
        self.export_sheets_btn.configure(state="normal")
        self.export_xlsx_btn.configure(state="normal")
        self.enrich_btn.configure(state="normal")
        self._rebuild_company_index()
        self._render_table()

    # ======================= ENRICHMENT =======================

    def _on_enrich_all(self):
        if self.filtered_df is None or self.filtered_df.empty:
            return
        self.enrich_btn.configure(state="disabled", text="Enriching...")

        companies = [c for c in self.filtered_df["company"].dropna().unique().tolist() if c.strip()]

        enrich_filters = {
            "industries": self.industry_group.get_selected(),
            "excluded_industries": self.exclude_group.get_selected(),
            "regions": self.region_group.get_selected(),
            "regulatory": self.regulatory_group.get_selected(),
            "commitment": self.commit_var.get(),
            "countries": [] if self.country_var.get() == "All" else [self.country_var.get()],
            "target_year_min": None,
            "target_year_max": None,
            "icp_score_min": None,
            "icp_score_max": None,
        }

        def cb(msg, pct):
            self.after(0, lambda: self.enrich_status.configure(text=msg))
            self.after(0, lambda: self.enrich_progress.set(max(0, pct / 100)))

        def run():
            try:
                results = batch_enrich(companies, progress_callback=cb)
                self.enrichment_results = results
                self.df = merge_enrichment(self.df, results)
                self._df_version += 1
                self._init_search_col()

                from filters import apply_filters
                refiltered = apply_filters(self.df, enrich_filters)
                if refiltered is not None and not refiltered.empty:
                    c = enrich_filters["commitment"]
                    if c != "All":
                        refiltered = refiltered[refiltered["sbti_status"].str.lower().str.contains(c.lower(), na=False)]

                self.after(0, lambda: self._on_filters_applied(refiltered))
                self.after(0, lambda: self.enrich_btn.configure(state="normal", text="\U0001f50e  Re-Enrich"))
                self.after(0, lambda: self.enrich_status.configure(text=f"Enriched {len(results)} companies. \u2713 OSI + SEC"))
            except Exception as e:
                self.after(0, lambda: self.enrich_status.configure(text=f"Error: {str(e)[:50]}"))
                self.after(0, lambda: self.enrich_btn.configure(state="normal", text="\U0001f50e  Enrich All"))
        threading.Thread(target=run, daemon=True).start()

    # ======================= CLEARBIT BATCH =======================

    def _on_clearbit_batch(self):
        if self.df is None or self.df.empty or self._cb_running:
            return
        self._cb_running = True
        self.cb_btn.configure(state="disabled", text="Running...")
        self.cb_status.configure(text="Starting Clearbit batch...")
        self.cb_progress.set(0)
        threading.Thread(target=self._clearbit_thread, daemon=True).start()

    def _clearbit_thread(self):
        try:
            from clearbit_enricher import run_batch

            def progress(current, total, resumed=False, rate=0, remaining=0):
                pct = (current / total) * 100 if total > 0 else 0
                eta = f"{remaining / 60:.1f} min" if remaining > 0 else ""
                status = "Resuming..." if resumed else f"{current}/{total} ({pct:.1f}%)"
                if rate > 0:
                    status += f" | {rate:.1f}/sec | ETA {eta}"
                self.after(0, lambda s=status: self.cb_status.configure(text=s))
                self.after(0, lambda p=pct: self.cb_progress.set(max(0, p / 100)))

            result_df = run_batch(self.df, progress_callback=progress)

            for col in ["clearbit_domain", "clearbit_confidence", "source_flags"]:
                if col not in self.df.columns:
                    self.df[col] = ""

            for _, cb_row in result_df.iterrows():
                name = str(cb_row.get("company", "")).strip()
                domain = str(cb_row.get("domain", "") or "")
                if not name or not domain:
                    continue
                mask = self.df["company"].str.lower().str.strip() == name.lower()
                if not mask.any():
                    continue
                self.df.loc[mask, "clearbit_domain"] = domain
                self.df.loc[mask, "clearbit_confidence"] = cb_row.get("confidence", "")
                self.df.loc[mask, "website"] = domain
                existing = str(self.df.loc[mask, "source_flags"].iloc[0]) if "source_flags" in self.df.columns and self.df.loc[mask, "source_flags"].iloc[0] else ""
                if "CB" not in existing:
                    self.df.loc[mask, "source_flags"] = (existing + "+CB" if existing else "CB")

            if len(result_df) > 0:
                save_cached_data(self.df)

            self._df_version += 1
            self.after(0, lambda: self.cb_status.configure(text="Clearbit batch complete!"))
            self.after(0, self._on_find_companies)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.after(0, lambda: self.cb_status.configure(text=f"Error: {e}"))
        finally:
            self._cb_running = False
            self.after(0, lambda: self.cb_btn.configure(state="normal", text="\U0001f310  Run Clearbit Batch"))

    # ======================= WIKIPEDIA EMPLOYEES =======================

    def _on_wikipedia_employees(self):
        if self.df is None or self.df.empty or self._wiki_running:
            return
        self._wiki_running = True
        self.wiki_btn.configure(state="disabled", text="Fetching...")
        self.wiki_status.configure(text="Starting Wikipedia lookup...")
        threading.Thread(target=self._wikipedia_thread, daemon=True).start()

    def _wikipedia_thread(self):
        try:
            from wikipedia_enricher import run_batch

            if "employees" not in self.df.columns:
                self.df["employees"] = 0
            emp_col = pd.to_numeric(self.df["employees"], errors="coerce")
            empty_emp = emp_col.isna() | (emp_col == 0)
            companies = self.df.loc[empty_emp, "company"].dropna().unique().tolist()
            companies = [c for c in companies if str(c).strip()]
            total_pending = len(companies)

            if total_pending == 0:
                self.after(0, lambda: self.wiki_status.configure(text="No missing employees to fill."))
                self.after(0, lambda: self.wiki_btn.configure(state="normal", text="\U0001f4cb  Fill Missing Employees"))
                return

            def progress(current, total, resumed=False, rate=0, remaining=0):
                pct = (current / total) * 100 if total > 0 else 0
                eta = f"{remaining / 60:.1f} min" if remaining > 0 else ""
                status = "Resuming..." if resumed else f"{current}/{total} ({pct:.1f}%)"
                if rate > 0:
                    status += f" | {rate:.1f}/sec | ETA {eta}"
                self.after(0, lambda s=status: self.wiki_status.configure(text=s))
                self.after(0, lambda p=pct: self.wiki_progress.set(max(0, p / 100)))

            result_df = run_batch(companies, progress_callback=progress)

            found = 0
            updated = 0
            for _, row in result_df.iterrows():
                name = str(row.get("company", "")).strip()
                if not name:
                    continue
                raw = row.get("employees")
                if raw is None:
                    continue
                try:
                    if isinstance(raw, float) and math.isnan(raw):
                        continue
                    emp_count = int(float(raw))
                except (ValueError, TypeError, OverflowError):
                    continue
                if emp_count <= 0:
                    continue
                found += 1
                mask = self.df["company"].str.lower().str.strip() == name.lower()
                if not mask.any():
                    continue
                current = self.df.loc[mask, "employees"].iloc[0]
                try:
                    curr_val = int(float(current)) if current not in (None, "", "nan", 0) else 0
                except (ValueError, TypeError):
                    curr_val = 0
                if emp_count > curr_val:
                    self.df.loc[mask, "employees"] = emp_count
                    if self.filtered_df is not None and not self.filtered_df.empty:
                        fmask = self.filtered_df["company"].str.lower().str.strip() == name.lower()
                        if fmask.any():
                            self.filtered_df.loc[fmask, "employees"] = emp_count
                    updated += 1

            if found > 0:
                save_cached_data(self.df)

            if updated > 0:
                self._df_version += 1

            msg = f"Wikipedia: {found} found, {updated} employees updated"
            self.after(0, lambda: self.wiki_status.configure(text=msg))
            self.after(0, self._on_find_companies)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.after(0, lambda: self.wiki_status.configure(text=f"Error: {e}"))
        finally:
            self._wiki_running = False
            self.after(0, lambda: self.wiki_btn.configure(state="normal", text="\U0001f4cb  Fill Missing Employees"))

    def _on_enrich_single(self, company_name, record):
        def cb(msg, pct):
            self.after(0, lambda: self.enrich_status.configure(text=msg))

        def run():
            try:
                result = enrich_company(company_name, progress_callback=cb)
                self.enrichment_results[company_name] = result
                self.df = merge_enrichment(self.df, {company_name: result})
                save_cached_data(self.df)
                self._df_version += 1
                self.after(0, lambda: self.status_bar.set_status(f"Enriched {company_name[:30]}"))
                match = self.df[self.df["company"].str.lower().str.strip() == company_name.lower().strip()]
                row = match.iloc[0] if not match.empty else record
                self.after(0, lambda: self._show_detail_panel(row))
            except Exception as e:
                self.after(0, lambda: self.enrich_status.configure(text=f"Error: {str(e)[:40]}"))
        threading.Thread(target=run, daemon=True).start()

    # ======================= WEBSITE VALIDATION =======================

    def _validate_cache_path(self):
        import os as _os
        return _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "cache", "website_validation.json")

    def _load_validation_cache(self):
        p = self._validate_cache_path()
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_validation_cache(self, cache):
        p = self._validate_cache_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(cache, f)

    def _on_validate_websites(self):
        df = self.filtered_df if self.filtered_df is not None else self.df
        if df is None or df.empty:
            return
        self.validate_btn.configure(state="disabled", text="Validating...")
        self.validate_status.configure(text="Starting...")
        threading.Thread(target=self._validate_thread, daemon=True).start()

    def _validate_thread(self):
        try:
            cp = self._validate_cache_path()
            df = self.filtered_df if self.filtered_df is not None else self.df
            website_col = df["website"].dropna().unique().tolist()
            pairs = [(u, u) for u in website_col if u]
            results = batch_validate_websites(pairs, checkpoint_path=cp, max_workers=20)
            total = len(results)
            valid_count = sum(1 for v in results.values() if v)
            for df_target in [self.df, self.filtered_df]:
                if df_target is not None and not df_target.empty:
                    if "website_valid" not in df_target.columns:
                        df_target["website_valid"] = ""
                    df_target["website_valid"] = df_target["website"].map(results)
            self.after(0, lambda: self.validate_status.configure(text=f"{valid_count} valid, {total - valid_count} invalid"))
            self.after(0, self._render_table)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.after(0, lambda: self.validate_status.configure(text=f"Error: {e}"))
        finally:
            self.after(0, lambda: self.validate_btn.configure(state="normal", text="\u2713 Validate Websites"))

    # ======================= SEARCH & TABLE =======================

    def _on_search_debounced(self):
        if self._search_timer:
            self.after_cancel(self._search_timer)
        self._search_timer = self.after(180, self._on_search)

    def _on_search(self):
        if self.df is None or self.df.empty:
            return
        if self.filtered_df is None or self.filtered_df.empty:
            self._on_find_companies()
        else:
            self._render_table()

    def _get_page_data(self):
        if self.filtered_df is None or self.filtered_df.empty:
            return []

        df = self.filtered_df
        sk = self.sort_var.get()
        if sk == "Score (High to Low)":
            df = df.sort_values("icp_score", ascending=False)
        elif sk == "Score (Low to High)":
            df = df.sort_values("icp_score", ascending=True)
        elif sk == "Company (A-Z)":
            df = df.sort_values("company", ascending=True)
        elif sk == "Company (Z-A)":
            df = df.sort_values("company", ascending=False)

        st = self.search_var.get().strip().lower()
        if st:
            mask = (
                df["_search_col"].str.contains(st, na=False)
            )
            df = df[mask]

        total = len(df)
        self.total_pages = max(1, (total + ROWS_PER_PAGE - 1) // ROWS_PER_PAGE)
        self.current_page = min(self.current_page, self.total_pages - 1)
        start = self.current_page * ROWS_PER_PAGE
        return df.iloc[start:start + ROWS_PER_PAGE].to_dict("records")

    def _render_empty_table(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.page_label.configure(text="Page 0 of 0")
        self.prev_btn.configure(state="disabled")
        self.next_btn.configure(state="disabled")

    def _render_table(self):
        children = self.tree.get_children()
        if children:
            self.tree.delete(*children)

        pd_ = self._get_page_data()
        if not pd_:
            self.page_label.configure(text="Page 0 of 0")
            self.prev_btn.configure(state="disabled")
            self.next_btn.configure(state="disabled")
            return

        _isnan = math.isnan
        for idx, rec in enumerate(pd_):
            s = rec.get("icp_score", 0)
            site = str(rec.get("website") or "")
            valid = rec.get("website_valid")
            if valid is True:
                site = "\u2713 " + site
            elif valid is False:
                site = "\u2717 " + site

            emp = rec.get("employees")
            if emp is None:
                emp_str = ""
            else:
                try:
                    ev = int(float(emp)) if not (isinstance(emp, float) and _isnan(emp)) else 0
                    emp_str = f"{ev:,}" if ev > 0 else ""
                except (ValueError, TypeError):
                    emp_str = ""

            rev = rec.get("revenue")
            if rev is None:
                rev_str = ""
            else:
                try:
                    rv = int(float(rev)) if not (isinstance(rev, float) and _isnan(rev)) else 0
                    rev_str = f"{rv:,}" if rv > 0 else ""
                except (ValueError, TypeError):
                    rev_str = ""

            ty = rec.get("target_year")
            if ty is not None and ty != "" and not (isinstance(ty, float) and _isnan(ty)):
                ty_str = str(int(float(ty)))
            else:
                ty_str = ""

            ls = rec.get("lead_status", "")
            if ls == "HOT":
                ls_display = "\U0001f525 HOT"
            elif ls == "WARM":
                ls_display = "\u26a1 WARM"
            elif ls == "COLD":
                ls_display = "\u2744 COLD"
            else:
                ls_display = ls
            self.tree.insert("", "end", values=(
                rec.get("company", ""),
                rec.get("country", ""),
                rec.get("industry", ""),
                emp_str,
                rev_str,
                rec.get("sbti_status", ""),
                rec.get("region", ""),
                ty_str,
                site,
                str(s) if isinstance(s, (int, float)) else str(s),
                ls_display,
            ))

        total = len(self.filtered_df) if self.filtered_df is not None else 0
        self.page_label.configure(text=f"Page {self.current_page + 1} of {self.total_pages}  ({total:,} total)")
        self.prev_btn.configure(state="normal" if self.current_page > 0 else "disabled")
        self.next_btn.configure(state="normal" if self.current_page < self.total_pages - 1 else "disabled")

    def _on_tree_sort(self, col):
        sort_map = {
            "company": "Company (A-Z)", "score": "Score (High to Low)",
            "country": "Company (A-Z)", "industry": "Company (A-Z)",
            "sbti_status": "Company (A-Z)", "employees": "Company (A-Z)",
            "revenue": "Score (High to Low)",
        }
        target = sort_map.get(col, "Score (High to Low)")
        if self.sort_var.get() == target:
            rev = {"Company (A-Z)": "Company (Z-A)", "Score (High to Low)": "Score (Low to High)"}
            target = rev.get(target, target)
        self.sort_var.set(target)
        self.current_page = 0
        self._render_table()

    def _on_tree_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        vals = self.tree.item(sel[0], "values")
        if not vals:
            return
        cn = vals[0].lower().strip()
        idx = self._company_index.get(cn)
        if idx is not None:
            src = self.filtered_df if self.filtered_df is not None else self.df
            if src is not None and idx in src.index:
                self.selected_row_data = src.loc[idx]
                self._show_detail_panel(src.loc[idx])

    def _on_tree_right_click(self, event):
        sel = self.tree.selection()
        if sel:
            self.tree_context_menu.tk_popup(event.x_root, event.y_root)

    def _on_apollo_enrich_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Apollo Enrich", "Select one or more rows first.")
            return

        key = self._get_apollo_key()
        if not key:
            return

        names = []
        for item in sel:
            vals = self.tree.item(item, "values")
            if vals and vals[0]:
                names.append(vals[0])

        if not names:
            return

        self.wiki_status.configure(text=f"Apollo enriching {len(names)} companies...")
        self.wiki_progress.set(0)

        def run():
            from apollo_api import search_company_org
            from concurrent.futures import ThreadPoolExecutor, as_completed
            total = len(names)
            results = {}

            def _lookup(name):
                try:
                    result = search_company_org(name, key)
                    return name, result
                except Exception:
                    return name, None

            with ThreadPoolExecutor(max_workers=5) as ex:
                futures = {ex.submit(_lookup, n): n for n in names}
                for i, f in enumerate(as_completed(futures)):
                    name, result = f.result()
                    results[name] = result
                    pct = (i + 1) / total * 100
                    self.after(0, lambda p=pct: self.wiki_progress.set(max(0, p / 100)))
                    self.after(0, lambda c=i+1, t=total: self.wiki_status.configure(
                        text=f"Apollo: {c}/{t} ({c/t*100:.0f}%)"))

            found = 0
            for name, result in results.items():
                if not isinstance(result, dict) or "error" in result:
                    continue
                emp = result.get("employee_count")
                rev = result.get("revenue")
                if not emp and not rev:
                    continue
                mask = self.df["company"].str.lower().str.strip() == name.lower().strip()
                if not mask.any():
                    continue
                if emp:
                    self.df.loc[mask, "employees"] = emp
                if rev:
                    if "revenue" not in self.df.columns:
                        self.df["revenue"] = None
                    self.df.loc[mask, "revenue"] = rev
                if self.filtered_df is not None and not self.filtered_df.empty:
                    fmask = self.filtered_df["company"].str.lower().str.strip() == name.lower().strip()
                    if fmask.any():
                        if emp:
                            self.filtered_df.loc[fmask, "employees"] = emp
                        if rev:
                            if "revenue" not in self.filtered_df.columns:
                                self.filtered_df["revenue"] = None
                            self.filtered_df.loc[fmask, "revenue"] = rev
                found += 1

            if found > 0:
                save_cached_data(self.df)
                self._df_version += 1
                self.after(0, self._on_find_companies)

            msg = f"Apollo: {found}/{total} companies enriched"
            self.after(0, lambda: self.wiki_status.configure(text=msg))
            self.after(0, lambda: self.wiki_progress.set(0))

        threading.Thread(target=run, daemon=True).start()

    # ======================= DETAIL PANEL =======================

    def _show_detail_panel(self, record):
        for w in self.right_scroll.winfo_children():
            w.destroy()

        c = ctk.CTkFrame(self.right_scroll, fg_color="transparent")
        c.pack(fill="both", expand=True, padx=12, pady=12)

        cn = record.get("company", "Unknown")
        ctk.CTkLabel(c, text=cn, font=(FONT_FAMILY, 18, "bold"), text_color=TEXT, wraplength=300, justify="left"
                     ).pack(anchor="w", pady=(0, 2))
        ctk.CTkLabel(c, text=f"{record.get('industry', '')}  |  {record.get('country', '')}",
                     font=(FONT_FAMILY, 11), text_color=TEXT_SECONDARY).pack(anchor="w", pady=(0, 8))

        # Score gauge
        score = record.get("icp_score", 0)
        gf = ctk.CTkFrame(c, fg_color="transparent")
        gf.pack(anchor="center", pady=4)
        circ = CircularProgress(gf, size=120)
        circ.pack()
        circ.draw(score)
        ctk.CTkLabel(c, text=f"ICP Score: {score}/90", font=(FONT_FAMILY, 13, "bold"),
                     text_color=score_color(score)).pack(anchor="center", pady=(2, 8))

        ctk.CTkFrame(c, fg_color="#2a2f3e", height=1).pack(fill="x", pady=4)

        # Lead Status with manual override
        current_ls = record.get("lead_status", "")
        lsf = ctk.CTkFrame(c, fg_color="transparent")
        lsf.pack(fill="x", pady=4)
        ctk.CTkLabel(lsf, text="Lead Status:", font=(FONT_FAMILY, 11, "bold"),
                     text_color=TEXT_SECONDARY).pack(side="left")
        ls_label = ctk.CTkLabel(lsf, text=current_ls, font=(FONT_FAMILY, 12, "bold"),
                                text_color={"HOT": ACCENT, "WARM": WARNING, "COLD": DANGER}.get(current_ls, TEXT))
        ls_label.pack(side="left", padx=(6, 0))

        def _set_lead_status(new_status):
            mask = self.df["company"].str.lower().str.strip() == cn.lower().strip()
            if mask.any():
                self.df.loc[mask, "lead_status"] = new_status
                self._df_version += 1
                record["lead_status"] = new_status
                ls_label.configure(text=new_status, text_color={"HOT": ACCENT, "WARM": WARNING, "COLD": DANGER}.get(new_status, TEXT))
                self._on_find_companies()

        sbf = ctk.CTkFrame(c, fg_color="transparent")
        sbf.pack(fill="x", pady=2)
        for st in LEAD_STATUS_OPTIONS:
            color = {"HOT": ACCENT, "WARM": WARNING, "COLD": DANGER}[st]
            btn = ctk.CTkButton(sbf, text=st, command=lambda s=st: _set_lead_status(s),
                                fg_color=CARD_LIGHT, hover_color=color,
                                text_color=color, font=(FONT_FAMILY, 11, "bold"),
                                corner_radius=6, height=28, width=60)
            btn.pack(side="left", padx=(0, 4))

        ctk.CTkFrame(c, fg_color="#2a2f3e", height=1).pack(fill="x", pady=4)

        # Badges
        bf = ctk.CTkFrame(c, fg_color="transparent")
        bf.pack(fill="x", pady=4)
        country = str(record.get("country", "")).lower()
        origin_ticker = record.get("origin_ticker", "")
        if any(eu in country for eu in EU_COUNTRIES):
            ctk.CTkLabel(bf, text="CSRD", fg_color="#0a3a2a", text_color=ACCENT,
                         font=(FONT_FAMILY, 10, "bold"), corner_radius=4, padx=8, pady=2).pack(side="left", padx=(0, 4))
        sbti = str(record.get("sbti_status", "")).lower()
        if sbti:
            ctk.CTkLabel(bf, text="SBTi", fg_color="#0a2a3a", text_color="#4da6ff",
                         font=(FONT_FAMILY, 10, "bold"), corner_radius=4, padx=8, pady=2).pack(side="left", padx=(0, 4))
        if record.get("osi_found"):
            ctk.CTkLabel(bf, text="OSI", fg_color="#0a2a1a", text_color="#00d4aa",
                         font=(FONT_FAMILY, 10, "bold"), corner_radius=4, padx=8, pady=2).pack(side="left", padx=(0, 4))
        if record.get("origin_found"):
            ctk.CTkLabel(bf, text="SEC Filing", fg_color="#1a0a2a", text_color="#a64dff",
                         font=(FONT_FAMILY, 10, "bold"), corner_radius=4, padx=8, pady=2).pack(side="left", padx=(0, 4))
        if origin_ticker:
            ctk.CTkLabel(bf, text="SEC Registrant", fg_color="#1a0a2a", text_color="#c084fc",
                         font=(FONT_FAMILY, 10, "bold"), corner_radius=4, padx=8, pady=2).pack(side="left", padx=(0, 4))
        if country == "united kingdom":
            ctk.CTkLabel(bf, text="UK SDR", fg_color="#0a1a3a", text_color="#60a5fa",
                         font=(FONT_FAMILY, 10, "bold"), corner_radius=4, padx=8, pady=2).pack(side="left", padx=(0, 4))

        # Source line
        sources = ["SBTi"]
        if record.get("osi_found"):
            sources.append("OSI")
        if record.get("origin_found"):
            sources.append("SEC")
        ctk.CTkLabel(c, text=f"Data sources: {', '.join(sources)}",
                     font=(FONT_FAMILY, 9), text_color=TEXT_SECONDARY).pack(anchor="w", pady=(2, 2))

        ctk.CTkFrame(c, fg_color="#2a2f3e", height=1).pack(fill="x", pady=6)

        # Score breakdown
        bd = record.get("score_breakdown", {})
        if isinstance(bd, str):
            import ast
            try:
                bd = json.loads(bd)
            except Exception:
                try:
                    bd = ast.literal_eval(bd)
                except Exception:
                    bd = {}
        if isinstance(bd, dict) and bd:
            ctk.CTkLabel(c, text="SCORE BREAKDOWN", font=(FONT_FAMILY, 10, "bold"),
                         text_color=TEXT_SECONDARY).pack(anchor="w", pady=(0, 6))
            for cat, det in bd.items():
                earned = 0
                max_score = 0
                desc = ""
                try:
                    parts = det.split("/")
                    earned = int(parts[0])
                    if "/" in det:
                        rest = det.split("/", 1)[1]
                        if " - " in rest:
                            max_score = int(rest.split(" - ")[0].strip())
                            desc = rest.split(" - ", 1)[1].strip()
                        else:
                            max_score = int(rest.strip())
                except:
                    pass
                ratio = earned / max_score if max_score > 0 else 0
                bar_color = score_color(int(ratio * 100))

                rf = ctk.CTkFrame(c, fg_color="transparent")
                rf.pack(fill="x", pady=2)

                ctk.CTkLabel(rf, text=cat, font=(FONT_FAMILY, 10, "bold"),
                             text_color=TEXT, width=130, anchor="w").pack(side="left")

                ctk.CTkLabel(rf, text=f"{earned}/{max_score}", font=(FONT_FAMILY, 14, "bold"),
                             text_color=bar_color, width=40, anchor="w").pack(side="left")
                if desc:
                    ctk.CTkLabel(rf, text=desc, font=(FONT_FAMILY, 10),
                                 text_color=TEXT_SECONDARY, anchor="w").pack(side="left", padx=(6, 0))

        ctk.CTkFrame(c, fg_color="#2a2f3e", height=1).pack(fill="x", pady=6)

        # Fields
        fields = [
            ("Employees", record.get("employees", "N/A")),
            ("Revenue", record.get("revenue", "N/A")),
            ("SBTi Status", record.get("sbti_status", "N/A")),
            ("Last Fetched", record.get("last_sbti_fetch", "N/A")),
            ("Target Year", record.get("target_year", "N/A")),
            ("Target Type", record.get("target_type", "N/A")),
            ("Sector", record.get("sector_raw", "N/A")),
            ("Website", record.get("website", "N/A")),
        ]
        if record.get("clearbit_domain"):
            fields.append(("CB Domain", record.get("clearbit_domain", "")))
            fields.append(("CB Confidence", record.get("clearbit_confidence", "N/A")))
        if record.get("osi_found"):
            fields.append(("OSI Revenue", record.get("osi_revenue", "N/A")))
            fields.append(("OSI Emissions", f"{record.get('osi_emissions_tco2e', 'N/A')} tCO2e"))
        if record.get("origin_found"):
            fields.append(("Origin Ticker", record.get("origin_ticker", "N/A")))
            fields.append(("Origin HQ", record.get("origin_headquarters", "N/A")))
            fields.append(("Origin SIC", record.get("origin_sic", "N/A")))

        df_ = ctk.CTkFrame(c, fg_color="transparent")
        df_.pack(fill="x", pady=2)
        for lab, val in fields:
            rf = ctk.CTkFrame(df_, fg_color="transparent")
            rf.pack(fill="x", pady=1)
            ctk.CTkLabel(rf, text=lab + ":", font=(FONT_FAMILY, 10, "bold"),
                         text_color=TEXT_SECONDARY, width=90, anchor="w").pack(side="left")
            ctk.CTkLabel(rf, text=str(val) if val is not None else "N/A",
                         font=(FONT_FAMILY, 10), text_color=TEXT, anchor="w").pack(side="left", padx=(4, 0))

        ctk.CTkFrame(c, fg_color="#2a2f3e", height=1).pack(fill="x", pady=6)

        # Actions
        ctk.CTkLabel(c, text="ACTIONS", font=(FONT_FAMILY, 10, "bold"),
                     text_color=TEXT_SECONDARY).pack(anchor="w", pady=(0, 4))

        def _btn(text, cmd):
            b = ctk.CTkButton(c, text=text, command=cmd, fg_color=CARD_LIGHT,
                              hover_color="#3a3f4e", text_color=TEXT, font=(FONT_FAMILY, 11),
                              corner_radius=6, height=30)
            b.pack(fill="x", pady=2)
            return b

        _btn("Find Contacts on Apollo", lambda: self._open_apollo(cn))
        _btn("Search ESG Report", lambda: self._open_esg(cn))
        _btn("Check SBTi Profile", lambda: self._open_sbti(cn))

        website = record.get("website", "")
        website_valid = record.get("website_valid")
        if website:
            label = "Visit Website"
            if website_valid is True:
                label = "\u2713 Visit Website"
            elif website_valid is False:
                label = "\u2717 Visit Website (invalid)"
            _btn(label, lambda: webbrowser.open(website))

        _btn("Enrich This Company", lambda: self._on_enrich_single(cn, record))

        my_list = load_my_list()
        is_saved = any(it.get("company", "") == cn for it in my_list)

        if is_saved:
            self.save_btn = ctk.CTkButton(
                c, text="Remove from My List", command=lambda: self._on_remove_from_list(cn),
                fg_color=DANGER, hover_color="#d63031", text_color="#ffffff",
                font=(FONT_FAMILY, 11), corner_radius=6, height=30,
            )
        else:
            self.save_btn = ctk.CTkButton(
                c, text="Add to My List", command=lambda: self._on_save_to_list(record),
                fg_color=ACCENT, hover_color="#00b898", text_color="#0a0a0a",
                font=(FONT_FAMILY, 11), corner_radius=6, height=30,
            )
        self.save_btn.pack(fill="x", pady=2)

        ctk.CTkFrame(c, fg_color="#2a2f3e", height=1).pack(fill="x", pady=6)

        ctk.CTkLabel(c, text="NOTES", font=(FONT_FAMILY, 10, "bold"),
                     text_color=TEXT_SECONDARY).pack(anchor="w", pady=(0, 4))
        self.notes_entry = ctk.CTkTextbox(
            c, height=80, fg_color="#0f1117", text_color=TEXT,
            font=(FONT_FAMILY, 11), border_width=1, border_color="#2a2f3e", corner_radius=6,
        )
        self.notes_entry.pack(fill="x", pady=(0, 8))
        self.notes_entry.insert("0.0", self.notes_text)

        ctk.CTkFrame(c, fg_color="#2a2f3e", height=1).pack(fill="x", pady=6)

        # Contacts section
        ctk.CTkLabel(c, text="CONTACTS", font=(FONT_FAMILY, 10, "bold"),
                     text_color=TEXT_SECONDARY).pack(anchor="w", pady=(0, 4))

        contacts = self._apollo_contacts.get(cn, [])
        if contacts and isinstance(contacts, list) and len(contacts) > 0:
            for ct in contacts:
                if not ct.get("name"):
                    continue
                cf = ctk.CTkFrame(c, fg_color="#151a28", corner_radius=4)
                cf.pack(fill="x", pady=2)
                ctk.CTkLabel(cf, text=ct.get("name", ""), font=(FONT_FAMILY, 11, "bold"),
                             text_color=TEXT).pack(anchor="w", padx=8, pady=(4, 0))
                ctk.CTkLabel(cf, text=ct.get("title", ""), font=(FONT_FAMILY, 9),
                             text_color=TEXT_SECONDARY).pack(anchor="w", padx=8)
                bf = ctk.CTkFrame(cf, fg_color="transparent")
                bf.pack(fill="x", padx=8, pady=(0, 4))
                email = ct.get("email", "")
                has_email = ct.get("has_email", False)
                cid = ct.get("id", "")
                if email:
                    ctk.CTkLabel(bf, text=email, font=(FONT_FAMILY, 9),
                                 text_color=ACCENT).pack(side="left")
                    ctk.CTkButton(bf, text="Copy", width=50, height=20,
                                  command=lambda e=email: self._copy_text(e),
                                  fg_color=CARD_LIGHT, hover_color="#3a3f4e",
                                  text_color=TEXT, font=(FONT_FAMILY, 9), corner_radius=4).pack(side="right")
                elif has_email and cid:
                    ctk.CTkLabel(bf, text="\u2709 Email available (view in Apollo)",
                                 font=(FONT_FAMILY, 9), text_color=TEXT_SECONDARY).pack(side="left")
                    ctk.CTkButton(bf, text="Open", width=50, height=20,
                                  command=lambda i=cid: webbrowser.open(build_apollo_contact_url(i)),
                                  fg_color=CARD_LIGHT, hover_color="#3a3f4e",
                                  text_color=TEXT, font=(FONT_FAMILY, 9), corner_radius=4).pack(side="right", padx=(4, 0))
                if cid:
                    ctk.CTkButton(bf, text="LinkedIn", width=60, height=20,
                                  command=lambda i=cid: webbrowser.open(build_apollo_contact_url(i)),
                                  fg_color="#0a2a3a", hover_color="#0a3a5a",
                                  text_color="#4da6ff", font=(FONT_FAMILY, 9), corner_radius=4).pack(side="right", padx=(4, 0))
        elif contacts and isinstance(contacts, list) and len(contacts) == 0:
            ctk.CTkLabel(c, text="No contacts found", font=(FONT_FAMILY, 10),
                         text_color=TEXT_SECONDARY).pack(anchor="w")
        else:
            _btn("Find Contacts (Apollo)", lambda: self._on_find_contacts_single(cn))

    # ======================= ACTIONS =======================

    def _get_apollo_key(self):
        key = self.apollo_key_entry.get().strip()
        if not key:
            messagebox.showwarning("API Key", "Enter your Apollo API key in the left panel first.")
            return None
        return key

    def _on_find_contacts_single(self, company_name):
        key = self._get_apollo_key()
        if not key:
            return

        cached = self._apollo_contacts.get(company_name)
        if cached is not None and isinstance(cached, list):
            self._show_detail_panel(self.selected_row_data)
            return

        def run():
            try:
                from apollo_api import search_company_contacts
                contacts = search_company_contacts(company_name, key)
                self._apollo_contacts[company_name] = contacts
                self.after(0, lambda: self._show_detail_panel(self.selected_row_data))
                self.after(0, lambda: self.status_bar.set_status(
                    f"Apollo: {len(contacts)} contacts for {company_name[:20]}"))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Apollo Error", str(e)))
        threading.Thread(target=run, daemon=True).start()

    def _copy_text(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status_bar.set_status(f"Copied: {text[:30]}")

    def _open_apollo(self, name):
        webbrowser.open(build_apollo_url(name))
        self.status_bar.set_status(f"Opened Apollo search for {name}")

    def _open_esg(self, name):
        webbrowser.open(build_esg_search_url(name))
        self.status_bar.set_status(f"Opened ESG report search for {name}")

    def _open_sbti(self, name):
        webbrowser.open(build_sbti_profile_url(name))
        self.status_bar.set_status(f"Opened SBTi profile for {name}")

    def _on_save_to_list(self, record):
        def run():
            try:
                total = save_to_my_list(record)
                self.my_list_count = total
                self.after(0, lambda: self.my_list_btn.configure(text=f"\u2b50 My List ({total})"))
                self.after(0, lambda: self.status_bar.set_status(f"Saved {record.get('company', '')}"))
                self.after(0, lambda: self._show_detail_panel(record))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Error", str(e)))
        threading.Thread(target=run, daemon=True).start()

    def _on_remove_from_list(self, company_name):
        def run():
            try:
                total = remove_from_my_list(company_name)
                self.my_list_count = total
                self.after(0, lambda: self.my_list_btn.configure(text=f"\u2b50 My List ({total})"))
                self.after(0, lambda: self.status_bar.set_status(f"Removed {company_name}"))
                if self.selected_row_data and self.selected_row_data.get("company") == company_name:
                    self.after(0, lambda: self._show_detail_panel(self.selected_row_data))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Error", str(e)))
        threading.Thread(target=run, daemon=True).start()

    def _on_bulk_add_filtered(self):
        if self.filtered_df is None or self.filtered_df.empty:
            messagebox.showinfo("No Data", "No filtered companies to add. Run a search first.")
            return
        records = self.filtered_df.to_dict("records")
        def run():
            added = 0
            for rec in records:
                before = len(load_my_list())
                save_to_my_list(rec)
                if len(load_my_list()) > before:
                    added += 1
            self.my_list_count = len(load_my_list())
            self.after(0, lambda: self.my_list_btn.configure(text=f"\u2b50 My List ({self.my_list_count})"))
            self.after(0, lambda: self.status_bar.set_status(f"Added {added} companies to My List"))
            self.after(0, lambda: messagebox.showinfo("Bulk Add", f"Added {added} new companies to My List (skipped {len(records) - added} duplicates)."))
        threading.Thread(target=run, daemon=True).start()

    def _on_show_my_list(self):
        my_list = load_my_list()
        if not my_list:
            messagebox.showinfo("My List", "No companies saved yet.")
            return

        window = ctk.CTkToplevel(self)
        window.title("My List - Saved Companies")
        window.geometry("700x500")
        window.configure(fg_color=BG)

        hdr = ctk.CTkLabel(window, text=f"Saved Companies ({len(my_list)})",
                           font=(FONT_FAMILY, 16, "bold"), text_color=TEXT)
        hdr.pack(pady=(12, 8))

        scroll = ctk.CTkScrollableFrame(window, fg_color=CARD, corner_radius=8)
        scroll.pack(fill="both", expand=True, padx=12, pady=8)

        for it in my_list:
            fr = ctk.CTkFrame(scroll, fg_color="#151a28", corner_radius=6)
            fr.pack(fill="x", padx=8, pady=3)
            ctk.CTkLabel(fr, text=it.get("company", "Unknown"), font=(FONT_FAMILY, 12, "bold"),
                         text_color=TEXT).pack(side="left", padx=12, pady=8)
            ctk.CTkLabel(fr, text=f"{it.get('industry', '')} | {it.get('country', '')}",
                         font=(FONT_FAMILY, 10), text_color=TEXT_SECONDARY).pack(side="left", padx=8, pady=8)
            sc = it.get("icp_score", 0)
            ctk.CTkLabel(fr, text=f"Score: {sc}", font=(FONT_FAMILY, 11, "bold"),
                         text_color=score_color(sc)).pack(side="right", padx=12, pady=8)

            def _mk(cn):
                return lambda: self._remove_from_list_window(cn, window, hdr, scroll)
            ctk.CTkButton(fr, text="\u2715", width=30, height=30, command=_mk(it.get("company", "")),
                          fg_color=DANGER, hover_color="#d63031", text_color="#ffffff",
                          font=(FONT_FAMILY, 11), corner_radius=4).pack(side="right", padx=4, pady=4)

        ef = ctk.CTkFrame(window, fg_color="transparent")
        ef.pack(fill="x", padx=12, pady=8)

        def export_my_list():
            p = export_to_csv(my_list)
            if p:
                messagebox.showinfo("Exported", f"Saved list exported to {p}")
                self.status_bar.set_status(f"Exported My List")

        ctk.CTkButton(ef, text="Export My List as CSV", command=export_my_list,
                      fg_color=ACCENT, hover_color="#00b898", text_color="#0a0a0a",
                      font=(FONT_FAMILY, 11), corner_radius=6).pack(side="right", padx=4)

        def export_my_list_xlsx():
            p = export_to_excel(my_list)
            if p:
                messagebox.showinfo("Exported", f"Saved list exported to {p}")

        ctk.CTkButton(ef, text="Export as Excel", command=export_my_list_xlsx,
                      fg_color=CARD_LIGHT, hover_color="#3a3f4e", text_color=TEXT,
                      font=(FONT_FAMILY, 11), corner_radius=6).pack(side="right", padx=4)

    def _remove_from_list_window(self, company_name, window, header_label, scroll_frame):
        total = remove_from_my_list(company_name)
        self.my_list_count = total
        self.my_list_btn.configure(text=f"\u2b50 My List ({total})")
        self.status_bar.set_status(f"Removed {company_name}")
        for w in scroll_frame.winfo_children():
            w.destroy()
        header_label.configure(text=f"Saved Companies ({total})")

        my_list = load_my_list()
        if not my_list:
            window.destroy()
            return
        for it in my_list:
            fr = ctk.CTkFrame(scroll_frame, fg_color="#151a28", corner_radius=6)
            fr.pack(fill="x", padx=8, pady=3)
            ctk.CTkLabel(fr, text=it.get("company", "Unknown"), font=(FONT_FAMILY, 12, "bold"),
                         text_color=TEXT).pack(side="left", padx=12, pady=8)
            ctk.CTkLabel(fr, text=f"{it.get('industry', '')} | {it.get('country', '')}",
                         font=(FONT_FAMILY, 10), text_color=TEXT_SECONDARY).pack(side="left", padx=8, pady=8)
            sc = it.get("icp_score", 0)
            ctk.CTkLabel(fr, text=f"Score: {sc}", font=(FONT_FAMILY, 11, "bold"),
                         text_color=score_color(sc)).pack(side="right", padx=12, pady=8)

            def _mk(cn):
                return lambda: self._remove_from_list_window(cn, window, header_label, scroll_frame)
            ctk.CTkButton(fr, text="\u2715", width=30, height=30, command=_mk(it.get("company", "")),
                          fg_color=DANGER, hover_color="#d63031", text_color="#ffffff",
                          font=(FONT_FAMILY, 11), corner_radius=4).pack(side="right", padx=4, pady=4)

    # ======================= PAGINATION =======================

    def _on_prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self._render_table()

    def _on_next_page(self):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self._render_table()

    # ======================= CLAY PUSH =======================

    def _on_push_to_clay(self):
        url = self.clay_url_entry.get().strip()
        if not url:
            self.clay_status.configure(text="Enter a Clay webhook URL first")
            return
        _save_config(webhook_url=url)

        df = self.filtered_df if self.filtered_df is not None else self.df
        if df is None or df.empty:
            self.clay_status.configure(text="No leads to push")
            return

        sel = self.tree.selection()
        if sel:
            selected_names = set()
            for item in sel:
                vals = self.tree.item(item, "values")
                if vals:
                    selected_names.add(vals[0])
            mask = df["company"].isin(selected_names)
            push_df = df[mask]
        else:
            push_df = df

        if push_df.empty:
            self.clay_status.configure(text="No leads to push")
            return

        self.clay_btn.configure(state="disabled", text="Pushing...")
        self.clay_status.configure(text=f"Sending {len(push_df)} leads to Clay...")

        def run():
            try:
                records = push_df.to_dict("records")
                payload = json.dumps(records, default=str)
                resp = requests.post(url, data=payload, headers={"Content-Type": "application/json"}, timeout=30)
                if resp.status_code in (200, 201, 202):
                    self.after(0, lambda n=len(records): self.clay_status.configure(text=f"Pushed {n} leads to Clay"))
                else:
                    self.after(0, lambda s=resp.status_code: self.clay_status.configure(text=f"Clay returned {s}"))
            except requests.RequestException as e:
                self.after(0, lambda: self.clay_status.configure(text=f"Push failed: {str(e)[:40]}"))
            finally:
                self.after(0, lambda: self.clay_btn.configure(state="normal", text="\U0001f4e4  Push to Clay"))

        threading.Thread(target=run, daemon=True).start()

    # ======================= EXPORT =======================

    def _on_export_csv(self):
        if self.filtered_df is None or self.filtered_df.empty:
            return
        p = export_to_csv(self.filtered_df.to_dict("records"))
        if p:
            messagebox.showinfo("Exported", f"Data exported to {p}")
            self.status_bar.set_status(f"Exported CSV")

    def _on_export_sheets(self):
        if self.filtered_df is None or self.filtered_df.empty:
            return
        p = export_google_sheets_format(self.filtered_df.to_dict("records"))
        if p:
            messagebox.showinfo("Exported", f"Google Sheets format exported to {p}")
            self.status_bar.set_status(f"Exported Sheets format")

    def _on_export_xlsx(self):
        if self.filtered_df is None or self.filtered_df.empty:
            return
        p = export_to_excel(self.filtered_df.to_dict("records"))
        if p:
            messagebox.showinfo("Exported", f"Excel exported to {p}")
            self.status_bar.set_status(f"Exported Excel")

    def _on_export_my_list(self):
        from data_handler import load_my_list
        my_list = load_my_list()
        if not my_list:
            messagebox.showinfo("My List Empty", "No saved companies to export.")
            return
        p = export_to_csv(my_list)
        if p:
            messagebox.showinfo("Exported", f"My List exported to {p} ({len(my_list)} companies)")
            self.status_bar.set_status(f"Exported My List ({len(my_list)} companies)")
