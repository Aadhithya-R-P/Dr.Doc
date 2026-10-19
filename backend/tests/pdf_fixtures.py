"""Tiny synthetic PDFs created in memory, without external documents or models."""

from io import BytesIO

from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, DecodedStreamObject, NameObject, NumberObject


def make_pdf(pages: list[str | None], *, image_page: int | None = None, encrypted=False,
             compress=False) -> bytes:
    writer = PdfWriter()
    for index, text in enumerate(pages, start=1):
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        })
        resources = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})
        })
        content = DecodedStreamObject()
        if index == image_page:
            image = DecodedStreamObject()
            image.set_data(b"\x00\x00\x00")
            image.update({
                NameObject("/Type"): NameObject("/XObject"),
                NameObject("/Subtype"): NameObject("/Image"),
                NameObject("/Width"): NumberObject(1),
                NameObject("/Height"): NumberObject(1),
                NameObject("/ColorSpace"): NameObject("/DeviceRGB"),
                NameObject("/BitsPerComponent"): NumberObject(8),
            })
            resources[NameObject("/XObject")] = DictionaryObject({NameObject("/Im0"): image})
            content.set_data(b"q 100 0 0 100 0 0 cm /Im0 Do Q")
        elif text:
            escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            lines = escaped.split("\n")
            operators = ["BT /F1 12 Tf 50 740 Td 14 TL"]
            operators += [f"({line}) Tj T*" for line in lines]
            operators.append("ET")
            content.set_data("\n".join(operators).encode("ascii"))
        else:
            content.set_data(b"")
        page[NameObject("/Resources")] = resources
        page[NameObject("/Contents")] = content.flate_encode() if compress else content
    if encrypted:
        writer.encrypt("test-only-password")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()
