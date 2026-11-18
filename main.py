import tkinter as tk
from tkinter import ttk, Menu
from pdf_viewer import PDFViewer, ResourcesDialog


def _fit_main_window(root):
    root.update_idletasks()
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    width = min(960, max(720, screen_w - 80))
    height = min(900, max(560, screen_h - 100))
    x = max(0, (screen_w - width) // 2)
    y = max(0, (screen_h - height) // 2)
    root.geometry(f'{width}x{height}+{x}+{y}')


root = tk.Tk()
ttk.Style().theme_use('clam')
root.title('Подпись и печать')
_fit_main_window(root)

viewer = PDFViewer(root)
viewer.pack(fill=tk.BOTH, expand=True)


def open_resources():
    ResourcesDialog(root, on_apply=viewer._on_resources_applied)


menubar = Menu(root)
file_menu = Menu(menubar, tearoff=0)
file_menu.add_command(label='Открыть PDF…\tCtrl+O', command=viewer.ask_open_pdf)
file_menu.add_separator()
file_menu.add_command(label='Выход', command=root.destroy)
menubar.add_cascade(label='Файл', menu=file_menu)

resources_menu = Menu(menubar, tearoff=0)
resources_menu.add_command(label='Подпись, печать и тексты…', command=open_resources)
menubar.add_cascade(label='Ресурсы', menu=resources_menu)

edit_menu = Menu(menubar, tearoff=0)
edit_menu.add_command(label='Отменить\tCtrl+Z', command=viewer.undo_last_action)
edit_menu.add_command(label='Повторить\tCtrl+Y', command=viewer.redo_last_action)
menubar.add_cascade(label='Правка', menu=edit_menu)

root.config(menu=menubar)
root.mainloop()
