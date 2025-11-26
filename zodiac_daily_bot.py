# zodiac_daily_bot.py

import os
import base64
import openai
from openai import OpenAI
import requests
from datetime import datetime, timedelta, timezone
from PIL import Image, ImageDraw, ImageFont
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask
import re
import base64
from dotenv import load_dotenv
from moviepy.editor import ImageClip, concatenate_videoclips, AudioFileClip, CompositeVideoClip, VideoFileClip
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from pytz import timezone
from zoneinfo import ZoneInfo
import feedparser
import json
from newsdataapi import NewsDataApiClient
from bs4 import BeautifulSoup
import textwrap
import glob
import random
import numpy as np
from typing import List, Dict, Any
import html


load_dotenv()

os.environ["IMAGEMAGICK_BINARY"] = "/usr/bin/convert"
YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

timestamps = {}

# ========== 환경 설정 ==========
# API Key 설정 (환경변수 또는 직접 입력)
NEWSDATA_API_KEY = os.getenv("NEWSDATA_API_KEY")
api = NewsDataApiClient(apikey=NEWSDATA_API_KEY)


IG_ACCESS_TOKEN = os.environ.get("IG_ACCESS_TOKEN")
IG_USER_ID = os.environ.get("IG_USER_ID")

ZODIACS = ["쥐", "소", "호랑이", "토끼", "용", "뱀", "말", "양", "원숭이", "닭", "개", "돼지"]
ZODIACS_star = ["물병", "물고기", "양", "황소", "쌍둥이", "게", "사자", "처녀", "천칭", "전갈", "사수", "염소"]

# BASE_DIR = "zodiac-daily-bot"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BG_DIR = os.path.join(BASE_DIR, "backgrounds")
OUT_DIR = os.path.join(BASE_DIR, "results")
# BG_DIR = "backgrounds"
# OUT_DIR = "results"
FONT_PATH = os.path.join(BASE_DIR, "fonts", "나눔손글씨 느릿느릿체.ttf")
FONT_SIZE = 90
TEXT_BOX = (190, 700, 830, 1500)  # (x1, y1, x2, y2) 좌표


####### 기사 관련 설정

# 뉴스 관련 파일 경로 설정
NEWS_SOURCE_FILE = os.path.join(BASE_DIR, "news_source_id_div.json")
ARTICLES_FILE = os.path.join(BASE_DIR, f"us_newsdata_articles.json")
UNKNOWN_SOURCE_FILE = os.path.join(BASE_DIR, "unknown_sources.txt")

# INTRO_BG = os.path.join(BG_DIR, "intro_bg.png")
# BODY_BG = os.path.join(BG_DIR, "body_bg.png")
OUTRO_BG = os.path.join(BG_DIR, "outro_bg.png")

OUTPUT_INTRO = os.path.join(OUT_DIR, "intro_output.jpg")
OUTPUT_BODY = os.path.join(OUT_DIR, "body_output")
OUTPUT_OUTRO = os.path.join(OUT_DIR, "outro_output.jpg")


os.makedirs(BG_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)



# ========== 경제 뉴스 관련 함수들 ==========

def get_news_from_html():
    # news_source_id_div.json 불러오기
    with open(NEWS_SOURCE_FILE, "r", encoding="utf-8") as f:
        source_rules = json.load(f)

    # source_name → rule 매핑
    source_map = {item["source_name"].strip(): item for item in source_rules}

    # 기사 리스트 불러오기
    with open(ARTICLES_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)

    collected_articles = []  # 전체 기사 본문
    unknown_sources = set()  # 못 찾은 source_name

    for article in articles:
        source_name = article.get("source_name").strip()
        link = article.get("link")
        source_url = article.get("source_url", "")

        if not link or not source_name:
            print("Missing link or source_name, skipping...")
            continue

        print(f"Processing: {source_name} | {link}")

        try:
            # HTML 가져오기
            response = requests.get(link, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            if source_name in source_map:
                rule = source_map[source_name]
                attr = rule.get("attribute")
                value = rule.get("value", "")

                extracted_text = ""

                if attr == "article":
                    # <article> 태그 모두
                    articles_html = soup.find_all("article")
                    extracted_text = "\n".join(a.get_text(strip=True) for a in articles_html)

                elif attr == "class":
                    elems = soup.find_all(class_=value)
                    extracted_text = "\n".join(e.get_text(strip=True) for e in elems)

                elif attr == "id":
                    elems = soup.find_all(id=value)
                    extracted_text = "\n".join(e.get_text(strip=True) for e in elems)

                else:
                    print(f"Unknown attribute for {source_name}: {attr}")

                collected_articles.append({
                    "source_name": source_name,
                    "link": link,
                    "content": extracted_text.strip()
                })

            else:
                # source_name이 rules에 없음
                unknown_sources.add((source_name, source_url))

        except Exception as e:
            print(f"Error processing {link}: {e}")
            unknown_sources.add((source_name, source_url))

    # unknown_sources.txt 파일 저장 (추가 모드)
    if unknown_sources:
        lines = [f"{name} | {url}" for name, url in sorted(unknown_sources)]
        if not os.path.exists(UNKNOWN_SOURCE_FILE):
            with open(UNKNOWN_SOURCE_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        else:
            with open(UNKNOWN_SOURCE_FILE, "a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")

    # 결과 출력
    print("\n=== 전체 기사 본문 ===")
    for idx, art in enumerate(collected_articles, start=1):
        print(f"[{idx}] {art['source_name']} ({art['link']})")
        print(art["content"][:400], "...\n")  # 앞부분 500자만 출력

    print("\n=== 못 찾은 source_name 목록 ===")
    for su, s in sorted(unknown_sources):
        print("-", su,":",s)

    return collected_articles

# 시간 범위 설정 (전날 7시 30분 ~ 현재 시간)
def get_time_range_iso():
    now = datetime.utcnow() + timedelta(hours=9)
    start = now - timedelta(days=1)
    start = start.replace(hour=7, minute=30, second=0, microsecond=0)
    return start.isoformat(), now.isoformat()

def fetch_newsdata_articles(q=None, country=None, language=None, category=None):
    # 최신 뉴스 endpoint (/1/news)
    params = {}
    if country:
        params["country"] = country
    if language:
        params["language"] = language
    if category:
        params["category"] = category
    if q:
        params["q"] = q  # '테슬라' 관련 기사만 필터링
    resp = api.news_api(**params)
    return resp.get("results", [])



RSS_FEEDS = {
    "kr": [
        "https://www.hankyung.com/feed/economy",
        "https://rss.etnews.com/Section901.xml",
        "https://www.mk.co.kr/rss/30000001/",
        "https://rss.edaily.co.kr/rss/economy.xml",
    ],
    "global": [
        "https://feeds.bbci.co.uk/news/business/rss.xml",
        "https://www.cnbc.com/id/10001147/device/rss/rss.html",
    ],
    "us": [
        "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258",  # CNBC 경제
        "https://feeds.content.dowjones.io/wsj/business",  # WSJ 비즈니스 (예시 URL)
    ]
}

def get_time_range():
    now = datetime.utcnow() + timedelta(hours=9)  # 한국 시간
    end_time = now
    start_time = now - timedelta(days=1)
    start_time = start_time.replace(hour=7, minute=30, second=0, microsecond=0)
    return start_time, end_time

def fetch_rss_articles(region):
    start_time, end_time = get_time_range()
    articles = []
    for feed_url in RSS_FEEDS.get(region, []):
        feed = feedparser.parse(feed_url)
        for entry in feed.entries:
            published = entry.get("published_parsed")
            if not published:
                continue
            pub_time = datetime(*published[:6])
            if start_time <= pub_time <= end_time:
                articles.append({
                    "title": entry.title,
                    "link": entry.link,
                    "published": pub_time.isoformat(),
                    "summary": entry.get("summary", ""),
                })
    return articles

def save_articles(region, source, articles):
    # date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"{region}_{source}_articles.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    print(f"[SAVED] {len(articles)}개 기사 저장 완료 → {filename}")


def summarize_articles(articles, target):
    summarized_results = []

    for idx, art in enumerate(articles, start=1):
        if len(summarized_results) >= 3:
            break  # 3개까지만 요약하고 반복 중지
        article = clean_emoji_text(art["content"])
        try:
            # GPT에게 요청할 프롬프트
            prompt = (
                "아래 기사를 주가에 영향을 줄 수 있는 핵심 내용 위주로 요약해 주세요\n"
                "모든 내용은 실제 기사 내용에서 인용해야 하고, 없는 사실을 지어내면 안됩니다.\n"
                "각 줄은 간결하고 명확해야 하며, 주제를 분명히 드러내야 합니다.\n"
                "원문 그대로의 언어로 요약해 주세요\n\n"
                f"간혹 광고 내용이 포함되어 있을 수 있습니다. {target}과 관련 없는 광고 내용의 경우엔 제외하고 요약해 주세요.\n\n"
                f"기사 내용:\n{article}"
            )
            print("기사 길이 : ", len(article))

            if len(article) > 10:
                response = openai.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "당신은 뉴스 요약 전문가입니다."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0
                    # max_tokens=300
                )

                summary = response.choices[0].message.content.strip()
                if len(summary) < 3:
                    print(f"[{idx}] 요약 실패: 요약이 너무 짧습니다.")
                    continue
                elif len(summary) > 50:
                    print(f"[{idx}] 요약 : 요약이 너무 깁니다. 다시 한 번 요약하겠습니다.")
                    response = openai.chat.completions.create(
                        model="gpt-4.1",
                        messages=[
                            {"role": "system", "content": "당신은 경제 뉴스 요약 전문가입니다."},
                            {"role": "user", "content": "핵심 내용 위주로, 없는 사실을 지어내지 말고 요약해 주세요. 가능한 주가와 관련 있을 만한 경제적인 내용은 요약 시에 포함시켜 주세요. 최종 출력은 한글로 번역해서 출력하세요. 다음의 요약된 기사를 한글 기준 250자 내로 다시 요약해 주세요.\n요약 기사 : " + summary}
                        ],
                        temperature=0
                        # max_tokens=300
                    )
                    summary = response.choices[0].message.content.strip()


                print(f"[{idx}] 1차 요약 : {summary}")


                response = openai.chat.completions.create(
                    model="gpt-4.1",
                    messages=[
                        {"role": "system", "content": "대답은 OK 또는 NO로만 대답하세요."},
                        {"role": "user", "content": f"이 요약이 {target}과 직/간접적으로 관련이 있는 기사가 정말 맞나요? {target}에 대한 최신 기준의 웹 서치 확인 후 답변해 주세요. 요약 : {summary}"}
                    ],
                    temperature=0
                    # max_tokens=300
                )

                if response.choices[0].message.content.strip().lower() != "ok":
                    print(f"[{idx}] 요약 생략: {target}과 관련 없는 기사입니다.")
                    continue

                response = openai.chat.completions.create(
                    model="gpt-4.1",
                    messages=[
                        {"role": "system", "content": "대답은 OK 또는 NO로만 대답하세요."},
                        {"role": "user", "content": f"지금 주어지는 '요약'과 중복되는 내용이 주어지는 '배열' 안에 있나요?\n'요약' : {summary}\n'배열' : {summarized_results}\n"}
                    ],
                    temperature=0
                    # max_tokens=300
                )

                if response.choices[0].message.content.strip().lower() == "ok":
                    print(f"[{idx}] 요약 생략: 중복되는 내용이 있습니다.")
                    print(f"[{idx}] 요약 : {summary}")
                    print("배열 : ", summarized_results)
                    continue

                summarized_results.append(summary)

                print(f"[{idx}] 요약 완료:")
                print(summary)
                print("=" * 50)
                print("요약 길이 : ", len(summary))
            else:
                print(f"[{idx}] 요약 생략: 기사 길이가 너무 짧습니다.")
                # summarized_results.append("기사 길이가 너무 짧아 요약할 수 없습니다.")

        except Exception as e:
            print(f"[{idx}] 요약 실패: {e}")
            # summarized_results.append("요약 실패")

    return summarized_results

# ===== 유틸: 테두리 + 반투명 박스 텍스트 =====
def draw_text_with_box(img, text, position, font, text_color, box_color, outline_color):
    # draw는 원본 이미지의 draw 객체
    draw = ImageDraw.Draw(img, "RGBA")
    text_bbox = draw.textbbox(position, text, font=font)
    box_padding = 10
    box_coords = (
        text_bbox[0] - box_padding,
        text_bbox[1] - box_padding,
        text_bbox[2] + box_padding,
        text_bbox[3] + box_padding
    )
    # 1. 오버레이 이미지 생성
    overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rectangle(box_coords, fill=box_color)
    # 2. 원본과 오버레이 합성
    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img, "RGBA")
    # 3. 테두리 효과
    x, y = position
    for dx in [-1, 1]:
        for dy in [-1, 1]:
            draw.text((x + dx, y + dy), text, font=font, fill=outline_color)
    # 4. 본문 텍스트
    draw.text(position, text, font=font, fill=text_color)
    return img  # 필요시 반환

