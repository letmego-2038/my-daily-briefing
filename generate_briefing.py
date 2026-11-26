import os
import re
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from google import genai
from google.genai import types

KST = timezone(timedelta(hours=9))
NOW = datetime.now(KST)
TODAY = NOW.strftime("%Y-%m-%d")

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
TODAY_FILE = DATA_DIR / f"{TODAY}.json"
INDEX_FILE = DATA_DIR / "index.json"

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def determine_slot() -> str:
    env_slot = os.environ.get("BRIEFING_SLOT", "").strip()
    if env_slot in ("08", "14", "16", "all"):
        return env_slot
    if NOW.hour < 12:
        return "08"
    elif NOW.hour < 15:
        return "14"
    return "16"


def ask_gemini_json(prompt: str) -> dict | list:
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.3,
        ),
    )
    text = response.text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        text = match.group(1).strip()
    return json.loads(text)


def fetch_domestic(slot: str) -> dict:
    slot_label = {"08": "장 시작 전(08:00)", "14": "장중(14:00)", "16": "장 마감 후(16:00)"}[slot]
    prompt = f"""
    오늘은 {TODAY}입니다. 한국 증시 {slot_label} 기준 최신 시황과 핵심 이슈를 웹 검색으로 조사해 아래 JSON 형식으로만 답하세요. (설명 문구 없이 순수 JSON만 출력)
    {{
      "updatedAt": "{NOW.strftime('%H:%M')} 업데이트",
      "marketSummary": "코스피·코스닥 핵심 흐름 및 수급 요약 (2문장)",
      "issues": [
        {{
          "id": "dom-{slot}-1",
          "tag": "핵심 섹터명",
          "title": "이슈 제목",
          "summary": "핵심 내용과 시장 영향 (2~3문장)",
          "companies": ["관련기업1", "관련기업2"],
          "picks": [
            {{"name": "종목명", "reason": "주목 포인트 한 줄 요약"}}
          ]
        }}
      ]
    }}
    issues는 가장 중요한 3가지를 작성하세요.
    """
    return ask_gemini_json(prompt)


def fetch_global_news() -> list:
    prompt = f"""
    오늘은 {TODAY}입니다. 한국(KR), 미국(US), 일본(JP)의 오늘 주요 경제·산업·증시 기사를 웹 검색으로 조사해 국가별 2건씩 총 6건을 아래 JSON 배열 형식으로만 답하세요.
    [
      {{
        "id": "news-1",
        "country": "KR",
        "source": "언론사명",
        "title": "기사 핵심 제목",
        "summary": "핵심 내용 2문장 요약",
        "impact": "시장·산업 시사점 한 줄"
      }}
    ]
    country는 반드시 "KR", "US", "JP" 중 하나를 사용하세요.
    """
    return ask_gemini_json(prompt)


def fetch_us_industry() -> list:
    prompt = f"""
    오늘은 {TODAY}입니다. 미국 3대 핵심 산업(전력·에너지, 데이터센터, 휴머노이드)의 최신 동향을 웹 검색으로 조사해 각 분야별 1~2건씩 아래 JSON 배열 형식으로만 답하세요.
    [
      {{
        "id": "us-1",
        "sector": "전력·에너지",
        "title": "핵심 동향 제목",
        "summary": "미국 현지 기업·정책·수주 동향 2~3문장",
        "usTickers": ["미국 관련주 티커 또는 기업명"],
        "krLink": "국내 연관 산업 및 주목할 기업 한 줄"
      }}
    ]
    sector는 반드시 "전력·에너지", "데이터센터", "휴머노이드" 중 하나를 사용하세요.
    """
    return ask_gemini_json(prompt)


def fetch_social_theme() -> list:
    prompt = f"""
    오늘은 {TODAY}입니다. 최근 국내에서 화제가 된 사회·사건·제도 변화 이슈(예: 시험 부정행위 방지 보안, 안전 규제 강화, 인구·생활 변화 등) 중 특정 산업과 상장 기업 수혜로 연결되는 테마 2~3건을 웹 검색으로 찾아 아래 JSON 배열 형식으로만 답하세요.
    [
      {{
        "id": "soc-1",
        "category": "보안·안전",
        "issue": "사회 이슈 및 사건 요약 (1~2문장)",
        "industryImpact": "이로 인해 커지는 산업·정책·공공조달 변화 (1~2문장)",
        "picks": [
          {{"name": "국내 관련 상장사", "reason": "연결 고리 및 수혜 포인트"}}
        ]
      }}
    ]
    """
    return ask_gemini_json(prompt)


def load_today_data() -> dict:
    if TODAY_FILE.exists():
        return json.loads(TODAY_FILE.read_text(encoding="utf-8"))
    return {
        "date": TODAY,
        "domestic": {},
        "news": [],
        "us_industry": [],
        "social_theme": [],
    }


def update_index():
    dates = sorted(
        [p.stem for p in DATA_DIR.glob("????-??-??.json")],
        reverse=True,
    )
    INDEX_FILE.write_text(json.dumps(dates, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    slot = determine_slot()
    data = load_today_data()

    if slot in ("08", "all"):
        data["domestic"]["08"] = fetch_domestic("08")
        data["news"] = fetch_global_news()
        data["us_industry"] = fetch_us_industry()
        data["social_theme"] = fetch_social_theme()
    if slot in ("14", "all"):
        data["domestic"]["14"] = fetch_domestic("14")
    if slot in ("16", "all"):
        data["domestic"]["16"] = fetch_domestic("16")

    TODAY_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    update_index()
    print(f"[{TODAY}] slot={slot} 브리핑 업데이트 완료")


if __name__ == "__main__":
    main()

