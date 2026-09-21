"""Small declarative layout system inspired by Jetpack Compose.

    Column
    Text
    Bitmap
    Divider
    Spacer
"""

from PIL import Image, ImageDraw

from .config import WIDTH, HEIGHT


class Component:
    """
    Base class for everything that can be rendered.

    render() returns the height actually consumed by the component.
    """

    def measure(self, draw, width, height):
        return width, 0

    def render(self, canvas, draw, x, y, width, height):
        return 0


class Text(Component):
    def __init__(
        self,
        text,
        font,
        *,
        align="left",
        fill=0,
    ):
        self.text = text
        self.font = font
        self.align = align
        self.fill = fill

    def measure(self, draw, width, height):
        bbox = draw.textbbox(
            (0, 0),
            self.text,
            font=self.font,
        )

        return width, bbox[3] - bbox[1]

    def render(self, canvas, draw, x, y, width, height):
        bbox = draw.textbbox(
            (0, 0),
            self.text,
            font=self.font,
        )

        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        if self.align == "center":
            text_x = x + (width - text_width) // 2

        elif self.align == "right":
            text_x = x + width - text_width

        else:
            text_x = x

        draw.text(
            (text_x, y),
            self.text,
            font=self.font,
            fill=self.fill,
        )

        return text_height


class Divider(Component):
    def __init__(self, thickness=2, margin=0):
        self.thickness = thickness
        self.margin = margin

    def measure(self, draw, width, height):
        return width, self.thickness + self.margin * 2

    def render(self, canvas, draw, x, y, width, height):
        line_y = y + self.margin

        draw.line(
            (x, line_y, x + width, line_y),
            fill=0,
            width=self.thickness,
        )

        return self.thickness + self.margin * 2


class Spacer(Component):
    def __init__(self, weight=1):
        self.weight = weight

    def measure(self, draw, width, height):
        return width, 0

    def render(self, canvas, draw, x, y, width, height):
        return height


class Bitmap(Component):
    def __init__(
        self,
        image,
        *,
        align="center",
    ):
        self.image = image
        self.align = align

    def measure(self, draw, width, height):
        return self.image.width, self.image.height

    def render(self, canvas, draw, x, y, width, height):
        if self.align == "center":
            image_x = x + (width - self.image.width) // 2

        elif self.align == "right":
            image_x = x + width - self.image.width

        else:
            image_x = x

        canvas.paste(
            self.image,
            (image_x, y),
        )

        return self.image.height


class Column(Component):
    def __init__(
        self,
        children,
        *,
        gap=0,
        padding=0,
    ):
        self.children = children
        self.gap = gap
        self.padding = padding

    def render(self, canvas, draw, x, y, width, height):
        content_x = x + self.padding
        content_y = y + self.padding

        content_width = max(
            0,
            width - self.padding * 2,
        )

        content_height = max(
            0,
            height - self.padding * 2,
        )

        fixed_height = 0
        spacer_weight = 0
        child_sizes = []

        for child in self.children:
            if isinstance(child, Spacer):
                spacer_weight += child.weight
                child_sizes.append((child, 0))
                continue

            _, child_height = child.measure(
                draw,
                content_width,
                content_height,
            )

            fixed_height += child_height
            child_sizes.append((child, child_height))

        gaps = self.gap * max(
            0,
            len(self.children) - 1,
        )

        remaining_height = max(
            0,
            content_height
            - fixed_height
            - gaps,
        )

        spacer_height = (
            remaining_height / spacer_weight
            if spacer_weight
            else 0
        )

        cursor_y = content_y

        for child, child_height in child_sizes:
            if isinstance(child, Spacer):
                cursor_y += int(
                    spacer_height * child.weight
                )
                continue

            child.render(
                canvas,
                draw,
                content_x,
                cursor_y,
                content_width,
                child_height,
            )

            cursor_y += child_height + self.gap

        return min(
            height,
            cursor_y - y + self.padding * 2,
        )


def render_layout(layout):
    img = Image.new(
        "1",
        (WIDTH, HEIGHT),
        1,
    )

    draw = ImageDraw.Draw(img)

    layout.render(
        img,
        draw,
        0,
        0,
        WIDTH,
        HEIGHT,
    )

    return img
