#!/usr/bin/env python3
"""YouTube Data API v3 — поиск видео и чтение описаний/комментариев."""

import os
import sys
import json
import argparse
import requests

PROXY = os.getenv("AGENT_PROXY", "")
PROXIES = {"http": PROXY, "https": PROXY}

API_KEY = os.getenv("YOUTUBE_API_KEY", "")
BASE = "https://www.googleapis.com/youtube/v3"


def api_get(endpoint, params):
    params["key"] = API_KEY
    r = requests.get(f"{BASE}/{endpoint}", params=params, proxies=PROXIES, timeout=30)
    r.raise_for_status()
    return r.json()


def search_videos(query, max_results=10, order="relevance"):
    """Поиск видео по запросу."""
    data = api_get("search", {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": max_results,
        "order": order,
        "relevanceLanguage": "ru",
    })
    results = []
    for item in data.get("items", []):
        vid = item["id"]["videoId"]
        snip = item["snippet"]
        results.append({
            "video_id": vid,
            "title": snip["title"],
            "channel": snip["channelTitle"],
            "published": snip["publishedAt"][:10],
            "description_preview": snip["description"][:300],
            "url": f"https://youtube.com/watch?v={vid}",
        })
    return results


def get_video_details(video_id):
    """Полное описание видео."""
    data = api_get("videos", {
        "part": "snippet,statistics",
        "id": video_id,
    })
    items = data.get("items", [])
    if not items:
        return None
    item = items[0]
    snip = item["snippet"]
    stats = item.get("statistics", {})
    return {
        "video_id": video_id,
        "title": snip["title"],
        "channel": snip["channelTitle"],
        "published": snip["publishedAt"][:10],
        "description": snip["description"],
        "views": stats.get("viewCount", "?"),
        "likes": stats.get("likeCount", "?"),
        "url": f"https://youtube.com/watch?v={video_id}",
    }


def get_comments(video_id, max_results=50):
    """Топ комментарии к видео."""
    data = api_get("commentThreads", {
        "part": "snippet",
        "videoId": video_id,
        "maxResults": max_results,
        "order": "relevance",
    })
    results = []
    for item in data.get("items", []):
        top = item["snippet"]["topLevelComment"]["snippet"]
        results.append({
            "author": top["authorDisplayName"],
            "text": top["textDisplay"][:500],
            "likes": top["likeCount"],
        })
    return results


def main():
    parser = argparse.ArgumentParser(description="YouTube API skill")
    sub = parser.add_subparsers(dest="cmd")

    p_search = sub.add_parser("search", help="Поиск видео")
    p_search.add_argument("query", help="Поисковый запрос")
    p_search.add_argument("-n", type=int, default=10, help="Количество результатов")

    p_info = sub.add_parser("info", help="Полное описание видео")
    p_info.add_argument("video_id", help="ID видео или URL")

    p_comments = sub.add_parser("comments", help="Комментарии к видео")
    p_comments.add_argument("video_id", help="ID видео или URL")
    p_comments.add_argument("-n", type=int, default=50)

    p_find = sub.add_parser("find-links", help="Поиск видео + извлечение ссылок из описания")
    p_find.add_argument("query", help="Поисковый запрос")
    p_find.add_argument("-n", type=int, default=5)

    args = parser.parse_args()

    if not API_KEY:
        print("ERROR: YOUTUBE_API_KEY не задан. Добавь в ~/.shectory-assist.env:", file=sys.stderr)
        print("  YOUTUBE_API_KEY=AIza...", file=sys.stderr)
        sys.exit(1)

    if args.cmd == "search":
        results = search_videos(args.query, args.n)
        for r in results:
            print(f"\n🎬 {r['title']}")
            print(f"   📺 {r['channel']} | {r['published']}")
            print(f"   🔗 {r['url']}")
            if r['description_preview']:
                print(f"   📝 {r['description_preview'][:150]}...")

    elif args.cmd == "info":
        vid_id = args.video_id.split("v=")[-1].split("&")[0] if "youtube" in args.video_id else args.video_id
        d = get_video_details(vid_id)
        if d:
            print(f"🎬 {d['title']}")
            print(f"📺 {d['channel']} | {d['published']}")
            print(f"👁 {d['views']} просмотров | 👍 {d['likes']}")
            print(f"🔗 {d['url']}")
            print(f"\n📝 ОПИСАНИЕ:\n{d['description']}")
        else:
            print("Видео не найдено")

    elif args.cmd == "comments":
        vid_id = args.video_id.split("v=")[-1].split("&")[0] if "youtube" in args.video_id else args.video_id
        comments = get_comments(vid_id, args.n)
        for c in comments:
            print(f"\n👤 {c['author']} (👍{c['likes']})")
            print(f"   {c['text']}")

    elif args.cmd == "find-links":
        import re
        results = search_videos(args.query, args.n)
        url_pattern = re.compile(r'https?://[^\s\)\]]+')
        for r in results:
            d = get_video_details(r["video_id"])
            if not d:
                continue
            links = url_pattern.findall(d["description"])
            print(f"\n🎬 {d['title']}")
            print(f"   🔗 {d['url']}")
            if links:
                print(f"   📎 Ссылки в описании ({len(links)}):")
                for link in links[:10]:
                    print(f"      • {link}")
            else:
                print("   📎 Ссылок в описании нет")


if __name__ == "__main__":
    main()
