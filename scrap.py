"""Standalone Instagram post scraper script (gallery-dl backend)."""

import os
import sys
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

import dotenv
from gallery_dl import config, exception as gallery_exception, job
from pydantic import BaseModel, Field, ValidationError, model_validator


# ---------------------------------------------------------------------------
# Custom Exceptions
# ---------------------------------------------------------------------------


class ScraperError(Exception):
    """Base exception for all scraper-related errors."""

    pass


class SessionError(ScraperError):
    """Session loading or authentication failure."""

    pass


class ProfileError(ScraperError):
    """Profile access failure (private, not found, bad request)."""

    pass


# ---------------------------------------------------------------------------
# Settings (strict Pydantic model)
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    """Strictly typed environment configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        frozen=True,
    )

    target_username: str = ""
    cookies_file: str = ""

    @model_validator(mode="before")
    @classmethod
    def _from_env(cls, data: dict) -> dict:
        """Load env vars before field validation.
        Accepts optional 'env_path' key, stripped before construction.
        """
        env_path = data.pop("env_path", ".env")
        dotenv.load_dotenv(env_path)

        target = os.getenv("TARGET_USERNAME")

        if not target:
            raise ValueError("TARGET_USERNAME is required in .env")

        return {
            "target_username": target,
            "cookies_file": os.getenv("COOKIES_FILE", ""),
        }


# ---------------------------------------------------------------------------
# Pydantic response model
# ---------------------------------------------------------------------------


class DownloadResult(BaseModel):
    """Result of a download run."""

    count: int = Field(strict=True, ge=0)
    username: str = Field(strict=True, min_length=1)


# ---------------------------------------------------------------------------
# Gallery-dl session (replaces instaloader)
# ---------------------------------------------------------------------------

# Image extensions counted as successful downloads (sidecars excluded).
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".avif"}


class GallerySession:
    """Wraps gallery-dl configuration for Instagram downloads."""

    def __init__(self, cookies_file: str = "") -> None:
        config.load()
        # Project-local safety config (rate limiting, retries, etc.).
        # Missing file is logged and ignored; defaults above still apply.
        config.load(["gallery-dl.conf"])
        config.set(("extractor", "instagram"), "videos", False)
        config.set(("extractor", "instagram"), "directory", ["downloads", "{username}"])

        if cookies_file:
            cookies_path = Path(cookies_file).expanduser()
            if not cookies_path.is_file():
                raise SessionError(
                    f"Cookies file not found: {cookies_file}. "
                    "Export a Netscape-format cookies.txt from your browser "
                    "(e.g. with the 'Get cookies.txt LOCALLY' extension) and "
                    "point COOKIES_FILE at it."
                )
            config.set(("extractor", "instagram"), "cookies", str(cookies_path))
        else:
            print(
                "Warning: COOKIES_FILE not set. Instagram may require "
                "authenticated cookies; downloads may fail with an auth error."
            )

    @staticmethod
    def profile_url(username: str) -> str:
        return f"https://www.instagram.com/{username}/"


# ---------------------------------------------------------------------------
# File Manager
# ---------------------------------------------------------------------------


class FileManager:
    """Directory creation and cleanup for downloaded files."""

    def __init__(self, base_dir: str = "downloads") -> None:
        self._base = Path(base_dir)

    def prepare(self, username: str) -> Path:
        """Create and clean the target download directory."""
        target_dir = self._base / username
        target_dir.mkdir(parents=True, exist_ok=True)

        existing_files = list(target_dir.iterdir())
        if existing_files:
            print(
                f"Directory '{target_dir}' already exists. "
                f"Cleaning up {len(existing_files)} old file(s)..."
            )
            for file in existing_files:
                if file.is_file():
                    file.unlink()
            print("Cleanup complete. Starting fresh.")

        return target_dir

    @staticmethod
    def remove_captions(target_dir: Path) -> None:
        """Delete JSON and TXT caption sidecar files."""
        removed = 0
        for file in target_dir.iterdir():
            if file.suffix.lower() in (".json", ".txt"):
                file.unlink()
                removed += 1
        if removed:
            print(f"Removed {removed} caption file(s).")


# ---------------------------------------------------------------------------
# Scraper Service
# ---------------------------------------------------------------------------


class ScraperService:
    """Orchestrates profile access and post downloading via gallery-dl."""

    def __init__(self, session: GallerySession) -> None:
        self._session = session

    def get_profile(self, username: str) -> None:
        """Probe the profile cheaply and surface auth/not-found errors.

        gallery-dl logs errors internally on DownloadJob, so we use a
        DataJob limited to one post to capture the real exception.
        """
        config.set(("extractor", "instagram"), "max-posts", 1)
        probe = job.DataJob(GallerySession.profile_url(username))
        probe.run()

        exc = probe.exception
        if exc is None:
            return

        if isinstance(exc, gallery_exception.NotFoundError):
            raise ProfileError(f"The profile '{username}' does not exist.")
        if isinstance(exc, (gallery_exception.AuthRequired, gallery_exception.AuthenticationError)):
            raise SessionError(
                f"Instagram requires valid cookies to access '{username}'. "
                "Set COOKIES_FILE to a fresh cookies.txt export from your browser."
            )
        if isinstance(exc, gallery_exception.HttpError):
            if exc.status == 429:
                raise ProfileError(
                    f"Instagram returned 429 Too Many Requests for '{username}'. "
                    "Wait a while before retrying; the endpoint itself is throttled."
                )
            raise ProfileError(
                f"Instagram returned HTTP {exc.status} for '{username}'. "
                "Your session cookie may be blocked or needs browser verification. "
                "Try waiting a while or re-export the cookies file."
            )
        raise ProfileError(f"Profile probe failed for '{username}': {exc}")

    def download(
        self,
        username: str,
        target_dir: Path,
        max_images: int,
    ) -> DownloadResult:
        """Download images from profile posts up to max_images."""
        config.set(("extractor", "instagram"), "max-posts", max_images)
        download_job = job.DownloadJob(GallerySession.profile_url(username))
        status = download_job.run()

        if status & 16:  # AuthenticationError / AuthorizationError codes
            raise SessionError(
                f"Instagram rejected the session while downloading '{username}'. "
                "Re-export COOKIES_FILE from your browser (fresh cookies.txt)."
            )
        if status & 4:  # ExtractionError (HttpError / NotFoundError)
            raise ScraperError(
                f"Instagram failed while downloading '{username}'. "
                "This is usually a 429 rate limit or a blocked session; "
                "wait a while and retry with fresh cookies."
            )

        count = sum(
            1
            for file in target_dir.iterdir()
            if file.is_file() and file.suffix.lower() in IMAGE_EXTENSIONS
        )
        if count == 0:
            raise ProfileError(
                f"No images found for '{username}'. "
                "The profile may be private or contain only videos."
            )

        return DownloadResult(count=count, username=username)


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------


def _prompt_max_images(target_username: str) -> int:
    """Read the maximum image count from user input."""
    raw = input(
        f"Enter the maximum number of images to download from " f"{target_username}: "
    )
    if not raw.strip():
        raise ValueError("No value entered")
    return int(raw)


def main() -> None:
    """Application entry point — wires dependencies and runs the scraper."""
    # --- Settings (Pydantic-validated) ---
    try:
        settings = Settings()
    except ValidationError as e:
        print(f"Configuration error:\n{e}")
        return

    # --- Session ---
    try:
        session = GallerySession(settings.cookies_file)
    except SessionError as e:
        print(f"Session error: {e}")
        return

    # --- Wire dependencies ---
    file_manager = FileManager('gallery-dl/downloads')
    scraper = ScraperService(session)

    # --- Profile ---
    try:
        scraper.get_profile(settings.target_username)
    except ProfileError as e:
        print(f"Profile error: {e}")
        return
    except SessionError as e:
        print(f"Session error: {e}")
        return

    # --- User input ---
    try:
        max_images = _prompt_max_images(settings.target_username)
    except ValueError:
        print("Invalid number entered.")
        return

    # --- Download ---
    target_dir = file_manager.prepare(settings.target_username)
    try:
        result = scraper.download(settings.target_username, target_dir, max_images)
        print(
            f"\nSuccessfully downloaded {result.count} image(s) "
            f"from {result.username}."
        )
        FileManager.remove_captions(target_dir)
        print("Caption files cleaned up. Done.")
    except (ProfileError, SessionError, ScraperError) as e:
        print(f"Download error: {e}")


if __name__ == "__main__":
    sys.exit(main())