def delete_body_images():
    """
    OUTPUT_BODY로 시작하는 모든 jpg 파일 삭제
    """
    pattern = f"{OUTPUT_BODY}*.jpg"
    files = glob.glob(pattern)
    for file in files:
        try:
            os.remove(file)
            print(f"삭제됨: {file}")
        except Exception as e:
            print(f"파일 삭제 오류: {file} - {e}")

# ===== 인트로 이미지 생성 =====
def create_intro_image_news(target_en, target_kr):
    # 본문 이미지 생성 전 기존 이미지 삭제
    delete_body_images()

    date_str = datetime.now().strftime("%Y.%m.%d")
    lines = [date_str, target_kr, "관련 뉴스"]

    intro_bg = os.path.join(BG_DIR, "intro_bg_"+target_en.split(" ")[0]+".png")
    # intro_bg가 없으면 fallback으로 대체
    if not os.path.exists(intro_bg):
        print(f"[경고] 파일이 존재하지 않습니다: {intro_bg}, 대체 이미지로 전환합니다.")
        intro_bg = os.path.join(BG_DIR, "intro_bg_business.png")

    img = Image.open(intro_bg).convert("RGBA")
    W, H = img.size
    draw = ImageDraw.Draw(img, "RGBA")

    # 폰트 크기 조정 (전체 높이의 절반 차지)
    font_size = 10
    font = ImageFont.truetype(FONT_PATH, font_size)
    while True:
        font = ImageFont.truetype(FONT_PATH, font_size)
        total_height = sum([draw.textbbox((0,0), line, font=font)[3] for line in lines])
        if total_height >= H * 0.5:
            break
        font_size += 2

    y_offset = (H - total_height) // 2
    for line in lines:
        w, h = draw.textsize(line, font=font)
        x = (W - w) // 2
        img = draw_text_with_box(img, line, (x, y_offset), font, "white", (0, 0, 0, 150), "black")
        draw = ImageDraw.Draw(img, "RGBA")  # draw 객체 갱신
        y_offset += h + 10

    img.convert("RGB").save(OUTPUT_INTRO)

def split_korean_sentences(text):
    # 한글 기준 문장 분리 (마침표, 물음표, 느낌표 뒤에 줄바꿈)
    sentences = re.split(r'(?<=[.?!])\s+', text.strip())
    # 빈 문장 제거
    return [s for s in sentences if s]


# ===== 본문 이미지 생성 =====
def create_body_image(text, idx, target):
    # 1. idx 붙이기
    text = f"{(idx+1)}) {text}"
    # 2. 문장 분리
    sentences = split_korean_sentences(text)
    # 🔥 HTML escape 제거
    sentences = [html.unescape(s).strip() for s in sentences]

    # 한 문장씩 묶기
    pages = []
    buffer = ""
    # for i in range(len(sentences)):
    #     page_text = sentences[i]
    #     pages.append(page_text)
    for sent in sentences:
        # 🔥 숫자 + '.' 형식인지 체크 (예: "1.", "2.", "10.")
        if re.fullmatch(r"\d+\.", sent):
            # 기존 buffer가 비어있지 않으면 먼저 저장
            if buffer.strip():
                pages.append(buffer.strip())
                buffer = ""
            # 넘버링은 단독 페이지
            pages.append(sent)
            continue

        # ------- 일반 문장 처리 -------
        # 현재 버퍼 + 문장을 합쳤을 때 50자 이하이면 같은 페이지로 묶기
        if len(buffer) + len(sent) <= 50:
            if buffer == "":
                buffer = sent
            else:
                buffer += " " + sent
        else:
            # 50자를 넘으면 현재 페이지 저장하고 새 페이지 시작
            if buffer.strip():
                pages.append(buffer.strip())
            buffer = sent

    # 버퍼 안 남아있으면 마지막으로 저장
    if buffer.strip():
        pages.append(buffer.strip())


    saved_files = []
    for page_num, page_text in enumerate(pages, start=1):
        body_bg = os.path.join(BG_DIR, "body_bg_"+target+".png")
        # intro_bg가 없으면 fallback으로 대체
        if not os.path.exists(body_bg):
            print(f"[경고] 파일이 존재하지 않습니다: {body_bg}, 대체 이미지로 전환합니다.")
            body_bg = os.path.join(BG_DIR, "body_bg_tesla.png")
        
        img = Image.open(body_bg).convert("RGBA")
        W, H = img.size
        draw = ImageDraw.Draw(img, "RGBA")

        # 폰트 크기 맞추기
        font_size = 50
        while True:
            font = ImageFont.truetype(FONT_PATH, font_size)
            wrapped = textwrap.fill(page_text, width=20)
            tw, th = draw.multiline_textsize(wrapped, font=font, spacing=10)
            if tw > W * 0.9 or th > H * 0.9:
                font_size -= 2
                font = ImageFont.truetype(FONT_PATH, font_size)
                wrapped = textwrap.fill(page_text, width=20)
                break
            font_size += 2

        tw, th = draw.multiline_textsize(wrapped, font=font, spacing=10)
        x = (W - tw) // 2
        y = (H - th) // 2

        # 반투명 박스
        box_coords = (x - 20, y - 20, x + tw + 20, y + th + 20)
        overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rectangle(box_coords, fill=(0, 0, 0, 150))
        img = Image.alpha_composite(img, overlay)
        draw = ImageDraw.Draw(img, "RGBA")

        # 테두리 + 텍스트
        for dx in [-1, 1]:
            for dy in [-1, 1]:
                draw.multiline_text((x + dx, y + dy), wrapped, font=font, fill="black", spacing=10)
        draw.multiline_text((x, y), wrapped, font=font, fill="white", spacing=10)

        out_path = f"{OUTPUT_BODY}{str(idx)}_{page_num}.jpg"
        img.convert("RGB").save(out_path)
        saved_files.append(out_path)
    return saved_files

# ===== 아웃트로 이미지 =====
def create_outro_image():
    # outro_bg = os.path.join(BG_DIR, "outro_bg_"+target+".png")
    img = Image.open(OUTRO_BG)
    img.save(OUTPUT_OUTRO)


def extract_numbers(filename):
    # body_output{idx}_{page}.jpg에서 idx와 page를 추출
    m = re.search(r'body_output(\d+)_(\d+)\.jpg', filename)
    if m:
        return int(m.group(1)), int(m.group(2))
    return 0, 0

