from __future__ import annotations

import unittest

from scripts.semantic_timeline import build_deck_timeline, build_phrase_timeline, build_semantic_timeline


def captions_for(text: str, step_ms: int = 100) -> dict:
    characters = [character for character in text if character.isalnum()]
    return {
        "captions": [
            {
                "text": character,
                "startMs": index * step_ms,
                "endMs": (index + 1) * step_ms,
                "confidence": 0.95,
            }
            for index, character in enumerate(characters)
        ]
    }


def page(unit: int, title: str, node: str, anchor: str) -> dict:
    return {
        "source_units": [unit],
        "series_title": "测试总题",
        "chapter_title": title,
        "page_title": title,
        "layout_type": "focus",
        "nodes": [node],
        "conclusion": "",
        "cues": [{
            "id": f"cue-{unit}",
            "anchor_text": anchor,
            "enter_ids": ["page-title", "illustration", "node-1"],
            "focus_id": "node-1",
        }],
    }


class SemanticTimelineTests(unittest.TestCase):
    def test_builds_phrase_timeline_before_slide_planning(self) -> None:
        copy = "先说明训练目标，再列出五项训练。然后逐项解释。"
        timeline = build_phrase_timeline(copy, captions_for(copy), 2200, fps=30)

        self.assertFalse(timeline["estimated_fallback_used"])
        self.assertEqual(timeline["source_coverage"], 1.0)
        self.assertGreaterEqual(len(timeline["phrases"]), 3)
        self.assertTrue(all(item["spoken_end_ms"] > item["spoken_start_ms"] for item in timeline["phrases"]))

    def test_misheard_phrase_uses_real_boundary_between_strong_neighbours(self) -> None:
        copy = "均由科学逻辑驱动。拒绝死记硬背，从改善大脑发育根源做起。"
        alignment = {"captions": [
            {"text": "均由科学逻辑驱动", "startMs": 0, "endMs": 1000, "confidence": 0.95},
            {"text": "拒绝时机应备", "startMs": 1000, "endMs": 2100, "confidence": 0.82},
            {"text": "从改善大脑发育根源做起", "startMs": 2100, "endMs": 4000, "confidence": 0.95},
        ]}

        timeline = build_phrase_timeline(copy, alignment, 4000, fps=30)
        rescued = timeline["phrases"][1]

        self.assertEqual(timeline["source_coverage"], 0.84)
        self.assertEqual(rescued["boundary_source"], "neighboring-word-boundary")
        self.assertEqual((rescued["spoken_start_ms"], rescued["spoken_end_ms"]), (1000, 2100))
        self.assertEqual(rescued["recognized_boundary_text"], "拒绝时机应备")

    def test_unrecognized_final_phrase_uses_real_tail_audio_activity(self) -> None:
        copy = "今天开始练习。先从最弱的一项开始：表达。"
        spoken_without_last_phrase = "今天开始练习先从最弱的一项开始"
        alignment = captions_for(spoken_without_last_phrase, step_ms=100)
        alignment["speechSegments"] = [
            {"startMs": 0, "endMs": 1700},
            {"startMs": 1880, "endMs": 2140},
        ]

        timeline = build_phrase_timeline(copy, alignment, 2400, fps=30)
        final_phrase = timeline["phrases"][-1]

        self.assertEqual(final_phrase["text"], "表达。")
        self.assertEqual(final_phrase["boundary_source"], "audio-activity-edge")
        self.assertEqual((final_phrase["spoken_start_ms"], final_phrase["spoken_end_ms"]), (1880, 2140))
        self.assertFalse(timeline["estimated_fallback_used"])

    def test_deck_groups_five_overview_items_on_one_real_phrase(self) -> None:
        copy = "这是五项训练。下面逐项说明。"
        phrase_timeline = build_phrase_timeline(copy, captions_for(copy), 1400, fps=30)
        phrase_ids = [item["id"] for item in phrase_timeline["phrases"]]
        trigger = phrase_ids[0]
        slides = [{
            "source_phrase_ids": phrase_ids,
            "series_title": "测试训练",
            "chapter_title": "训练总览",
            "page_title": "五项训练",
            "page_title_trigger_phrase_id": trigger,
            "illustration_trigger_phrase_id": trigger,
            "layout_type": "overview",
            "role": "overview",
            "relationship_type": "none",
            "key_items": [
                {"label": f"训练{index}", "trigger_phrase_id": trigger}
                for index in range(1, 6)
            ],
            "nodes": [f"训练{index}" for index in range(1, 6)],
            "conclusion": "",
        }]

        timed, report = build_deck_timeline(copy, slides, phrase_timeline, 1400, fps=30)

        self.assertFalse(report["estimated_fallback_used"])
        first_cue = timed[0]["timed_cues"][0]
        self.assertEqual(first_cue["phrase_id"], trigger)
        self.assertEqual(
            set(first_cue["enter_ids"]),
            {"page-title", "illustration", "node-1", "node-2", "node-3", "node-4", "node-5"},
        )

    def test_uses_acoustic_tokens_and_never_leads_the_anchor(self) -> None:
        copy = "第一部分说明方法。第二部分给出结论。"
        plan = [
            page(1, "方法", "说明方法", "说明方法"),
            page(2, "结论", "给出结论", "给出结论"),
        ]
        alignment = captions_for(copy)
        duration_ms = len([value for value in copy if value.isalnum()]) * 100

        timed, report = build_semantic_timeline(copy, plan, alignment, duration_ms, fps=30)

        self.assertFalse(report["estimated_fallback_used"])
        self.assertEqual(report["source_coverage"], 1.0)
        for current_page in timed:
            cue = current_page["timed_cues"][0]
            acoustic_frame = -(-cue["spoken_start_ms"] * 30 // 1000)
            self.assertGreaterEqual(cue["start_frame"], acoustic_frame)
        self.assertEqual(timed[0]["start_ms"], 0)
        self.assertGreater(timed[1]["start_ms"], timed[0]["start_ms"])

    def test_rejects_anchor_that_is_not_exact_source_text(self) -> None:
        copy = "第一部分说明方法。"
        plan = [page(1, "方法", "说明方法", "不存在的锚点")]
        with self.assertRaisesRegex(RuntimeError, "锚点"):
            build_semantic_timeline(copy, plan, captions_for(copy), 800, fps=30)

    def test_rejects_low_global_alignment_coverage(self) -> None:
        copy = "第一部分说明方法。第二部分给出结论。"
        plan = [
            page(1, "方法", "说明方法", "说明方法"),
            page(2, "结论", "给出结论", "给出结论"),
        ]
        with self.assertRaisesRegex(RuntimeError, "整篇旁白与原文匹配覆盖率"):
            build_semantic_timeline(copy, plan, captions_for("完全不同"), 1200, fps=30)

    def test_page_waits_for_the_next_real_token_across_silence(self) -> None:
        copy = "第一部分说明方法。第二部分给出结论。"
        plan = [
            page(1, "方法", "说明方法", "说明方法"),
            page(2, "结论", "给出结论", "给出结论"),
        ]
        characters = [character for character in copy if character.isalnum()]
        second_page_start = characters.index("第", 1)
        alignment = {"captions": []}
        for index, character in enumerate(characters):
            start_ms = index * 100 if index < second_page_start else 5000 + (index - second_page_start) * 100
            alignment["captions"].append({
                "text": character,
                "startMs": start_ms,
                "endMs": start_ms + 100,
                "confidence": 0.95,
            })

        timed, _ = build_semantic_timeline(copy, plan, alignment, 6000, fps=30)

        self.assertEqual(timed[1]["start_ms"], 5000)
        self.assertEqual(timed[0]["end_ms"], 5000)
        self.assertEqual(timed[0]["end_frame"], timed[1]["start_frame"])

    def test_rejects_duplicate_element_entry(self) -> None:
        copy = "第一部分说明方法。"
        invalid_page = page(1, "方法", "说明方法", "说明方法")
        invalid_page["cues"][0]["anchor_text"] = "说明"
        invalid_page["cues"].append({
            "id": "duplicate",
            "anchor_text": "方法",
            "enter_ids": ["node-1"],
            "focus_id": "node-1",
        })
        with self.assertRaisesRegex(RuntimeError, "重复入场"):
            build_semantic_timeline(copy, [invalid_page], captions_for(copy), 1000, fps=30)


if __name__ == "__main__":
    unittest.main()
