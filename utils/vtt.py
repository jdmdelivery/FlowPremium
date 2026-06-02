"""WebVTT parse, serialize, and translate while preserving timestamps."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_TIMESTAMP_LINE = re.compile(
    r"^(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})"
)


@dataclass
class VttCue:
    start: str
    end: str
    text: str


def parse_vtt(content: str) -> list[VttCue]:
    """Parse WebVTT into cues (timestamps preserved as strings)."""
    lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cues: list[VttCue] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line or line == "WEBVTT" or line.startswith("NOTE") or line.isdigit():
            continue
        match = _TIMESTAMP_LINE.match(line)
        if not match:
            continue
        start, end = match.group(1), match.group(2)
        text_lines: list[str] = []
        while i < len(lines) and lines[i].strip():
            text_lines.append(lines[i].strip())
            i += 1
        text = "\n".join(text_lines).strip()
        if text:
            cues.append(VttCue(start=start, end=end, text=text))
    return cues


def cues_to_vtt(cues: list[VttCue]) -> str:
    lines = ["WEBVTT", ""]
    for cue in cues:
        lines.append(f"{cue.start} --> {cue.end}")
        lines.append(cue.text)
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _batch_translate_texts(
    texts: list[str],
    target_lang: str,
    source_lang: str,
) -> list[str]:
    if not texts:
        return []

    deepl_key = None
    try:
        from flask import current_app

        deepl_key = (current_app.config.get("DEEPL_API_KEY") or "").strip()
        provider = (current_app.config.get("SUBTITLE_TRANSLATE_PROVIDER") or "auto").lower()
    except RuntimeError:
        provider = "auto"
        deepl_key = ""

    target = target_lang.lower()[:2]
    source = source_lang.lower()[:2]
    if target == source:
        return texts

    if deepl_key and provider in ("auto", "deepl"):
        try:
            return _translate_deepl(texts, source, target, deepl_key)
        except Exception:
            logger.exception("DeepL translation failed, falling back")

    return _translate_google(texts, source, target)


def _translate_google(texts: list[str], source: str, target: str) -> list[str]:
    from deep_translator import GoogleTranslator

    translator = GoogleTranslator(source=source, target=target)
    out: list[str] = []
    batch_size = 40
    for i in range(0, len(texts), batch_size):
        chunk = texts[i : i + batch_size]
        try:
            translated = translator.translate_batch(chunk)
            out.extend(translated)
        except Exception:
            for line in chunk:
                try:
                    out.append(translator.translate(line))
                except Exception:
                    out.append(line)
    return out


def _translate_deepl(texts: list[str], source: str, target: str, api_key: str) -> list[str]:
    import deepl

    translator = deepl.Translator(api_key)
    source_code = "ES" if source.startswith("es") else source.upper()
    target_code = "EN-US" if target.startswith("en") else target.upper()
    out: list[str] = []
    for text in texts:
        result = translator.translate_text(text, source_lang=source_code, target_lang=target_code)
        out.append(result.text)
    return out


def translate_vtt(content: str, target_lang: str, source_lang: str = "es") -> str:
    """Translate cue text only; timestamps unchanged."""
    cues = parse_vtt(content)
    if not cues:
        return content
    translated = _batch_translate_texts([c.text for c in cues], target_lang, source_lang)
    for cue, new_text in zip(cues, translated):
        cue.text = new_text
    return cues_to_vtt(cues)
