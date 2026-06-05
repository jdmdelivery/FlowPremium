"""Admin episode form: language checkboxes and per-language uploads."""

from __future__ import annotations

import json

from flask import Request

from modules.streaming.models import Episode
from modules.streaming.services.episode_media import (
    set_extra_audio_key,
    set_subtitle_key,
    sync_episode_track_metadata,
)
from modules.streaming.services.languages import parse_admin_language_list
from modules.streaming.services.languages import LANG_BY_CODE, normalize_lang_code
from modules.streaming.upload import (
    _delete_media_key,
    delete_episode_hls,
    delete_episode_primary_video,
    delete_episode_subtitle_lang,
    delete_episode_subtitles,
    delete_episode_thumbnail,
    delete_episode_video,
    save_episode_audio_track,
    save_episode_hls,
    save_episode_thumbnail,
    save_episode_video,
    save_subtitle_file,
    save_subtitle_vtt,
)


def _checked_audio_languages(form) -> list[str]:
    return parse_admin_language_list(form.getlist("audio_languages"))


def _checked_subtitle_languages(form) -> list[str]:
    return parse_admin_language_list(form.getlist("subtitle_languages"))


def apply_episode_form_uploads(
    episode: Episode,
    request: Request,
    series_id: int,
    *,
    new_video_uploaded: bool,
) -> list[str]:
    """Process file uploads and language settings. Returns flash messages."""
    messages: list[str] = []
    form = request.form

    episode.audio_languages = json.dumps(_checked_audio_languages(form), ensure_ascii=False)
    episode.subtitle_languages = json.dumps(
        _checked_subtitle_languages(form), ensure_ascii=False
    )

    video = request.files.get("video")
    if video and video.filename:
        from utils.video import warn_if_mp4_not_faststart

        warn = warn_if_mp4_not_faststart(video)
        if warn:
            messages.append(("warning", warn))
        if episode.video_url_r2:
            delete_episode_primary_video(episode)
            delete_episode_subtitles(episode)
            episode.subtitle_url = None
            episode.subtitle_url_es = None
            episode.subtitle_url_en = None
            episode.subtitle_langs = None
            episode.subtitle_generated_at = None
            episode.subtitle_status = "none"
        episode.video_url_r2 = save_episode_video(video, series_id=series_id, lang="es")
        langs = _checked_audio_languages(form)
        if LANG_BY_CODE["es"]["name"] not in langs:
            langs = [LANG_BY_CODE["es"]["name"]] + langs
            episode.audio_languages = json.dumps(langs, ensure_ascii=False)

    video_en = request.files.get("video_en")
    if video_en and video_en.filename:
        from utils.video import warn_if_mp4_not_faststart

        warn = warn_if_mp4_not_faststart(video_en)
        if warn:
            messages.append(("warning", warn))
        if episode.video_url_r2_en:
            _delete_media_key(episode.video_url_r2_en)
        episode.video_url_r2_en = save_episode_video(video_en, series_id=series_id, lang="en")

    upload_audio = request.files.get("upload_audio")
    audio_lang = normalize_lang_code(form.get("upload_audio_lang"))
    if upload_audio and upload_audio.filename and audio_lang:
        if audio_lang == "es":
            if episode.video_url_r2:
                delete_episode_primary_video(episode)
            episode.video_url_r2 = save_episode_video(upload_audio, series_id=series_id, lang="es")
        elif audio_lang == "en":
            if episode.video_url_r2_en:
                _delete_media_key(episode.video_url_r2_en)
            episode.video_url_r2_en = save_episode_video(upload_audio, series_id=series_id, lang="en")
        else:
            key = save_episode_audio_track(
                upload_audio, series_id=series_id, episode_id=episode.id, lang=audio_lang
            )
            set_extra_audio_key(episode, audio_lang, key)
        messages.append(("success", f"Audio {LANG_BY_CODE[audio_lang]['name']} guardado."))

    upload_sub = request.files.get("upload_subtitle")
    sub_lang = normalize_lang_code(form.get("upload_subtitle_lang"))
    if upload_sub and upload_sub.filename and sub_lang:
        key, vtt_content = save_subtitle_file(
            upload_sub, series_id=series_id, episode_id=episode.id, lang=sub_lang
        )
        set_subtitle_key(episode, sub_lang, key)
        if sub_lang == "es":
            episode.subtitle_status = "ready"
        messages.append(("success", f"Subtítulo {LANG_BY_CODE[sub_lang]['name']} guardado."))

    subtitle_en = request.files.get("subtitle_en")
    if subtitle_en and subtitle_en.filename:
        content = subtitle_en.read().decode("utf-8-sig")
        if not content.strip().upper().startswith("WEBVTT"):
            raise ValueError("El archivo debe ser WebVTT (.vtt)")
        delete_episode_subtitle_lang(episode, "en")
        if not episode.id:
            raise ValueError("Guarda el episodio antes de subir subtítulos")
        key = save_subtitle_vtt(content, series_id, episode.id, lang="en")
        set_subtitle_key(episode, "en", key)
        messages.append(("success", "Subtítulo inglés (VTT) guardado."))

    hls_file = request.files.get("hls_master")
    if hls_file and hls_file.filename:
        if episode.hls_url_r2:
            delete_episode_hls(episode)
        episode.hls_url_r2 = save_episode_hls(hls_file, series_id, episode.id)
        episode.hls_master_url = episode.hls_url_r2

    thumb = request.files.get("thumbnail")
    if thumb and thumb.filename:
        if episode.thumbnail_url:
            delete_episode_thumbnail(episode)
        episode.thumbnail_url = save_episode_thumbnail(thumb, series_id=series_id)

    sync_episode_track_metadata(episode)
    return messages
