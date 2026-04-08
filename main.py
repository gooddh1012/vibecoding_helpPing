import sys
import json
import os
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pdfplumber

from dotenv import load_dotenv
from openai import OpenAI

from pymongo import MongoClient
from datetime import datetime
import sys
print("현재 Python 경로:", sys.executable)
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
    # PDF 전체 텍스트 읽기
    text = read_pdf(file_path)

    # PDF 전체 내용을 그대로 저장할 week와 topics 추출
    # 예시: GPT로 주제만 뽑기
    template = load_prompt("text_prompt.txt")
    prompt = template.replace("{{TEXT}}", text)
    
    result = run_gpt(prompt)
    parsed = json.loads(result)

    topics = parsed["topics"]  # ["프로시저", "사용자 정의 함수", ...]

    # MongoDB에 전체 PDF 저장
    mongo_collection.update_one(
        {"file_name": os.path.basename(file_path)},
        {"$set": {
            "week": 13,                  # 예시로 week 13
            "topics": [t["topic"] for t in topics],
            "content": text,             # PDF 전체 내용 통째로
            "date": datetime.now().strftime("%Y-%m-%d")
        }},
        upsert=True
    )

    print("전체 PDF와 topics 저장 완료", flush=True)
    return topics

###################################
# question
###################################

def process_question(question):
    keyword = question.split()[0]  # 예: "프로시저"

    # MongoDB에서 topics 배열 안 검색
    found = mongo_collection.find_one({
        "topics": {
            "$elemMatch": {"$regex": keyword, "$options": "i"}
        }
    })

    if not found:
        return {"answer": "관련 내용을 찾지 못했습니다."}

    context = f"""
        주제: {', '.join(found['topics'])}
        내용: {found['content']}
        주차: {found['week']}
        """

    prompt = f"""
        다음 학습 정보를 참고하여 질문에 자연스럽게 답하라.

        정보:
        {context}

        질문:
        {question}

        답변은 사람이 말하듯 자연스럽게 작성하라.
        또한 주차가 없으면 없다고 말하고 추측은 하지 않고 정보에 기반한 사실만을 토대로 말을 해
        없는 내용이면 굳이 대답을 하지 않아도 괜찮아
        """

    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[{"role": "user", "content": prompt}]
    )

    answer = response.choices[0].message.content

    return {"answer": answer}

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