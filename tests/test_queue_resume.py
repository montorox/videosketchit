import importlib.util
import asyncio
import io
import json
import queue
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock

from starlette.requests import Request
from starlette.datastructures import UploadFile


RELEASE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RELEASE_ROOT))
SPEC = importlib.util.spec_from_file_location("whiteboard_release_server", RELEASE_ROOT / "webapp" / "server.py")
assert SPEC and SPEC.loader
SERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVER)

from scripts.add_key_text import clean_key_text


class QueueResumeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        SERVER.JOBS_DIR = Path(self.temporary.name)
        SERVER.JOBS = {}
        SERVER.VOICE_QUEUE = queue.Queue()
        SERVER.MODEL_QUEUE = queue.Queue()
        SERVER.ensure_pipeline_workers = lambda: None

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def job(self, job_id: str) -> dict:
        return {
            "id": job_id,
            "status": "queued",
            "stage": "等待语音克隆",
            "progress": 1,
            "created_at": 1.0,
            "started_at": 1.0,
            "queue_order": 1,
            "queue_stage": "voice",
            "job_type": "generate",
            "copy": "这是一段用于验证任务断点恢复的测试文案。",
            "style": SERVER.DEFAULT_STYLE,
            "scenes_per_image": 1,
            "pen_text": "",
            "include_key_text": True,
            "include_subtitles": True,
            "stroke_detail": "detailed",
            "timings": {},
        }

    def test_task_name_defaults_to_first_fifteen_script_characters(self) -> None:
        name = SERVER.normalized_task_name("", "  一二三四五六七八九十\n十一十二十三十四十五十六  ", "job-test")
        self.assertEqual(name, "一二三四五六七八九十十一十二十")

    def test_explicit_task_name_is_preserved(self) -> None:
        self.assertEqual(SERVER.normalized_task_name("  我的任务  ", "备用文案", "job-test"), "我的任务")

    def test_key_text_preserves_spaces_in_english(self) -> None:
        self.assertEqual(clean_key_text("  Cash Flow Crisis!  "), "Cash Flow Crisis")

    def test_key_text_keeps_compact_chinese_limit(self) -> None:
        self.assertEqual(clean_key_text("纸面上的百分之一", 6), "纸面上的百分")

    def test_standard_storyboard_requires_source_language_for_visible_text(self) -> None:
        response = [
            {"title": "Paper Wealth", "key_text": "Paper Wealth", "concept": "A wealthy founder", "elements": ["founder watches city", "luxury watch shines", "car waits below"]},
            {"title": "Frozen Credit", "key_text": "Frozen Credit", "concept": "The bank freezes credit", "elements": ["bank locks account", "credit line freezes", "founder checks phone"]},
        ]
        with mock.patch.object(SERVER, "codex_text_response", return_value={"output_text": json.dumps(response)}) as generate:
            scenes = SERVER.make_plan({}, "The company looks wealthy! Its credit line is frozen.", 20, SERVER.DEFAULT_STYLE)

        prompt = generate.call_args.args[0]
        self.assertIn("原文是英文时，这些字段必须全部使用英文", prompt)
        self.assertEqual([scene["key_text"] for scene in scenes], ["Paper Wealth", "Frozen Credit"])

    def test_custom_reference_prompt_replaces_default_character(self) -> None:
        prompt = SERVER.build_board_prompt(
            [{"title": "相遇", "concept": "小昌和小林交谈", "elements": ["小昌挥手", "小林回应"], "text": "两个人见面了。"}],
            "自定义参考",
            "输入图1是风格参考。输入图2定义人物“小昌”，输入图3定义人物“小林”。",
            True,
        )
        self.assertIn("人物“小昌”", prompt)
        self.assertIn("人物“小林”", prompt)
        self.assertNotIn("同一主角固定为：中国青年男性", prompt)

    def test_paper_metaphor_routes_process_copy_to_machine_reference(self) -> None:
        paths, instruction = SERVER.paper_metaphor_reference_context([
            {"title": "自动化流程", "concept": "把生产系统变成稳定流程", "text": "系统自动完成每个步骤。"}
        ])
        self.assertEqual(paths[0].name, "03-process-machine.png")
        self.assertIn("流程", instruction)
        self.assertIn("禁止照搬", instruction)

    def test_paper_metaphor_prompt_keeps_story_character(self) -> None:
        prompt = SERVER.build_board_prompt(
            [{"title": "小猴改正", "concept": "小猴向大家道歉", "elements": ["小猴低头道歉"], "text": "小猴认识到了错误。"}],
            SERVER.PAPER_METAPHOR_STYLE,
            "输入图仅作为纸艺风格参考。",
        )
        self.assertIn("动物、人物身份与年龄不得被替换", prompt)
        self.assertNotIn("同一主角固定为：中国青年男性", prompt)

    def test_unknown_style_never_silently_falls_back(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "后台未加载画面风格"):
            SERVER.style_recipe("不存在的风格")

    def test_snapshot_keeps_reference_summary_private(self) -> None:
        job_id = "reference-snapshot"
        metadata = self.job(job_id)
        metadata.update(reference_mode="custom", character_count=2, visual_references={"style_image": "secret-name.png"})
        SERVER.JOBS[job_id] = metadata
        snapshot = SERVER.job_snapshot(job_id)
        self.assertEqual(snapshot["reference_mode"], "custom")
        self.assertEqual(snapshot["character_count"], 2)
        self.assertNotIn("visual_references", snapshot)

    def test_snapshot_translates_progress_and_timing_labels_to_english(self) -> None:
        job_id = "english-progress"
        metadata = self.job(job_id)
        metadata.update(
            status="running",
            stage="正在浓缩中心句、列出关键词并规划 PPT 页面",
            current_phase=None,
            timings={"planning": {"label": "内容结构", "seconds": 4.2}},
        )
        SERVER.JOBS[job_id] = metadata

        snapshot = SERVER.job_snapshot(job_id)

        self.assertEqual(snapshot["stage"], "Extracting key ideas and planning presentation pages")
        self.assertEqual(snapshot["timings"]["planning"]["label"], "Content structure")

    def test_snapshot_translates_dynamic_image_progress_to_english(self) -> None:
        job_id = "english-image-progress"
        metadata = self.job(job_id)
        metadata.update(status="running", stage="正在按第 2/4 页已确定的插图槽位生成插画")
        SERVER.JOBS[job_id] = metadata
        self.assertEqual(
            SERVER.job_snapshot(job_id)["stage"],
            "Generating illustration 2/4 from the planned visual slots",
        )

    def test_failed_snapshot_can_be_retried(self) -> None:
        job_id = "failed-snapshot"
        metadata = self.job(job_id)
        metadata.update(status="error", error="temporary model failure")
        SERVER.JOBS[job_id] = metadata
        self.assertTrue(SERVER.job_snapshot(job_id)["can_retry"])

    def test_manual_retry_requeues_same_job(self) -> None:
        job_id = "manual-retry"
        job_dir = SERVER.JOBS_DIR / job_id
        job_dir.mkdir(parents=True)
        metadata = self.job(job_id)
        metadata.update(status="error", error="model failed", finished_at=2.0)
        SERVER.JOBS[job_id] = metadata
        captured = []
        original = SERVER.enqueue_job_from_checkpoint
        SERVER.enqueue_job_from_checkpoint = lambda current_id, item: captured.append((current_id, item["status"]))
        try:
            request = Request({"type": "http", "client": ("198.51.100.8", 1234), "headers": []})
            snapshot = SERVER.retry_failed_job(job_id, request)
        finally:
            SERVER.enqueue_job_from_checkpoint = original
        self.assertEqual(captured, [(job_id, "queued")])
        self.assertEqual(snapshot["status"], "queued")
        self.assertEqual(snapshot["manual_retry_count"], 1)
        self.assertIsNone(snapshot.get("error"))

    def test_image_generation_delegates_to_signed_in_codex(self) -> None:
        target = Path(self.temporary.name) / "board.png"
        with (
            mock.patch.object(SERVER, "codex_account_summary", return_value={"signed_in": True}),
            mock.patch.object(SERVER, "codex_generate_image") as generate,
        ):
            SERVER.generate_image({}, "draw a storyboard", target)
        generate.assert_called_once_with(
            "draw a storyboard",
            target,
            cwd=SERVER.ROOT,
            state_dir=SERVER.STATE_DIR,
            reference_images=None,
        )

    def test_scene_durations_fit_voice_track_exactly(self) -> None:
        scenes = [
            {"text": "短句", "duration_ms": 2000},
            {"text": "这是一段明显更长的中间文案", "duration_ms": 12000},
            {"text": "结尾", "duration_ms": 2000},
        ]
        changed = SERVER.fit_scene_durations(scenes, 5.123)
        self.assertTrue(changed)
        self.assertEqual(sum(scene["duration_ms"] for scene in scenes), 5123)
        self.assertGreaterEqual(scenes[-1]["duration_ms"], 1000)

    def test_old_scene_clip_with_extra_half_second_is_rejected(self) -> None:
        with mock.patch.object(SERVER, "valid_media_file", return_value=True), mock.patch.object(SERVER, "probe_duration", return_value=2.5):
            self.assertFalse(SERVER.valid_timed_video(Path("old.mp4"), 2000))
        with mock.patch.object(SERVER, "valid_media_file", return_value=True), mock.patch.object(SERVER, "probe_duration", return_value=2.04):
            self.assertTrue(SERVER.valid_timed_video(Path("current.mp4"), 2000))

    def test_restore_converts_running_job_back_to_queue(self) -> None:
        job_id = "restore-test"
        job_dir = SERVER.JOBS_DIR / job_id
        job_dir.mkdir(parents=True)
        metadata = self.job(job_id)
        metadata.update(status="running", current_phase="images", phase_started_at=1.0)
        (job_dir / "job.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")

        SERVER.restore_jobs()

        self.assertEqual(SERVER.JOBS[job_id]["status"], "queued")
        self.assertEqual(SERVER.JOBS[job_id]["resume_count"], 1)
        self.assertIsNone(SERVER.JOBS[job_id]["current_phase"])
        self.assertEqual(SERVER.JOBS[job_id]["task_name"], "这是一段用于验证任务断点恢复的")

    def test_missing_voice_returns_to_voice_queue(self) -> None:
        job_id = "voice-test"
        job_dir = SERVER.JOBS_DIR / job_id
        job_dir.mkdir(parents=True)
        (job_dir / "reference.wav").write_bytes(b"reference")
        SERVER.JOBS[job_id] = self.job(job_id)

        SERVER.resume_pending_jobs()

        self.assertEqual(SERVER.VOICE_QUEUE.qsize(), 1)
        self.assertEqual(SERVER.MODEL_QUEUE.qsize(), 0)

    def test_valid_voice_skips_to_model_queue(self) -> None:
        job_id = "model-test"
        job_dir = SERVER.JOBS_DIR / job_id
        job_dir.mkdir(parents=True)
        (job_dir / "reference.wav").write_bytes(b"reference")
        with wave.open(str(job_dir / "voice.wav"), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16000)
            output.writeframes(b"\x00\x00" * 16000)
        SERVER.JOBS[job_id] = self.job(job_id)

        with mock.patch.object(SERVER, "valid_media_file", side_effect=lambda path: Path(path).name == "voice.wav"):
            SERVER.resume_pending_jobs()

        self.assertEqual(SERVER.VOICE_QUEUE.qsize(), 0)
        self.assertEqual(SERVER.MODEL_QUEUE.qsize(), 1)

    def test_finished_narration_skips_voice_clone_queue(self) -> None:
        job_id = "finished-narration-test"
        job_dir = SERVER.JOBS_DIR / job_id
        job_dir.mkdir(parents=True)
        reference = job_dir / "reference.mp3"
        reference.write_bytes(b"finished narration")
        metadata = self.job(job_id)
        metadata.update(narration_source="upload", queue_stage="model", progress=14)
        SERVER.JOBS[job_id] = metadata

        with (
            mock.patch.object(SERVER, "valid_media_file", return_value=False),
            mock.patch.object(SERVER, "prepare_uploaded_narration", return_value=12.5) as prepare,
        ):
            SERVER.resume_pending_jobs()

        prepare.assert_called_once_with(reference, job_dir / "voice.wav", job_id)
        self.assertEqual(SERVER.VOICE_QUEUE.qsize(), 0)
        self.assertEqual(SERVER.MODEL_QUEUE.qsize(), 1)
        self.assertEqual(SERVER.JOBS[job_id]["checkpoint"], "voice_done")
        self.assertEqual(SERVER.JOBS[job_id]["duration"], 12.5)

    def test_finished_narration_upload_creates_voice_checkpoint(self) -> None:
        audio = io.BytesIO()
        with wave.open(audio, "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16000)
            output.writeframes(b"\x00\x00" * 16000)
        audio.seek(0)
        request = Request({"type": "http", "client": ("127.0.0.1", 1234), "headers": []})

        snapshot = asyncio.run(SERVER.create_job(
            request=request,
            script="This finished narration should skip voice cloning completely.",
            style=SERVER.DEFAULT_STYLE,
            scenes_per_image=1,
            task_name="Finished narration",
            pen_text="",
            include_key_text=True,
            include_subtitles=True,
            stroke_detail="detailed",
            reference=UploadFile(filename="narration.wav", file=audio),
            narration_source="upload",
            reference_mode="standard",
            character_manifest="[]",
            style_reference=None,
            character_references=None,
        ))

        job_dir = SERVER.JOBS_DIR / snapshot["id"]
        self.assertEqual(snapshot["narration_source"], "upload")
        self.assertEqual(snapshot["checkpoint"], "voice_done")
        self.assertEqual(snapshot["queue_stage"], "model")
        self.assertTrue(SERVER.valid_media_file(job_dir / "voice.wav"))
        self.assertEqual(SERVER.VOICE_QUEUE.qsize(), 0)
        self.assertEqual(SERVER.MODEL_QUEUE.qsize(), 1)

    def test_english_subtitles_keep_words_intact(self) -> None:
        chunks = SERVER._subtitle_chunks("Imagine that you are standing on the terrace overlooking Central Park.", 24)
        self.assertEqual(" ".join(chunks), "Imagine that you are standing on the terrace overlooking Central Park.")
        self.assertTrue(all(len(chunk) <= 24 for chunk in chunks))


if __name__ == "__main__":
    unittest.main()
