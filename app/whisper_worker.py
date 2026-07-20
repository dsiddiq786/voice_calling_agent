import json
import os
import sys
from pathlib import Path


def main() -> None:
    try:
        import imageio_ffmpeg
        import whisper
    except ImportError as exc:
        raise SystemExit("Speech support is not installed. Run ./scripts/install-speech.sh") from exc

    audio_path = sys.argv[1]
    model = sys.argv[2]
    # Whisper invokes an executable named ffmpeg. imageio-ffmpeg supplies a
    # local binary so users do not need Homebrew or another system install.
    bundled_ffmpeg = Path(imageio_ffmpeg.get_ffmpeg_exe())
    shim_dir = bundled_ffmpeg.parent
    expected_name = shim_dir / "ffmpeg"
    if not expected_name.exists():
        expected_name.symlink_to(bundled_ffmpeg.name)
    os.environ["PATH"] = f"{shim_dir}:{os.environ.get('PATH', '')}"

    model_dir = Path(__file__).resolve().parent.parent / "work" / "models"
    model_dir.mkdir(parents=True, exist_ok=True)
    speech_model = whisper.load_model(model, device="cpu", download_root=str(model_dir))
    result = speech_model.transcribe(
        audio_path,
        fp16=False,
        initial_prompt="NomNosh restaurant order. Urdu and English menu names.",
    )
    print(json.dumps({"text": result.get("text", "")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
