# zodiac_daily_bot.py

import os
import base64
import openai
from openai import OpenAI
import requests
from datetime import datetime
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

load_dotenv()

YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

timestamps = {}

# ========== 환경 설정 ==========
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

os.makedirs(BG_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)


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

    # text = """
    # 🐭 쥐띠
    # 작은 선택이 큰 변화를 가져올 수 있는 하루예요. 망설이지 말고 마음 가는 길을 따라가 보세요. 오늘의 당신은 충분히 멋져요.

    # 🐮 소띠
    # 느긋함 속에 여유가 피어나는 날이에요. 조급해하지 말고, 지금 이 순간을 천천히 음미해보세요. 좋은 일이 다가오고 있어요.

    # 🐯 호랑이띠
    # 에너지가 넘치는 하루예요. 새로운 도전 앞에서도 두려움보다는 설렘이 더 클 거예요. 오늘의 당신, 무서울 게 없어요.

    # 🐰 토끼띠
    # 섬세한 감성이 빛나는 날이에요. 누군가에게 따뜻한 말 한마디가 큰 위로가 될 수 있어요. 당신의 다정함이 세상을 부드럽게 감싸요.

    # 🐲 용띠
    # 당신이 기다리던 소식이 들려올지도 몰라요. 기대와 설렘을 품고 하루를 시작해 보세요. 기분 좋은 변화가 곧 찾아올 거예요.

    # 🐍 뱀띠
    # 마음이 고요해지고 중심이 잡히는 하루예요. 복잡한 생각은 잠시 접어두고, 나 자신을 위한 시간을 가져보세요.

    # 🐴 말띠
    # 오늘은 흐름을 타는 것이 중요해요. 억지로 끌고 가지 않아도, 자연스럽게 풀릴 일이 많을 거예요. 힘을 빼는 연습, 해보세요.

    # 🐐 양띠
    # 누군가의 미소가 당신의 하루를 따뜻하게 밝혀줄 거예요. 소소한 인연 속에서 큰 위안을 얻게 되는 날이에요.

    # 🐵 원숭이띠
    # 기발한 아이디어와 유쾌한 에너지가 빛나는 날이에요. 당신의 센스가 주변 사람들에게 기분 좋은 자극이 될 거예요.

    # 🐔 닭띠
    # 작지만 확실한 기쁨이 찾아와요. 커피 한 잔, 따뜻한 말, 잊고 있던 노래 한 곡이 오늘을 특별하게 만들어줄 거예요.

    # 🐶 개띠
    # 주변 사람과의 교감이 깊어지는 하루예요. 당신의 진심이 전해지는 순간, 마음과 마음이 연결돼요. 따뜻함을 나눠주세요.

    # 🐷 돼지띠
    # 오늘은 마음이 풍요로워지는 날이에요. 혼자 있어도 외롭지 않고, 함께 있어 더 행복한 하루가 될 거예요. 감사를 놓치지 마세요.
    # """
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

    # text = """
    # 물병자리
    # 오늘은 당신의 아이디어가 반짝이는 날이에요. 평소와 다른 방식으로 생각해보면 의외의 기회가 생길 수 있어요. 자신감을 갖고 말해보세요, 주목받게 될 거예요.

    # 물고기자리
    # 감성이 풍부해지는 하루예요. 누군가의 말 한마디에 마음이 흔들릴 수 있지만, 그만큼 깊은 공감이 당신의 매력이 돼줄 거예요. 솔직한 감정을 표현해보세요.

    # 양자리
    # 에너지가 넘치는 하루! 하고 싶은 일이 있다면 지금이 바로 그 타이밍이에요. 적극적인 행동이 좋은 결과로 이어질 수 있어요. 머뭇거리지 말고 질러보세요!

    # 황소자리
    # 안정감을 찾고 싶은 하루예요. 익숙한 루틴 속에서 작지만 확실한 행복을 발견하게 될 거예요. 소소한 휴식도 당신에겐 큰 힘이 될 수 있어요.

    # 쌍둥이자리
    # 오늘은 당신의 말 한마디가 분위기를 좌우할 수 있어요. 유쾌한 농담도 좋지만, 상황을 잘 읽고 말하는 센스를 발휘해보세요. 사람들의 마음을 사로잡을 거예요.

    # 게자리
    # 감정의 파도가 살짝 몰아치는 날이에요. 누군가와의 오해는 빠르게 풀어내는 게 좋아요. 진심 어린 한마디가 관계를 더 깊게 만들어줄 거예요.

    # 사자자리
    # 주목받는 하루가 될 수 있어요. 자신감 있는 모습이 사람들을 이끌게 될 거예요. 무대는 이미 준비됐어요—이제 당신이 빛날 차례예요!

    # 처녀자리
    # 세심함이 빛을 발하는 하루예요. 주변에서 당신의 배려에 감동할 수 있어요. 너무 모든 걸 책임지려 하진 말고, 스스로를 위한 시간도 챙겨주세요.

    # 천칭자리
    # 균형 감각이 필요한 하루예요. 한쪽으로 치우치지 않도록 중심을 잘 잡는 게 중요해요. 주변의 조언에 귀 기울이면 더 좋은 선택을 할 수 있어요.

    # 전갈자리
    # 강렬한 직감이 당신을 이끄는 날이에요. 왠지 모르게 끌리는 일이 있다면 가볍게 넘기지 말고 한 번 들여다보세요. 예상 밖의 기회가 숨어 있을지도 몰라요.

    # 사수자리
    # 새로운 도전이 눈앞에 있어요. 망설이지 말고 한 발 내딛어보세요. 실수해도 괜찮아요—중요한 건 당신의 용기와 열정이에요!

    # 염소자리
    # 계획했던 일들이 하나씩 자리 잡는 날이에요. 꾸준히 노력해온 만큼 좋은 결과가 따를 수 있어요. 오늘은 자신을 칭찬해주는 것도 잊지 마세요.
    # """
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
    from datetime import datetime

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

    # token.json 삭제
    try:
        os.remove("token.json")
        print("token.json 파일 삭제 완료.")
    except FileNotFoundError:
        print("token.json 파일이 이미 존재하지 않음.")
    except Exception as e:
        print(f"token.json 삭제 중 오류 발생: {e}")


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
