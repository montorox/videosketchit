#!/usr/bin/env python3
"""Create a strict audio-backed timeline for dynamic infographic elements.

No duration-by-character or even-spacing fallback is allowed here. Every Cue
must contain an exact source anchor and enough Whisper token matches to obtain
an acoustic start/end timestamp.
"""
from __future__ import annotations

import difflib
import math
import re
from copy import deepcopy
from typing import Any

from opencc import OpenCC


GLOBAL_SOURCE_COVERAGE_MIN = 0.72
ANCHOR_COVERAGE_MIN = 0.65
ANCHOR_CONFIDENCE_MIN = 0.20
T2S = OpenCC("t2s")
DIGIT_SPOKEN_FORM = str.maketrans("0123456789", "零一二三四五六七八九")


def _units(copy: str) -> list[str]:
    return [value.strip() for value in re.findall(r"[^。！？!?；;\n]+[。！？!?；;]?", copy) if value.strip()]


def _phrases(copy: str) -> list[str]:
    """Split narration before content planning, preserving book titles as one phrase."""
    return [
        value.strip()
        for value in re.findall(r"《[^》]+》|[^，,。！？!?；;：:\n]+[，,。！？!?；;：:]?", copy)
        if _normalized(value)
    ]


def _normalized(text: str) -> str:
    simplified = T2S.convert(str(text)).translate(DIGIT_SPOKEN_FORM)
    return "".join(character.lower() for character in simplified if character.isalnum())


def _caption_stream(payload: dict[str, Any]) -> tuple[str, list[int], list[dict[str, Any]]]:
    captions = payload.get("captions")
    if not isinstance(captions, list) or not captions:
        raise RuntimeError("语音对齐结果不包含 token 时间戳")
    normalized_text: list[str] = []
    character_tokens: list[int] = []
    cleaned: list[dict[str, Any]] = []
    for raw in captions:
        if not isinstance(raw, dict):
            continue
        token_text = _normalized(str(raw.get("text") or ""))
        if not token_text:
            continue
        start_ms = int(round(float(raw.get("startMs", 0))))
        end_ms = int(round(float(raw.get("endMs", start_ms))))
        if end_ms < start_ms:
            continue
        confidence = float(raw.get("confidence", 0.0) or 0.0)
        token_index = len(cleaned)
        cleaned.append({"text": token_text, "start_ms": start_ms, "end_ms": end_ms, "confidence": confidence})
        normalized_text.extend(token_text)
        character_tokens.extend([token_index] * len(token_text))
    if not cleaned:
        raise RuntimeError("语音对齐结果没有可用的中文或字母数字 token")
    return "".join(normalized_text), character_tokens, cleaned


def _audio_activity_window(payload: dict[str, Any], lower_ms: int, upper_ms: int) -> tuple[int, int] | None:
    """Return real non-silent audio bounded by already anchored neighbours."""
    raw_segments = payload.get("speechSegments")
    if not isinstance(raw_segments, list) or upper_ms <= lower_ms:
        return None
    overlaps: list[tuple[int, int]] = []
    for raw in raw_segments:
        if not isinstance(raw, dict):
            continue
        raw_start_ms = int(round(float(raw.get("startMs", 0))))
        raw_end_ms = int(round(float(raw.get("endMs", raw_start_ms))))
        # A speech island crossing an anchored boundary cannot be assigned to
        # either side without estimating. Only use islands fully enclosed by
        # the neighbouring acoustic anchors.
        if raw_start_ms < lower_ms or raw_end_ms > upper_ms:
            continue
        start_ms = raw_start_ms
        end_ms = raw_end_ms
        if end_ms - start_ms >= 45:
            overlaps.append((start_ms, end_ms))
    if not overlaps or sum(end - start for start, end in overlaps) < 60:
        return None
    return overlaps[0][0], overlaps[-1][1]


def _source_to_token_map(source: str, recognized: str, recognized_character_tokens: list[int]) -> tuple[dict[int, int], float]:
    matcher = difflib.SequenceMatcher(a=source, b=recognized, autojunk=False)
    mapping: dict[int, int] = {}
    matched = 0
    for block in matcher.get_matching_blocks():
        if not block.size:
            continue
        for offset in range(block.size):
            source_index = block.a + offset
            recognized_index = block.b + offset
            mapping[source_index] = recognized_character_tokens[recognized_index]
            matched += 1
    return mapping, matched / max(1, len(source))


