"""인스타그램 공개 계정 이미지 크롤러.

Instaloader를 사용해 공개 계정의 최근 포스트 이미지 URL을 수집합니다.
로그인 없이 공개 계정만 접근 가능합니다.

사용:
    python image_crawler.py                        # 기본 계정(torriden_official), 9장
    python image_crawler.py --account 계정명 --limit 12
"""

import argparse
import json
import sys
import time
from pathlib import Path

import instaloader


def fetch_post_image_urls(account: str, limit: int = 9, download_dir: str = "image_crawled") -> list[dict]:
    """공개 인스타그램 계정에서 최근 포스트 이미지를 다운로드하고 URL을 수집합니다.

    Args:
        account: 인스타그램 계정명 (@ 제외)
        limit: 수집할 포스트 수
        download_dir: 이미지 저장 폴더

    Returns:
        [{"url": str, "local_path": str, "shortcode": str, "timestamp": str, "caption": str}, ...]
    """
    save_dir = Path(download_dir)
    save_dir.mkdir(exist_ok=True)

    L = instaloader.Instaloader(
        download_pictures=True,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        post_metadata_txt_pattern="",  # 텍스트 파일 생성 안 함
        dirname_pattern=str(save_dir / "{target}"),
        quiet=True,
    )

    print(f"[크롤러] {account} 계정에서 최근 {limit}개 포스트 수집 중...")

    try:
        profile = instaloader.Profile.from_username(L.context, account)
    except instaloader.exceptions.ProfileNotExistsException:
        print(f"[오류] 계정 '{account}'을 찾을 수 없습니다.")
        sys.exit(1)
    except Exception as e:
        print(f"[오류] 프로필 로드 실패: {e}")
        sys.exit(1)

    results = []
    for post in profile.get_posts():
        if len(results) >= limit:
            break

        url = post.url

        # 다운로드 실행
        try:
            L.download_post(post, target=profile.username)
            # 저장된 파일 경로 탐색 (shortcode 포함 jpg/png)
            post_dir = save_dir / profile.username
            matched = sorted(post_dir.glob(f"*{post.shortcode}*.jpg")) + \
                      sorted(post_dir.glob(f"*{post.shortcode}*.png"))
            local_path = str(matched[0]) if matched else ""
        except Exception as e:
            print(f"  [다운로드 오류] {post.shortcode}: {e}")
            local_path = ""

        results.append({
            "url": url,
            "local_path": local_path,
            "shortcode": post.shortcode,
            "timestamp": post.date_utc.isoformat(),
            "caption": (post.caption or "")[:100],
        })

        time.sleep(1.0)  # 서버 부하 방지

    print(f"[크롤러] {len(results)}개 포스트 수집 완료 → {save_dir / account}/")
    return results


def main():
    parser = argparse.ArgumentParser(description="인스타그램 공개 계정 이미지 URL 크롤러")
    parser.add_argument("--account", default="torriden_official", help="인스타그램 계정명")
    parser.add_argument("--limit", type=int, default=9, help="수집할 포스트 수")
    parser.add_argument("--download-dir", default="image_crawled", help="이미지 저장 폴더")
    parser.add_argument("--output", default="crawled_images.json", help="결과 저장 파일명")
    args = parser.parse_args()

    posts = fetch_post_image_urls(args.account, args.limit, args.download_dir)

    output_path = Path(args.output)
    output_path.write_text(json.dumps(posts, ensure_ascii=False, indent=2))
    print(f"[크롤러] 결과 저장: {output_path}")

    # 미리보기 출력
    for i, p in enumerate(posts, 1):
        print(f"  {i}. [{p['timestamp'][:10]}] {p['url'][:60]}...")


if __name__ == "__main__":
    main()
