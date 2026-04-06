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

print("MongoDB 연결 완료")

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

    chunks = []

    start = 0

    while start < len(text):

        end = start + max_length

        chunks.append(
            text[start:end]
        )

        start = end

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

    for chunk in chunks:

        prompt = template.replace(
            "{{TEXT}}",
            chunk
        )

        result = run_gpt(prompt)

        parsed = json.loads(result)

        topics = parsed["topics"]

        save_topics(topics)

        all_topics.extend(topics)

    return all_topics

###################################
# question
###################################

def process_question(question):

    keyword = question.split()[0]

    found = mongo_collection.find_one({

        "topic": {
            "$regex": keyword,
            "$options": "i"
        }

    })

    if found:

        found["_id"] = str(found["_id"])

        return found

    return {
        "message": "기록 없음"
    }

###################################
# summary
###################################

def process_summary():

    docs =
    list(mongo_collection.find())

    text = ""

    for d in docs:

        text += d["content"] + "\n"

    chunks = split_text(text)

    template = load_prompt(
        "summary_prompt.txt"
    )

    summaries = []

    for chunk in chunks:

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

    print(json.dumps(result))

elif mode == "summary":

    result = process_summary()

    print(result)