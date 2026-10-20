"""Deterministic typography for explicitly requested text-only covers."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from xhs_operations import OperationError


def render_text_cover(text, target, size=(1024, 1536)):
    if not isinstance(text, str) or not text.strip() or len(text) > 100:
        raise OperationError('文字封面缺少短句或文字过长')
    if 'ai' in text.casefold():
        raise OperationError('文字封面含制作来源字样')
    fonts = (Path('/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc'),
             Path('C:/Windows/Fonts/simsun.ttc'))
    font_path = next((p for p in fonts if p.is_file()), None)
    if font_path is None:
        raise OperationError('文字封面缺少中文字体')
    image = Image.new('RGB', size, '#fff8f5')
    draw = ImageDraw.Draw(image)
    margin = round(size[0] * .11)
    lines = text.strip().splitlines()
    # Wrap by measured glyph width so punctuation also fits inside the canvas.
    for point_size in range(round(size[0] * .105), 35, -1):
        font = ImageFont.truetype(str(font_path), point_size)
        wrapped = []
        for line in lines:
            part = ''
            for char in line:
                if part and draw.textlength(part + char, font=font) > size[0] - 2 * margin:
                    wrapped.append(part)
                    part = ''
                part += char
            wrapped.append(part)
        line_height = round(point_size * 1.55)
        if len(wrapped) * line_height <= size[1] * .64:
            break
    else:
        raise OperationError('文字封面排版超出画幅')
    top = round(size[1] * .23)
    boxes = []
    for index, line in enumerate(wrapped):
        position = (margin, top + index * line_height)
        bbox = draw.textbbox(position, line, font=font, anchor='lt')
        if bbox[0] < 0 or bbox[2] > size[0] or bbox[3] > size[1]:
            raise OperationError('文字封面文字超出边界')
        draw.text(position, line, font=font, fill='#a83f29', anchor='lt')
        boxes.append(list(bbox))
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, quality=97, subsampling=0)
    return {'text': text, 'lines': wrapped, 'text_boxes': boxes, 'size': list(size),
            'font': font_path.name, 'background': '#fff8f5', 'foreground': '#a83f29'}