def create_youtube_shorts_video(intro_path, body_dir, outro_path, bgm_path, output_path):
    # 본문 이미지들: body_output{idx}_{page}.jpg 형식 모두 사용
    body_images = sorted(
        [f for f in os.listdir(body_dir) if f.startswith("body_output") and f.endswith(".jpg")],
        key=extract_numbers
    )
    num_intro = 1
    num_body = len(body_images)
    num_outro = 1
    total_images = num_intro + num_body + num_outro

    # 기본값
    intro_duration = 3
    body_duration = 3
    outro_duration = 2

    # 총 길이 계산 및 조정
    total_duration = intro_duration + body_duration * num_body + outro_duration
    target_duration = 60

    # 본문이 많을 때 자동 조정
    if total_duration > target_duration:
        # 본문 길이 최소 2초로 조정
        body_duration = max(2, (target_duration - 6) // num_body)
        # 인트로/아웃트로는 2~4초 사이로 조정
        intro_duration = min(max(2, intro_duration), 4)
        outro_duration = min(max(2, outro_duration), 4)
        # 다시 총 길이 계산
        total_duration = intro_duration + body_duration * num_body + outro_duration
        # 남은 시간 분배
        if total_duration < target_duration:
            remain = target_duration - (body_duration * num_body)
            # 인트로/아웃트로에 남은 시간 분배 (최대 4초까지)
            intro_duration = min(4, remain // 2)
            outro_duration = min(4, remain - intro_duration)
        # 최종 체크
        total_duration = intro_duration + body_duration * num_body + outro_duration
        if total_duration > target_duration:
            # 아웃트로부터 줄임
            diff = total_duration - target_duration
            outro_duration = max(2, outro_duration - diff)

    clips = []

    # 1. 인트로 이미지
    intro_clip = ImageClip(intro_path).set_duration(intro_duration)
    clips.append(intro_clip)

    # 2. 본문 이미지들
    for img_file in body_images:
        img_path = os.path.join(body_dir, img_file)
        body_clip = ImageClip(img_path).set_duration(body_duration)
        clips.append(body_clip)

    # 3. 아웃트로 이미지
    outro_clip = ImageClip(outro_path).set_duration(outro_duration)
    clips.append(outro_clip)

    # 4. 세로(9:16) 유튜브 쇼츠 사이즈 맞추기
    clips = [clip.resize(height=1920).resize(width=1080) for clip in clips]

    # 5. 영상 합치기
    final_clip = concatenate_videoclips(clips, method="compose")

    # 6. BGM 설정
    bgm = AudioFileClip(bgm_path).volumex(0.5)  # 배경음악 볼륨 조절
    final_clip = final_clip.set_audio(bgm.set_duration(final_clip.duration))

    # 7. 저장
    final_clip.write_videofile(output_path, fps=30, codec='libx264', audio_codec='aac')

# ===== 텍스트 이미지 생성 함수 =====
def create_caption_image(text, output_path, size=(1080, 1920), font_path=None, font_size=50):
    """
    반투명 박스 + 중앙 텍스트 PNG 이미지 생성
    """
    img = Image.new("RGBA", size, (0, 0, 0, 0))  # 완전 투명 배경
    draw = ImageDraw.Draw(img)

    # 이미지 크기
    image_width, image_height = img.size

    max_text_height = image_height * 0.4
    max_text_width = image_width * 0.8

    # 폰트 로딩
    font_size_init = 10
    if font_path:
        font_size = font_size_init
        while True:
            font = ImageFont.truetype(font_path, font_size)
            # 테스트 줄바꿈
            lines = wrap_text_by_pixel(text, font, max_text_width, draw)
            line_heights = [draw.textbbox((0,0), line, font=font)[3] for line in lines]
            total_height = sum(line_heights) + 10*(len(lines)-1)
            if total_height >= max_text_height or font_size > 200:
                break
            font_size += 2
    else:
        font = ImageFont.load_default()
        lines = wrap_text_by_pixel(text, font, max_text_width, draw)
        line_heights = [draw.textbbox((0,0), line, font=font)[3] for line in lines]

    spacing = 10
    total_height = sum(line_heights) + spacing*(len(lines)-1)

    # 박스 영역
    box_width = max_text_width + 40
    box_height = total_height + 40
    box_x = (size[0] - box_width)//2
    box_y = (size[1] - box_height)//2

    # 반투명 박스
    draw.rectangle(
        (box_x, box_y, box_x + box_width, box_y + box_height),
        fill=(0, 0, 0, 150)
    )

    # 텍스트 중앙 정렬
    y_text = box_y + 20
    for line, h in zip(lines, line_heights):
        w = draw.textbbox((0, 0), line, font=font)[2]
        x = (size[0] - w)//2
        # 테두리 효과
        for dx in [-1, 1]:
            for dy in [-1, 1]:
                draw.text((x+dx, y_text+dy), line, font=font, fill=(0,0,0,255))
        draw.text((x, y_text), line, font=font, fill=(255,255,255,255))
        y_text += h + spacing

    # PNG로 저장 (반투명 유지)
    img.save(output_path, format="PNG")


# ===== 픽셀 기반 줄바꿈 =====
def wrap_text_by_pixel(text, font, max_width, draw):
    words = text.split()
    lines = []
    current_line = ""
    for word in words:
        test_line = f"{current_line} {word}".strip()
        if draw.textlength(test_line, font=font) <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)
    return lines

# ===== 메모리 기반 캡션 이미지 생성 =====
def create_caption_image_array(text, size=(1080, 1920), font_path=None):
    text = html.unescape(text or "")
    
    img = Image.new("RGBA", size, (0,0,0,0))
    draw = ImageDraw.Draw(img)

    image_width, image_height = img.size
    max_text_height = image_height * 0.4
    max_text_width = image_width * 0.8

    # 폰트 로딩
    font_size = 10
    if font_path:
        while True:
            font = ImageFont.truetype(font_path, font_size)
            lines = wrap_text_by_pixel(text, font, max_text_width, draw)
            line_heights = [draw.textbbox((0,0), line, font=font)[3] for line in lines]
            # line_heights = [(font.getbbox(line)[3] - font.getbbox(line)[1]) for line in lines]
            total_height = sum(line_heights) + 10*(len(lines)-1)
            # max_width = max([draw.textlength(line, font=font) for line in lines])
            max_width = max([font.getlength(line) for line in lines])
            if total_height >= max_text_height or max_width >= max_text_width or font_size > 200:
                break
            font_size += 2
    else:
        font = ImageFont.load_default()
        lines = wrap_text_by_pixel(text, font, max_text_width, draw)
        line_heights = [draw.textbbox((0,0), line, font=font)[3] for line in lines]

    spacing = 10
    total_height = sum(line_heights) + spacing*(len(lines)-1)

    # 박스 영역
    box_width = max_text_width + 40
    box_height = total_height + 40
    box_x = (size[0] - box_width)//2
    box_y = (size[1] - box_height)//2

    # 반투명 박스
    draw.rectangle(
        (box_x, box_y, box_x + box_width, box_y + box_height),
        fill=(0,0,0,150)
    )

    # 텍스트 중앙 정렬
    y_text = box_y + 20
    for line, h in zip(lines, line_heights):
        # w = draw.textbbox((0,0), line, font=font)[2]
        bbox = font.getbbox(line)
        w = bbox[2] - bbox[0]
        x = (size[0]-w)//2
        # 테두리
        for dx in [-1,1]:
            for dy in [-1,1]:
                draw.text((x+dx, y_text+dy), line, font=font, fill=(0,0,0,255))
        draw.text((x, y_text), line, font=font, fill=(255,255,255,255))
        y_text += h + spacing

    # PIL -> Numpy Array (MoviePy ImageClip 사용 가능)
    return np.array(img)

# ===== 본 영상 생성 함수 (개선판, summary별 다른 배경 영상 + 번호 붙이기) =====
def create_news_shorts_video_with_bgvideo_fast(
    target_en, summaries, bg_dir, out_dir, bgm_path, output_path,
    duration_per_caption=3, target_kr="테슬라", font_path=None
):
    # 1. 배경 영상 리스트 구성
    video_candidates = [f for f in os.listdir(bg_dir) if f.endswith(".mp4")]
    target_videos = [f for f in video_candidates if target_en.lower() in f.lower()]
    business_videos = [f for f in video_candidates if f.startswith("business")]

    if not target_videos and not business_videos:
        raise FileNotFoundError("적절한 배경 영상(mp4)이 backgrounds 폴더에 없습니다.")

    # summary 수 만큼 배경 영상 리스트 생성
    bg_video_list = []
    for i in range(len(summaries)+3):
        if i < len(target_videos):
            bg_video_list.append(target_videos[i])
        else:
            bg_video_list.append(random.choice(business_videos))

    # 2. intro/outro 이미지
    create_intro_image_news(target_en, target_kr)
    intro_img_path = OUTPUT_INTRO
    if not os.path.exists(intro_img_path):
        intro_img_path = os.path.join(bg_dir, "intro_bg_tesla.png")
    outro_img_path = os.path.join(bg_dir, "outro_bg.png")

    clips = []

    # 3. 인트로
    intro_clip = ImageClip(intro_img_path).set_duration(3).resize((1080, 1920))
    clips.append(intro_clip)

    # 4. 배경 영상 객체 미리 로딩
    bg_video_clips = [VideoFileClip(os.path.join(bg_dir, f)).resize((1080, 1920)) for f in bg_video_list]
    random.shuffle(bg_video_clips)
    bg_video_index = 0
    bg_video_start = 0

    # 5. 전체 자막 수에 따라 자막 시간 계산
    intro_duration = 2
    outro_duration = 2
    total_max_duration = 60
    available_caption_duration = total_max_duration - intro_duration - outro_duration

    total_sentences = 0
    for idx, summary in enumerate(summaries):
        numbered_summary = f"{idx+1}. {summary}"
        total_sentences += len(split_korean_sentences(numbered_summary))

    per_caption = available_caption_duration / total_sentences
    per_caption = max(2, min(4, per_caption))  # 너무 짧거나 길지 않게

    # 6. 본문 생성
    for idx, summary in enumerate(summaries):
        numbered_summary = f"{idx+1}. {summary}"
        sentences = split_korean_sentences(numbered_summary)

        for sent in sentences:
            caption_array = create_caption_image_array(sent, size=(1080, 1920), font_path=font_path)

            # ⏱️ Duration 설정
            if f"{idx+1}." == sent.strip():
                duration = 1
            else:
                duration = per_caption

            caption_clip = ImageClip(caption_array, transparent=True).set_duration(duration)

            remaining_time = duration
            bg_subclips = []

            # 🔁 필요한 만큼 배경 영상 이어붙이기
            while remaining_time > 0:
                current_clip = bg_video_clips[bg_video_index]
                current_duration = current_clip.duration

                available = current_duration - bg_video_start
                use_duration = min(available, remaining_time)

                if use_duration <= 0:
                    bg_video_index = (bg_video_index + 1) % len(bg_video_clips)
                    bg_video_start = 0
                    continue

                subclip = current_clip.subclip(bg_video_start, bg_video_start + use_duration)
                bg_subclips.append(subclip)

                bg_video_start += use_duration
                remaining_time -= use_duration

                if bg_video_start >= current_duration:
                    bg_video_index = (bg_video_index + 1) % len(bg_video_clips)
                    bg_video_start = 0

            bg_clip = concatenate_videoclips(bg_subclips)
            comp_clip = CompositeVideoClip([bg_clip, caption_clip])
            clips.append(comp_clip)

    # 7. 아웃트로
    outro_clip = ImageClip(outro_img_path).set_duration(2).resize((1080, 1920))
    clips.append(outro_clip)

    # 8. 전체 영상 합성
    final_clip = concatenate_videoclips(clips, method="compose")

    # 9. 배경음악
    if bgm_path and os.path.exists(bgm_path):
        bgm = AudioFileClip(bgm_path).volumex(0.5)
        final_clip = final_clip.set_audio(bgm.set_duration(final_clip.duration))

    # 10. 저장
    final_clip.write_videofile(output_path, fps=30, codec='libx264', audio_codec='aac')



# ============================ 유튭 업로드 ===========================
def upload_video_to_youtube_news(video_path, target_kr):
    global timestamps
    creds = Credentials.from_authorized_user_file("token.json", YOUTUBE_SCOPES)
    youtube = build("youtube", "v3", credentials=creds)

    now = datetime.now(ZoneInfo("Asia/Seoul"))
    date_str = now.strftime("%Y년 %m월 %d일")

    body = {
        "snippet": {
            "title": f"{date_str} "+target_kr+" 관련 뉴스",  # 영상 제목
            "description":
            f"{date_str} 오늘의 "+target_kr+" 관련 뉴스 요약입니다.\n\n#뉴스요약 #"+target_kr+" #"+target_kr+"뉴스 #오늘의"+target_kr+" #뉴스 #shorts",
            "tags": ["뉴스", "뉴스요약", target_kr, target_kr+"뉴스", "오늘의"+target_kr, "shorts"],
            "categoryId": "25"  # News & Politics
        },
        "status": {
            "privacyStatus": "public"  # 또는 unlisted, private
        }
    }

    media = MediaFileUpload(video_path,
                            chunksize=-1,
                            resumable=True,
                            mimetype="video/*")

    print("📤 유튜브 업로드 시작...")
    request = youtube.videos().insert(part="snippet,status",
                                      body=body,
                                      media_body=media)
    response = None

    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"🔄 업로드 진행: {int(status.progress() * 100)}%")

    print(f"✅ 업로드 완료! YouTube Video ID: {response.get('id')}")

    if target_kr == "조비 에비에이션":
        run_market_impact_pipeline()
    elif target_kr == "코인":
        # token.json 삭제
        try:
            os.remove("token.json")
            print("token.json 파일 삭제 완료.")
        except FileNotFoundError:
            print("token.json 파일이 이미 존재하지 않음.")
        except Exception as e:
            print(f"token.json 삭제 중 오류 발생: {e}")

    elif target_kr == "테슬라":
        run_daily_pipeline_news_jovy()
    elif target_kr == "경제":
        run_daily_pipeline_news_coin()

