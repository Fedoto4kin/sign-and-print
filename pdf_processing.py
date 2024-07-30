from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image
import os
import io
from config import config

# Регистрация шрифта
current_directory = os.getcwd()
font_path = os.path.join(current_directory, config['font']['path'])
pdfmetrics.registerFont(TTFont('MonoFont', font_path))

def add_graphic(page, image_path, positions, image_size):
    packet = io.BytesIO()
    # Увеличиваем размеры страницы
    enlarged_page_size = (landscape(letter)[0] * 2, landscape(letter)[1] * 2)
    watermark_c = canvas.Canvas(packet, pagesize=enlarged_page_size)
    width, height = image_size
    for position in positions:
        x, y = position
        watermark_c.drawImage(image_path, float(x) - width / 2, float(y) - height / 2, width=width, height=height, mask='auto')
    watermark_c.save()
    packet.seek(0)
    watermark_pdf = PdfReader(packet)
    page.merge_page(watermark_pdf.pages[0])

def add_text(page, text, position, font_name=config['font']['name'], font_size=config['font']['size']):
    packet = io.BytesIO()
    # Увеличиваем размеры страницы
    enlarged_page_size = (landscape(letter)[0] * 2, landscape(letter)[1] * 2)
    can = canvas.Canvas(packet, pagesize=enlarged_page_size)
    can.setFont(font_name, font_size)
    text_height = font_size * 1.33  # Преобразование из pt в px (1 pt = 1.33 px)
    can.drawString(position[0], position[1] - text_height, text)  # Поправка на высоту текста
    can.save()
    packet.seek(0)
    new_pdf = PdfReader(packet)
    page.merge_page(new_pdf.pages[0])

def sign(input_pdf_path, output_pdf_path, click_positions):
    # Загрузка путей к изображениям и текстов из конфигурации
    sign_png_path = config['images']['signature']['path']
    print_png_path = config['images']['print']['path']

    # Получение размера изображений
    with Image.open(sign_png_path) as img:
        sign_image_width, sign_image_height = img.size
    with Image.open(print_png_path) as img:
        print_image_width, print_image_height = img.size

    original_pdf = PdfReader(input_pdf_path)
    pdf_writer = PdfWriter()

    for page_num in range(len(original_pdf.pages)):
        page = original_pdf.pages[page_num]
        page_height = float(page.mediabox[3])  # Высота страницы

        # Разделяем позиции для подписей, печатей и текста
        signatures_on_page = [(float(x), page_height - float(y)) for click_page, x, y, option, *text in click_positions if click_page == page_num and option == "signature"]
        prints_on_page = [(float(x), page_height - float(y)) for click_page, x, y, option, *text in click_positions if click_page == page_num and option == "print"]
        texts_on_page = [(float(x), page_height - float(y), text[0]) for click_page, x, y, option, *text in click_positions if click_page == page_num and option == "text"]

        if signatures_on_page:
            add_graphic(page, sign_png_path, signatures_on_page, (sign_image_width, sign_image_height))
        if prints_on_page:
            add_graphic(page, print_png_path, prints_on_page, (print_image_width, print_image_height))
        if texts_on_page:
            for x, y, text in texts_on_page:
                add_text(page, text, (x, y))

        pdf_writer.add_page(page)

    with open(output_pdf_path, 'wb') as out_pdf:
        pdf_writer.write(out_pdf)