def _align_phrases_to_caption_groups(
    phrase_texts: list[str],
    captions: list[dict[str, Any]],
    max_group_size: int | None = None,
) -> list[list[int]]:
    """Monotonically bind every source phrase to real adjacent ASR boundaries.

    Whisper word-boundary chunks are usually close to clauses, but a source
    phrase may span several chunks. Dynamic programming preserves narration
    order and lets a locally misheard phrase inherit the acoustic chunk between
    two strong neighbours; no duration interpolation is involved.
    """
    sources = [_normalized(value) for value in phrase_texts]
    recognized = [str(value["text"]) for value in captions]
    phrase_count = len(sources)
    caption_count = len(recognized)
    max_group_size = max_group_size or max(4, max((len(value) for value in sources), default=0))
    if phrase_count == 0 or caption_count < phrase_count or caption_count > phrase_count * max_group_size:
        raise RuntimeError("短语数量与语音边界数量无法建立逐段对应关系")

    negative_infinity = float("-inf")
    scores = [[negative_infinity] * (caption_count + 1) for _ in range(phrase_count + 1)]
    choices = [[0] * (caption_count + 1) for _ in range(phrase_count + 1)]
    scores[0][0] = 0.0
    for phrase_index in range(1, phrase_count + 1):
        minimum_caption_count = phrase_index
        maximum_caption_count = min(caption_count, phrase_index * max_group_size)
        remaining_phrases = phrase_count - phrase_index
        for caption_end in range(minimum_caption_count, maximum_caption_count + 1):
            if caption_count - caption_end < remaining_phrases:
                continue
            for group_size in range(1, min(max_group_size, caption_end) + 1):
                caption_start = caption_end - group_size
                previous = scores[phrase_index - 1][caption_start]
                if previous == negative_infinity:
                    continue
                candidate_text = "".join(recognized[caption_start:caption_end])
                similarity = difflib.SequenceMatcher(
                    a=sources[phrase_index - 1],
                    b=candidate_text,
                    autojunk=False,
                ).ratio()
                length_balance = min(len(sources[phrase_index - 1]), len(candidate_text)) / max(
                    1, max(len(sources[phrase_index - 1]), len(candidate_text))
                )
                candidate_score = previous + similarity + (0.12 * length_balance)
                if candidate_score > scores[phrase_index][caption_end]:
                    scores[phrase_index][caption_end] = candidate_score
                    choices[phrase_index][caption_end] = group_size

    if choices[phrase_count][caption_count] == 0:
        raise RuntimeError("无法按旁白顺序把短语绑定到真实语音边界")
    groups: list[list[int]] = []
    caption_end = caption_count
    for phrase_index in range(phrase_count, 0, -1):
        group_size = choices[phrase_index][caption_end]
        caption_start = caption_end - group_size
        groups.append(list(range(caption_start, caption_end)))
        caption_end = caption_start
    groups.reverse()
    return groups


