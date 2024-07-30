import os
import tkinter as tk
from tkinter import Toplevel, Canvas, Button, filedialog, messagebox, Radiobutton, StringVar, simpledialog, OptionMenu, Frame, PhotoImage
import fitz  # PyMuPDF
from pdf_processing import sign
from config import config

class PDFViewer(Toplevel):
    def __init__(self, pdf_path, click_positions, input_pdf_path):
        super().__init__()
        self.title("Подпишите документ")
        self.geometry("840x900")

        self.toolbar = Frame(self)
        self.toolbar.pack(side=tk.TOP, fill=tk.X)

        self.option = StringVar(value="signature")
        self.signature_radio = Radiobutton(self.toolbar, text="Подпись", variable=self.option, value="signature", command=self.update_dropdown_state)
        self.signature_radio.pack(side=tk.LEFT, padx=2, pady=2)
        self.print_radio = Radiobutton(self.toolbar, text="Печать", variable=self.option, value="print", command=self.update_dropdown_state)
        self.print_radio.pack(side=tk.LEFT, padx=2, pady=2)
        self.text_radio = Radiobutton(self.toolbar, text="Текст", variable=self.option, value="text", command=self.update_dropdown_state)
        self.text_radio.pack(side=tk.LEFT, padx=2, pady=2)

        self.text_var = StringVar(value="выберите текст")
        text_options = ["выберите текст"] + [entry['content'] for entry in config['texts']] + ["Другое"]
        self.text_dropdown = OptionMenu(self.toolbar, self.text_var, *text_options)
        self.text_dropdown.config(state=tk.DISABLED)
        self.text_dropdown.pack(side=tk.LEFT, padx=2, pady=2)

        self.checkmark_image = PhotoImage(file="resources/checkmark.png")
        self.sign_button = Button(self.toolbar, text="Подписать", image=self.checkmark_image, compound=tk.LEFT, command=self.sign_pdf)
        self.sign_button.pack(side=tk.RIGHT, padx=2, pady=2)

        self.undo_image = PhotoImage(file="resources/undo.png")
        self.undo_button = Button(self.toolbar, text="Отменить", image=self.undo_image, compound=tk.LEFT, command=self.undo_last_action)
        self.undo_button.pack(side=tk.RIGHT, padx=2, pady=2)

        self.canvas = Canvas(self, bg="white")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.pdf_document = fitz.open(pdf_path)
        self.current_page = 0
        self.click_positions = click_positions
        self.input_pdf_path = input_pdf_path

        self.signature_image = tk.PhotoImage(file=config['images']['signature']['path'])  # Путь к изображению подписи из конфига
        self.print_image = tk.PhotoImage(file=config['images']['print']['path'])  # Путь к изображению печати из конфига

        self.show_page(self.current_page)

        self.next_button = Button(self, text="Следующая страница", command=self.next_page)
        self.next_button.pack(side=tk.RIGHT)
        self.prev_button = Button(self, text="Предыдущая страница", command=self.prev_page)
        self.prev_button.pack(side=tk.LEFT)

        self.canvas.bind("<Button-1>", self.on_click)

    def update_dropdown_state(self):
        if self.option.get() == "text":
            self.text_dropdown.config(state=tk.NORMAL)
        else:
            self.text_dropdown.config(state=tk.DISABLED)
            self.text_var.set("выберите текст")

    def show_page(self, page_number):
        page = self.pdf_document.load_page(page_number)
        pix = page.get_pixmap()
        img = tk.PhotoImage(data=pix.tobytes())
        self.canvas.create_image(0, 0, anchor=tk.NW, image=img)
        self.canvas.image = img
        self.canvas.config(scrollregion=self.canvas.bbox(tk.ALL))
        self.display_click_positions()

    def next_page(self):
        if self.current_page < len(self.pdf_document) - 1:
            self.current_page += 1
            self.show_page(self.current_page)

    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.show_page(self.current_page)

    def on_click(self, event):
        x, y = event.x, event.y
        if self.option.get() == "text":
            text = self.text_var.get()
            if text == "Другое":
                text = simpledialog.askstring("Ввод текста", "Введите текст для вставки:")
            if text and text != "выберите текст":
                self.click_positions.append((self.current_page, x, y, self.option.get(), text))
                print(f"Clicked at: ({x}, {y}) on page {self.current_page} as {self.option.get()} with text: {text}")
        else:
            self.click_positions.append((self.current_page, x, y, self.option.get()))
            print(f"Clicked at: ({x}, {y}) on page {self.current_page} as {self.option.get()}")
        self.display_click_positions()

    def display_click_positions(self):
        self.canvas.delete("signature")  # Удаляем все предыдущие подписи, печати и тексты
        for page, x, y, option, *text in self.click_positions:
            if page == self.current_page:
                if option == "signature":
                    self.canvas.create_image(x, y, anchor=tk.CENTER, image=self.signature_image, tags="signature")
                elif option == "print":
                    self.canvas.create_image(x, y, anchor=tk.CENTER, image=self.print_image, tags="signature")
                elif option == "text" and text:
                    self.canvas.create_text(x, y, text=text[0], anchor=tk.NW, tags="signature")

    def undo_last_action(self):
        if self.click_positions:
            self.click_positions.pop()
            self.display_click_positions()
            print("Последнее действие отменено")

    def sign_pdf(self):
        sign(self.input_pdf_path.get(), 'temp_output.pdf', self.click_positions)
        self.destroy()  # Закрываем окно просмотра PDF перед сохранением
        self.save_pdf()

    def save_pdf(self):
        loaded_file_directory = os.path.dirname(self.input_pdf_path.get())
        loaded_file_name = os.path.basename(self.input_pdf_path.get())
        suggested_output_name = f"{os.path.splitext(loaded_file_name)[0]}(подписано).pdf"
        file_path = filedialog.asksaveasfilename(
            initialdir=loaded_file_directory,
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            initialfile=suggested_output_name
        )
        if file_path:
            if os.path.exists('temp_output.pdf'):
                os.rename('temp_output.pdf', file_path)
                messagebox.showinfo("Сохранение", "Файл сохранен")
            else:
                messagebox.showerror("Ошибка", "Файл temp_output.pdf не найден")
            self.quit()
