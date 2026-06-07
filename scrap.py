import instaloader
import dotenv
import os
import time
import random
from pathlib import Path

# Initialize Instaloader
loader = instaloader.Instaloader(
    download_comments=False,
    download_geotags=False,
    download_videos=False,
    download_video_thumbnails=False,
    save_metadata=False,
    download_pictures=True,
    compress_json=True,
)


def loadEnvVariables() -> tuple[str, str]:
    dotenv.load_dotenv("./.env")
    ACCOUNT_NAME = os.getenv("ACCOUNT_NAME")  # Your login username
    TARGET_USERNAME = os.getenv("TARGET_USERNAME")  # The target profile username
    return ACCOUNT_NAME, TARGET_USERNAME


def get_target_profile(username: str) -> instaloader.Profile:
    profile = instaloader.Profile.from_username(loader.context, username)
    try:
        if profile.is_private:
            print(f"The profile '{username}' is private. Cannot access posts.")
            exit(1)
    except instaloader.exceptions.QueryReturnedBadRequestException:
        print("\n[Error] Instagram returned a 400 Bad Request.")
        print("Your session cookie might be blocked or needs browser verification.")
        print(
            "Might need to wait for a while or log in again to refresh the session cookie."
        )
        exit(1)
    except instaloader.exceptions.ProfileNotExistsException:
        print(f"The profile '{username}' does not exist.")
        exit(1)
    return profile


try:
    ACCOUNT_NAME, TARGET_USERNAME = loadEnvVariables()
except dotenv.error.DotenvError as e:
    print(f"Error loading environment variables: {e}", end="\n")
    print(
        "Please ensure that the .env file exists and contains ACCOUNT_NAME and TARGET_USERNAME."
    )
    exit(1)

# Load session from file
try:
    loader.load_session_from_file(ACCOUNT_NAME)
    print(f"Session loaded successfully for {ACCOUNT_NAME}!")
except instaloader.exceptions.BadCredentialsException:
    print(
        f"Invalid credentials for {ACCOUNT_NAME}. Please run 'instaloader --login {ACCOUNT_NAME}' in terminal to create a new session."
    )
    exit(1)


profile: instaloader.Profile = get_target_profile(TARGET_USERNAME)


def main() -> None:
    count_images = 0
    maximum_image = int(
        input(
            f"Enter the maximum number of images to download from {TARGET_USERNAME}: "
        )
    )

    # Download path
    target_dir = Path(f"downloads/{TARGET_USERNAME}")
    target_dir.mkdir(parents=True, exist_ok=True)

    def clean_caption_files() -> None:
        for file in target_dir.iterdir():
            if file.suffix.lower() in [".json", ".txt"]:
                file.unlink()

    try:
        for post in profile.get_posts():
            if post.is_video:
                continue

            success: bool = loader.download_post(post, target=target_dir)

            if success:
                count_images += 1
                print(f"Progress: {count_images}/{maximum_image} images downloaded.")
                sleep_time: float = random.uniform(1, 3)
                print(
                    f"Waiting for a few {sleep_time:.2f} seconds before the next download..."
                )
                time.sleep(sleep_time)

            if count_images >= maximum_image:
                print(
                    f"\nSuccessfully downloaded {count_images} images from {TARGET_USERNAME}."
                )
                clean_caption_files()
                print("Cleaned up caption files. Exiting.")
                break

    except instaloader.exceptions.ConnectionException as e:
        print(f"\nInstagram blocked the request: {e}")
        print("Your session might have expired, or you're being rate-limited.")


if __name__ == "__main__":
    main()
