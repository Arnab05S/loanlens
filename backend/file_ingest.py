"""Bounded, in-memory extraction for common loan-rejection document formats.

No uploaded path is written to disk. ZIP/XML inputs are size-limited and treated as
untrusted data. The returned text is always passed under the backend's untrusted-data
instructions; embedded images are sent as image Parts.
"""
from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
from pathlib import PurePosixPath
from typing import Iterable
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException

from openpyxl import load_workbook
from PIL import Image, ImageOps, UnidentifiedImageError
from striprtf.striprtf import rtf_to_text

Image.MAX_IMAGE_PIXELS = 40_000_000

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_TEXT_CHARS = 30_000
MAX_UNPACKED_BYTES = 50 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 500
MAX_ZIP_DOCUMENTS = 12
MAX_EMBEDDED_IMAGES = 8
MAX_EMBEDDED_IMAGE_BYTES = 12 * 1024 * 1024
MAX_DIRECT_IMAGE_BYTES = 12 * 1024 * 1024
MAX_XML_BYTES = 12 * 1024 * 1024
MAX_XLSX_CELLS = 20_000
MAX_XLSX_ROWS = 2_000
MAX_XLSX_COLUMNS = 100
MAX_XLSX_SHEETS = 8
MAX_PPTX_SLIDES = 40
MAX_EML_ATTACHMENTS = 12