def build_phrase_timeline(
    copy: str,
    alignment_payload: dict[str, Any],
    audio_duration_ms: int,
    fps: int = 30,
) -> dict[str, Any]:
    """Build the complete phrase-to-acoustic-time JSON before slide planning."""
    source = _normalized(copy)
    if not source:
        raise RuntimeError("文案没有可对齐的有效字符")
    recognized, recognized_character_tokens, tokens = _caption_stream(alignment_payload)
    source_mapping, source_coverage = _source_to_token_map(source, recognized, recognized_character_tokens)
    if source_coverage < GLOBAL_SOURCE_COVERAGE_MIN:
        raise RuntimeError(
            f"整篇旁白与原文匹配覆盖率 {source_coverage:.0%}，低于 {GLOBAL_SOURCE_COVERAGE_MIN:.0%}；禁止生成估算短语时间"
        )

    phrase_texts = _phrases(copy)
    phrase_ranges: list[tuple[int, int]] = []
    source_cursor = 0
    for text in phrase_texts:
        normalized = _normalized(text)
        source_start = source.find(normalized, source_cursor)
        if source_start < 0:
            raise RuntimeError(f"短语无法按原文顺序定位：{text}")
        source_end = source_start + len(normalized)
        phrase_ranges.append((source_start, source_end))
        source_cursor = source_end
    caption_groups = _align_phrases_to_caption_groups(phrase_texts, tokens)
    group_similarities = [
        difflib.SequenceMatcher(
            a=_normalized(text),
            b="".join(str(tokens[index]["text"]) for index in group),
            autojunk=False,
        ).ratio()
        for text, group in zip(phrase_texts, caption_groups)
    ]
    phrases: list[dict[str, Any]] = []
    for order, (text, boundary_token_indexes) in enumerate(zip(phrase_texts, caption_groups), 1):
        normalized = _normalized(text)
        source_start, source_end = phrase_ranges[order - 1]
        matched_positions = [position for position in range(source_start, source_end) if position in source_mapping]
        coverage = len(matched_positions) / max(1, len(normalized))
        mapped_token_indexes = sorted({source_mapping[position] for position in matched_positions})
        boundary_text = "".join(str(tokens[index]["text"]) for index in boundary_token_indexes)
        boundary_similarity = group_similarities[order - 1]
        neighbour_similarities = [
            group_similarities[index]
            for index in (order - 2, order)
            if 0 <= index < len(group_similarities)
        ]
        context_is_anchored = bool(neighbour_similarities) and min(neighbour_similarities) >= 0.65
        if coverage >= 0.55 and mapped_token_indexes:
            token_indexes = mapped_token_indexes
            boundary_source = "character-match"
            start_ms = min(int(tokens[index]["start_ms"]) for index in token_indexes)
            end_ms = max(int(tokens[index]["end_ms"]) for index in token_indexes)
            confidence = sum(float(tokens[index]["confidence"]) for index in token_indexes) / len(token_indexes)
        elif boundary_similarity >= 0.30 and context_is_anchored:
            token_indexes = boundary_token_indexes
            boundary_source = "neighboring-word-boundary"
            start_ms = min(int(tokens[index]["start_ms"]) for index in token_indexes)
            end_ms = max(int(tokens[index]["end_ms"]) for index in token_indexes)
            confidence = sum(float(tokens[index]["confidence"]) for index in token_indexes) / len(token_indexes)
        else:
            previous_end = int(phrases[-1]["spoken_end_ms"]) if phrases else 0
            next_start: int | None = None
            for later_start, later_end in phrase_ranges[order:]:
                later_tokens = sorted({
                    source_mapping[position]
                    for position in range(later_start, later_end)
                    if position in source_mapping
                })
                if later_tokens:
                    next_start = min(int(tokens[index]["start_ms"]) for index in later_tokens)
                    break
            is_first = order == 1
            is_last = order == len(phrase_texts)
            has_required_anchors = (is_first and next_start is not None) or (is_last and bool(phrases)) or (
                not is_first and not is_last and bool(phrases) and next_start is not None
            )
            upper_ms = next_start if next_start is not None else audio_duration_ms
            activity = _audio_activity_window(alignment_payload, previous_end, upper_ms) if has_required_anchors else None
            if activity is None:
                raise RuntimeError(
                    f"短语“{text}”没有足够的文字匹配，也没有可由相邻锚点确定的真实语音活动"
                )
            start_ms, end_ms = activity
            confidence = 0.0
            boundary_source = "audio-activity-edge" if is_first or is_last else "audio-activity-between-anchors"
            boundary_text = ""
        start_frame = math.ceil(start_ms * fps / 1000)
        end_frame = max(start_frame + 1, math.ceil(end_ms * fps / 1000))
        phrases.append({
            "id": f"p{order:03d}",
            "order": order,
            "text": text,
            "normalized_text": normalized,
            "source_start": source_start,
            "source_end": source_end,
            "spoken_start_ms": start_ms,
            "spoken_end_ms": end_ms,
            "start_frame": start_frame,
            "end_frame": end_frame,
            "alignment_coverage": round(coverage, 4),
            "alignment_confidence": round(confidence, 4),
            "boundary_source": boundary_source,
            "boundary_similarity": round(boundary_similarity, 4),
            "neighbor_anchor_similarity": round(min(neighbour_similarities), 4) if neighbour_similarities else None,
            "recognized_boundary_text": boundary_text,
        })
    if not phrases:
        raise RuntimeError("文案没有生成任何短语时间段")
    return {
        "schema_version": 2,
        "timing_source": "whisper.cpp-word-boundary-dtw-audio-v2",
        "estimated_fallback_used": False,
        "fps": fps,
        "audio_duration_ms": audio_duration_ms,
        "source_coverage": round(source_coverage, 4),
        "phrases": phrases,
    }