def run_daily_pipeline_news():
    print("🚀 테슬라 뉴스 요약 쇼츠 생성 시작")
    us_newsdata = fetch_newsdata_articles("tesla", country="us", language="en")
    save_articles("us", "newsdata", us_newsdata)

    collected_articles = get_news_from_html()
    summaries = summarize_articles(collected_articles, "tesla")

    if len(summaries) > 0:
        create_intro_image_news("tesla", "테슬라")
        # for idx, summary in enumerate(summaries):
        #     create_body_image(summary, idx, "tesla")
        create_outro_image()

        date_str = datetime.now().strftime("%Y%m%d")

        # create_youtube_shorts_video(
        #     intro_path=OUTPUT_INTRO,
        #     body_dir=os.path.join(BASE_DIR,"results"),  # body 이미지가 있는 폴더
        #     outro_path=OUTPUT_OUTRO,
        #     bgm_path=os.path.join(BASE_DIR, "bgm", "bgm_news.mp3"),
        #     output_path=os.path.join(OUT_DIR,  f"{date_str}_tesla_news_shorts.mp4")
        # )

        create_news_shorts_video_with_bgvideo_fast(
            "tesla", summaries, BG_DIR, OUT_DIR, os.path.join(BASE_DIR, "bgm", "bgm_news.mp3"), os.path.join(OUT_DIR,  f"{date_str}_tesla_news_shorts.mp4"), duration_per_caption=3, target_kr="테슬라", font_path=FONT_PATH
        )

        # ⏭️ 다음 단계: YouTube 업로드
        upload_video_to_youtube_news(os.path.join(OUT_DIR,  f"{date_str}_tesla_news_shorts.mp4"), "테슬라")
    else:
        run_daily_pipeline_news_jovy()

def run_daily_pipeline_news_jovy():
    print("🚀 조비 뉴스 요약 쇼츠 생성 시작")
    us_newsdata = fetch_newsdata_articles('Joby OR "Joby Aviation"', country="us", language="en")
    save_articles("us", "newsdata", us_newsdata)

    collected_articles = get_news_from_html()
    summaries = summarize_articles(collected_articles, "Jovy Aviation")

    if len(summaries) > 0:
        create_intro_image_news("Jovy Aviation", "조비 에비에이션")
        # for idx, summary in enumerate(summaries):
        #     create_body_image(summary, idx, "Jovy")
        create_outro_image()

        date_str = datetime.now().strftime("%Y%m%d")

        create_news_shorts_video_with_bgvideo_fast(
            "Jovy", summaries, BG_DIR, OUT_DIR, os.path.join(BASE_DIR, "bgm", "bgm_news.mp3"), os.path.join(OUT_DIR,  f"{date_str}_Jovy_news_shorts.mp4"), duration_per_caption=3, target_kr="조비 에비에이션", font_path=FONT_PATH
        )

        # ⏭️ 다음 단계: YouTube 업로드
        upload_video_to_youtube_news(os.path.join(OUT_DIR,  f"{date_str}_Jovy_news_shorts.mp4"), "조비 에비에이션")
    else:
        run_market_impact_pipeline()


def run_daily_pipeline_news_business():
    print("🚀 비트마인 뉴스 요약 쇼츠 생성 시작")
    us_newsdata = fetch_newsdata_articles("bitmine", country="us", language="en", category="business")
    save_articles("us", "newsdata", us_newsdata)

    collected_articles = get_news_from_html()
    summaries = summarize_articles(collected_articles, "bitmine")

    if len(summaries) > 0:
        create_intro_image_news("bitmine", "비트마인")
        # for idx, summary in enumerate(summaries):
        #     create_body_image(summary, idx, "business")
        create_outro_image()

        date_str = datetime.now().strftime("%Y%m%d")

        create_news_shorts_video_with_bgvideo_fast(
            "bitmine", summaries, BG_DIR, OUT_DIR, os.path.join(BASE_DIR, "bgm", "bgm_news.mp3"), os.path.join(OUT_DIR,  f"{date_str}_bitmine_news_shorts.mp4"), duration_per_caption=3, target_kr="비트마인", font_path=FONT_PATH
        )

        # ⏭️ 다음 단계: YouTube 업로드
        upload_video_to_youtube_news(os.path.join(OUT_DIR,  f"{date_str}_bitmine_news_shorts.mp4"), "비트마인")
    else:
        run_daily_pipeline_news_coin()
        

def run_daily_pipeline_news_coin():
    print("🚀 코인 관련 뉴스 요약 쇼츠 생성 시작")
    us_newsdata = fetch_newsdata_articles("bitcoin OR ethereum OR crypto", country="us", language="en", category="business")
    save_articles("us", "newsdata", us_newsdata)

    collected_articles = get_news_from_html()
    summaries = summarize_articles(collected_articles, "crypto")

    if len(summaries) > 0:
        create_intro_image_news("crypto", "코인")
        # for idx, summary in enumerate(summaries):
        #     create_body_image(summary, idx, "business")
        create_outro_image()

        date_str = datetime.now().strftime("%Y%m%d")

        create_news_shorts_video_with_bgvideo_fast(
            "crypto", summaries, BG_DIR, OUT_DIR, os.path.join(BASE_DIR, "bgm", "bgm_news.mp3"), os.path.join(OUT_DIR,  f"{date_str}_crypto_news_shorts.mp4"), duration_per_caption=3, target_kr="코인", font_path=FONT_PATH
        )

        # ⏭️ 다음 단계: YouTube 업로드
        upload_video_to_youtube_news(os.path.join(OUT_DIR,  f"{date_str}_crypto_news_shorts.mp4"), "코인")
    else:
        # token.json 삭제
        try:
            os.remove("token.json")
            print("token.json 파일 삭제 완료.")
        except FileNotFoundError:
            print("token.json 파일이 이미 존재하지 않음.")
        except Exception as e:
            print(f"token.json 삭제 중 오류 발생: {e}")





# ========== 운세 생성 ==========
def clean_fortune_text(text):
    # 1. "쥐띠", "말띠", "호랑이띠" 등 띠 이름 제거 (문장 시작 위치에만)
    text = re.sub(r'^[^가-힣]*([가-힣]{1,5}띠)[\\s:：,.~!\\-]*', r'\1 - ', text)

    # 2. 이모지 제거
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # 이모티콘
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U00002600-\U000026FF"
        "\U00002700-\U000027BF"
        "\U0001F900-\U0001F9FF"
        "\U0001FA70-\U0001FAFF"
        "\u200d"
        "\u2640-\u2642"
        "\u23cf"
        "\u23e9-\u23f3"
        "\u25fb-\u25fe"
        "\u2614-\u2615"
        "]+",
        flags=re.UNICODE)
    return emoji_pattern.sub(r'', text).strip()


