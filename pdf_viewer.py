import copy
import os
import tkinter as tk
from tkinter import (
    Toplevel, Canvas, Button, filedialog, messagebox, Radiobutton, StringVar,
    simpledialog, Frame, PhotoImage, Scrollbar, Scale, Label, Menubutton,
    Menu, Listbox, END, LEFT, RIGHT, BOTH, X, Y, TOP, BOTTOM, DISABLED, NORMAL,
)
from PIL import Image, ImageTk
import pymupdf
from pdf_processing import sign
from config import config, save_config, get_initial_dir, remember_dir


def _viewer_cfg(key, default):
    return config.get('viewer', {}).get(key, default)


class ResourcesDialog(Toplevel):
    """Меню загрузки подписи, печати и предустановленных текстов."""

    def __init__(self, master, on_apply):
        super().__init__(master)
        self.title('Ресурсы')
        self.transient(master)
        self.grab_set()
        self.on_apply = on_apply
        self.resizable(False, False)

        body = Frame(self, padx=10, pady=10)
        body.pack(fill=BOTH, expand=True)

        # Подпись
        Label(body, text='Подпись (PNG):').grid(row=0, column=0, sticky='w')
        self.sig_path = StringVar(value=config['images']['signature']['path'])
        Label(body, textvariable=self.sig_path, wraplength=320, anchor='w').grid(
            row=0, column=1, sticky='w', padx=4
        )
        Button(body, text='Выбрать…', command=self._pick_signature).grid(row=0, column=2, padx=4)

        # Печать
        Label(body, text='Печать (PNG):').grid(row=1, column=0, sticky='w', pady=(8, 0))
        self.print_path = StringVar(value=config['images']['print']['path'])
        Label(body, textvariable=self.print_path, wraplength=320, anchor='w').grid(
            row=1, column=1, sticky='w', padx=4, pady=(8, 0)
        )
        Button(body, text='Выбрать…', command=self._pick_print).grid(
            row=1, column=2, padx=4, pady=(8, 0)
        )

        # Тексты
        Label(body, text='Предустановленные тексты:').grid(
            row=2, column=0, columnspan=3, sticky='w', pady=(12, 4)
        )
        self.texts_list = Listbox(body, height=6, width=50)
        self.texts_list.grid(row=3, column=0, columnspan=3, sticky='ew')
        self._reload_texts()

        text_btns = Frame(body)
        text_btns.grid(row=4, column=0, columnspan=3, sticky='ew', pady=4)
        Button(text_btns, text='Добавить', command=self._add_text).pack(side=LEFT, padx=2)
        Button(text_btns, text='Изменить', command=self._edit_text).pack(side=LEFT, padx=2)
        Button(text_btns, text='Удалить', command=self._remove_text).pack(side=LEFT, padx=2)

        actions = Frame(body)
        actions.grid(row=5, column=0, columnspan=3, sticky='e', pady=(12, 0))
        Button(actions, text='Отмена', command=self.destroy).pack(side=RIGHT, padx=4)
        Button(actions, text='Сохранить', command=self._save).pack(side=RIGHT, padx=4)

    def _reload_texts(self):
        self.texts_list.delete(0, END)
        for entry in config.get('texts', []):
            self.texts_list.insert(END, entry['content'])

    def _pick_signature(self):
        path = filedialog.askopenfilename(
            parent=self,
            initialdir=get_initial_dir('open'),
            filetypes=[('PNG', '*.png'), ('Все файлы', '*.*')],
        )
        if path:
            remember_dir(path, 'open')
            self.sig_path.set(path)

    def _pick_print(self):
        path = filedialog.askopenfilename(
            parent=self,
            initialdir=get_initial_dir('open'),
            filetypes=[('PNG', '*.png'), ('Все файлы', '*.*')],
        )
        if path:
            remember_dir(path, 'open')
            self.print_path.set(path)

    def _add_text(self):
        text = simpledialog.askstring('Новый текст', 'Введите текст:', parent=self)
        if text:
            config.setdefault('texts', []).append({'content': text})
            self._reload_texts()

    def _edit_text(self):
        sel = self.texts_list.curselection()
        if not sel:
            return
        idx = sel[0]
        current = config['texts'][idx]['content']
        text = simpledialog.askstring('Изменить текст', 'Текст:', initialvalue=current, parent=self)
        if text is not None:
            config['texts'][idx]['content'] = text
            self._reload_texts()

    def _remove_text(self):
        sel = self.texts_list.curselection()
        if not sel:
            return
        del config['texts'][sel[0]]
        self._reload_texts()

    def _save(self):
        config['images']['signature']['path'] = self.sig_path.get()
        config['images']['print']['path'] = self.print_path.get()
        try:
            save_config()
        except OSError as exc:
            messagebox.showerror('Ошибка', f'Не удалось сохранить config.yml:\n{exc}', parent=self)
            return
        self.on_apply()
        self.destroy()


