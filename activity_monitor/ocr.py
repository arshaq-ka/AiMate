from PIL import Image


class OcrUnavailableError(RuntimeError):
    """Raised when the optional local Tesseract engine is unavailable."""


def extract_text(image: Image.Image) -> str:
    try:
        import pytesseract

        return pytesseract.image_to_string(image).strip()
    except ImportError as exc:
        raise OcrUnavailableError(
            "OCR needs the optional pytesseract package and a local Tesseract "
            "OCR installation. Install Tesseract locally to enable OCR."
        ) from exc
    except pytesseract.TesseractNotFoundError as exc:
        raise OcrUnavailableError(
            "Tesseract OCR was not found. Install the Tesseract OCR application "
            "locally; screenshots remain disabled until OCR is available."
        ) from exc