IMAGE_MIME = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".heic": "image/heic", ".heif": "image/heif",
    ".bmp": "image/bmp", ".gif": "image/gif", ".tif": "image/tiff", ".tiff": "image/tiff",
}
CONVERTIBLE_IMAGE_EXTENSIONS = {".bmp", ".gif", ".tif", ".tiff"}
DIRECT_MIME = {
    ".pdf": "application/pdf",
    **{ext: mime for ext, mime in IMAGE_MIME.items() if ext not in CONVERTIBLE_IMAGE_EXTENSIONS},
    ".doc": "application/msword", ".xls": "application/vnd.ms-excel",
    ".ppt": "application/vnd.ms-powerpoint",
}
TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".html", ".htm", ".xml"}
SUPPORTED_EXTENSIONS = set(DIRECT_MIME) | CONVERTIBLE_IMAGE_EXTENSIONS | TEXT_EXTENSIONS | {
    ".docx", ".odt", ".xlsx", ".pptx", ".rtf", ".eml", ".zip",
}
MIME_TO_EXTENSION = {
    "application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png",
    "image/webp": ".webp", "image/heic": ".heic", "image/heif": ".heif",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/msword": ".doc",
    "application/vnd.oasis.opendocument.text": ".odt",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/vnd.ms-powerpoint": ".ppt",
    "image/bmp": ".bmp", "image/gif": ".gif", "image/tiff": ".tif",
    "text/plain": ".txt", "text/markdown": ".md", "text/csv": ".csv",
    "text/rtf": ".rtf", "text/html": ".html", "application/xhtml+xml": ".html",
    "text/xml": ".xml", "application/xml": ".xml", "application/json": ".json",
    "message/rfc822": ".eml", "application/zip": ".zip", "application/x-zip-compressed": ".zip",
    "application/rtf": ".rtf", "text/x-csv": ".csv", "image/pjpeg": ".jpg",
}
ALLOWED_MIME_BY_EXTENSION = {
    ".pdf": {"application/pdf"},
    ".jpg": {"image/jpeg", "image/pjpeg"}, ".jpeg": {"image/jpeg", "image/pjpeg"},
    ".png": {"image/png"}, ".webp": {"image/webp"}, ".bmp": {"image/bmp"},
    ".gif": {"image/gif"}, ".tif": {"image/tiff"}, ".tiff": {"image/tiff"},
    ".doc": {"application/msword"}, ".xls": {"application/vnd.ms-excel"},
    ".ppt": {"application/vnd.ms-powerpoint"},
    ".heic": {"image/heic"}, ".heif": {"image/heif"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/zip"},
    ".odt": {"application/vnd.oasis.opendocument.text", "application/zip"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/zip"},
    ".pptx": {"application/vnd.openxmlformats-officedocument.presentationml.presentation", "application/zip"},
    ".txt": {"text/plain"}, ".md": {"text/markdown", "text/plain"},
    ".csv": {"text/csv", "text/x-csv", "application/csv", "text/plain"},
    ".json": {"application/json", "text/json", "text/plain"},
    ".html": {"text/html", "application/xhtml+xml", "text/plain"},
    ".htm": {"text/html", "application/xhtml+xml", "text/plain"},
    ".xml": {"text/xml", "application/xml", "text/plain"},
    ".rtf": {"text/rtf", "application/rtf", "text/plain"},
    ".eml": {"message/rfc822", "text/plain"},
    ".zip": {"application/zip", "application/x-zip-compressed"},
}


def _validate_mime(extension: str, content_type: str | None) -> None:
    claimed = (content_type or "").split(";", 1)[0].strip().casefold()
    if not claimed or claimed == "application/octet-stream":
        return
    if claimed not in ALLOWED_MIME_BY_EXTENSION.get(extension, set()):
        raise UploadError("The file’s name and content type do not match. Re-save or rename the file correctly, then try again.", 415)


class UploadError(ValueError):
    """A supported-format, size, or readability problem with an uploaded file."""
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


class _VisibleHTML(HTMLParser):
    _BLOCK_TAGS = {"br", "p", "div", "li", "tr", "td", "th", "h1", "h2", "h3", "h4", "section", "article"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.casefold()
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        elif not self._skip_depth and tag in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        tag = tag.casefold()
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
        elif not self._skip_depth and tag in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip_depth:
            self.parts.append(data)


def _clean_text(value: str) -> str:
    value = value.replace("\x00", " ")
    value = "".join(ch if ch in "\n\r\t" or ord(ch) >= 32 else " " for ch in value)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n[ \t]+", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace")


def _safe_archive(data: bytes) -> zipfile.ZipFile:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        members = archive.infolist()
    except (zipfile.BadZipFile, OSError) as exc:
        raise UploadError("This Office/ZIP file is damaged or unreadable. Re-save it and try again.") from exc
    if len(members) > MAX_ARCHIVE_MEMBERS:
        archive.close()
        raise UploadError("This archive contains too many items to analyse safely.")
    total = 0
    for member in members:
        if member.flag_bits & 0x1:
            archive.close()
            raise UploadError("Password-protected Office/ZIP files are not supported. Remove the password or upload a redacted PDF.")
        total += member.file_size
        if total > MAX_UNPACKED_BYTES:
            archive.close()
            raise UploadError("This compressed file expands beyond the safe 50 MB processing limit.")
    return archive


def _xml_root(data: bytes) -> ET.Element:
    if len(data) > MAX_XML_BYTES:
        raise UploadError("The document’s text structure is too large to analyse safely.")
    try:
        return ET.fromstring(data, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except DefusedXmlException as exc:
        raise UploadError("This document contains unsupported XML declarations. Re-save it as PDF and try again.") from exc
    except ET.ParseError as exc:
        raise UploadError("The document’s text structure is damaged or unreadable.") from exc


def _limit_image_parts(parts: Iterable[tuple[bytes, str]]) -> tuple[list[tuple[bytes, str]], int]:
    kept: list[tuple[bytes, str]] = []
    total = 0
    omitted = 0
    for payload, mime in parts:
        if len(kept) >= MAX_EMBEDDED_IMAGES or len(payload) > MAX_EMBEDDED_IMAGE_BYTES or total + len(payload) > MAX_EMBEDDED_IMAGE_BYTES:
            omitted += 1
            continue
        kept.append((payload, mime))
        total += len(payload)
    return kept, omitted


def _archive_images(archive: zipfile.ZipFile, prefix: str) -> tuple[list[tuple[bytes, str]], list[str]]:
    images: list[tuple[bytes, str]] = []
    notes: list[str] = []
    total_bytes = 0
    for member in archive.infolist():
        if not member.filename.startswith(prefix) or member.is_dir():
            continue
        ext = PurePosixPath(member.filename).suffix.casefold()
        mime = IMAGE_MIME.get(ext)
        if not mime:
            continue
        if member.file_size > MAX_EMBEDDED_IMAGE_BYTES:
            notes.append("An embedded image exceeded the safe size limit and was not analysed.")
            continue
        try:
            payload = archive.read(member)
            if ext in CONVERTIBLE_IMAGE_EXTENSIONS:
                if not _signature_ok(ext, payload):
                    raise UploadError("Invalid embedded image signature.")
                parts, note = _to_gemini_images(payload, ext)
                if note:
                    notes.append(note)
            else:
                if not _signature_ok(ext, payload):
                    raise UploadError("Invalid embedded image signature.")
                if ext in {".jpg", ".jpeg", ".png", ".webp"}:
                    _validate_image_blob(payload, ext)
                parts = [(payload, mime)]
            for part in parts:
                if len(images) >= MAX_EMBEDDED_IMAGES or total_bytes + len(part[0]) > MAX_EMBEDDED_IMAGE_BYTES:
                    notes.append("Additional embedded images were omitted at the safe analysis limit.")
                    break
                images.append(part)
                total_bytes += len(part[0])
        except UploadError:
            notes.append("An embedded image could not be read and was not analysed.")
    return images, notes


def _docx_text(data: bytes) -> tuple[str, list[tuple[bytes, str]]]:
    archive = _safe_archive(data)
    try:
        try:
            document_xml = archive.read("word/document.xml")
        except KeyError as exc:
            raise UploadError("This is not a readable DOCX document. Re-save it as DOCX or PDF.") from exc
        root = _xml_root(document_xml)
        ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        paragraphs: list[str] = []
        for paragraph in root.iter(ns + "p"):
            parts: list[str] = []
            for node in paragraph.iter():
                if node.tag == ns + "t" and node.text:
                    parts.append(node.text)
                elif node.tag == ns + "tab":
                    parts.append("\t")
                elif node.tag == ns + "br":
                    parts.append("\n")
            if parts:
                paragraphs.append("".join(parts))
        images, notes = _archive_images(archive, "word/media/")
        text = _clean_text("\n".join(paragraphs))
        if notes:
            text += "\n" + " ".join(notes)
        return text, images
    finally:
        archive.close()


def _odt_text(data: bytes) -> tuple[str, list[tuple[bytes, str]]]:
    archive = _safe_archive(data)
    try:
        try:
            root = _xml_root(archive.read("content.xml"))
        except KeyError as exc:
            raise UploadError("This is not a readable ODT document. Re-save it as ODT or PDF.") from exc
        ns = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
        paragraphs = []
        for paragraph in root.iter():
            if paragraph.tag in {ns + "p", ns + "h"}:
                text = "".join(paragraph.itertext())
                if text.strip():
                    paragraphs.append(text)
        images, notes = _archive_images(archive, "Pictures/")
        text = _clean_text("\n".join(paragraphs))
        if notes:
            text += "\n" + " ".join(notes)
        return text, images
    finally:
        archive.close()


def _pptx_text(data: bytes) -> tuple[str, list[tuple[bytes, str]]]:
    archive = _safe_archive(data)
    try:
        slide_names = sorted(
            (name for name in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)),
            key=lambda name: int(re.search(r"slide(\d+)", name).group(1)),
        )
        paragraphs = []
        ns = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
        for slide_name in slide_names[:MAX_PPTX_SLIDES]:
            root = _xml_root(archive.read(slide_name))
            for paragraph in root.iter(ns + "p"):
                text = "".join(node.text or "" for node in paragraph.iter(ns + "t"))
                if text.strip():
                    paragraphs.append(text)
        images, notes = _archive_images(archive, "ppt/media/")
        text = _clean_text("\n".join(paragraphs))
        if len(slide_names) > MAX_PPTX_SLIDES:
            text += f"\n[Only the first {MAX_PPTX_SLIDES} of {len(slide_names)} slides were analysed.]"
        if notes:
            text += "\n" + " ".join(notes)
        if not text and not images:
            raise UploadError("No readable text or embedded image was found in this PPTX. Try exporting it as PDF.")
        return text, images
    except KeyError as exc:
        raise UploadError("This is not a readable PPTX presentation. Re-save it as PPTX or PDF.") from exc
    finally:
        archive.close()


def _xlsx_text(data: bytes) -> str:
    archive = _safe_archive(data)
    archive.close()
    try:
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True, keep_links=False)
    except Exception as exc:
        raise UploadError("This XLSX spreadsheet is damaged or unreadable. Re-save it and try again.") from exc
    lines: list[str] = []
    used_cells = 0
    try:
        worksheets = workbook.worksheets
        for worksheet in worksheets[:MAX_XLSX_SHEETS]:
            lines.append("Sheet: " + _clean_text(str(worksheet.title))[:100])
            for row_number, row in enumerate(worksheet.iter_rows(max_row=MAX_XLSX_ROWS, max_col=MAX_XLSX_COLUMNS, values_only=True), start=1):
                nonempty = []
                for column, value in enumerate(row, start=1):
                    if value is None:
                        continue
                    used_cells += 1
                    if used_cells > MAX_XLSX_CELLS:
                        lines.append("[Spreadsheet extraction stopped at the safe cell limit.]" )
                        return _clean_text("\n".join(lines))[:MAX_TEXT_CHARS]
                    text = value.isoformat() if hasattr(value, "isoformat") else str(value)
                    if text.strip():
                        nonempty.append(f"C{column}: {text[:500]}")
                if nonempty:
                    lines.append(f"Row {row_number}: " + " | ".join(nonempty))
            if worksheet.max_row and worksheet.max_row > MAX_XLSX_ROWS:
                lines.append(f"[Only the first {MAX_XLSX_ROWS} rows of sheet {worksheet.title!r} were analysed.]")
        if len(worksheets) > MAX_XLSX_SHEETS:
            lines.append(f"[Only the first {MAX_XLSX_SHEETS} of {len(worksheets)} sheets were analysed.]")
        return _clean_text("\n".join(lines))[:MAX_TEXT_CHARS]
    finally:
        workbook.close()


def _csv_text(data: bytes) -> str:
    decoded = _decode_text(data)
    rows = []
    try:
        for row_num, row in enumerate(csv.reader(io.StringIO(decoded), strict=False), start=1):
            rows.append(f"Row {row_num}: " + " | ".join(cell[:500] for cell in row[:100]))
            if row_num >= MAX_XLSX_ROWS:
                rows.append("[CSV extraction stopped at the safe row limit.]")
                break
    except csv.Error as exc:
        raise UploadError("This CSV file is malformed. Re-save it as CSV or PDF and try again.") from exc
    return _clean_text("\n".join(rows))[:MAX_TEXT_CHARS]


def _html_text(data: bytes) -> str:
    parser = _VisibleHTML()
    try:
        parser.feed(_decode_text(data))
    except Exception as exc:
        raise UploadError("This HTML file is malformed. Re-save it as PDF or plain text and try again.") from exc
    return _clean_text("".join(parser.parts))


def _xml_text(data: bytes) -> str:
    root = _xml_root(data)
    return _clean_text(" ".join(piece for piece in root.itertext() if piece and piece.strip()))


def _eml_text(data: bytes) -> tuple[str, list[tuple[bytes, str]], int]:
    try:
        message = BytesParser(policy=policy.default).parsebytes(data)
    except Exception as exc:
        raise UploadError("This email file is damaged or unreadable. Save the message as .eml and try again.") from exc
    text_parts = []
    images: list[tuple[bytes, str]] = []
    attachment_count = 0
    skipped_count = 0
    omitted_images = 0
    if message.get("subject"):
        text_parts.append("Subject: " + str(message.get("subject")))
    for part in message.walk():
        if part.is_multipart():
            continue
        filename = part.get_filename()
        if filename:
            attachment_count += 1
            if attachment_count > MAX_EML_ATTACHMENTS:
                skipped_count += 1
                continue
            payload = part.get_payload(decode=True) or b""
            try:
                attachment_text, attachment_images, _ = _extract_one(
                    str(filename), payload, part.get_content_type(), allow_zip=False
                )
                text_parts.append("Attached document content:\n" + attachment_text)
                images, omitted = _limit_image_parts(images + attachment_images)
                omitted_images += omitted
            except UploadError:
                skipped_count += 1
            continue
        if part.get_content_maintype() != "text":
            continue
        try:
            body = part.get_content()
        except Exception:
            body = _decode_text(part.get_payload(decode=True) or b"")
        if part.get_content_subtype() == "html":
            body = _html_text(str(body).encode("utf-8"))
        text_parts.append(str(body))
    if skipped_count:
        text_parts.append(f"[The email contains {skipped_count} attachment(s) that were unsupported, unreadable, or oversized and were not analysed. Upload them separately if they are relevant.]")
    if omitted_images:
        text_parts.append(f"[The email contains {omitted_images} additional image/document attachment part(s) omitted at the safe analysis limit.]")
    return _clean_text("\n".join(text_parts)), images, attachment_count


def resolve_extension(filename: str | None, content_type: str | None = None) -> str:
    ext = PurePosixPath((filename or "").replace("\\", "/")).suffix.casefold()
    if ext in SUPPORTED_EXTENSIONS:
        return ext
    mime = (content_type or "").split(";", 1)[0].strip().casefold()
    inferred = MIME_TO_EXTENSION.get(mime)
    if inferred:
        return inferred
    supported = "PDF, JPEG/PNG/WEBP/HEIC/HEIF/BMP/GIF/TIFF photos, DOC/DOCX/ODT, XLS/XLSX, PPT/PPTX, TXT/MD/CSV/JSON/HTML/XML/RTF, EML, or ZIP"
    raise UploadError(f"This file type is not supported yet. Upload {supported}; unsupported files are rejected instead of receiving a sample analysis.", 415)


def _signature_ok(extension: str, data: bytes) -> bool:
    if extension == ".pdf":
        return data.startswith(b"%PDF-")
    if extension in {".jpg", ".jpeg"}:
        return data.startswith(b"\xff\xd8\xff")
    if extension == ".png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if extension == ".webp":
        return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    if extension == ".bmp":
        return data.startswith(b"BM")
    if extension == ".gif":
        return data.startswith((b"GIF87a", b"GIF89a"))
    if extension in {".tif", ".tiff"}:
        return data.startswith((b"II*\x00", b"MM\x00*"))
    if extension in {".doc", ".xls", ".ppt"}:
        return data.startswith(bytes.fromhex("D0CF11E0A1B11AE1"))
    if extension in {".heic", ".heif"}:
        if len(data) < 12 or data[4:8] != b"ftyp":
            return False
        brands = data[8:40]
        return any(brand in brands for brand in (b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1"))
    return True


def _to_gemini_images(data: bytes, extension: str) -> tuple[list[tuple[bytes, str]], str]:
    images: list[tuple[bytes, str]] = []
    notes: list[str] = []
    total_bytes = 0
    try:
        with Image.open(io.BytesIO(data)) as source:
            frame_count = getattr(source, "n_frames", 1)
            frame_limit = min(frame_count, 8) if extension in {".tif", ".tiff"} else 1
            for frame_index in range(frame_limit):
                source.seek(frame_index)
                width, height = source.size
                if width <= 0 or height <= 0 or width * height > Image.MAX_IMAGE_PIXELS:
                    raise UploadError("This image has too many pixels to process safely. Resize it or export it as a smaller PDF.")
                frame = ImageOps.exif_transpose(source.copy())
                try:
                    mode = "RGBA" if "transparency" in frame.info or frame.mode in {"RGBA", "LA"} else "RGB"
                    normalized = frame.convert(mode)
                    try:
                        output = io.BytesIO()
                        normalized.save(output, format="PNG", optimize=True)
                        payload = output.getvalue()
                    finally:
                        normalized.close()
                finally:
                    frame.close()
                if len(payload) > MAX_EMBEDDED_IMAGE_BYTES or total_bytes + len(payload) > MAX_EMBEDDED_IMAGE_BYTES:
                    raise UploadError("This image or its converted pages exceed the safe combined processing limit. Try a smaller image.")
                images.append((payload, "image/png"))
                total_bytes += len(payload)
            if frame_count > frame_limit:
                notes.append(f"Only the first {frame_limit} page(s)/frame(s) of this multi-frame image were analysed.")
            elif extension == ".gif" and frame_count > 1:
                notes.append("Only the first frame of this animated GIF was analysed.")
    except UploadError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise UploadError("This image is damaged or has unsafe dimensions. Try a clearer, smaller JPEG or PNG.") from exc
    if not images:
        raise UploadError("No readable image frame was found. Try a clearer JPEG or PNG.")
    return images, " ".join(notes)


def _validate_image_blob(data: bytes, extension: str) -> None:
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.width * image.height > Image.MAX_IMAGE_PIXELS:
                raise UploadError("This image has too many pixels to process safely. Resize it or export it as a smaller PDF.")
            expected = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP"}.get(extension)
            if expected and image.format != expected:
                raise UploadError("The file extension does not match the image contents. Re-save it as the correct format and try again.", 415)
            image.verify()
    except UploadError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise UploadError("This image is damaged or has unsafe dimensions. Try a clearer, smaller JPEG or PNG.") from exc


def _extract_one(filename: str, data: bytes, content_type: str | None = None, *, allow_zip: bool = True) -> tuple[str, list[tuple[bytes, str]], list[str]]:
    if not data:
        raise UploadError("The uploaded file is empty.", 400)
    if len(data) > MAX_FILE_BYTES:
        raise UploadError("File too large. Maximum size is 20 MB.", 413)
    extension = resolve_extension(filename, content_type)
    _validate_mime(extension, content_type)
    safe_name = PurePosixPath((filename or "uploaded file").replace("\\", "/")).name[:160]
    if extension in CONVERTIBLE_IMAGE_EXTENSIONS:
        if not _signature_ok(extension, data):
            raise UploadError(f"The uploaded file does not appear to be a valid {extension.lstrip('.').upper()} image.")
        images, note = _to_gemini_images(data, extension)
        text = "Uploaded photo converted to a safe PNG for visual analysis."
        if note:
            text += " " + note
        return text, images, [safe_name]
    if extension in DIRECT_MIME:
        if not _signature_ok(extension, data):
            raise UploadError(f"The uploaded file does not appear to be a valid {extension.lstrip('.').upper()} file. Re-save it and try again.")
        if extension in {".jpg", ".jpeg", ".png", ".webp"}:
            _validate_image_blob(data, extension)
            if len(data) > MAX_DIRECT_IMAGE_BYTES:
                images, note = _to_gemini_images(data, extension)
                text = "Large image converted to a safe PNG for visual analysis."
                if note:
                    text += " " + note
                return text, images, [safe_name]
        if extension in {".heic", ".heif"} and len(data) > MAX_DIRECT_IMAGE_BYTES:
            raise UploadError("HEIC/HEIF photos larger than 12 MB cannot be sent safely inline. Convert to a smaller JPEG/PNG or PDF.", 413)
        return "Uploaded document content (original filename omitted for privacy).", [(data, DIRECT_MIME[extension])], [safe_name]
    if extension in TEXT_EXTENSIONS:
        if extension in {".html", ".htm"}:
            text = _html_text(data)
        elif extension == ".xml":
            text = _xml_text(data)
        elif extension == ".json":
            decoded = _decode_text(data)
            try:
                text = json.dumps(json.loads(decoded), ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                text = decoded
        elif extension == ".csv":
            text = _csv_text(data)
        else:
            text = _decode_text(data)
        return "Uploaded text content extracted from a user-supplied file:\n" + text, [], [safe_name]
    if extension == ".rtf":
        try:
            text = rtf_to_text(_decode_text(data))
        except Exception as exc:
            raise UploadError("This RTF document is damaged or unreadable. Re-save it as PDF or DOCX and try again.") from exc
        return "Uploaded text content extracted from a user-supplied file:\n" + text, [], [safe_name]
    if extension == ".docx":
        text, images = _docx_text(data)
        if not text and not images:
            raise UploadError("No readable text or embedded image was found in this DOCX. Try exporting it as PDF.")
        return f"Extracted text from user-supplied DOCX:\n{text}", images, [safe_name]
    if extension == ".odt":
        text, images = _odt_text(data)
        if not text and not images:
            raise UploadError("No readable text or embedded image was found in this ODT. Try exporting it as PDF.")
        return f"Extracted text from user-supplied ODT:\n{text}", images, [safe_name]
    if extension == ".pptx":
        text, images = _pptx_text(data)
        return f"Extracted slide text from user-supplied PPTX:\n{text}", images, [safe_name]
    if extension == ".xlsx":
        text = _xlsx_text(data)
        if not text:
            raise UploadError("No readable cell values were found in this XLSX. Try exporting the relevant sheet as CSV.")
        return f"Extracted cell values from user-supplied spreadsheet:\n{text}", [], [safe_name]
    if extension == ".eml":
        if not allow_zip:
            raise UploadError("Nested email files are not analysed automatically. Upload the relevant message separately.")
        text, images, _ = _eml_text(data)
        if not text:
            raise UploadError("No readable message body was found in this EML email.")
        return f"Extracted email content from user-supplied file:\n{text}", images, [safe_name]
    if extension == ".zip":
        if not allow_zip:
            raise UploadError("Nested ZIP files are not supported. Upload each supported document separately.")
        archive = _safe_archive(data)
        try:
            members = [m for m in archive.infolist() if not m.is_dir() and not m.filename.startswith("__MACOSX/")]
            results = []
            images: list[tuple[bytes, str]] = []
            omitted_images = 0
            skipped_count = 0
            for member in members:
                if len(results) >= MAX_ZIP_DOCUMENTS:
                    skipped_count += 1
                    continue
                path = PurePosixPath(member.filename.replace("\\", "/"))
                if path.is_absolute() or ".." in path.parts or member.file_size > MAX_FILE_BYTES:
                    skipped_count += 1
                    continue
                ext = path.suffix.casefold()
                if ext not in SUPPORTED_EXTENSIONS or ext == ".zip":
                    skipped_count += 1
                    continue
                payload = archive.read(member)
                try:
                    text_part, image_parts, names = _extract_one(path.name, payload, allow_zip=False)
                except UploadError:
                    skipped_count += 1
                    continue
                results.append((text_part, names))
                images, omitted = _limit_image_parts(images + image_parts)
                omitted_images += omitted
            if not results:
                raise UploadError("No supported, readable files were found in this ZIP. Use PDF, photos, DOCX, ODT, PPTX, XLSX, TXT, CSV, RTF, EML, or JSON files.")
            text = "\n\n".join(r[0] for r in results)
            if skipped_count:
                text += f"\n\n[Notice: {skipped_count} archive item(s) were not analysed because they were unsupported, oversized, or unreadable. Upload any relevant item separately.]"
            if omitted_images:
                text += f"\n\n[Notice: {omitted_images} image/document part(s) were omitted at the safe analysis limit. Upload the relevant file separately if needed.]"
            names = [name for r in results for name in r[1]]
            return f"Extracted content from a user-supplied ZIP containing {len(names)} readable supported document(s):\n{text}", images, names
        finally:
            archive.close()
    raise UploadError("This file format is not supported.")


def prepare_upload(filename: str | None, content_type: str | None, data: bytes) -> tuple[str, list[tuple[bytes, str]], list[str]]:
    """Return extracted text, binary image/PDF parts, and included original names."""
    return _extract_one(filename or "uploaded-file", data, content_type)


def truncate_extracted_text(text: str) -> str:
    text = _clean_text(text)
    if len(text) <= MAX_TEXT_CHARS:
        return text
    return text[:MAX_TEXT_CHARS] + "\n[Further extracted text omitted at the safe 30,000-character limit.]"
