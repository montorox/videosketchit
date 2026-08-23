from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any


def find_codex_binary() -> str:
    configured = os.environ.get("CODEX_BIN", "").strip()
    if configured:
        return configured
    discovered = shutil.which("codex")
    if discovered:
        return discovered
    if sys.platform == "darwin":
        bundled = Path("/Applications/ChatGPT.app/Contents/Resources/codex")
        if bundled.exists():
            return str(bundled)
    raise RuntimeError(
        "Codex was not found. Install the ChatGPT desktop app or Codex CLI, "
        "then set CODEX_BIN if it is installed in a custom location."
    )


class CodexAppServer:
    """Small JSON-RPC client for Codex account/login and usage information."""

    def __init__(self) -> None:
        self._process: subprocess.Popen[str] | None = None
        self._pending: dict[int, queue.Queue[dict[str, Any]]] = {}
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._next_id = 1

    def _start(self) -> None:
        with self._lock:
            if self._process and self._process.poll() is None:
                return
            self._pending.clear()
            self._process = subprocess.Popen(
                [find_codex_binary(), "app-server"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
            threading.Thread(target=self._read_loop, daemon=True).start()

        self.request(
            "initialize",
            {
                "clientInfo": {
                    "name": "cs_board_codex",
                    "title": "CS Board Codex Edition",
                    "version": "1.0.0",
                }
            },
            timeout=20,
            ensure_started=False,
        )
        self.notify("initialized", {})

    def _read_loop(self) -> None:
        process = self._process
        if not process or not process.stdout:
            return
        for raw_line in process.stdout:
            try:
                message = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            request_id = message.get("id")
            if request_id is None:
                continue
            with self._lock:
                waiter = self._pending.pop(int(request_id), None)
            if waiter:
                waiter.put(message)

    def _send(self, message: dict[str, Any]) -> None:
        process = self._process
        if not process or process.poll() is not None or not process.stdin:
            raise RuntimeError("Codex App Server is not running")
        with self._write_lock:
            process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
            process.stdin.flush()

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self._send({"method": method, "params": params})

    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float = 30,
        ensure_started: bool = True,
    ) -> dict[str, Any]:
        if ensure_started:
            self._start()
        with self._lock:
            request_id = self._next_id
            self._next_id += 1
            waiter: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
            self._pending[request_id] = waiter
        try:
            self._send({"method": method, "id": request_id, "params": params or {}})
            response = waiter.get(timeout=timeout)
        except queue.Empty as exc:
            with self._lock:
                self._pending.pop(request_id, None)
            raise RuntimeError(f"Codex App Server timed out while running {method}") from exc
        if response.get("error"):
            error = response["error"]
            raise RuntimeError(str(error.get("message") if isinstance(error, dict) else error))
        return response.get("result") or {}

    def account(self, refresh: bool = False) -> dict[str, Any]:
        return self.request("account/read", {"refreshToken": refresh})

    def rate_limits(self) -> dict[str, Any]:
        return self.request("account/rateLimits/read")

    def start_chatgpt_login(self) -> dict[str, Any]:
        return self.request(
            "account/login/start",
            {
                "type": "chatgpt",
                "useHostedLoginSuccessPage": True,
                "appBrand": "chatgpt",
            },
        )

    def start_device_login(self) -> dict[str, Any]:
        return self.request("account/login/start", {"type": "chatgptDeviceCode"})

    def logout(self) -> dict[str, Any]:
        return self.request("account/logout")


APP_SERVER = CodexAppServer()


def codex_account_summary(refresh: bool = False) -> dict[str, Any]:
    account = APP_SERVER.account(refresh=refresh)
    account_data = account.get("account") if isinstance(account.get("account"), dict) else account
    auth_mode = account.get("authMode") or account_data.get("authMode") or account_data.get("type")
    plan_type = account.get("planType") or account_data.get("planType")
    signed_in = bool(account_data) and auth_mode not in {None, "null"}
    result: dict[str, Any] = {
        "available": True,
        "signed_in": signed_in,
        "auth_mode": auth_mode,
        "plan_type": plan_type,
        "email": account_data.get("email"),
    }
    if signed_in and auth_mode in {"chatgpt", "chatgptAuthTokens"}:
        try:
            result["rate_limits"] = APP_SERVER.rate_limits().get("rateLimits")
        except Exception:
            result["rate_limits"] = None
    return result


def codex_exec(
    prompt: str,
    *,
    cwd: Path,
    state_dir: Path,
    images: list[Path] | None = None,
    timeout: float = 1800,
) -> str:
    binary = find_codex_binary()
    state_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="codex-run-", dir=state_dir) as temp_name:
        final_path = Path(temp_name) / "final.txt"
        command = [
            binary,
            "exec",
            "--skip-git-repo-check",
            "--ephemeral",
            "--approve-for-me",
            "--color",
            "never",
            "-C",
            str(cwd),
            "-o",
            str(final_path),
        ]
        for image in images or []:
            command.extend(["-i", str(image)])
        command.append("-")
        completed = subprocess.run(
            command,
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
        )
        if completed.returncode:
            detail = (completed.stderr or completed.stdout).strip()[-3000:]
            raise RuntimeError(f"Codex failed: {detail or f'exit code {completed.returncode}'}")
        result = final_path.read_text(encoding="utf-8").strip() if final_path.exists() else completed.stdout.strip()
        if not result:
            raise RuntimeError("Codex completed without returning a response")
        return result


def codex_generate_image(
    prompt: str,
    target: Path,
    *,
    cwd: Path,
    state_dir: Path,
    reference_images: list[Path] | None = None,
) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    request = f"""$imagegen
Generate exactly one 16:9 image for a narrated video using the instructions below.
Save the finished PNG to this exact absolute path:
{target.resolve()}

Do not create an HTML mockup, SVG, program, or explanation. Use the built-in image generation skill.
The attached images, when present, are visual or character references and must guide the result.

IMAGE INSTRUCTIONS:
{prompt}
"""
    response = codex_exec(
        request,
        cwd=cwd,
        state_dir=state_dir,
        images=reference_images,
        timeout=1800,
    )
    if not target.exists() or target.stat().st_size < 1024:
        raise RuntimeError(f"Codex did not save the requested image. Last response: {response[-1000:]}")
