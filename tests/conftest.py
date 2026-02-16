"""
Pytest configuration and shared fixtures.
"""

import pytest
import shutil
import subprocess
from pathlib import Path
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TDRC, TCON, TRCK

# ---------- Constants ----------

# Minimal valid audio file headers for testing
AUDIO_HEADERS = {
    '.mp3': b'ID3\x03\x00\x00\x00\x00\x0F' b'TIT2\x00\x00\x00\x03\x00\x00\x00HI' b'\xFF\xFB\x90\x00\x00\x00\x00\x00',
    '.flac': b'fLaC\x00\x00\x00\x22\x12\x00\x12\x80\x00\x00\x00\x00\x00\x00\x00\x00',
    '.m4a': b'\x00\x00\x00\x20ftypM4A \x00\x00\x00\x00M4A mp42isom',
    '.wav': b'RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00',
    '.ogg': b'OggS\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00',
    '.opus': b'OggS\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00OpusHead\x01\x01\x00\x00',
}

# FFmpeg configuration for generating real audio files
FFMPEG = shutil.which("ffmpeg")
FF_ARGS = {
    ".wav": ["-c:a", "pcm_s16le"],
    ".mp3": ["-c:a", "libmp3lame"],
    ".flac": ["-c:a", "flac"],
    ".m4a": ["-c:a", "aac"],
    ".mp4": ["-c:a", "aac"],
    ".ogg": ["-c:a", "libvorbis"],
    ".opus": ["-c:a", "libopus"],
    ".wma": ["-c:a", "wmav2"],
}

TAGS = {
    "title": "Test Title",
    "artist": "Test Artist",
    "album": "Test Album",
    "date": "2025",
    "genre": "TestGenre",
    "tracknumber": "1",
}

AUDIO_DIR = Path(__file__).parent / "audio"

# ---------- Helper Functions ----------

def generate_audio(path: Path, ext: str):
    """Generate a real audio file using ffmpeg."""
    if not FFMPEG:
        raise RuntimeError("ffmpeg not found on PATH")
    
    args = FF_ARGS.get(ext)
    if not args:
        raise RuntimeError(f"No ffmpeg args for {ext}")

    sample_rate = 48000 if ext == ".opus" else 44100

    cmd = [
        FFMPEG,
        "-f", "lavfi",
        "-i", "sine=frequency=440:duration=1",
        "-ar", str(sample_rate),
        "-ac", "2",
        *args,
        str(path),
        "-y",
        "-loglevel", "error",
    ]
    
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed for {ext}: {proc.stderr.decode()}")

def write_mp3_tags(path: Path):
    """Write ID3 tags to generated MP3 file."""
    audio = MP3(str(path), ID3=ID3)
    if audio.tags is None:
        audio.add_tags()
    
    audio.tags.add(TIT2(encoding=3, text=TAGS["title"]))
    audio.tags.add(TPE1(encoding=3, text=TAGS["artist"]))
    audio.tags.add(TALB(encoding=3, text=TAGS["album"]))
    audio.tags.add(TDRC(encoding=3, text=TAGS["date"]))
    audio.tags.add(TCON(encoding=3, text=TAGS["genre"]))
    audio.tags.add(TRCK(encoding=3, text=TAGS["tracknumber"]))
    audio.save(v2_version=3)

def _get_audio_files():
    """Helper to get list of real audio files for parametrization."""
    from mudio.core import SimpleMusic
    if not AUDIO_DIR.exists():
        return []
    return [
        f for f in AUDIO_DIR.iterdir() 
        if f.is_file() and f.suffix.lower() in SimpleMusic.SUPPORTED_EXT
    ]

# ---------- Fixtures ----------

@pytest.fixture(scope="session")
def audio_assets(tmp_path_factory):
    """Generate minimal valid audio test files (fast, dummy content)."""
    assets_dir = tmp_path_factory.mktemp("assets")
    files = []
    
    for ext, header in AUDIO_HEADERS.items():
        test_file = assets_dir / f"test{ext}"
        test_file.write_bytes(header + b'\x00' * 1024)
        files.append(test_file)
    
    return files

@pytest.fixture(scope="session")
def audio_template(tmp_path_factory):
    """Generate a single real MP3 file with actual audio and tags for readonly tests."""
    if not FFMPEG:
        pytest.skip("ffmpeg not found - cannot generate real audio files")
    
    template_dir = tmp_path_factory.mktemp("template")
    template_file = template_dir / "test.mp3"
    
    try:
        generate_audio(template_file, ".mp3")
        write_mp3_tags(template_file)
    except Exception as e:
        pytest.skip(f"Failed to generate audio template: {e}")
    
    return template_file

@pytest.fixture(scope="session")
def all_format_files(audio_assets):
    """Ensure we have all formats for comprehensive testing."""
    found_formats = {f.suffix.lower() for f in audio_assets}
    expected = set(AUDIO_HEADERS.keys())
    
    missing = expected - found_formats
    if missing:
        pytest.fail(f"Failed to generate test files for: {missing}")
    
    return audio_assets

@pytest.fixture
def temp_audio_dir(tmp_path):
    """Create a temporary directory with dummy audio files."""
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()

    # Create dummy files of various formats
    headers = {
        '.mp3': b'ID3\x03\x00\x00\x00\x00\x0F' b'TIT2\x00\x00\x00\x03\x00\x00\x00HI' b'\xFF\xFB\x90\x00\x00\x00\x00\x00',
        '.flac': b'fLaC\x00\x00\x00\x22\x12\x00\x12\x80\x00\x00\x00\x00\x00\x00\x00\x00',
        '.m4a': b'\x00\x00\x00\x20ftypM4A \x00\x00\x00\x00M4A mp42isom',
    }

    for ext, header in headers.items():
        for i in range(3):
            file = audio_dir / f"track_{i:02d}{ext}"
            file.write_bytes(header + b'\x00' * 1024)

    # Add a subdirectory with more files
    subdir = audio_dir / "sub"
    subdir.mkdir()
    (subdir / "sub_track.mp3").write_bytes(headers['.mp3'] + b'\x00' * 1024)

    return audio_dir

@pytest.fixture
def small_batch_files(tmp_path):
    """Create a small number of files (< MIN_FILES_FOR_PARALLEL)."""
    files = []
    for i in range(3):
        f = tmp_path / f"small_{i}.mp3"
        f.write_bytes(
            b'ID3\x03\x00\x00\x00\x00\x0F' b'TIT2\x00\x00\x00\x03\x00\x00\x00HI' b'\xFF\xFB\x90\x00\x00\x00\x00\x00')
        files.append(f)
    return files

@pytest.fixture(params=_get_audio_files())
def audio_file(request, tmp_path):
    """
    Parametrized fixture that yields a copy of each real audio file in tests/audio.
    Usage: simple include 'audio_file' in test arguments.
    """
    original_file = request.param
    # Create a source directory to avoid backup collision issues
    source_dir = tmp_path / "source"
    source_dir.mkdir(exist_ok=True)
    temp_file = source_dir / original_file.name
    shutil.copy2(original_file, temp_file)
    return temp_file