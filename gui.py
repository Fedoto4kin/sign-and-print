import os
from tkinter import filedialog, messagebox
from config import config
from pdf_viewer import PDFViewer

# Глобальный массив для хранения координат и номеров страниц
click_positions = []


def load_pdf(input_pdf_path, filename_label):
    file_path = filedialog.askopenfilename(
        initialdir=os.path.expanduser(config['path']['default']),
        filetypes=[("PDF files", "*.pdf")]
    )
    if file_path:
        input_pdf_path.set(file_path)
        filename_label.config(text=os.path.basename(file_path))
        filename_label.pack()
        PDFViewer(file_path, click_positions, input_pdf_path)