def build_deck_timeline(
    copy: str,
    slides: list[dict[str, Any]],
    phrase_timeline: dict[str, Any],
    audio_duration_ms: int,
    fps: int = 30,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Attach slide elements to precomputed phrase times without re-estimating."""
    phrases = phrase_timeline.get("phrases")
    if not isinstance(phrases, list) or not phrases:
        raise RuntimeError("完整短语时间表为空，禁止制作 PPT")
    if phrase_timeline.get("estimated_fallback_used") is not False:
        raise RuntimeError("短语时间表使用了估算时间，禁止制作 PPT")
    phrase_by_id = {str(phrase["id"]): phrase for phrase in phrases if isinstance(phrase, dict) and phrase.get("id")}
    phrase_ids = [str(phrase["id"]) for phrase in phrases]
    phrase_order = {phrase_id: index for index, phrase_id in enumerate(phrase_ids)}
    pages = deepcopy(slides)
    used_ids: list[str] = []
    for page_index, page in enumerate(pages, 1):
        current_ids = [str(value) for value in page.get("source_phrase_ids") or []]
        if not current_ids or any(value not in phrase_by_id for value in current_ids):
            raise RuntimeError(f"第 {page_index} 页引用了不存在的短语编号")
        positions = [phrase_order[value] for value in current_ids]
        if positions != list(range(positions[0], positions[-1] + 1)):
            raise RuntimeError(f"第 {page_index} 页必须引用连续短语")
        used_ids.extend(current_ids)
    if used_ids != phrase_ids:
        raise RuntimeError("PPT 页面没有按顺序完整覆盖短语时间表")

    page_start_ms = [0]
    page_start_ms.extend(int(phrase_by_id[str(page["source_phrase_ids"][0])]["spoken_start_ms"]) for page in pages[1:])
    page_end_ms = page_start_ms[1:] + [audio_duration_ms]
    total_frames = max(1, math.ceil(audio_duration_ms * fps / 1000))
    previous_chapter = ""
    seen_series: set[str] = set()
    report_pages: list[dict[str, Any]] = []

    for page_index, (page, start_ms, end_ms) in enumerate(zip(pages, page_start_ms, page_end_ms), 1):
        current_ids = [str(value) for value in page["source_phrase_ids"]]
        current_set = set(current_ids)
        if end_ms <= start_ms:
            raise RuntimeError(f"第 {page_index} 页真实语音时段无效")
        nodes = [str(value) for value in page.get("nodes") or []]
        entries: list[tuple[str, str]] = [
            ("page-title", str(page.get("page_title_trigger_phrase_id") or current_ids[0])),
            ("illustration", str(page.get("illustration_trigger_phrase_id") or current_ids[0])),
        ]
        key_items = page.get("key_items") or []
        for node_index, item in enumerate(key_items):
            trigger = str(item.get("trigger_phrase_id") or current_ids[0]) if isinstance(item, dict) else current_ids[0]
            entries.append((f"node-{node_index + 1}", trigger))
        if str(page.get("conclusion") or "").strip():
            entries.append(("conclusion", str(page.get("conclusion_trigger_phrase_id") or current_ids[-1])))
        invalid_triggers = sorted({trigger for _element_id, trigger in entries if trigger not in current_set})
        if invalid_triggers:
            raise RuntimeError(f"第 {page_index} 页元素引用了本页以外的短语：{', '.join(invalid_triggers)}")

        grouped: dict[str, list[str]] = {}
        for element_id, trigger in entries:
            grouped.setdefault(trigger, []).append(element_id)
        timed_cues: list[dict[str, Any]] = []
        ordered_triggers = sorted(grouped, key=lambda value: phrase_order[value])
        for cue_index, trigger in enumerate(ordered_triggers, 1):
            phrase = phrase_by_id[trigger]
            enter_ids = grouped[trigger]
            focus_id = next((value for value in enter_ids if value.startswith("node-")), enter_ids[0])
            timed_cues.append({
                "id": f"page-{page_index}-cue-{cue_index}",
                "phrase_id": trigger,
                "anchor_text": str(phrase["text"]),
                "spoken_start_ms": int(phrase["spoken_start_ms"]),
                "spoken_end_ms": int(phrase["spoken_end_ms"]),
                "start_frame": math.ceil(int(phrase["spoken_start_ms"]) * fps / 1000),
                "end_frame": 0,
                "enter_ids": enter_ids,
                "focus_id": focus_id,
                "alignment_coverage": float(phrase["alignment_coverage"]),
                "alignment_confidence": float(phrase["alignment_confidence"]),
            })

        page_start_frame = math.floor(start_ms * fps / 1000)
        page_end_frame = total_frames if page_index == len(pages) else math.floor(end_ms * fps / 1000)
        page_end_frame = max(page_start_frame + 1, page_end_frame)
        for cue_index, cue in enumerate(timed_cues):
            next_frame = timed_cues[cue_index + 1]["start_frame"] if cue_index + 1 < len(timed_cues) else page_end_frame
            cue["end_frame"] = max(int(cue["start_frame"]) + 1, int(next_frame))

        series_title = str(page.get("series_title") or "动态知识解说")
        chapter_title = str(page.get("chapter_title") or page.get("page_title") or "本章要点")
        page["text"] = "".join(str(phrase_by_id[value]["text"]) for value in current_ids)
        page["start_ms"] = start_ms
        page["end_ms"] = end_ms
        page["duration_ms"] = end_ms - start_ms
        page["start_frame"] = page_start_frame
        page["end_frame"] = page_end_frame
        page["timed_cues"] = timed_cues
        page["subtitle_cues"] = [{
            "text": str(phrase_by_id[value]["text"]),
            "start_ms": int(phrase_by_id[value]["spoken_start_ms"]),
            "end_ms": int(phrase_by_id[value]["spoken_end_ms"]),
            "alignment_coverage": float(phrase_by_id[value]["alignment_coverage"]),
        } for value in current_ids]
        page["series_persistent"] = series_title in seen_series
        page["chapter_persistent"] = chapter_title == previous_chapter
        page["_plan_mode"] = "narrated_deck_v4_timed"
        seen_series.add(series_title)
        previous_chapter = chapter_title
        report_pages.append({
            "page": page_index,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "phrase_ids": current_ids,
            "cue_count": len(timed_cues),
        })

    return pages, {
        "schema_version": 2,
        "timing_source": "precomputed-phrase-timeline",
        "estimated_fallback_used": False,
        "fps": fps,
        "audio_duration_ms": audio_duration_ms,
        "source_coverage": phrase_timeline.get("source_coverage"),
        "pages": report_pages,
    }


def _first_token_time(mapping: dict[int, int], tokens: list[dict[str, Any]], start: int, end: int) -> int:
    for position in range(start, end):
        token_index = mapping.get(position)
        if token_index is not None:
            return int(tokens[token_index]["start_ms"])
    raise RuntimeError("页面原文没有任何可用的真实语音时间锚点")


def _anchor_timing(
    anchor: str,
    source: str,
    page_start: int,
    page_end: int,
    search_cursor: int,
    mapping: dict[int, int],
    tokens: list[dict[str, Any]],
) -> tuple[int, int, int, float, float]:
    normalized_anchor = _normalized(anchor)
    if len(normalized_anchor) < 2:
        raise RuntimeError(f"Cue 锚点至少需要两个有效字符：{anchor}")
    found = source.find(normalized_anchor, max(page_start, search_cursor), page_end)
    if found < 0:
        raise RuntimeError(f"Cue 锚点不是本页原文中的连续短语，或顺序错误：{anchor}")
    anchor_end = found + len(normalized_anchor)
    token_indexes = [mapping[position] for position in range(found, anchor_end) if position in mapping]
    anchor_coverage = len(token_indexes) / len(normalized_anchor)
    if anchor_coverage < ANCHOR_COVERAGE_MIN:
        raise RuntimeError(
            f"Cue 锚点“{anchor}”语音匹配覆盖率 {anchor_coverage:.0%}，低于 {ANCHOR_COVERAGE_MIN:.0%}"
        )
    unique_token_indexes = sorted(set(token_indexes))
    confidence_values = [float(tokens[index]["confidence"]) for index in unique_token_indexes]
    confidence = sum(confidence_values) / max(1, len(confidence_values))
    if confidence < ANCHOR_CONFIDENCE_MIN:
        raise RuntimeError(
            f"Cue 锚点“{anchor}”语音置信度 {confidence:.2f}，低于 {ANCHOR_CONFIDENCE_MIN:.2f}"
        )
    spoken_start = min(int(tokens[index]["start_ms"]) for index in unique_token_indexes)
    spoken_end = max(int(tokens[index]["end_ms"]) for index in unique_token_indexes)
    return spoken_start, spoken_end, anchor_end, anchor_coverage, confidence


def build_semantic_timeline(
    copy: str,
    scenes: list[dict[str, Any]],
    alignment_payload: dict[str, Any],
    audio_duration_ms: int,
    fps: int = 30,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not scenes:
        raise RuntimeError("信息图计划为空，不能建立语义时间轴")
    source_units = _units(copy)
    if not source_units:
        raise RuntimeError("文案没有可对齐的语义单元")
    normalized_units = [_normalized(value) for value in source_units]
    source = "".join(normalized_units)
    unit_offsets: list[int] = [0]
    for value in normalized_units:
        unit_offsets.append(unit_offsets[-1] + len(value))

    recognized, recognized_character_tokens, tokens = _caption_stream(alignment_payload)
    source_mapping, source_coverage = _source_to_token_map(source, recognized, recognized_character_tokens)
    if source_coverage < GLOBAL_SOURCE_COVERAGE_MIN:
        raise RuntimeError(
            f"整篇旁白与原文匹配覆盖率 {source_coverage:.0%}，低于 {GLOBAL_SOURCE_COVERAGE_MIN:.0%}；禁止使用估算时间继续渲染"
        )

    pages = deepcopy(scenes)
    page_character_ranges: list[tuple[int, int]] = []
    expected_unit = 1
    for page in pages:
        indexes = [int(value) for value in page.get("source_units") or []]
        if not indexes or indexes != list(range(indexes[0], indexes[-1] + 1)):
            raise RuntimeError("信息图页面必须引用连续的原文编号")
        if indexes[0] != expected_unit:
            raise RuntimeError("信息图页面原文编号必须按顺序且无遗漏")
        expected_unit = indexes[-1] + 1
        page_character_ranges.append((unit_offsets[indexes[0] - 1], unit_offsets[indexes[-1]]))
    if expected_unit != len(source_units) + 1:
        raise RuntimeError("信息图页面没有完整覆盖原文")

    page_start_ms = [
        _first_token_time(source_mapping, tokens, start, end)
        for start, end in page_character_ranges
    ]
    page_start_ms[0] = 0
    for index in range(1, len(page_start_ms)):
        if page_start_ms[index] <= page_start_ms[index - 1]:
            raise RuntimeError(f"第 {index + 1} 页的真实语音起点没有晚于上一页")
    page_end_ms = page_start_ms[1:] + [audio_duration_ms]

    report_pages: list[dict[str, Any]] = []
    seen_series: set[str] = set()
    previous_chapter = ""
    total_frames = max(1, math.ceil(audio_duration_ms * fps / 1000))
    for page_index, (page, character_range, start_ms, end_ms) in enumerate(
        zip(pages, page_character_ranges, page_start_ms, page_end_ms), 1
    ):
        if end_ms <= start_ms:
            raise RuntimeError(f"第 {page_index} 页真实语音时段无效")
        raw_cues = page.get("cues")
        if not isinstance(raw_cues, list) or not raw_cues:
            raise RuntimeError(f"第 {page_index} 页没有语义 Cue")
        nodes = [str(value) for value in page.get("nodes") or []]
        required_ids = {"page-title", "illustration", *(f"node-{index + 1}" for index in range(len(nodes)))}
        if str(page.get("conclusion") or "").strip():
            required_ids.add("conclusion")
        entered_ids: list[str] = []
        cue_cursor = character_range[0]
        timed_cues: list[dict[str, Any]] = []
        for cue_index, cue in enumerate(raw_cues, 1):
            if not isinstance(cue, dict):
                raise RuntimeError(f"第 {page_index} 页第 {cue_index} 个 Cue 结构无效")
            anchor = str(cue.get("anchor_text") or "").strip()
            enter_ids = [str(value) for value in cue.get("enter_ids") or []]
            focus_id = str(cue.get("focus_id") or "").strip()
            unknown = set(enter_ids) - required_ids
            if unknown:
                raise RuntimeError(f"第 {page_index} 页 Cue 包含未知元素：{', '.join(sorted(unknown))}")
            if focus_id not in required_ids:
                raise RuntimeError(f"第 {page_index} 页 Cue 的 focus_id 无效：{focus_id}")
            spoken_start, spoken_end, cue_cursor, anchor_coverage, confidence = _anchor_timing(
                anchor,
                source,
                character_range[0],
                character_range[1],
                cue_cursor,
                source_mapping,
                tokens,
            )
            if spoken_start < start_ms or spoken_start >= end_ms:
                raise RuntimeError(f"第 {page_index} 页 Cue“{anchor}”落在页面真实语音时段之外")
            timed_cues.append({
                "id": str(cue.get("id") or f"page-{page_index}-cue-{cue_index}"),
                "anchor_text": anchor,
                "spoken_start_ms": spoken_start,
                "spoken_end_ms": spoken_end,
                "start_frame": math.ceil(spoken_start * fps / 1000),
                "end_frame": 0,
                "enter_ids": enter_ids,
                "focus_id": focus_id,
                "alignment_coverage": round(anchor_coverage, 4),
                "alignment_confidence": round(confidence, 4),
            })
            entered_ids.extend(enter_ids)

        missing = required_ids - set(entered_ids)
        duplicates = sorted({value for value in entered_ids if entered_ids.count(value) > 1})
        if missing:
            raise RuntimeError(f"第 {page_index} 页以下语义元素没有 Cue：{', '.join(sorted(missing))}")
        if duplicates:
            raise RuntimeError(f"第 {page_index} 页以下语义元素被重复入场：{', '.join(duplicates)}")
        timed_cues.sort(key=lambda value: int(value["start_frame"]))
        page_start_frame = math.floor(start_ms * fps / 1000)
        page_end_frame = total_frames if page_index == len(pages) else math.floor(end_ms * fps / 1000)
        page_end_frame = max(page_start_frame + 1, page_end_frame)
        for cue_index, cue in enumerate(timed_cues):
            next_frame = timed_cues[cue_index + 1]["start_frame"] if cue_index + 1 < len(timed_cues) else page_end_frame
            cue["end_frame"] = max(int(cue["start_frame"]) + 1, int(next_frame))

        series_title = str(page.get("series_title") or "动态知识解说")
        chapter_title = str(page.get("chapter_title") or page.get("page_title") or "本章要点")
        page["start_ms"] = start_ms
        page["end_ms"] = end_ms
        page["duration_ms"] = end_ms - start_ms
        page["start_frame"] = page_start_frame
        page["end_frame"] = page_end_frame
        page["timed_cues"] = timed_cues
        page_subtitles: list[dict[str, Any]] = []
        for unit_index in [int(value) for value in page.get("source_units") or []]:
            unit_start = unit_offsets[unit_index - 1]
            unit_end = unit_offsets[unit_index]
            unit_token_indexes = sorted({
                source_mapping[position]
                for position in range(unit_start, unit_end)
                if position in source_mapping
            })
            unit_coverage = sum(1 for position in range(unit_start, unit_end) if position in source_mapping) / max(1, unit_end - unit_start)
            if not unit_token_indexes or unit_coverage < 0.55:
                raise RuntimeError(f"第 {unit_index} 条原文不足以生成真实时间字幕，禁止使用估算字幕")
            page_subtitles.append({
                "text": source_units[unit_index - 1],
                "start_ms": min(int(tokens[token_index]["start_ms"]) for token_index in unit_token_indexes),
                "end_ms": max(int(tokens[token_index]["end_ms"]) for token_index in unit_token_indexes),
                "alignment_coverage": round(unit_coverage, 4),
            })
        page["subtitle_cues"] = page_subtitles
        page["series_persistent"] = series_title in seen_series
        page["chapter_persistent"] = chapter_title == previous_chapter
        page["_plan_mode"] = "infographic_v3_timed"
        seen_series.add(series_title)
        previous_chapter = chapter_title
        report_pages.append({
            "page": page_index,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "cue_count": len(timed_cues),
            "minimum_anchor_coverage": min(value["alignment_coverage"] for value in timed_cues),
            "minimum_anchor_confidence": min(value["alignment_confidence"] for value in timed_cues),
        })

    report = {
        "schema_version": 1,
        "timing_source": "whisper.cpp-token-dtw",
        "estimated_fallback_used": False,
        "fps": fps,
        "audio_duration_ms": audio_duration_ms,
        "source_coverage": round(source_coverage, 4),
        "minimum_source_coverage": GLOBAL_SOURCE_COVERAGE_MIN,
        "minimum_anchor_coverage": ANCHOR_COVERAGE_MIN,
        "minimum_anchor_confidence": ANCHOR_CONFIDENCE_MIN,
        "pages": report_pages,
    }
    return pages, report
