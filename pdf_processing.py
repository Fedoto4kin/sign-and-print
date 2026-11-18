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


def _element_type(item):
    if isinstance(item, dict):
        return item.get('type') or item.get('option')
    return item[3]


def _element_xy(item):
    if isinstance(item, dict):
        return float(item['x']), float(item['y'])
    return float(item[1]), float(item[2])


def _element_page(item):
    if isinstance(item, dict):
        return item['page']
    return item[0]


def _element_text(item):
    if isinstance(item, dict):
        return item.get('text')
    return item[4] if len(item) > 4 else None


def _element_scale(item, default=1.0):
    if isinstance(item, dict):
        return float(item.get('scale', default))
    return default


def _element_font_size(item):
    if isinstance(item, dict):
        return float(item.get('font_size', config['font']['size']))
    return float(config['font']['size'])


def add_graphic(page, image_path, placements):
    """placements: list of (x, y, width, height) in PDF coords."""
    packet = io.BytesIO()
    enlarged_page_size = (landscape(letter)[0] * 2, landscape(letter)[1] * 2)
    watermark_c = canvas.Canvas(packet, pagesize=enlarged_page_size)
    for x, y, width, height in placements:
        watermark_c.drawImage(
            image_path,
            float(x) - width / 2,
            float(y) - height / 2,
            width=width,
            height=height,
            mask='auto',
        )
    watermark_c.save()
    packet.seek(0)
    watermark_pdf = PdfReader(packet)
    page.merge_page(watermark_pdf.pages[0])


def add_text(page, text, position, font_name=None, font_size=None):
    font_name = font_name or config['font']['name']
    font_size = font_size if font_size is not None else config['font']['size']
    packet = io.BytesIO()
    enlarged_page_size = (landscape(letter)[0] * 2, landscape(letter)[1] * 2)
    can = canvas.Canvas(packet, pagesize=enlarged_page_size)
    can.setFont(font_name, font_size)
    text_height = font_size * 1.33
    can.drawString(position[0], position[1] - text_height, text)
    can.save()
    packet.seek(0)
    new_pdf = PdfReader(packet)
    page.merge_page(new_pdf.pages[0])


def sign(input_pdf_path, output_pdf_path, click_positions):
    sign_png_path = config['images']['signature']['path']
    print_png_path = config['images']['print']['path']
    default_sign_scale = float(config['images']['signature'].get('scale', 1.0))
    default_print_scale = float(config['images']['print'].get('scale', 1.0))

    with Image.open(sign_png_path) as img:
        sign_w, sign_h = img.size
    with Image.open(print_png_path) as img:
        print_w, print_h = img.size

    original_pdf = PdfReader(input_pdf_path)
    pdf_writer = PdfWriter()

    for page_num in range(len(original_pdf.pages)):
        page = original_pdf.pages[page_num]
        page_height = float(page.mediabox[3])

        signatures = []
        prints = []
        texts = []

        for item in click_positions:
            if _element_page(item) != page_num:
                continue
            x, y = _element_xy(item)
            pdf_x, pdf_y = x, page_height - y
            kind = _element_type(item)
            if kind == 'signature':
                scale = _element_scale(item, default_sign_scale)
                signatures.append((pdf_x, pdf_y, sign_w * scale, sign_h * scale))
            elif kind == 'print':
                scale = _element_scale(item, default_print_scale)
                prints.append((pdf_x, pdf_y, print_w * scale, print_h * scale))
            elif kind == 'text':
                text = _element_text(item)
                if text:
                    texts.append((pdf_x, pdf_y, text, _element_font_size(item)))

        if signatures:
            add_graphic(page, sign_png_path, signatures)
        if prints:
            add_graphic(page, print_png_path, prints)
        for x, y, text, font_size in texts:
            add_text(page, text, (x, y), font_size=font_size)

        pdf_writer.add_page(page)

    os.makedirs(os.path.dirname(output_pdf_path) or '.', exist_ok=True)
    with open(output_pdf_path, 'wb') as out_pdf:
        pdf_writer.write(out_pdf)
