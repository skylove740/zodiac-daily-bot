# zodiac_daily_bot.py

import os
import base64
import openai
from openai import OpenAI
import requests
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask
import re
import base64
from dotenv import load_dotenv
from moviepy.editor import ImageClip, concatenate_videoclips, AudioFileClip
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

load_dotenv()



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
                unknown_sources.add(source_name)

        except Exception as e:
            print(f"Error processing {link}: {e}")
            unknown_sources.add(source_name)

    # unknown_sources.txt 파일 저장 (추가 모드)
    if unknown_sources:
        if not os.path.exists(UNKNOWN_SOURCE_FILE):
            with open(UNKNOWN_SOURCE_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(sorted(unknown_sources)) + "\n")
        else:
            with open(UNKNOWN_SOURCE_FILE, "a", encoding="utf-8") as f:
                f.write("\n".join(sorted(unknown_sources)) + "\n")

    # 결과 출력
    print("\n=== 전체 기사 본문 ===")
    for idx, art in enumerate(collected_articles, start=1):
        print(f"[{idx}] {art['source_name']} ({art['link']})")
        print(art["content"][:400], "...\n")  # 앞부분 500자만 출력

    print("\n=== 못 찾은 source_name 목록 ===")
    for s in sorted(unknown_sources):
        print("-", s)
        print("soruce url : ", source_map[s].get("source_url", "N/A"))

    return collected_articles

# 시간 범위 설정 (전날 7시 30분 ~ 현재 시간)
def get_time_range_iso():
    now = datetime.utcnow() + timedelta(hours=9)
    start = now - timedelta(days=1)
    start = start.replace(hour=7, minute=30, second=0, microsecond=0)
    return start.isoformat(), now.isoformat()

def fetch_newsdata_articles(q, country=None, language=None):
    # 최신 뉴스 endpoint (/1/news)
    params = {}
    if country:
        params["country"] = country
    if language:
        params["language"] = language
    # params["category"] = "business"  # 카테고리를 유지할지 제거할지 선택 가능
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


def summarize_articles(articles):
    summarized_results = []

    for idx, art in enumerate(articles, start=1):
        article = art["content"]
        try:
            # GPT에게 요청할 프롬프트
            prompt = (
                "아래 기사를 주가에 영향을 줄 수 있는 핵심 내용 위주로, "
                "2줄 내로 최대한 간결하게 요약해 주세요.\n"
                "한글 글자 기준 250자 내로 요약해주세요.\n"
                "모든 내용은 실제 기사 내용에서 인용해야 하고, 없는 사실을 지어내면 안됩니다.\n"
                "각 줄은 간결하고 명확해야 하며, 주제를 분명히 드러내야 합니다. 최종 출력은 한글이어야 합니다.\n"
                "한글로 요약된 내용만 답변하세요\n\n"
                f"기사 내용:\n{article}"
            )
            print("기사 길이 : ", len(article))

            if len(article) > 10:
                response = openai.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "당신은 주식 및 경제 뉴스 전문 요약가입니다."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0,
                    max_tokens=300
                )

                summary = response.choices[0].message.content.strip()
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
def draw_text_with_box(draw, text, position, font, text_color, box_color, outline_color):
    # draw는 원본 이미지의 draw 객체
    img = draw.im  # 원본 이미지 객체 얻기
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

# ===== 인트로 이미지 생성 =====
def create_intro_image_news(target_en, target_kr):
    date_str = datetime.now().strftime("%Y.%m.%d")
    lines = [date_str, target_kr, "관련 뉴스"]

    intro_bg = os.path.join(BG_DIR, "intro_bg_"+target_en.split(" ")[0]+".png")

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
        img = draw_text_with_box(draw, line, (x, y_offset), font, "white", (0, 0, 0, 150), "black")
        draw = ImageDraw.Draw(img, "RGBA")  # draw 객체 갱신
        y_offset += h + 10

    img.convert("RGB").save(OUTPUT_INTRO)

# ===== 본문 이미지 생성 =====
def create_body_image(text, idx, target):
    body_bg = os.path.join(BG_DIR, "body_bg_"+target+".png")
    
    img = Image.open(body_bg).convert("RGBA")
    W, H = img.size
    draw = ImageDraw.Draw(img, "RGBA")

    # 폰트 크기 맞추기
    font_size = 50
    while True:
        font = ImageFont.truetype(FONT_PATH, font_size)
        wrapped = textwrap.fill(text, width=20)  # 줄바꿈
        tw, th = draw.multiline_textsize(wrapped, font=font, spacing=10)
        if tw > W * 0.9 or th > H * 0.9:
            font_size -= 2
            font = ImageFont.truetype(FONT_PATH, font_size)
            wrapped = textwrap.fill(text, width=20)
            break
        font_size += 2

    tw, th = draw.multiline_textsize(wrapped, font=font, spacing=10)
    x = (W - tw) // 2
    y = (H - th) // 2

    # 반투명 박스
    box_coords = (x - 20, y - 20, x + tw + 20, y + th + 20)
    draw.rectangle(box_coords, fill=(0, 0, 0, 150))

    # 테두리 + 텍스트
    for dx in [-1, 1]:
        for dy in [-1, 1]:
            draw.multiline_text((x + dx, y + dy), wrapped, font=font, fill="black", spacing=10)
    draw.multiline_text((x, y), wrapped, font=font, fill="white", spacing=10)

    img.convert("RGB").save(OUTPUT_BODY+str(idx)+'.jpg')

