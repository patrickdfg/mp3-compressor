"""Local MP3 compression; originals are never overwritten."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
from typing import Callable


class CompressionError(Exception):
    pass


class Cancelled(CompressionError):
    pass


@dataclass(frozen=True)
class Result:
    source: Path
    output: Path | None
    original_bytes: int
    compressed_bytes: int


def find_ffmpeg() -> str:
    """Prefer a user-provided binary beside the program, then the system PATH."""
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
    bundled = Path(getattr(sys, "_MEIPASS", base))
    for folder in (base, bundled):
        for name in ("ffmpeg.exe", "ffmpeg"):
            candidate = folder / name
            if candidate.is_file():
                return str(candidate)
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise CompressionError("FFmpeg를 찾을 수 없습니다. ffmpeg.exe를 프로그램과 같은 폴더에 넣어 주세요.")


def compress(
    source: Path,
    output_dir: Path,
    *,
    bitrate: int = 48,
    mono: bool = True,
    cancel: threading.Event | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> Result:
    source = Path(source).resolve()
    output_dir = Path(output_dir).resolve()
    if bitrate not in (32, 48, 64, 96, 128):
        raise CompressionError("지원하는 비트레이트: 32, 48, 64, 96, 128 kbps")
    if not source.is_file() or source.suffix.lower() != ".mp3":
        raise CompressionError("존재하는 MP3 파일을 선택해 주세요.")
    if cancel is not None and cancel.is_set():
        raise Cancelled("취소되었습니다.")
    ffmpeg = find_ffmpeg()
    original_bytes = source.stat().st_size
    output_dir.mkdir(parents=True, exist_ok=True)
    # Work on the destination filesystem and publish only complete, smaller files.
    with tempfile.TemporaryDirectory(prefix=".mp3-compress-", dir=output_dir) as temp:
        encoded = Path(temp) / "encoded.mp3"
        log_path = Path(temp) / "error.log"
        progress_path = Path(temp) / "progress.txt"
        command = [
            ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-n",
            "-i", str(source), "-map", "0:a:0", "-vn", "-map_metadata", "-1",
            "-map_chapters", "-1", "-c:a", "libmp3lame", "-b:a", f"{bitrate}k",
            "-ar", "24000", "-ac", "1" if mono else "2",
            "-progress", str(progress_path), str(encoded),
        ]
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        with log_path.open("wb") as error_log:
            process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=error_log, creationflags=flags)
            try:
                while True:
                    try:
                        process.wait(timeout=0.15)
                        break
                    except subprocess.TimeoutExpired:
                        pass
                    if cancel is not None and cancel.is_set():
                        raise Cancelled("취소되었습니다.")
                    if on_progress and progress_path.exists():
                        lines = progress_path.read_text(encoding="utf-8", errors="replace").splitlines()
                        for line in reversed(lines):
                            if line.startswith("out_time_us="):
                                try:
                                    on_progress(max(0, int(line.split("=", 1)[1])) / 1_000_000)
                                except ValueError:
                                    pass
                                break
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait()
        if cancel is not None and cancel.is_set():
            raise Cancelled("취소되었습니다.")
        if process.returncode != 0 or not encoded.exists():
            detail = log_path.read_text(encoding="utf-8", errors="replace")[-1600:].strip()
            raise CompressionError(detail or "오디오를 변환할 수 없습니다.")
        compressed_bytes = encoded.stat().st_size
        if compressed_bytes >= original_bytes:
            return Result(source, None, original_bytes, compressed_bytes)
        suffix = f"_{bitrate}kbps"
        for index in range(10000):
            extra = "" if index == 0 else f"_{index}"
            destination = output_dir / f"{source.stem}{suffix}{extra}.mp3"
            try:
                # Exclusive creation protects existing files, including same-name originals.
                with destination.open("xb") as target:
                    try:
                        with encoded.open("rb") as stream:
                            shutil.copyfileobj(stream, target)
                    except BaseException:
                        target.close()
                        destination.unlink(missing_ok=True)
                        raise
                return Result(source, destination, original_bytes, compressed_bytes)
            except FileExistsError:
                continue
        raise CompressionError("저장할 파일 이름을 만들 수 없습니다.")


def main() -> int:
    parser = argparse.ArgumentParser(description="MP3 용량 줄이기 (기본 48kbps, 모노)")
    parser.add_argument("files", type=Path, nargs="+")
    parser.add_argument("-o", "--output", type=Path, default=Path("compressed"))
    parser.add_argument("-b", "--bitrate", type=int, choices=(32, 48, 64, 96, 128), default=48)
    parser.add_argument("--stereo", action="store_true")
    args = parser.parse_args()
    failed = False
    for path in args.files:
        try:
            result = compress(path, args.output, bitrate=args.bitrate, mono=not args.stereo)
            if result.output:
                print(f"{path.name}: {result.original_bytes:,} → {result.compressed_bytes:,} bytes | {result.output}")
            else:
                print(f"{path.name}: 원본이 더 작아서 저장을 생략했습니다.")
        except (CompressionError, OSError) as exc:
            failed = True
            print(f"{path}: {exc}", file=sys.stderr)
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
