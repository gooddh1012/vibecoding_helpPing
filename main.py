import sys
import json
import os
import io

# stdout UTF-8 설정
sys.stdout = io.TextIOWrapper(
    sys.stdout.buffer,
    encoding='utf-8'
)

import pdfplumber

from dotenv import load_dotenv
from openai import OpenAI

from pymongo import MongoClient
from datetime import datetime

###################################
# 로그 함수 (stderr)
###################################

def log(*args):
    print(*args, file=sys.stderr, flush=True)

log("현재 Python 경로:", sys.executable)

###################################
# ENV 로드
###################################

load_dotenv()

###################################
# OpenAI
###################################

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

###################################
# MongoDB 연결
###################################

mongo_client = MongoClient(
    os.getenv("MONGO_URI")
)

mongo_db = mongo_client[
    os.getenv("MONGO_DB")
]

mongo_collection = mongo_db[
    os.getenv("MONGO_COLLECTION")
]

###################################
# index (email 기준 검색 최적화)
###################################

mongo_collection.create_index(
    [("email", 1), ("topics", 1)]
)

###################################
# prompt 읽기
###################################

def load_prompt(name):

    with open(
        f"prompts/{name}",
        "r",
        encoding="utf-8"
    ) as f:

        return f.read()

###################################
# PDF 읽기
###################################

def read_pdf(path):

    log("PDF 읽는 중...")

    text = ""

    with pdfplumber.open(path) as pdf:

        for page in pdf.pages:

            page_text = page.extract_text()

            if page_text:

                text += page_text + "\n"

    return text

###################################
# GPT 실행
###################################

def run_gpt(prompt):

    log("GPT 실행 중...")

    response = client.chat.completions.create(

        model="gpt-4.1",

        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],

        response_format={
            "type": "json_object"
        }

    )

    result = response.choices[0].message.content

    log("GPT 결과:", result)

    return result

###################################
# topic 정리
###################################

def clean_topics(raw_topics):

    clean = []

    for t in raw_topics:

        if isinstance(t, dict):

            topic_name = t.get("topic")

            if topic_name:
                clean.append(topic_name)

        elif isinstance(t, str):

            if t.strip():
                clean.append(t.strip())

    return clean

###################################
# upload 처리 (email 저장)
###################################

def process_upload(file_path, email):

    text = read_pdf(file_path)

    if not text.strip():

        raise Exception(
            "PDF 텍스트 없음"
        )

    template = load_prompt(
        "text_prompt.txt"
    )

    prompt = template.replace(
        "{{TEXT}}",
        text
    )

    result = run_gpt(prompt)

    ###################################
    # JSON 파싱
    ###################################

    try:

        parsed = json.loads(result)

    except Exception:

        log("JSON 파싱 실패:", result)

        raise Exception(
            "GPT JSON 파싱 실패"
        )

    ###################################
    # topics 추출
    ###################################

    raw_topics = parsed.get(
        "topics",
        []
    )

    topics = clean_topics(
        raw_topics
    )

    log("정리된 topics:", topics)

    ###################################
    # MongoDB 저장
    ###################################

    mongo_collection.insert_one({

        "email": email,

        "file_name":
        os.path.basename(
            file_path
        ),

        "topics": topics,

        "content": text,

        "date":
        datetime.now()
        .strftime("%Y-%m-%d")

    })

    log("전체 PDF와 topics 저장 완료")

    return topics

###################################
# 질문 처리 (email 기준 검색)
###################################

def process_question(question, email):

    ###################################
    # 1단계: 해당 email의 모든 자료 가져오기
    ###################################

    docs = list(mongo_collection.find({
        "email": email
    }))

    if not docs:

        return {
            "answer":
            "업로드된 학습 자료가 없습니다."
        }

    ###################################
    # 2단계: 모든 topic 모으기
    ###################################

    all_topics = []

    for doc in docs:

        for t in doc.get("topics", []):

            all_topics.append(t)

    ###################################
    # 3단계: GPT로 topic 선택
    ###################################

    topic_prompt = f"""
다음은 학습 주제 목록이다.

{all_topics}

사용자 질문:
{question}

이 질문과 가장 관련 있는 topic 하나만 정확히 선택해서 출력하라.
몇 주차에 배웠는지도 말하여라
반드시 JSON 형식으로 출력하라.
출력 형식:
{{
  "topic": "선택된 topic"
}}
"""

    topic_response = client.chat.completions.create(

        model="gpt-4.1",

        messages=[
            {
                "role": "user",
                "content": topic_prompt
            }
        ],

        response_format={
            "type": "json_object"
        }

    )

    topic_json = json.loads(
        topic_response.choices[0]
        .message.content
    )

    selected_topic = topic_json.get(
        "topic"
    )

    log("선택된 topic:", selected_topic)

    ###################################
    # 4단계: 해당 topic 문서 찾기
    ###################################

    found = mongo_collection.find_one({

        "email": email,

        "topics": selected_topic

    })

    if not found:

        return {
            "answer":
            "관련 내용을 찾지 못했습니다."
        }

    ###################################
    # 5단계: GPT로 최종 답변 생성
    ###################################

    context = f"""
주제: {', '.join(found['topics'])}

내용:
{found['content']}
"""

    answer_prompt = f"""
다음 학습 정보를 참고하여 질문에 답하라.
질문한 것 만 말하여라 또한
몇 주차에 배웠는지도 말하여라

정보:
{context}

질문:
{question}
반드시 정보 안에서만 답하라.
"""

    response = client.chat.completions.create(

        model="gpt-4.1",

        messages=[
            {
                "role": "user",
                "content": answer_prompt
            }
        ]

    )

    answer = response.choices[0] \
        .message.content

    return {
        "answer": answer
    }

###################################
# MAIN
###################################

try:

    mode = sys.argv[1]

    ###################################
    # upload
    ###################################

    if mode == "upload":

        file_path = sys.argv[2]

        email = sys.argv[3]

        topics = process_upload(
            file_path,
            email
        )

        print(json.dumps({

            "topics": topics

        }, ensure_ascii=False))

    ###################################
    # question
    ###################################

    elif mode == "question":

        question = sys.argv[2]

        email = sys.argv[3]

        result = process_question(
            question,
            email
        )

        print(json.dumps(
            result,
            ensure_ascii=False
        ))

except Exception as e:

    log("ERROR:", str(e))

    print(json.dumps({
        "error": str(e)
    }))