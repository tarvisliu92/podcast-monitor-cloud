#!/usr/bin/env python3
# ============================================================
# check_new_content.py — GitHub Actions version
# Reads all settings from environment variables (set as GitHub secrets)
# ============================================================

import os
import re
import smtplib
import requests
import feedparser
from datetime import datetime, timedelta, timezone
from dateutil import parser as dateparser
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ── settings from environment variables ───────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
YOUTUBE_API_KEY   = os.environ.get("YOUTUBE_API_KEY", "")
GMAIL_SENDER      = os.environ["GMAIL_SENDER"]
GMAIL_PASSWORD    = os.environ["GMAIL_PASSWORD"]
GMAIL_RECIPIENT   = os.environ["GMAIL_RECIPIENT"].split(",")
CLOUD_APP_URL     = os.environ["CLOUD_APP_URL"]
SECRET_KEY        = os.environ["SECRET_KEY"]
LOOKBACK_DAYS     = 8

PODCAST_FEEDS = {
    "Lex Fridman Podcast":          "https://lexfridman.com/feed/podcast/",
    "Acquired":                     "https://feeds.transistor.fm/acquired",
    "80,000 Hours Podcast":         "https://feeds.transistor.fm/80000-hours-podcast",
    "All-In":                       "https://allinchamathjason.libsyn.com/rss",
    "BG2":                          "https://anchor.fm/s/db5b6d74/podcast/rss",
    "Capital Allocators":           "https://tedseides.libsyn.com/rss",
    "Cheeky Pint":                  "https://feeds.transistor.fm/cheeky-pint-with-john-collison",
    "Conversations with Tyler":     "https://feeds.megaphone.fm/conversationswithtyler",
    "Founders":                     "https://podcasts.apple.com/hk/podcast/founders/id1141877104?l=en-GB",
    "David Senra":                  "https://feeds.megaphone.fm/SCIM9007816585",
    "Dwarkesh Podcast":             "https://feeds.megaphone.fm/dwarkesh",
    "Huberman Lab":                 "https://feeds.megaphone.fm/hubermanlab",
    "In Good Company":              "https://feeds.acast.com/public/shows/in-good-company-with-nicolai-tangen",
    "Invest Like The Best":         "https://feeds.megaphone.fm/investlikethebest",
    "Lenny's Podcast":              "https://feeds.megaphone.fm/lennyspodcast",
    "Masters in Business":          "https://podcasts.apple.com/hk/podcast/masters-in-business/id730188152?l=en-GB",
    "Odd Lots":                     "https://www.omnycontent.com/d/playlist/e73c998e-6e60-432f-8610-ae210140c5b1/8a94442e-5a74-4fa2-8b8d-ae27003a8d6b/982f5071-765c-403d-969d-ae27003a8d83/podcast.rss",
    "Old School with Shilo Brooks":  "https://feeds.megaphone.fm/RUNMED9953716923",
    "The a16z Podcast":             "https://feeds.simplecast.com/LpAGSLnY",
    "The Diary of a CEO":           "https://feeds.megaphone.fm/diaryofaceo",
    "The Generalist":               "https://feeds.megaphone.fm/thegeneralist",
    "The Knowledge Project":        "https://feeds.megaphone.fm/knowledgeproject",
    "Y Combinator":                 "https://podcasts.apple.com/hk/podcast/y-combinator-startup-podcast/id1236907421?l=en-GB",
}

KOL_NAMES = [
    "Elon Musk", "Larry Page", "Sergey Brin", "Sundar Pichai",
    "Dario Amodei", "Demis Hassabis", "Mark Zuckerberg", "Satya Nadella",
    "Ilya Sutskever", "Geoffrey Hinton", "Fei-Fei Li", "Yann LeCun",
    "Andrej Karpathy", "Gavin Baker", "Marc Andreessen", "Ben Horowitz",
    "Jensen Huang", "Sam Altman", "Lisa Su", "Lip-Bu Tan",
    "C.C. Wei", "Andrew Feldman",
]