def get_daily_fortunes():
    client = OpenAI()

    prompt = (
    "오늘 날짜 기준으로 12개 띠별 각각의 운세를 한 문단씩 써줘.\n"
    "절대 빠짐없이 12개 모두 써야 하고, 띠 순서는 다음과 같아:\n"
    + ", ".join(ZODIACS) + "\n\n"
    "각 운세는 유튜브 쇼츠에 어울리는 말투로, 2문장 정도로 짧고 인상 깊게 써줘.\n"
    "띠별 이름으로 문단을 구분하고, 각 문단은 줄바꿈으로 나눠서 보여줘.\n"
    "예: \n"
    "쥐띠\n오늘은 기회가 숨어있는 날이에요. 평소와 다른 선택이 행운을 부를 수 있어요.\n\n"
    "소띠\n마음이 안정되고 집중력이 높아지는 하루예요. 중요한 결정을 내리기 좋아요.\n\n"
    "이 형식을 꼭 지켜서 12개 띠를 전부 포함해서 작성해줘."
    )
    res = client.chat.completions.create(model="gpt-3.5-turbo",
                                         messages=[{
                                             "role": "user",
                                             "content": prompt
                                         }],
                                         temperature=0.85)
    text = res.choices[0].message.content.strip()
    print("GPT 운세 생성 결과:\n", text)

    fortunes = dict(zip(ZODIACS, text.split("\n\n")))
    return fortunes

def clean_emoji_text(text):
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # 이모티콘
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U00002600-\U000026FF"
        "\U00002700-\U000027BF"
        "\U0001F900-\U0001F9FF"
        "\U0001FA70-\U0001FAFF"
        "\u200d"
        "\u2640-\u2642"
        "\u23cf"
        "\u23e9-\u23f3"
        "\u25fb-\u25fe"
        "\u2614-\u2615"
        "]+",
        flags=re.UNICODE)
    return emoji_pattern.sub(r'', text).strip()


def clean_fortune_text_star(text):
    # 1. 자리 이름 제거 (문장 시작 위치에만)
    text = re.sub(r'^([^가-힣]*[가-힣]{1,5}자리)[\s:：,.~!\-]*', r'\1 - ', text)
    return clean_emoji_text(text)


def get_daily_star_fortunes():
    client = OpenAI()

    prompt = (
    "오늘 날짜 기준으로 12개 별자리 각각의 운세를 한 문단씩 써줘.\n"
    "절대 빠짐없이 12개 모두 써야 하고, 별자리 순서는 다음과 같아:\n"
    + ", ".join(ZODIACS_star) + "\n\n"
    "각 운세는 유튜브 쇼츠에 어울리는 말투로, 2문장 정도로 짧고 인상 깊게 써줘.\n"
    "별자리 이름으로 문단을 구분하고, 각 문단은 줄바꿈으로 나눠서 보여줘.\n"
    "예: \n"
    "양자리\n오늘은 기회가 숨어있는 날이에요. 평소와 다른 선택이 행운을 부를 수 있어요.\n\n"
    "황소자리\n마음이 안정되고 집중력이 높아지는 하루예요. 중요한 결정을 내리기 좋아요.\n\n"
    "이 형식을 꼭 지켜서 12개 별자리를 전부 포함해서 작성해줘."
    )

    res = client.chat.completions.create(model="gpt-3.5-turbo",
                                         messages=[{
                                             "role": "user",
                                             "content": prompt
                                         }],
                                         temperature=0.85)
    text = res.choices[0].message.content.strip()
    print("GPT 운세 생성 결과:\n", text)

    fortunes = dict(zip(ZODIACS_star, text.split("\n\n")))
    return fortunes



# 이미지 영역에 맞춰 줄바꿈
def wrap_text(text, font, max_width):
    """
    텍스트를 주어진 너비(max_width)에 맞춰 자동 줄바꿈 해주는 함수
    """
    lines = []
    words = text.split()

    current_line = ""
    for word in words:
        test_line = current_line + (" " if current_line else "") + word
        if font.getlength(test_line) <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word

    if current_line:
        lines.append(current_line)

    return lines