class PDFViewer(Frame):
    """Просмотр и подпись PDF внутри одного главного окна."""

    def __init__(self, master):
        super().__init__(master)

        self.pdf_document = None
        self.current_page = 0
        self.click_positions = []
        self.input_pdf_path = StringVar()

        self.zoom = float(_viewer_cfg('zoom', 1.0))
        self.min_zoom = float(_viewer_cfg('min_zoom', 0.5))
        self.max_zoom = float(_viewer_cfg('max_zoom', 2.5))
        self.zoom_step = float(_viewer_cfg('zoom_step', 0.1))

        self.signature_scale = float(config['images']['signature'].get('scale', 1.0))
        self.print_scale = float(config['images']['print'].get('scale', 1.0))
        self.text_font_size = float(config['font']['size'])

        self._undo_stack = []
        self._redo_stack = []
        self._drag_index = None
        self._drag_offset = (0, 0)
        self._drag_moved = False
        self._selected_index = None
        self._pil_cache = {}
        self._tk_overlay_refs = []
        self._panning = False
        self._tool_buttons = {}

        self._build_top_toolbar()
        self._build_body()
        self._build_nav()
        self._load_asset_images()
        self._bind_keys()
        self._on_tool_change()
        self._show_empty_state()
        self.update_nav_buttons()

    # --- document ---

    def ask_open_pdf(self):
        if getattr(self, '_open_dialog_open', False):
            return
        self._open_dialog_open = True
        try:
            file_path = filedialog.askopenfilename(
                parent=self.winfo_toplevel(),
                initialdir=get_initial_dir('open'),
                filetypes=[('PDF files', '*.pdf')],
            )
        finally:
            self._open_dialog_open = False
        if file_path:
            remember_dir(file_path, 'open')
            self.open_pdf(file_path)

    def open_pdf(self, file_path):
        if self.pdf_document is not None:
            self.pdf_document.close()
            self.pdf_document = None

        self.click_positions.clear()
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._selected_index = None
        self.current_page = 0
        self.input_pdf_path.set(file_path)
        remember_dir(file_path, 'open')

        self.pdf_document = pymupdf.open(file_path)
        top = self.winfo_toplevel()
        top.title(f'Подпись и печать — {os.path.basename(file_path)}')
        self.show_page(self.current_page)
        self.update_nav_buttons()

    def _show_empty_state(self):
        self.canvas.delete('all')
        self.canvas.image = None
        self.canvas.create_text(
            360, 240,
            text='Откройте PDF\nФайл → Открыть  ·  Ctrl+O  ·  кнопка «Открыть»',
            fill='#868e96',
            font=('DejaVu Sans', 13),
            justify=tk.CENTER,
            tags='empty',
        )
        self.canvas.config(scrollregion=(0, 0, 640, 480))
        self.page_label.config(text='Документ не открыт')

    # --- layout ---

    def _load_ui_icons(self):
        self.icon_open = PhotoImage(file='resources/icon_folder_open.png')
        self.icon_undo = PhotoImage(file='resources/icon_undo_2.png')
        self.icon_sign = PhotoImage(file='resources/icon_badge_check.png')
        self.icon_zoom_in = PhotoImage(file='resources/icon_zoom_in.png')
        self.icon_zoom_out = PhotoImage(file='resources/icon_zoom_out.png')
        self.icon_hand = PhotoImage(file='resources/icon_hand.png')
        self.icon_signature = PhotoImage(file='resources/icon_signature.png')
        self.icon_stamp = PhotoImage(file='resources/icon_stamp.png')
        self.icon_type = PhotoImage(file='resources/icon_type.png')

    def _tool_btn_style(self):
        return dict(
            indicatoron=False,
            bd=0,
            highlightthickness=0,
            padx=6,
            pady=8,
            font=('DejaVu Sans', 9),
            compound=TOP,
            width=84,
            activebackground='#e8eef7',
            selectcolor='#d4e3f7',
            offrelief=tk.FLAT,
            relief=tk.FLAT,
            cursor='hand2',
        )

    def _action_btn(self, parent, text, image, command, primary=False):
        bg = '#2d6a4f' if primary else '#f4f6f8'
        fg = '#ffffff' if primary else '#212529'
        active = '#1b4332' if primary else '#e9ecef'
        btn = Button(
            parent,
            text=text,
            image=image,
            compound=LEFT,
            command=command,
            bd=0,
            padx=10,
            pady=6,
            font=('DejaVu Sans', 10),
            bg=bg,
            fg=fg,
            activebackground=active,
            activeforeground=fg,
            highlightthickness=0,
            cursor='hand2',
            relief=tk.FLAT,
        )
        return btn

    def _build_top_toolbar(self):
        self._load_ui_icons()

        self.toolbar = Frame(self, bg='#f4f6f8', pady=4)
        self.toolbar.pack(side=TOP, fill=X)

        self.option = StringVar(value='signature')
        self.text_var = StringVar(value='выберите текст')
        self.text_dropdown = None

        self._action_btn(self.toolbar, 'Открыть', self.icon_open, self.ask_open_pdf).pack(
            side=LEFT, padx=(8, 4), pady=2
        )

        sep = Frame(self.toolbar, width=1, bg='#ced4da')
        sep.pack(side=LEFT, fill=Y, padx=6, pady=4)

        self.size_label = Label(self.toolbar, text='Размер %', bg='#f4f6f8', font=('DejaVu Sans', 9))
        self.size_label.pack(side=LEFT, padx=(4, 0))
        self.size_scale = Scale(
            self.toolbar, from_=30, to=200, orient=tk.HORIZONTAL, length=110,
            showvalue=True, command=self._on_size_change,
            bg='#f4f6f8', highlightthickness=0, troughcolor='#dee2e6',
            font=('DejaVu Sans', 8),
        )
        self._suppress_size_callback = True
        self.size_scale.set(int(self.signature_scale * 100))
        self._suppress_size_callback = False
        self.size_scale.pack(side=LEFT, padx=2)
        self._size_undo_pushed = False
        self.size_scale.bind('<ButtonPress-1>', lambda e: setattr(self, '_size_undo_pushed', False))
        self.size_scale.bind('<ButtonRelease-1>', lambda e: setattr(self, '_size_undo_pushed', False))

        zoom_box = Frame(self.toolbar, bg='#f4f6f8')
        zoom_box.pack(side=LEFT, padx=(10, 4))
        Button(
            zoom_box, image=self.icon_zoom_out, command=self.zoom_out,
            bd=0, bg='#f4f6f8', activebackground='#e9ecef',
            highlightthickness=0, cursor='hand2', padx=2, pady=2,
        ).pack(side=LEFT)
        self.zoom_label = Label(
            zoom_box, text=self._zoom_text(), width=5, bg='#f4f6f8',
            font=('DejaVu Sans', 10),
        )
        self.zoom_label.pack(side=LEFT)
        Button(
            zoom_box, image=self.icon_zoom_in, command=self.zoom_in,
            bd=0, bg='#f4f6f8', activebackground='#e9ecef',
            highlightthickness=0, cursor='hand2', padx=2, pady=2,
        ).pack(side=LEFT)

        self._action_btn(
            self.toolbar, 'Подписать', self.icon_sign, self.sign_pdf, primary=True
        ).pack(side=RIGHT, padx=(4, 10), pady=2)
        self._action_btn(
            self.toolbar, 'Отменить', self.icon_undo, self.undo_last_action
        ).pack(side=RIGHT, padx=4, pady=2)

    def _build_body(self):
        body = Frame(self, bg='#e9ecef')
        body.pack(fill=BOTH, expand=True)

        self.left_tools = Frame(body, bg='#f8f9fa', padx=6, pady=10, width=108)
        self.left_tools.pack(side=LEFT, fill=Y)
        self.left_tools.pack_propagate(False)

        Label(
            self.left_tools, text='Инструменты', bg='#f8f9fa',
            fg='#6c757d', font=('DejaVu Sans', 8),
        ).pack(side=TOP, pady=(0, 6))

        tools = [
            ('pan', 'Рука', self.icon_hand),
            ('signature', 'Подпись', self.icon_signature),
            ('print', 'Печать', self.icon_stamp),
            ('text', 'Текст', self.icon_type),
        ]
        style = self._tool_btn_style()
        for value, label, icon in tools:
            btn = Radiobutton(
                self.left_tools,
                text=label,
                image=icon,
                variable=self.option,
                value=value,
                command=self._on_tool_change,
                bg='#f8f9fa',
                fg='#212529',
                **style,
            )
            btn.pack(side=TOP, pady=4, fill=X)
            self._tool_buttons[value] = btn
            if value == 'text':
                self.text_submenu = Frame(self.left_tools, bg='#f8f9fa')
                self.text_submenu.pack(side=TOP, fill=X, padx=2, pady=(0, 6))
                self.text_dropdown = None
                self._rebuild_text_dropdown()

        # тонкий разделитель справа от панели
        Frame(body, width=1, bg='#ced4da').pack(side=LEFT, fill=Y)

        canvas_frame = Frame(body, bg='white')
        canvas_frame.pack(side=LEFT, fill=BOTH, expand=True)
        self.v_scroll = Scrollbar(canvas_frame, orient=tk.VERTICAL)
        self.h_scroll = Scrollbar(canvas_frame, orient=tk.HORIZONTAL)
        self.canvas = Canvas(
            canvas_frame, bg='#ffffff',
            highlightthickness=0,
            yscrollcommand=self.v_scroll.set,
            xscrollcommand=self.h_scroll.set,
        )
        self.v_scroll.config(command=self.canvas.yview)
        self.h_scroll.config(command=self.canvas.xview)

        self.v_scroll.pack(side=RIGHT, fill=Y)
        self.h_scroll.pack(side=BOTTOM, fill=X)
        self.canvas.pack(side=LEFT, fill=BOTH, expand=True)

        self.canvas.bind('<Button-1>', self.on_press)
        self.canvas.bind('<B1-Motion>', self.on_drag)
        self.canvas.bind('<ButtonRelease-1>', self.on_release)
        self.canvas.bind('<Control-MouseWheel>', self._on_ctrl_wheel)
        self.canvas.bind('<Control-Button-4>', lambda e: self._zoom_by(self.zoom_step))
        self.canvas.bind('<Control-Button-5>', lambda e: self._zoom_by(-self.zoom_step))
        self.canvas.bind('<MouseWheel>', self._on_wheel_scroll)
        self.canvas.bind('<Button-4>', lambda e: self.canvas.yview_scroll(-1, 'units'))
        self.canvas.bind('<Button-5>', lambda e: self.canvas.yview_scroll(1, 'units'))
        # Средняя кнопка мыши — временное панорамирование
        self.canvas.bind('<Button-2>', self._pan_mark)
        self.canvas.bind('<B2-Motion>', self._pan_dragto)

    def _build_nav(self):
        self.nav_frame = Frame(self, bg='#f4f6f8')
        self.nav_frame.pack(side=BOTTOM, fill=X)
        nav_btn = dict(
            bd=0, padx=12, pady=6, font=('DejaVu Sans', 9),
            bg='#f4f6f8', activebackground='#e9ecef',
            highlightthickness=0, cursor='hand2', relief=tk.FLAT,
        )
        self.prev_button = Button(self.nav_frame, text='← Предыдущая', command=self.prev_page, **nav_btn)
        self.next_button = Button(self.nav_frame, text='Следующая →', command=self.next_page, **nav_btn)
        self.page_label = Label(
            self.nav_frame, text='', bg='#f4f6f8',
            fg='#495057', font=('DejaVu Sans', 9),
        )
        self.page_label.pack(side=tk.TOP, pady=4)

    def _bind_keys(self):
        # Один раз на toplevel: он есть в bindtags дочерних виджетов.
        # Бинд и на Frame, и на окно давал двойной Ctrl+O.
        top = self.winfo_toplevel()

        def _bind(sequence, handler):
            def _wrapped(event, h=handler):
                h()
                return 'break'
            top.bind(sequence, _wrapped)

        _bind('<Control-z>', self.undo_last_action)
        _bind('<Control-Z>', self.undo_last_action)
        _bind('<Control-y>', self.redo_last_action)
        _bind('<Control-Y>', self.redo_last_action)
        _bind('<Control-Shift-Z>', self.redo_last_action)
        _bind('<Control-o>', self.ask_open_pdf)
        _bind('<Control-O>', self.ask_open_pdf)
        self.focus_set()
    # --- resources / dropdown ---

    def _text_label_short(self, text, limit=9):
        """Фиксированная длина подписи, чтобы не менялась ширина панели."""
        text = (text or 'текст').strip()
        if text == 'выберите текст':
            text = 'текст…'
        elif text == 'Другое':
            text = 'другое'
        if len(text) > limit:
            text = text[: limit - 1] + '…'
        return f'▾ {text}'

    def _select_preset_text(self, value):
        self.text_var.set(value)
        self._refresh_text_menu_label()
        if self.option.get() != 'text':
            self.option.set('text')
            self._on_tool_change()

    def _refresh_text_menu_label(self):
        if getattr(self, 'text_dropdown', None) is None:
            return
        self.text_dropdown.config(text=self._text_label_short(self.text_var.get()))

    def _rebuild_text_dropdown(self):
        if not hasattr(self, 'text_submenu'):
            return
        if self.text_dropdown is not None:
            self.text_dropdown.destroy()

        options = [e['content'] for e in config.get('texts', [])]
        current = self.text_var.get()
        valid = options + ['выберите текст', 'Другое']
        if current not in valid:
            self.text_var.set('выберите текст')

        self.text_dropdown = Menubutton(
            self.text_submenu,
            text=self._text_label_short(self.text_var.get()),
            direction='right',
            bd=0,
            relief=tk.FLAT,
            bg='#eef2f6',
            activebackground='#d4e3f7',
            fg='#212529',
            font=('DejaVu Sans', 8),
            padx=2,
            pady=4,
            cursor='hand2',
            highlightthickness=0,
            anchor='w',
            width=12,
            wraplength=96,
        )
        menu = Menu(self.text_dropdown, tearoff=0, font=('DejaVu Sans', 9))
        menu.add_command(
            label='— выберите текст —',
            command=lambda: self._select_preset_text('выберите текст'),
        )
        if options:
            menu.add_separator()
        for opt in options:
            menu.add_command(
                label=opt,
                command=lambda value=opt: self._select_preset_text(value),
            )
        menu.add_separator()
        menu.add_command(
            label='Другое…',
            command=lambda: self._select_preset_text('Другое'),
        )
        self.text_dropdown.configure(menu=menu)
        self.text_dropdown.pack(fill=X)
        self._refresh_text_menu_label()
        if hasattr(self, 'size_scale'):
            self.update_dropdown_state()

    def open_resources(self):
        ResourcesDialog(self, on_apply=self._on_resources_applied)

    def _on_resources_applied(self):
        self._load_asset_images()
        self._rebuild_text_dropdown()
        self.display_click_positions()

    def _load_asset_images(self):
        self._pil_cache.clear()
        self._signature_pil = Image.open(config['images']['signature']['path']).convert('RGBA')
        self._print_pil = Image.open(config['images']['print']['path']).convert('RGBA')

    # --- size / zoom helpers ---

    def _zoom_text(self):
        return f'{int(round(self.zoom * 100))}%'

    def _on_tool_change(self):
        self.update_dropdown_state()
        self._update_canvas_cursor()

    def _update_canvas_cursor(self):
        if not hasattr(self, 'canvas'):
            return
        kind = self.option.get()
        if kind == 'pan':
            self.canvas.config(cursor='fleur')
        elif kind == 'text':
            self.canvas.config(cursor='xterm')
        else:
            self.canvas.config(cursor='crosshair')

    def _on_size_change(self, value):
        if getattr(self, '_suppress_size_callback', False):
            return
        pct = float(value) / 100.0
        kind = self.option.get()
        if kind == 'pan':
            return
        if kind == 'signature':
            self.signature_scale = pct
            config['images']['signature']['scale'] = pct
        elif kind == 'print':
            self.print_scale = pct
            config['images']['print']['scale'] = pct
        elif kind == 'text':
            base = float(config['font']['size'])
            self.text_font_size = max(4, base * pct)
        if self._selected_index is not None:
            self._apply_size_to_selected()
        else:
            self.display_click_positions()

    def _apply_size_to_selected(self):
        idx = self._selected_index
        if idx is None or idx >= len(self.click_positions):
            return
        if not self._size_undo_pushed:
            self._push_undo()
            self._size_undo_pushed = True
        item = self.click_positions[idx]
        kind = item['type']
        if kind == 'signature':
            item['scale'] = self.signature_scale
        elif kind == 'print':
            item['scale'] = self.print_scale
        elif kind == 'text':
            item['font_size'] = self.text_font_size
        self.display_click_positions()

    def update_dropdown_state(self):
        kind = self.option.get()
        placing = kind in ('signature', 'print', 'text')
        size_state = NORMAL if placing or self._selected_index is not None else DISABLED
        self.size_scale.config(state=size_state)
        self.size_label.config(state=size_state)

        # Подменю текста всегда на месте — только активность, без pack_forget (иначе «плавает» панель)
        if getattr(self, 'text_dropdown', None) is not None:
            if kind == 'text':
                self.text_dropdown.config(
                    state=NORMAL, bg='#d4e3f7', fg='#212529',
                    activebackground='#c5d7f0',
                )
            else:
                self.text_dropdown.config(
                    state=DISABLED, bg='#f0f2f4', fg='#adb5bd',
                    activebackground='#f0f2f4',
                )

        self._suppress_size_callback = True
        try:
            if kind == 'text':
                base = float(config['font']['size'])
                pct = int(round((self.text_font_size / base) * 100)) if base else 100
                self.size_scale.set(pct)
            elif kind == 'signature':
                self.size_scale.set(int(self.signature_scale * 100))
            elif kind == 'print':
                self.size_scale.set(int(self.print_scale * 100))
        finally:
            self._suppress_size_callback = False

    def zoom_in(self):
        self._zoom_by(self.zoom_step)

    def zoom_out(self):
        self._zoom_by(-self.zoom_step)

    def _zoom_by(self, delta):
        if self.pdf_document is None:
            return
        new_zoom = round(self.zoom + delta, 2)
        new_zoom = max(self.min_zoom, min(self.max_zoom, new_zoom))
        if new_zoom == self.zoom:
            return
        self.zoom = new_zoom
        self.zoom_label.config(text=self._zoom_text())
        self.show_page(self.current_page)

    def _on_ctrl_wheel(self, event):
        if event.delta > 0:
            self._zoom_by(self.zoom_step)
        else:
            self._zoom_by(-self.zoom_step)

    def _on_wheel_scroll(self, event):
        if event.delta > 0:
            self.canvas.yview_scroll(-1, 'units')
        else:
            self.canvas.yview_scroll(1, 'units')

    # --- coordinates ---

    def _event_doc_xy(self, event):
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        return cx / self.zoom, cy / self.zoom

    def _doc_to_canvas(self, x, y):
        return x * self.zoom, y * self.zoom

    # --- page navigation ---

    def show_page(self, page_number):
        if self.pdf_document is None:
            self._show_empty_state()
            return
        page = self.pdf_document.load_page(page_number)
        mat = pymupdf.Matrix(self.zoom, self.zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = tk.PhotoImage(data=pix.tobytes('ppm'))
        self.canvas.delete('all')
        self.canvas.create_image(0, 0, anchor=tk.NW, image=img, tags='page')
        self.canvas.image = img
        self.canvas.config(scrollregion=(0, 0, pix.width, pix.height))
        self.display_click_positions()
        self.update_nav_buttons()

    def update_nav_buttons(self):
        self.prev_button.pack_forget()
        self.next_button.pack_forget()
        if self.pdf_document is None:
            self.page_label.config(text='Документ не открыт')
            return
        total = len(self.pdf_document)
        self.page_label.config(text=f'Страница {self.current_page + 1} из {total}')
        if self.current_page > 0:
            self.prev_button.pack(side=LEFT, padx=4, pady=4)
        if self.current_page < total - 1:
            self.next_button.pack(side=RIGHT, padx=4, pady=4)

    def next_page(self):
        if self.pdf_document is None:
            return
        if self.current_page < len(self.pdf_document) - 1:
            self.current_page += 1
            self._selected_index = None
            self.show_page(self.current_page)

    def prev_page(self):
        if self.pdf_document is None:
            return
        if self.current_page > 0:
            self.current_page -= 1
            self._selected_index = None
            self.show_page(self.current_page)
    # --- elements ---

    def _normalize_item(self, item):
        """Привести старый tuple к dict (на всякий случай)."""
        if isinstance(item, dict):
            return item
        page, x, y, option, *rest = item
        data = {'page': page, 'x': float(x), 'y': float(y), 'type': option, 'scale': 1.0}
        if option == 'text' and rest:
            data['text'] = rest[0]
            data['font_size'] = self.text_font_size
        return data

    def _item_size(self, item):
        kind = item['type']
        if kind == 'signature':
            w, h = self._signature_pil.size
            scale = float(item.get('scale', self.signature_scale))
            return w * scale, h * scale
        if kind == 'print':
            w, h = self._print_pil.size
            scale = float(item.get('scale', self.print_scale))
            return w * scale, h * scale
        # text approximate bbox in doc coords
        text = item.get('text') or ''
        font_size = float(item.get('font_size', self.text_font_size))
        return max(10, len(text) * font_size * 0.6), font_size * 1.4

    def _hit_test(self, doc_x, doc_y):
        """Вернуть индекс верхнего элемента под курсором на текущей странице."""
        for idx in range(len(self.click_positions) - 1, -1, -1):
            item = self._normalize_item(self.click_positions[idx])
            self.click_positions[idx] = item
            if item['page'] != self.current_page:
                continue
            w, h = self._item_size(item)
            if item['type'] == 'text':
                left, top = item['x'], item['y']
                right, bottom = left + w, top + h
            else:
                left = item['x'] - w / 2
                top = item['y'] - h / 2
                right = item['x'] + w / 2
                bottom = item['y'] + h / 2
            if left <= doc_x <= right and top <= doc_y <= bottom:
                return idx
        return None

    def _scaled_photo(self, pil_image, scale):
        display_scale = scale * self.zoom
        key = (id(pil_image), round(display_scale, 3))
        if key in self._pil_cache:
            return self._pil_cache[key]
        w = max(1, int(pil_image.width * display_scale))
        h = max(1, int(pil_image.height * display_scale))
        resized = pil_image.resize((w, h), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(resized)
        self._pil_cache[key] = photo
        return photo

    def display_click_positions(self):
        self.canvas.delete('overlay')
        self.canvas.delete('selection')
        self._tk_overlay_refs = []

        for idx, raw in enumerate(self.click_positions):
            item = self._normalize_item(raw)
            self.click_positions[idx] = item
            if item['page'] != self.current_page:
                continue
            cx, cy = self._doc_to_canvas(item['x'], item['y'])
            kind = item['type']
            tags = ('overlay', f'item-{idx}')
            if kind == 'signature':
                photo = self._scaled_photo(self._signature_pil, float(item.get('scale', 1.0)))
                self._tk_overlay_refs.append(photo)
                self.canvas.create_image(cx, cy, anchor=tk.CENTER, image=photo, tags=tags)
            elif kind == 'print':
                photo = self._scaled_photo(self._print_pil, float(item.get('scale', 1.0)))
                self._tk_overlay_refs.append(photo)
                self.canvas.create_image(cx, cy, anchor=tk.CENTER, image=photo, tags=tags)
            elif kind == 'text' and item.get('text'):
                font_size = float(item.get('font_size', self.text_font_size)) * self.zoom
                self.canvas.create_text(
                    cx, cy, text=item['text'], anchor=tk.NW,
                    font=('DejaVu Sans Mono', max(4, int(round(font_size)))),
                    fill='black', tags=tags,
                )

            if idx == self._selected_index:
                w, h = self._item_size(item)
                if kind == 'text':
                    x0, y0 = cx, cy
                    x1, y1 = cx + w * self.zoom, cy + h * self.zoom
                else:
                    x0 = cx - (w * self.zoom) / 2
                    y0 = cy - (h * self.zoom) / 2
                    x1 = cx + (w * self.zoom) / 2
                    y1 = cy + (h * self.zoom) / 2
                self.canvas.create_rectangle(
                    x0, y0, x1, y1, outline='#1a73e8', width=2, dash=(4, 2), tags='selection'
                )

    # --- mouse ---

    def _pan_mark(self, event):
        self._panning = True
        self.canvas.scan_mark(event.x, event.y)
        self.canvas.config(cursor='fleur')

    def _pan_dragto(self, event):
        if self._panning:
            self.canvas.scan_dragto(event.x, event.y, gain=1)

    def on_press(self, event):
        if self.pdf_document is None:
            return
        if self.option.get() == 'pan':
            self._pan_mark(event)
            return

        doc_x, doc_y = self._event_doc_xy(event)
        hit = self._hit_test(doc_x, doc_y)
        self._drag_moved = False
        if hit is not None:
            self._drag_index = hit
            item = self.click_positions[hit]
            self._drag_offset = (doc_x - item['x'], doc_y - item['y'])
            self._selected_index = hit
            self._push_undo()
            self.display_click_positions()
            return

        self._drag_index = None
        self._selected_index = None
        self._place_new(doc_x, doc_y)

    def on_drag(self, event):
        if self._panning or self.option.get() == 'pan':
            self._pan_dragto(event)
            return
        if self._drag_index is None:
            return
        doc_x, doc_y = self._event_doc_xy(event)
        item = self.click_positions[self._drag_index]
        item['x'] = doc_x - self._drag_offset[0]
        item['y'] = doc_y - self._drag_offset[1]
        self._drag_moved = True
        self.display_click_positions()

    def on_release(self, event):
        if self._panning:
            self._panning = False
            self._update_canvas_cursor()
            return
        if self._drag_index is not None and not self._drag_moved:
            # клик по элементу без движения — только выделение; undo-снимок лишний
            if self._undo_stack:
                self._undo_stack.pop()
            self._sync_size_scale_from_selected()
        self._drag_index = None
        self._drag_moved = False

    def _sync_size_scale_from_selected(self):
        if self._selected_index is None:
            return
        item = self.click_positions[self._selected_index]
        self.option.set(item['type'])
        self._suppress_size_callback = True
        try:
            if item['type'] == 'text':
                base = float(config['font']['size']) or 1
                self.text_font_size = float(item.get('font_size', base))
                self.size_scale.set(int(round(self.text_font_size / base * 100)))
                if item.get('text'):
                    self.text_var.set(item['text'])
                    self._refresh_text_menu_label()
            elif item['type'] == 'signature':
                self.signature_scale = float(item.get('scale', 1.0))
                self.size_scale.set(int(self.signature_scale * 100))
            else:
                self.print_scale = float(item.get('scale', 1.0))
                self.size_scale.set(int(self.print_scale * 100))
        finally:
            self._suppress_size_callback = False
        self.update_dropdown_state()

    def _place_new(self, doc_x, doc_y):
        kind = self.option.get()
        if kind == 'pan':
            return
        if kind == 'text':
            text = self.text_var.get()
            if text == 'Другое':
                text = simpledialog.askstring('Ввод текста', 'Введите текст для вставки:', parent=self)
            if not text or text == 'выберите текст':
                self.display_click_positions()
                return
            self._push_undo()
            self.click_positions.append({
                'page': self.current_page,
                'x': doc_x,
                'y': doc_y,
                'type': 'text',
                'text': text,
                'font_size': self.text_font_size,
                'scale': 1.0,
            })
        else:
            scale = self.signature_scale if kind == 'signature' else self.print_scale
            self._push_undo()
            self.click_positions.append({
                'page': self.current_page,
                'x': doc_x,
                'y': doc_y,
                'type': kind,
                'scale': scale,
            })
        self._selected_index = len(self.click_positions) - 1
        self.display_click_positions()

    # --- undo / redo ---

    def _push_undo(self):
        self._undo_stack.append(copy.deepcopy(self.click_positions))
        self._redo_stack.clear()

    def undo_last_action(self):
        if not self._undo_stack:
            return
        self._redo_stack.append(copy.deepcopy(self.click_positions))
        self.click_positions[:] = self._undo_stack.pop()
        self._selected_index = None
        self.display_click_positions()

    def redo_last_action(self):
        if not self._redo_stack:
            return
        self._undo_stack.append(copy.deepcopy(self.click_positions))
        self.click_positions[:] = self._redo_stack.pop()
        self._selected_index = None
        self.display_click_positions()

    # --- sign / save ---

    def sign_pdf(self):
        if self.pdf_document is None or not self.input_pdf_path.get():
            messagebox.showwarning('Подпись', 'Сначала откройте PDF', parent=self.winfo_toplevel())
            return
        if not self.click_positions:
            messagebox.showwarning('Подпись', 'Нет элементов для подписи', parent=self.winfo_toplevel())
            return
        sign(self.input_pdf_path.get(), 'tmp/temp_output.pdf', self.click_positions)
        self.save_pdf()

    def save_pdf(self):
        top = self.winfo_toplevel()
        loaded_file_name = os.path.basename(self.input_pdf_path.get())
        suggested_output_name = f'{os.path.splitext(loaded_file_name)[0]}(подписано).pdf'
        file_path = filedialog.asksaveasfilename(
            parent=top,
            initialdir=get_initial_dir('save'),
            defaultextension='.pdf',
            filetypes=[('PDF files', '*.pdf')],
            initialfile=suggested_output_name,
        )
        if not file_path:
            if os.path.exists('tmp/temp_output.pdf'):
                os.remove('tmp/temp_output.pdf')
            return
        if os.path.exists('tmp/temp_output.pdf'):
            os.replace('tmp/temp_output.pdf', file_path)
            remember_dir(file_path, 'save')
            messagebox.showinfo('Сохранение', 'Файл сохранен', parent=top)
            self.click_positions.clear()
            self._undo_stack.clear()
            self._redo_stack.clear()
            self._selected_index = None
            self.display_click_positions()
        else:
            messagebox.showerror('Ошибка', 'Файл temp_output.pdf не найден', parent=top)