# ===== 아웃트로 이미지 =====
def create_outro_image():
    # outro_bg = os.path.join(BG_DIR, "outro_bg_"+target+".png")
    img = Image.open(OUTRO_BG)
    img.save(OUTPUT_OUTRO)


def create_youtube_shorts_video(intro_path, body_dir, outro_path, bgm_path, output_path):
    # 장면 길이 설정 (250자 기준 읽을 수 있는 시간: 약 7~8초)
    intro_duration = 3  # 인트로는 짧게
    body_duration = 8   # 본문 한 장당
    outro_duration = 2  # 아웃트로는 짧게

    clips = []

    # 1. 인트로 이미지
    intro_clip = ImageClip(intro_path).set_duration(intro_duration)
    clips.append(intro_clip)

    # 2. 본문 이미지들
    body_images = sorted([f for f in os.listdir(body_dir) if f.startswith("body") and f.endswith(".jpg")])
    for img_file in body_images:
        img_path = os.path.join(body_dir, img_file)
        body_clip = ImageClip(img_path).set_duration(body_duration)
        clips.append(body_clip)

    # 3. 아웃트로 이미지
    outro_clip = ImageClip(outro_path).set_duration(outro_duration)
    clips.append(outro_clip)

    # 4. 세로(9:16) 유튜브 쇼츠 사이즈 맞추기
    # moviepy에서 ImageClip은 원본 비율 유지, 필요시 resize와 margin 적용 가능
    clips = [clip.resize(height=1920).resize(width=1080) for clip in clips]

    # 5. 영상 합치기
    final_clip = concatenate_videoclips(clips, method="compose")

    # 6. BGM 설정
    bgm = AudioFileClip(bgm_path).volumex(0.5)  # 배경음악 볼륨 조절
    final_clip = final_clip.set_audio(bgm.set_duration(final_clip.duration))

    # 7. 저장
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

def run_daily_pipeline_news():
    print("🚀 테슬라 뉴스 요약 쇼츠 생성 시작")
    us_newsdata = fetch_newsdata_articles("tesla", country="us", language="en")
    save_articles("us", "newsdata", us_newsdata)

    collected_articles = get_news_from_html()
    summaries = summarize_articles(collected_articles)

    if len(summaries) > 0:
        create_intro_image_news("tesla", "테슬라")
        for idx, summary in enumerate(summaries):
            create_body_image(summary, idx, "tesla")
        create_outro_image()

        date_str = datetime.now().strftime("%Y%m%d")

        create_youtube_shorts_video(
            intro_path=OUTPUT_INTRO,
            body_dir=os.path.join(BASE_DIR,"results"),  # body 이미지가 있는 폴더
            outro_path=OUTPUT_OUTRO,
            bgm_path=os.path.join(BASE_DIR, "bgm", "bgm_news.mp3"),
            output_path=os.path.join(OUT_DIR,  f"{date_str}_tesla_news_shorts.mp4")
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
    summaries = summarize_articles(collected_articles)

    if len(summaries) > 0:
        create_intro_image_news("Jovy Aviation", "조비 에비에이션")
        for idx, summary in enumerate(summaries):
            create_body_image(summary, idx, "Jovy")
        create_outro_image()

        date_str = datetime.now().strftime("%Y%m%d")

        create_youtube_shorts_video(
            intro_path=OUTPUT_INTRO,
            body_dir=os.path.join(BASE_DIR,"results"),  # body 이미지가 있는 폴더
            outro_path=OUTPUT_OUTRO,
            bgm_path=os.path.join(BASE_DIR, "bgm", "bgm_news.mp3"),
            output_path=os.path.join(OUT_DIR,  f"{date_str}_jovy_news_shorts.mp4")
        )

        # ⏭️ 다음 단계: YouTube 업로드
        upload_video_to_youtube_news(os.path.join(OUT_DIR,  f"{date_str}_jovy_news_shorts.mp4"), "조비 에비에이션")
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


def clean_fortune_text_star(text):
    # 1. 자리 이름 제거 (문장 시작 위치에만)
    text = re.sub(r'^([^가-힣]*[가-힣]{1,5}자리)[\s:：,.~!\-]*', r'\1 - ', text)

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

    # base64 문자열 가져오기
    # token_b64 = os.getenv("TOKEN_JSON_BASE64")
    # with open("token.json", "wb") as f:
    #     f.write(base64.b64decode(token_b64))

    # # 디코딩 후 token.json로 저장
    # if token_b64:
    #     with open("token.json", "wb") as f:
    #         f.write(base64.b64decode(token_b64))
    #     print("token.json 파일 복원 완료.")
    # else:
    #     print("TOKEN_JSON_BASE64 환경변수가 설정되지 않았습니다.")

    # ⏭️ 다음 단계: YouTube 업로드
    upload_video_to_youtube_star(video_path)



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