# 첫 페이지 생성용
def create_intro_image():

    now = datetime.now(ZoneInfo("Asia/Seoul"))
    date_str = f"{now.year}. {now.month}. {now.day}"  # ex: 2025. 7. 10
    line1 = f"{date_str}"
    line2 = "띠별 운세"

    image_path = os.path.join(BG_DIR, "first_img_숏츠.png")
    image = Image.open(image_path).convert("RGBA")
    draw = ImageDraw.Draw(image)

    font = ImageFont.truetype(FONT_PATH, FONT_SIZE * 2)
    x = image.width // 2
    y = image.height // 2

    LINE_SPACING = int(FONT_SIZE * 1.4)

    text_size = draw.textbbox((x, y), line1, font=font, anchor="mm")
    text_w = text_size[2] - text_size[0]
    text_h = text_size[3] - text_size[1]

    # 반투명 회색 박스 그리기
    box_padding = 10
    box_coords = [
        x - text_w // 2 - box_padding,
        y - (text_h * 2) // 2 - box_padding,
        x + text_w // 2 + box_padding,
        y + (text_h * 2) // 2 + box_padding,
    ]
    box_color = (75, 75, 75, 150)  # 반투명 회색
    overlay = Image.new("RGBA", image.size, (255, 255, 255, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rectangle(box_coords, fill=box_color)
    image = Image.alpha_composite(image, overlay)

    # 텍스트 그리기
    draw = ImageDraw.Draw(image)  # 다시 draw 객체 재생성

    draw.text((x, y - LINE_SPACING // 2),
              line1,
              font=font,
              fill="black",
              anchor="mm",
              stroke_width=4,
              stroke_fill="black")
    draw.text((x, y - LINE_SPACING // 2),
              line1,
              font=font,
              fill="white",
              anchor="mm",
              stroke_width=2)

    draw.text((x, y + LINE_SPACING // 2),
              line2,
              font=font,
              fill="black",
              anchor="mm",
              stroke_width=4,
              stroke_fill="black")
    draw.text((x, y + LINE_SPACING // 2),
              line2,
              font=font,
              fill="white",
              anchor="mm",
              stroke_width=2)

    out_path = os.path.join(OUT_DIR, "0_intro.png")
    image.save(out_path)


# ========== 이미지에 텍스트 삽입 ==========
def insert_fortune_text(zodiac, text):
    image_path = os.path.join(BG_DIR, f"{zodiac}숏츠.png")
    output_path = os.path.join(OUT_DIR, f"{zodiac}_운세.png")

    try:
        img = Image.open(image_path).convert("RGBA")
        draw = ImageDraw.Draw(img)
        font = ImageFont.truetype(FONT_PATH, FONT_SIZE)

        x1, y1, x2, y2 = TEXT_BOX
        max_width = x2 - x1
        lines = wrap_text(text, font, max_width)

        words = text.split()
        lines, line = [], ""
        for word in words:
            test_line = f"{line} {word}".strip()
            if draw.textlength(test_line, font=font) <= max_width:
                line = test_line
            else:
                lines.append(line)
                line = word
        lines.append(line)

        LINE_SPACING = int(FONT_SIZE * 1.1)  # 글자 크기 대비 줄 간격

        max_lines = (y2 - y1) // LINE_SPACING
        for i, l in enumerate(lines[:max_lines]):
            y = y1 + i * LINE_SPACING
            x = (x1 + x2) // 2
            if y + LINE_SPACING > y2:
                break

            # 텍스트 크기 측정
            text_size = draw.textbbox((x, y), l, font=font, anchor="mm")
            text_w = text_size[2] - text_size[0]
            text_h = text_size[3] - text_size[1]

            # 반투명 회색 박스 그리기
            box_padding = 10
            box_coords = [
                x - text_w // 2 - box_padding,
                y - text_h // 2 - box_padding,
                x + text_w // 2 + box_padding,
                y + text_h // 2 + box_padding,
            ]
            box_color = (75, 75, 75, 150)  # 반투명 회색
            overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
            overlay_draw = ImageDraw.Draw(overlay)
            overlay_draw.rectangle(box_coords, fill=box_color)
            img = Image.alpha_composite(img, overlay)

            # 텍스트 그리기
            draw = ImageDraw.Draw(img)  # 다시 draw 객체 재생성

            draw.text((x, y),
                      l,
                      font=font,
                      fill="black",
                      anchor="mm",
                      stroke_width=2,
                      stroke_fill="black")
            draw.text((x, y), l, font=font, fill="white", anchor="mm")

        img.save(output_path)
        print(f"✅ 저장 완료: {output_path}")
    except FileNotFoundError:
        print(f"❌ 이미지 없음: {image_path}")



# 첫 페이지 생성용
def create_star_intro_image():
    from datetime import datetime

    now = datetime.now(ZoneInfo("Asia/Seoul"))
    date_str = f"{now.year}. {now.month}. {now.day}"  # ex: 2025. 7. 10
    line1 = f"{date_str}"
    line2 = "별자리 운세"

    image_path = os.path.join(BG_DIR, "first_img.png")
    image = Image.open(image_path).convert("RGBA")
    draw = ImageDraw.Draw(image)

    font = ImageFont.truetype(FONT_PATH, FONT_SIZE * 2)
    x = image.width // 2
    y = image.height // 2

    LINE_SPACING = int(FONT_SIZE * 1.4)

    text_size = draw.textbbox((x, y), line1, font=font, anchor="mm")
    text_w = text_size[2] - text_size[0]
    text_h = text_size[3] - text_size[1]

    # 반투명 회색 박스 그리기
    box_padding = 10
    box_coords = [
        x - text_w // 2 - box_padding,
        y - (text_h * 2) // 2 - box_padding,
        x + text_w // 2 + box_padding,
        y + (text_h * 2) // 2 + box_padding,
    ]
    box_color = (75, 75, 75, 150)  # 반투명 회색
    overlay = Image.new("RGBA", image.size, (255, 255, 255, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rectangle(box_coords, fill=box_color)
    image = Image.alpha_composite(image, overlay)

    # 텍스트 그리기
    draw = ImageDraw.Draw(image)  # 다시 draw 객체 재생성

    draw.text((x, y - LINE_SPACING // 2),
              line1,
              font=font,
              fill="black",
              anchor="mm",
              stroke_width=4,
              stroke_fill="black")
    draw.text((x, y - LINE_SPACING // 2),
              line1,
              font=font,
              fill="white",
              anchor="mm",
              stroke_width=2)

    draw.text((x, y + LINE_SPACING // 2),
              line2,
              font=font,
              fill="black",
              anchor="mm",
              stroke_width=4,
              stroke_fill="black")
    draw.text((x, y + LINE_SPACING // 2),
              line2,
              font=font,
              fill="white",
              anchor="mm",
              stroke_width=2)

    out_path = os.path.join(OUT_DIR, "0_intro.png")
    image.save(out_path)


# ========== 이미지에 텍스트 삽입 ==========
def insert_fortune_text_star(zodiac, text):
    image_path = os.path.join(BG_DIR, f"{zodiac}.png")
    output_path = os.path.join(OUT_DIR, f"{zodiac}자리_운세.png")

    try:
        img = Image.open(image_path).convert("RGBA")
        draw = ImageDraw.Draw(img)
        font = ImageFont.truetype(FONT_PATH, FONT_SIZE)

        x1, y1, x2, y2 = TEXT_BOX
        max_width = x2 - x1
        lines = wrap_text(text, font, max_width)

        words = text.split()
        lines, line = [], ""
        for word in words:
            test_line = f"{line} {word}".strip()
            if draw.textlength(test_line, font=font) <= max_width:
                line = test_line
            else:
                lines.append(line)
                line = word
        lines.append(line)

        LINE_SPACING = int(FONT_SIZE * 1.1)  # 글자 크기 대비 줄 간격

        max_lines = (y2 - y1) // LINE_SPACING
        for i, l in enumerate(lines[:max_lines]):
            y = y1 + i * LINE_SPACING
            x = (x1 + x2) // 2
            if y + LINE_SPACING > y2:
                break

            # 텍스트 크기 측정
            text_size = draw.textbbox((x, y), l, font=font, anchor="mm")
            text_w = text_size[2] - text_size[0]
            text_h = text_size[3] - text_size[1]

            # 반투명 회색 박스 그리기
            box_padding = 10
            box_coords = [
                x - text_w // 2 - box_padding,
                y - text_h // 2 - box_padding,
                x + text_w // 2 + box_padding,
                y + text_h // 2 + box_padding,
            ]
            box_color = (75, 75, 75, 150)  # 반투명 회색
            overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
            overlay_draw = ImageDraw.Draw(overlay)
            overlay_draw.rectangle(box_coords, fill=box_color)
            img = Image.alpha_composite(img, overlay)

            # 텍스트 그리기
            draw = ImageDraw.Draw(img)  # 다시 draw 객체 재생성

            draw.text((x, y),
                      l,
                      font=font,
                      fill="black",
                      anchor="mm",
                      stroke_width=2,
                      stroke_fill="black")
            draw.text((x, y), l, font=font, fill="white", anchor="mm")

        img.save(output_path)
        print(f"✅ 저장 완료: {output_path}")
    except FileNotFoundError:
        print(f"❌ 이미지 없음: {image_path}")






# 영상으로 변환
def generate_zodiac_video(image_paths,
                          out_path,
                          duration_per_image=2.5,
                          bgm_path=None):
    """
    image_paths: 운세 이미지 경로 리스트
    out_path: 저장될 mp4 경로
    duration_per_image: 각 이미지 지속 시간 (초)
    bgm_path: 배경음악 mp3 경로 (선택)
    """
    clips = []

    for image_path in image_paths:
        clip = ImageClip(image_path, duration=duration_per_image).resize(
            height=1920).set_position("center")
        clips.append(clip)

    final_clip = concatenate_videoclips(clips, method="compose")

    if bgm_path and os.path.exists(bgm_path):
        audio = AudioFileClip(bgm_path).subclip(0, final_clip.duration)
        final_clip = final_clip.set_audio(audio)

    final_clip.write_videofile(out_path,
                               fps=30,
                               codec="libx264",
                               audio_codec="aac")


def create_daily_video_from_images():
    global timestamps
    date_str = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d")
    image_files = ["0_intro.png"] + [f"{z}_운세.png" for z in ZODIACS
                                     ] + ["end_img.png"]  # 🔧 여기 수정됨

    image_paths = [
        os.path.join(OUT_DIR, f) for f in image_files
        if os.path.exists(os.path.join(OUT_DIR, f))
    ]

    video_out_path = os.path.join(OUT_DIR, f"{date_str}_zodiac_video.mp4")

    bgm_path = os.path.join(BASE_DIR, "bgm", "bgm.mp3")
    if not os.path.exists(bgm_path):
        bgm_path = None

    # ⏱️ 타임스탬프 생성
    duration_per_image = 2.5
    timestamps = {}
    start_time = duration_per_image  # 첫 번째 띠는 intro(0초) 다음인 2.5초부터 시작
    for zodiac in ZODIACS:
        minutes = int(start_time // 60)
        seconds = int(start_time % 60)
        timestamps[zodiac] = f"{minutes:02d}:{seconds:02d}"
        start_time += duration_per_image

    generate_zodiac_video(image_paths,
                          video_out_path,
                          duration_per_image=duration_per_image,
                          bgm_path=bgm_path)
    print(f"🎥 영상 생성 완료: {video_out_path}")
    return video_out_path


generated_images = []


# ============================ 유튭 업로드 ===========================
def upload_video_to_youtube(video_path):
    global timestamps
    creds = Credentials.from_authorized_user_file("token.json", YOUTUBE_SCOPES)
    youtube = build("youtube", "v3", credentials=creds)

    now = datetime.now(ZoneInfo("Asia/Seoul"))
    date_str = now.strftime("%Y년 %m월 %d일")

    timestamp_description = "\n".join(
        [f"🐾 {name}띠 운세 : {time}" for name, time in timestamps.items()])

    body = {
        "snippet": {
            "title": f"{date_str} 띠별 운세 ✨",  # 영상 제목
            "description":
            f"{date_str} 오늘의 띠별 운세입니다.\n\n{timestamp_description}\n\n#운세 #띠별운세 #shorts",
            "tags": ["운세", "띠별운세", "오늘의운세", "shorts"],
            "categoryId": "22"  # People & Blogs
        },
        "status": {
            "privacyStatus": "public"  # 또는 unlisted, private
        }
    }

    media = MediaFileUpload(video_path,
                            chunksize=-1,
                            resumable=True,
                            mimetype="video/*")

    print("📤 유튜브 업로드 시작...")
    request = youtube.videos().insert(part="snippet,status",
                                      body=body,
                                      media_body=media)
    response = None

    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"🔄 업로드 진행: {int(status.progress() * 100)}%")

    print(f"✅ 업로드 완료! YouTube Video ID: {response.get('id')}")

    # # token.json 삭제
    # try:
    #     os.remove("token.json")
    #     print("token.json 파일 삭제 완료.")
    # except FileNotFoundError:
    #     print("token.json 파일이 이미 존재하지 않음.")
    # except Exception as e:
    #     print(f"token.json 삭제 중 오류 발생: {e}")


def run_daily_pipeline():
    print("🚀 띠별 운세 생성 시작")
    create_intro_image()  # 맨 앞장 이미지 생성
    generated_images.append(os.path.join(OUT_DIR, "0_intro.png"))

    fortunes = get_daily_fortunes()
    for zodiac in ZODIACS:
        text = fortunes.get(zodiac, "오늘도 행복한 하루 보내세요!")
        text = clean_fortune_text(text)
        insert_fortune_text(zodiac, text)
        image_path = os.path.join(OUT_DIR, f"{zodiac}_운세.png")
        generated_images.append(image_path)

    follow_image = os.path.join(BG_DIR, "follow_prompt.png")
    if os.path.exists(follow_image):
        generated_images.append(follow_image)

    print("✅ 전체 이미지 생성 완료")

    # 🎬 여기서 영상으로 변환!
    video_path = create_daily_video_from_images()

    # base64 문자열 가져오기
    token_b64 = os.getenv("TOKEN_JSON_BASE64")
    with open("token.json", "wb") as f:
        f.write(base64.b64decode(token_b64))

    # 디코딩 후 token.json로 저장
    if token_b64:
        with open("token.json", "wb") as f:
            f.write(base64.b64decode(token_b64))
        print("token.json 파일 복원 완료.")
    else:
        print("TOKEN_JSON_BASE64 환경변수가 설정되지 않았습니다.")

    # ⏭️ 다음 단계: YouTube 업로드
    upload_video_to_youtube(video_path)

    ## 별자리 운세 생성
    run_daily_pipeline_star()



def create_daily_video_from_images_star():
    global timestamps
    date_str = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d")
    image_files = ["0_intro.png"] + [f"{z}자리_운세.png" for z in ZODIACS_star
                                     ] + ["end_img.png"]  # 🔧 여기 수정됨

    image_paths = [
        os.path.join(OUT_DIR, f) for f in image_files
        if os.path.exists(os.path.join(OUT_DIR, f))
    ]

    video_out_path = os.path.join(OUT_DIR, f"{date_str}_star_video.mp4")

    bgm_path = os.path.join(BASE_DIR, "bgm", "bgm_star.mp3")
    if not os.path.exists(bgm_path):
        bgm_path = None

    # ⏱️ 타임스탬프 생성
    duration_per_image = 2.5
    timestamps = {}
    start_time = duration_per_image  # 첫 번째 별자리는 intro(0초) 다음인 2.5초부터 시작
    for zodiac in ZODIACS_star:
        minutes = int(start_time // 60)
        seconds = int(start_time % 60)
        timestamps[zodiac] = f"{minutes:02d}:{seconds:02d}"
        start_time += duration_per_image

    generate_zodiac_video(image_paths,
                          video_out_path,
                          duration_per_image=duration_per_image,
                          bgm_path=bgm_path)
    print(f"🎥 영상 생성 완료: {video_out_path}")
    return video_out_path


generated_images = []


# ============================ 유튭 업로드 ===========================
def upload_video_to_youtube_star(video_path):
    global timestamps
    creds = Credentials.from_authorized_user_file("token.json", YOUTUBE_SCOPES)
    youtube = build("youtube", "v3", credentials=creds)

    now = datetime.now(ZoneInfo("Asia/Seoul"))
    date_str = now.strftime("%Y년 %m월 %d일")

    timestamp_description = "\n".join(
        [f"🐾 {name}자리 운세 : {time}" for name, time in timestamps.items()])

    body = {
        "snippet": {
            "title": f"{date_str} 별자리 운세 ✨",  # 영상 제목
            "description":
            f"{date_str} 오늘의 별자리 운세입니다.\n\n{timestamp_description}\n\n#운세 #별자리운세 #shorts",
            "tags": ["운세", "별자리운세", "오늘의운세", "shorts"],
            "categoryId": "22"  # People & Blogs
        },
        "status": {
            "privacyStatus": "public"  # 또는 unlisted, private
        }
    }

    media = MediaFileUpload(video_path,
                            chunksize=-1,
                            resumable=True,
                            mimetype="video/*")

    print("📤 유튜브 업로드 시작...")
    request = youtube.videos().insert(part="snippet,status",
                                      body=body,
                                      media_body=media)
    response = None

    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"🔄 업로드 진행: {int(status.progress() * 100)}%")

    print(f"✅ 업로드 완료! YouTube Video ID: {response.get('id')}")

    run_daily_pipeline_news()


def run_daily_pipeline_star():
    print("🚀 별자리 운세 생성 시작")
    create_star_intro_image()  # 맨 앞장 이미지 생성
    generated_images.append(os.path.join(OUT_DIR, "0_intro.png"))

    fortunes = get_daily_star_fortunes()
    for zodiac in ZODIACS_star:
        text = fortunes.get(zodiac, "오늘도 행복한 하루 보내세요!")
        text = clean_fortune_text_star(text)
        insert_fortune_text_star(zodiac, text)
        image_path = os.path.join(OUT_DIR, f"{zodiac}자리_운세.png")
        generated_images.append(image_path)

    follow_image = os.path.join(BG_DIR, "follow_prompt.png")
    if os.path.exists(follow_image):
        generated_images.append(follow_image)

    print("✅ 전체 이미지 생성 완료")

    # 🎬 여기서 영상으로 변환!
    video_path = create_daily_video_from_images_star()

    # ⏭️ 다음 단계: YouTube 업로드
    upload_video_to_youtube_star(video_path)



# ========== new 자산 관련 신규 뉴스 함수 ======

# -----------------------
# 보조 유틸: 날짜 파싱 안전 함수
# -----------------------
def parse_date_flexible(s: str):
    """여러 포맷을 시도해서 datetime 반환 (UTC+9 기준으로 반환). 실패 시 None."""
    if s is None:
        return None
    # 이미 ISO 형태일 가능성
    try:
        # 일부 API는 '2025-08-01T12:34:56Z' 또는 '2025-08-01 12:34:56' 등으로 제공.
        # datetime.fromisoformat은 Z를 못 받으므로 replace 처리
        txt = s.strip()
        txt = txt.replace("Z", "+00:00")
        dt = None
        try:
            dt = datetime.fromisoformat(txt)
        except Exception:
            pass
        if dt is None:
            # fallback common formats
            for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%a, %d %b %Y %H:%M:%S %Z"):
                try:
                    dt = datetime.strptime(txt, fmt)
                    break
                except Exception:
                    continue
        if dt is None:
            # try numeric-only fallback
            nums = re.findall(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", txt)
            if nums:
                dt = datetime.fromisoformat(nums[0])
        if dt is None:
            return None
        # If no tzinfo, assume UTC then convert to Asia/Seoul
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        # convert to Asia/Seoul (KST)
        try:
            return dt.astimezone(ZoneInfo("Asia/Seoul"))
        except Exception:
            # zoneinfo 없음 → 안전 fallback
            kst = dt + timedelta(hours=9)
            return kst.replace(tzinfo=None)   # tzinfo 강제 설정하지 않음
    except Exception:
        return None
    
# -----------------------
# 보조: 기사 리스트를 수집하고 시간 범위로 필터
# -----------------------
def collect_recent_articles(from_dt: datetime, to_dt: datetime) -> List[Dict[str, Any]]:
    """
    기존의 fetch_newsdata_articles / fetch_rss_articles 등 사용자 정의 함수들을 재사용해서
    from_dt <= published <= to_dt 범위의 기사들을 수집하여 반환.
    결과 항목 dict: {title, content, url, source, published}
    """
    collected = []

    # 1) NewsData (예: country combinations)
    try:
        # 가능한 조합: kr(ko), us(en), global/en 등 — 기존 환경에 맞게 호출
        try:
            us = fetch_newsdata_articles(q=None, country="us", language="en", category="business") or []
            print("NewsData US articles fetched:", len(us))
            print("us가 있음에도 아래에서 collected append가 안되고 있음, us- :")
            print(us)
            for a in us:
                pub = a.get("pubDate") or a.get("published_at") or a.get("date")
                print("pub == ", pub)
                pub_dt = parse_date_flexible(pub)
                print("pub_dt == ", pub_dt)
                # if pub_dt and from_dt <= pub_dt <= to_dt:
                collected.append({
                    "title": a.get("title"),
                    "content": a.get("content") or a.get("description") or a.get("summary") or "",
                    "url": a.get("link") or a.get("url") or a.get("source_url"),
                    "source": a.get("source_id") or a.get("source", {}).get("name") if isinstance(a.get("source"), dict) else a.get("source"),
                    "published": pub_dt.isoformat()
                })
        except Exception as e:
            print("NewsData US fetch error:", e)

        try:
            kr = fetch_newsdata_articles(q=None, country="kr", language="ko", category="business") or []
            print("NewsData KR articles fetched:", len(kr))
            print("kr가 있음에도 아래에서 collected append가 안되고 있음, kr- :")
            print(kr)
            for a in kr:
                pub = a.get("pubDate") or a.get("published_at") or a.get("date")
                print("pub == ", pub)
                pub_dt = parse_date_flexible(pub)
                print("pub_dt == ", pub_dt)
                # if pub_dt and from_dt <= pub_dt <= to_dt:
                collected.append({
                    "title": a.get("title"),
                    "content": a.get("content") or a.get("description") or a.get("summary") or "",
                    "url": a.get("link") or a.get("url"),
                    "source": a.get("source_id") or a.get("source"),
                    "published": pub_dt.isoformat()
                })
        except Exception as e:
            print("NewsData KR fetch error:", e)
    except Exception as e:
        print("NewsData fetch general error:", e)

    # 2) RSS 피드 (기존 fetch_rss_articles를 region별로)
    try:
        for region in ("kr", "global"):
            try:
                rss_list = fetch_rss_articles(region) or []
                print("RSS도 계속 없다고 함, rss list ====== ")
                print(rss_list)
                for a in rss_list:
                    pub = a.get("published")
                    print("pub == ", pub)
                    pub_dt = parse_date_flexible(pub)
                    print("pub_dt == ", pub_dt)
                    # if pub_dt and from_dt <= pub_dt <= to_dt:
                    collected.append({
                        "title": a.get("title"),
                        "content": a.get("summary") or "",
                        "url": a.get("link"),
                        "source": region,
                        "published": pub_dt.isoformat()
                    })
            except Exception as e:
                print("RSS fetch error for region", region, e)
        print("all articles fetched:", len(collected))
    except Exception as e:
        print("RSS fetch general error", e)

    # dedupe by URL or title
    seen = set()
    deduped = []
    for art in collected:
        key = (art.get("url") or "")[:200] + "|" + (art.get("title") or "")[:200]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(art)
    print(f"[collect_recent_articles] collected {len(deduped)} articles in time range.")
    return deduped


# -----------------------
# GPT에게 분석 요청하는 함수
# -----------------------
def ask_gpt_market_impact(articles: List[Dict[str,Any]], from_dt: datetime, to_dt: datetime) -> Dict[str, List[Dict[str,Any]]]:
    """
    articles: list of {title, content, url, source, published}
    반환: dict mapping asset category -> list of items:
      { "stocks": [ {title, summary, impact_score, rationale, url, published}, ... ], "crypto": [...], ... }
    """

    # asset categories 순서 (원하면 추가)
    asset_categories = ["Stocks", "Gold", "Crypto", "RealEstate", "Forex", "Bonds", "Commodities", "Other"]

    # Build prompt
    # 약식: 전달받은 기사 목록(제목+요약+url+source+published)을 넣고 -> 각 asset에 대해서
    # 영향을 줄만한 기사들을 뽑고 영향정도(0-100), 짧은 요약, 간단 근거를 JSON 포맷으로 달라
    article_texts = []
    for i, a in enumerate(articles, start=1):
        article_texts.append(f"{i}. TITLE: {a.get('title')}\nURL: {a.get('url')}\nPUBLISHED: {a.get('published')}\nSOURCE: {a.get('source')}\nCONTENT: {a.get('content')[:2000]}\n---")
    big_block = "\n".join(article_texts)

    prompt = (
        "Please answer everything in Korean.\n"
        "You are an expert market analyst. Based on the following collection of news articles (titles, short content, urls and published times),\n"
        "identify which articles within the given 48-hour window are likely to have meaningful impact on specific asset markets (Stocks, Gold, Crypto, RealEstate, Forex, Bonds, Commodities, Other).\n"
        "For each asset category, please produce a JSON object mapping the category name to an array of objects. Each object must include:\n"
        "  - title: a short title (from the article)\n"
        "  - summary: a concise summary focusing on how it affects that asset (max ~250 chars)\n"
        "  - impact_score: integer 0-100 estimating the magnitude of impact on that asset\n"
        "  - rationale: 1-2 sentence justification why it affects that asset\n"
        "  - url: original url\n"
        "  - published: published datetime in ISO format\n\n"
        "Return only valid JSON and nothing else. Use the following category order: " + ", ".join(asset_categories) + ".\n\n"
        "Articles (only those within last 48 hours):\n" + big_block + "\n\n"
        "Important: Keep the JSON compact but valid. If a category has no relevant articles, return an empty array for it.\n"
    )

    # Call GPT (using user's existing style)
    try:
        response = openai.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role":"system", "content":"You are a market research analyst."},
                {"role":"user", "content": prompt}
            ],
            temperature=0
        )
        raw = response.choices[0].message.content.strip()
        print(">>>>>>>> GPT raw response:\n", raw[:1000])
    except Exception as e:
        print("GPT call error:", e)
        return {}

    # try to extract JSON substring
    json_text = raw
    # if raw contains code fences or text around json, extract {...}
    m = re.search(r'(\{.*\})', raw, flags=re.S)
    if m:
        json_text = m.group(1)

    try:
        parsed = json.loads(json_text)
        # normalize keys -> ensure each asset_category present
        normalized = {}
        for cat in asset_categories:
            if cat in parsed:
                items = parsed[cat]
            elif cat.lower() in parsed:
                items = parsed[cat.lower()]
            else:
                items = []
            normalized[cat] = items
        print(">>>>>>>> GPT parsed and normalized JSON:\n",normalized)
        return normalized
    except Exception as e:
        print("JSON parse failed:", e)
        print("raw GPT output:\n", raw[:2000])
        return {}
    
# -----------------------
# 페이지(프레임) 생성 함수: 자산별 title + numbered items
# -----------------------
def build_pages_for_assets(assets_dict: Dict[str, List[Dict[str,Any]]], max_chars_per_frame=120) -> List[str]:
    """
    Return list of 'page texts' in the order:
      [ asset_title_1, asset1_item1_short, asset1_item2_short, ..., asset_title_2, asset2_item1_short, ... ]
    Each entry is a single string that will be converted to an image/frame.
    Splits long summaries into multiple frames by max_chars_per_frame.
    """
    pages = []
    for asset, items in assets_dict.items():
        # asset title page
        pages.append(asset)  # will be rendered as a title page
        # numbered items
        for i, it in enumerate(items, start=1):
            # build "1) summary (score:xx)"
            title = it.get("title") or ""
            summary = it.get("summary") or ""
            score = it.get("impact_score") or ""
            combined = f"{i}) {summary} (Impact: {score})"
            # split combined if too long
            if len(combined) <= max_chars_per_frame:
                pages.append(combined)
            else:
                # split into chunks at word boundaries
                words = combined.split()
                chunk = ""
                for w in words:
                    if len(chunk) + 1 + len(w) <= max_chars_per_frame:
                        chunk = (chunk + " " + w).strip()
                    else:
                        pages.append(chunk)
                        chunk = w
                if chunk:
                    pages.append(chunk)
    return pages

# -----------------------
# 비디오 빌드 + 업로드 : pages -> short video (재사용 가능한 로직)
# -----------------------
def build_and_save_shorts_video_from_pages(pages: List[str],
                                           bg_dir: str,
                                           out_dir: str,
                                           bgm_path: str,
                                           output_path: str,
                                           font_path: str = None):
    """
    이 함수는 pages 리스트(각 페이지는 문자)를 받아서
    이전 create_news_shorts_video_with_bgvideo_fast의 '배경 이어붙이기' 로직을 사용해
    영상으로 만드는 함수입니다. (인트로/아웃트로 이미지는 기존 것 사용)
    """
    # prepare intro/outro
    intro_img_path = OUTPUT_INTRO if os.path.exists(OUTPUT_INTRO) else os.path.join(bg_dir, "intro_bg_business.png")
    outro_img_path = OUTRO_BG if os.path.exists(OUTRO_BG) else os.path.join(bg_dir, "outro_bg.png")

    clips = []
    intro_clip = ImageClip(intro_img_path).set_duration(3).resize((1080,1920))
    clips.append(intro_clip)

    # prepare bg clips list — reuse earlier logic: create a list longer than needed
    video_candidates = [f for f in os.listdir(bg_dir) if f.endswith(".mp4")]
    if not video_candidates:
        raise FileNotFoundError("Background mp4 files not found in bg_dir")

    # create a list of background filenames (randomized)
    # make length > pages count to reduce immediate repeat
    bg_file_list = []
    for i in range(max(len(pages), len(video_candidates)) + 3):
        bg_file_list.append(random.choice(video_candidates))
    random.shuffle(bg_file_list)

    # load VideoFileClip objects
    bg_video_clips = [VideoFileClip(os.path.join(bg_dir, f)).resize((1080,1920)) for f in bg_file_list]
    bg_index = 0
    bg_pos = 0.0

    # total duration allocation similar to earlier: compute per-page duration so final <= 60s
    intro_duration = 3
    outro_duration = 2
    total_max = 60
    available = total_max - intro_duration - outro_duration
    per_page = available / max(1, len(pages))
    per_page = max(1.0, min(4.0, per_page))  # keep between 1 and 4 sec (pages can be many)

    for p in pages:
        caption_array = create_caption_image_array(p, size=(1080,1920), font_path=font_path)
        caption_clip = ImageClip(caption_array, transparent=True).set_duration(per_page)
        remaining = per_page
        subclips = []
        while remaining > 0:
            cur_clip = bg_video_clips[bg_index]
            avail = cur_clip.duration - bg_pos
            use = min(avail, remaining)
            if use <= 0:
                bg_index = (bg_index + 1) % len(bg_video_clips)
                bg_pos = 0.0
                continue
            sub = cur_clip.subclip(bg_pos, bg_pos + use)
            subclips.append(sub)
            bg_pos += use
            remaining -= use
            if bg_pos >= cur_clip.duration - 1e-6:
                bg_index = (bg_index + 1) % len(bg_video_clips)
                bg_pos = 0.0
        bg_clip = concatenate_videoclips(subclips)
        comp = CompositeVideoClip([bg_clip, caption_clip])
        clips.append(comp)

    # outro
    outro_clip = ImageClip(outro_img_path).set_duration(2).resize((1080,1920))
    clips.append(outro_clip)

    final = concatenate_videoclips(clips, method="compose")
    if bgm_path and os.path.exists(bgm_path):
        bgm = AudioFileClip(bgm_path).volumex(0.5)
        final = final.set_audio(bgm.set_duration(final.duration))

    # ensure out_dir exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    final.write_videofile(output_path, fps=30, codec='libx264', audio_codec='aac')
    return output_path

# -----------------------
# 최종 통합 함수: 요구사항(1)-(4)을 수행
# -----------------------
def run_market_impact_pipeline():
    print("🚀 시장 영향 뉴스 쇼츠 생성 시작")
    """
    1) now 기준으로 48시간 전부터 now까지 기사 수집
    2) GPT에게 각 자산시장별 영향 분석 요청 (JSON)
    3) 결과를 페이지로 변환(자산별 타이틀 한 장 + 번호 매긴 요약 장들)
    4) 기존 스타일의 쇼츠 생성 & 유튜브 업로드
    """
    now = datetime.now(tz=ZoneInfo("Asia/Seoul"))
    from_dt = now - timedelta(hours=48)
    print(f"[market pipeline] Time window: {from_dt.isoformat()} ~ {now.isoformat()}")

    # 1) collect
    articles = collect_recent_articles(from_dt, now)

    if not articles:
        print("[market pipeline] 수집된 기사 없음 — 종료")
        run_daily_pipeline_news_coin()
        return

    # 2) ask GPT
    assets_analysis = ask_gpt_market_impact(articles, from_dt, now)
    if not assets_analysis:
        print("[market pipeline] GPT에서 유효한 분석을 받지 못함 — 종료")
        run_daily_pipeline_news_coin()
        return
    print("[market pipeline] GPT 분석 결과:", assets_analysis)

    # 3) build pages
    pages = build_pages_for_assets(assets_analysis, max_chars_per_frame=120)
    if not pages:
        print("[market pipeline] 생성된 페이지 없음 — 종료")
        run_daily_pipeline_news_coin()
        return
    print("[market pipeline] 생성된 페이지:", pages)

    # create output filename
    date_str = now.strftime("%Y%m%d_%H%M")
    out_filename = os.path.join(OUT_DIR, f"{date_str}_market_impact_shorts.mp4")
    bgm_file = os.path.join(BASE_DIR, "bgm", "bgm_news2.mp3") if 'BASE_DIR' in globals() else None

    # 4) build video
    print("[market pipeline] 페이지 수:", len(pages))
    video_path = build_and_save_shorts_video_from_pages(pages, BG_DIR, OUT_DIR, bgm_file, out_filename, font_path=FONT_PATH)

    # 5) upload (reuse existing uploader, pass target string "시장요약")
    upload_video_to_youtube_news(video_path, "투자관련뉴스")

    print("[market pipeline] 완료: ", video_path)

    run_daily_pipeline_news_coin()



# ========== 스케줄러 설정 ==========
# seoul_tz = timezone('Asia/Seoul')

# scheduler = BackgroundScheduler(timezone=seoul_tz)
# scheduler.add_job(run_daily_pipeline, 'cron', hour=8, minute=0)
# scheduler.start()

# ========== Flask 웹서버 for UptimeRobot ==========
# app = Flask(__name__)


# @app.route("/")
# def home():
#     return "✅ Zodiac bot is alive!"


if __name__ == "__main__":

    run_daily_pipeline()  # 수동 실행도 가능

    # scheduler.start()
    # app.run(host="0.0.0.0", port=8080)
