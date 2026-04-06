import sys
import json
import os

import pdfplumber

from dotenv import load_dotenv
from openai import OpenAI

from pymongo import MongoClient
from datetime import datetime

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

print("MongoDB 연결 완료", flush=True)

###################################
# index 생성
###################################

mongo_collection.create_index(
    [("topic", 1), ("week", 1)],
    unique=True
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

    print("PDF 읽는 중...", flush=True)

    text = ""

    with pdfplumber.open(path) as pdf:

        for page in pdf.pages:

            page_text = page.extract_text()

            if page_text:

                text += page_text + "\n"

    return text

###################################
# chunk 분리
###################################

def split_text(text, max_length=8000):

    print("텍스트 분할 중...", flush=True)

    chunks = []

    start = 0

    while start < len(text):

        end = start + max_length

        chunks.append(
            text[start:end]
        )

        start = end

    print(f"총 chunk 수: {len(chunks)}", flush=True)

    return chunks

###################################
# GPT 실행
###################################

def run_gpt(prompt):

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

    return response.choices[0].message.content

###################################
# 저장
###################################

def save_topics(topics):

    for t in topics:

        print(
            f"저장 중: {t['topic']} (week {t['week']})",
            flush=True
        )

        mongo_collection.update_one(

            {
                "topic": t["topic"],
                "week": t["week"]
            },

            {
                "$set": {

                    "topic": t["topic"],

                    "content": t["content"],

                    "week": t["week"],

                    "date":
                    datetime.now()
                    .strftime("%Y-%m-%d")

                }
            },

            upsert=True

        )

###################################
# upload
###################################

def process_upload(file_path):

    text = read_pdf(file_path)

    chunks = split_text(text)

    template = load_prompt(
        "text_prompt.txt"
    )

    all_topics = []

    for i, chunk in enumerate(chunks):

        print(
            f"GPT 처리 중 {i+1}/{len(chunks)}",
            flush=True
        )

        prompt = template.replace(
            "{{TEXT}}",
            chunk
        )

        result = run_gpt(prompt)

        parsed = json.loads(result)

        topics = parsed["topics"]

        save_topics(topics)

        all_topics.extend(topics)

        print(
            f"완료 {i+1}/{len(chunks)}",
            flush=True
        )

    print("전체 완료", flush=True)

    return all_topics

###################################
# question
###################################

def process_question(question):

    # 질문에서 키워드 추출
    keyword = question.split()[0]

    # MongoDB에서 topic 검색
    found = mongo_collection.find_one({
        "topic": {
            "$regex": keyword,
            "$options": "i"
        }
    })

    # 찾지 못한 경우
    if not found:
        return {
            "answer": "관련 내용을 찾지 못했습니다."
        }

    # GPT에 전달할 context 생성
    context = f"""
주제: {found['topic']}
내용: {found['content']}
주차: {found['week']}
"""

    # GPT 프롬프트 생성
    prompt = f"""
다음 학습 정보를 참고하여 질문에 자연스럽게 답하라.

정보:
{context}

질문:
{question}

답변은 사람이 말하듯 자연스럽게 작성하라.
"""

    # GPT 호출
    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    # GPT 답변 추출
    answer = response.choices[0].message.content

    # 결과 반환
    return {
        "answer": answer
    }

###################################
# summary
###################################

def process_summary():

    print("summary 생성 중...", flush=True)

    docs = list(mongo_collection.find())

    text = ""

    for d in docs:

        text += d["content"] + "\n"

    chunks = split_text(text)

    template = load_prompt(
        "summary_prompt.txt"
    )

    summaries = []

    for i, chunk in enumerate(chunks):

        print(
            f"summary GPT {i+1}/{len(chunks)}",
            flush=True
        )

        prompt = template.replace(
            "{{TEXT}}",
            chunk
        )

        result = run_gpt(prompt)

        summaries.append(result)

    return "\n".join(summaries)

###################################
# MAIN
###################################

try:

    mode = sys.argv[1]

    if mode == "upload":

        file_path = sys.argv[2]

        topics = process_upload(
            file_path
        )

        print(json.dumps({
            "topics": topics
        }))

    elif mode == "question":

        question = sys.argv[2]

        result = process_question(
            question
        )

        print(json.dumps(result, ensure_ascii=False))

    elif mode == "summary":

        result = process_summary()

        print(result)

except Exception as e:

    print("ERROR:", str(e), flush=True)