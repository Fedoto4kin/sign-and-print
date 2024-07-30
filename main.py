import tkinter as tk
from tkinter import ttk
from gui import load_pdf

# Создание GUI
root = tk.Tk()
ttk.Style().theme_use('clam')

root.title('Подписать Комплект от АтомЭнергоСбыт')
root.geometry("360x120")

input_pdf_path = tk.StringVar()

load_button = tk.Button(
    root,
    text='Загрузить PDF',
    command=lambda: load_pdf(input_pdf_path, tk.Label(root, text="")))
load_button.pack(expand=True)

root.mainloop()
