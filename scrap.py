"""Standalone Instagram post scraper script"""

import os
import time
import random
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

import dotenv
import instaloader
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

    account_name: str = ""
    target_username: str = ""

    @model_validator(mode="before")
    @classmethod
    def _from_env(cls, data: dict) -> dict:
        """Load env vars before field validation.
        Accepts optional 'env_path' key, stripped before construction.
        """
        env_path = data.pop("env_path", ".env")
        dotenv.load_dotenv(env_path)

        account = os.getenv("ACCOUNT_NAME")
        target = os.getenv("TARGET_USERNAME")

        if not account:
            raise ValueError("ACCOUNT_NAME is required in .env")
        if not target:
            raise ValueError("TARGET_USERNAME is required in .env")

        return {"account_name": account, "target_username": target}


# ---------------------------------------------------------------------------
# Pydantic response model
# ---------------------------------------------------------------------------


class DownloadResult(BaseModel):
    """Result of a download run."""

    count: int = Field(strict=True, ge=0)
    username: str = Field(strict=True, min_length=1)


# ---------------------------------------------------------------------------
# Instagram Session
# ---------------------------------------------------------------------------


class InstagramSession:
    """Wraps Instaloader initialisation and session management."""

    def __init__(self) -> None:
        self._loader = instaloader.Instaloader(
            download_comments=False,
            download_geotags=False,
            download_videos=False,
            download_video_thumbnails=False,
            save_metadata=False,
            download_pictures=True,
            compress_json=True,
        )

    @property
    def loader(self) -> instaloader.Instaloader:
        return self._loader

    @property
    def context(self):
        return self._loader.context

    def load_session(self, account_name: str) -> None:
        """Load an existing Instaloader session from disk."""
        try:
            self._loader.load_session_from_file(account_name)
        except instaloader.exceptions.BadCredentialsException:
            raise SessionError(
                f"Invalid credentials for {account_name}. "
                f"Run 'instaloader --login {account_name}' in terminal "
                f"to create a new session."
            )


# ---------------------------------------------------------------------------
# Rate Limiter
# ---------------------------------------------------------------------------


class RateLimiter:
    """Randomised delay between requests to avoid rate limiting."""

    def __init__(self, min_seconds: float = 1.0, max_seconds: float = 3.0) -> None:
        self._min = min_seconds
        self._max = max_seconds

    def wait(self) -> None:
        """Sleep for a random interval."""
        delay = random.uniform(self._min, self._max)
        print(f"Waiting {delay:.2f} seconds before next download...")
        time.sleep(delay)


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
    """Orchestrates profile access and post downloading."""

    def __init__(
        self,
        session: InstagramSession,
        rate_limiter: RateLimiter,
    ) -> None:
        self._session = session
        self._rate_limiter = rate_limiter

    def get_profile(self, username: str) -> instaloader.Profile:
        """Fetch and validate a public Instagram profile."""
        try:
            profile = instaloader.Profile.from_username(self._session.context, username)
            if profile.is_private:
                raise ProfileError(
                    f"The profile '{username}' is private. Cannot access posts."
                )
        except instaloader.exceptions.ProfileNotExistsException:
            raise ProfileError(f"The profile '{username}' does not exist.")
        except instaloader.exceptions.QueryReturnedBadRequestException:
            raise ProfileError(
                "Instagram returned a 400 Bad Request. "
                "Your session cookie may be blocked or needs browser verification. "
                "Try waiting a while or re-login to refresh the session cookie."
            )

        return profile

    def download(
        self,
        profile: instaloader.Profile,
        target_dir: Path,
        max_images: int,
    ) -> DownloadResult:
        """Download images from profile posts up to max_images."""
        count = 0

        try:
            for post in profile.get_posts():
                if post.is_video:
                    continue

                if self._session.loader.download_post(post, target=target_dir):
                    count += 1
                    print(f"Progress: {count}/{max_images} images downloaded.")

                    if count < max_images:
                        self._rate_limiter.wait()

                if count >= max_images:
                    break

        except instaloader.exceptions.ConnectionException as cause:
            raise ScraperError(
                f"Instagram blocked the request: {cause}. "
                "Session may have expired or you are being rate-limited."
            ) from cause

        return DownloadResult(count=count, username=profile.username)


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
    session = InstagramSession()
    try:
        session.load_session(settings.account_name)
        print(f"Session loaded successfully for {settings.account_name}!")
    except SessionError as e:
        print(f"Session error: {e}")
        return

    # --- Wire dependencies ---
    file_manager = FileManager()
    rate_limiter = RateLimiter()
    scraper = ScraperService(session, rate_limiter)

    # --- Profile ---
    try:
        profile = scraper.get_profile(settings.target_username)
    except ProfileError as e:
        print(f"Profile error: {e}")
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
        result = scraper.download(profile, target_dir, max_images)
        print(
            f"\nSuccessfully downloaded {result.count} image(s) "
            f"from {result.username}."
        )
        FileManager.remove_captions(target_dir)
        print("Caption files cleaned up. Done.")
    except ScraperError as e:
        print(f"Download error: {e}")


if __name__ == "__main__":
    main()