YOUTUBE_TO_PODCAST_MAP = {
    "Lex Fridman":    "https://lexfridman.com/feed/podcast/",
    "Acquired":       "https://feeds.transistor.fm/acquired",
    "Tim Ferriss":    "https://rss.art19.com/tim-ferriss-show",
    "Huberman Lab":   "https://feeds.megaphone.fm/hubermanlab",
    "20VC":           "https://feeds.simplecast.com/JGE3yC0V",
}


# ── helpers ────────────────────────────────────────────────

def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")


def is_recent(date_str):
    if not date_str:
        return True
    try:
        dt = dateparser.parse(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt >= datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    except Exception:
        return True


def fmt_date(date_str):
    if not date_str:
        return ""
    try:
        return dateparser.parse(date_str).strftime("%b %d, %Y")
    except Exception:
        return date_str[:10]


def send_email(subject, body_html):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_SENDER
    msg["To"]      = ", ".join(GMAIL_RECIPIENT)
    msg.attach(MIMEText(body_html, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(GMAIL_SENDER, GMAIL_PASSWORD)
        s.sendmail(GMAIL_SENDER, GMAIL_RECIPIENT, msg.as_string())


# ── podcast polling ────────────────────────────────────────

def check_podcasts():
    items, feed_errors = [], []
    log("Checking podcast feeds...")
    for show, rss_url in PODCAST_FEEDS.items():
        try:
            feed = feedparser.parse(rss_url)
            if feed.bozo and not feed.entries:
                raise ValueError(f"Parse error: {feed.bozo_exception}")
            if not feed.entries:
                log(f"  ⚠ {show}: 0 episodes (skipping)")
                continue
            for entry in feed.entries[:10]:
                uid = entry.get("id") or entry.get("link", "")
                pub = entry.get("published", "")
                if pub and not is_recent(pub):
                    continue
                desc = re.sub(r"<[^>]+>", "",
                    entry.get("summary", "") or entry.get("description", "")).strip()
                audio_url = next(
                    (l["href"] for l in entry.get("links", [])
                     if l.get("type", "").startswith("audio")), None)
                has_transcript = bool(
                    entry.get("content") or
                    any("transcript" in str(l).lower() for l in entry.get("links", [])))
                items.append({
                    "type": "podcast", "uid": uid, "show": show,
                    "title": entry.get("title", "Untitled"),
                    "url": entry.get("link", rss_url),
                    "audio_url": audio_url,
                    "date": fmt_date(pub),
                    "description": desc[:200],
                    "has_transcript": has_transcript,
                    "use_youtube": False,
                })
                log(f"  ✓ {show}: {entry.get('title','')[:60]}")
                break  # only latest episode per show
        except Exception as e:
            feed_errors.append((show, rss_url, str(e)))
            log(f"  ✗ {show}: {e}")
    log(f"Podcasts: {len(items)} new. Parse errors: {len(feed_errors)}")
    return items, feed_errors


# ── KOL YouTube search ─────────────────────────────────────

def check_kol_youtube():
    if not YOUTUBE_API_KEY:
        log("No YouTube API key, skipping.")
        return []
    log("Searching YouTube for KOL appearances...")
    items = []
    try:
        from googleapiclient.discovery import build
        yt = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
        published_after = (datetime.now(timezone.utc) -
                           timedelta(days=LOOKBACK_DAYS)).isoformat()
        for kol in KOL_NAMES:
            try:
                res = yt.search().list(
                    q=kol, part="snippet", type="video",
                    publishedAfter=published_after,
                    videoDuration="long",
                    order="date", maxResults=3,
                ).execute()
                for item in res.get("items", []):
                    vid_id  = item["id"]["videoId"]
                    snippet = item["snippet"]
                    channel = snippet.get("channelTitle", "")
                    pub     = snippet.get("publishedAt", "")
                    podcast_rss = next(
                        (rss for key, rss in YOUTUBE_TO_PODCAST_MAP.items()
                         if key.lower() in channel.lower()), None)
                    items.append({
                        "type": "kol", "uid": f"yt_{vid_id}", "kol": kol,
                        "title": snippet.get("title", ""),
                        "channel": channel,
                        "url": f"https://www.youtube.com/watch?v={vid_id}",
                        "date": fmt_date(pub),
                        "description": snippet.get("description", "")[:200],
                        "podcast_url": None,
                        "audio_url": None,
                        "has_transcript": False,
                        "use_youtube": podcast_rss is None,
                    })
                    log(f"  ✓ {kol} on {channel}: {snippet.get('title','')[:50]}")
                    break  # one result per KOL
            except Exception as e:
                log(f"  ✗ {kol}: {e}")
    except Exception as e:
        log(f"  ✗ YouTube API: {e}")
    log(f"KOL: {len(items)} appearances.")
    return items


# ── push to cloud & email ──────────────────────────────────

def push_to_cloud(items):
    try:
        r = requests.post(
            f"{CLOUD_APP_URL}/ingest",
            json={"secret": SECRET_KEY, "items": items},
            timeout=15)
        r.raise_for_status()
        log(f"Pushed {len(items)} items to cloud app ✓")
    except Exception as e:
        log(f"Cloud push failed: {e}")


def send_feed_error_alert(feed_errors):
    rows = "".join(
        f"<tr><td style='padding:8px;border-bottom:1px solid #eee;'><b>{n}</b></td>"
        f"<td style='padding:8px;border-bottom:1px solid #eee;color:#c0392b;'>{e}</td></tr>"
        for n, u, e in feed_errors)
    html = f"""<html><body style="font-family:Arial,sans-serif;max-width:700px;margin:auto;">
      <h2 style="color:#c0392b;">⚠️ RSS Feed Errors — {datetime.now().strftime('%b %d, %Y')}</h2>
      <p>{len(feed_errors)} feed(s) had parse errors. Update URLs in check_new_content.py on GitHub.</p>
      <table width="100%">{rows}</table>
    </body></html>"""
    try:
        send_email(f"⚠️ {len(feed_errors)} broken RSS feed(s)", html)
        log("Feed error alert sent.")
    except Exception as e:
        log(f"Could not send error alert: {e}")


def format_digest_html(podcast_items, kol_items):
    date_str = datetime.now().strftime("%A, %B %d %Y")
    rows_p = "".join(f"""
    <tr><td style="padding:10px;border-bottom:1px solid #eee;">
      <b>{i['show']}</b><br>
      <a href="{i['url']}">{i['title']}</a><br>
      <small style="color:#888;">{i['date']} — {i['description'][:120]}...</small>
    </td></tr>""" for i in podcast_items)

    rows_k = "".join(f"""
    <tr><td style="padding:10px;border-bottom:1px solid #eee;">
      <b>{i['kol']}</b> on <i>{i['channel']}</i><br>
      <a href="{i['url']}">{i['title']}</a><br>
      <small style="color:#888;">{i['date']}</small>
    </td></tr>""" for i in kol_items)

    return f"""<html><body style="font-family:Arial,sans-serif;max-width:700px;margin:auto;color:#333;">
      <h2>📻 Content Digest — {date_str}</h2>
      <p style="background:#fffbe6;padding:12px;border-left:4px solid #f0a500;border-radius:4px;">
        <b>To summarize:</b> Open <a href="{CLOUD_APP_URL}">{CLOUD_APP_URL}</a>,
        select episodes, hit Summarize.
      </p>
      <h3>New Episodes ({len(podcast_items)})</h3>
      {'<table width="100%">' + rows_p + '</table>' if podcast_items else '<p>None found.</p>'}
      <h3>KOL Appearances ({len(kol_items)})</h3>
      {'<table width="100%">' + rows_k + '</table>' if kol_items else '<p>None found.</p>'}
    </body></html>"""


# ── main ───────────────────────────────────────────────────

def main():
    log("=" * 55)
    log("GitHub Actions — checking for new content...")

    podcast_items, feed_errors = check_podcasts()
    kol_items = check_kol_youtube()
    all_items = podcast_items + kol_items

    if feed_errors:
        send_feed_error_alert(feed_errors)

    if not all_items:
        log("No new content found.")
        return

    push_to_cloud(all_items)

    try:
        html = format_digest_html(podcast_items, kol_items)
        send_email(
            f"📻 Content Digest — {len(all_items)} new items ({datetime.now().strftime('%b %d')})",
            html)
        log("Digest email sent ✓")
    except Exception as e:
        log(f"Email failed: {e}")

    log(f"Done. {len(all_items)} items pushed.")


if __name__ == "__main__":
    main()
