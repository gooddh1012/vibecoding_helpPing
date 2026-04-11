import sys
import json
import os
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from dotenv import load_dotenv
from openai import OpenAI

from pymongo import MongoClient
from datetime import datetime
import sys
print("현재 Python 경로:", sys.executable)

import pdfplumber

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

mongo_client = MongoClient(
    os.getenv("MONGO_URI")
)

mongo_db = mongo_client[
    os.getenv("MONGO_DB")
]

mongo_collection = mongo_db[
    os.getenv("MONGO_COLLECTION") 
]

mongo_collection.create_index(
    [("topic", 1), ("week", 1)],
    unique=True
)

def load_prompt(name):

    with open(
        f"prompts/{name}",
        "r",
        encoding="utf-8"
    ) as f:

        return f.read()

def read_pdf(path):

    print("PDF 읽는 중...", flush=True)

    text = ""

    with pdfplumber.open(path) as pdf:

        for page in pdf.pages:

            page_text = page.extract_text()

            if page_text:

                text += page_text + "\n"

    return text

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

def process_upload(file_path):
    text = read_pdf(file_path)

    template = load_prompt("text_prompt.txt")
    prompt = template.replace("{{TEXT}}", text)
    
    result = run_gpt(prompt)
    parsed = json.loads(result)

    topics = parsed["topics"] 

    mongo_collection.update_one(
        {"file_name": os.path.basename(file_path)},
        {"$set": {
            "week": 13,                
            "topics": [t["topic"] for t in topics],
            "content": text,             
            "date": datetime.now().strftime("%Y-%m-%d")
        }},
        upsert=True
    )

    print("전체 PDF와 topics 저장 완료", flush=True)
    return topics

def process_question(question):
    keyword = question.split()[0] 

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
    다음 학습 정보를 기반으로 질문에 답하라.

    정보:
    {context}

    질문:
    {question}

    [답변 규칙]

    - 반드시 위에 제공된 정보만을 근거로 답하라.
    - 정보에 없는 내용은 절대 추가하지 마라.
    - 추측, 일반 상식 보완, 외부 지식 사용을 금지한다.
    - 주차 정보가 제공되지 않았다면 "주차 정보는 제공되지 않았다"고만 말하라.
    - 질문이 제공 정보와 관련이 없다면 답변하지 말고 "제공된 정보로는 답할 수 없다"고 말하라.
    - 내용을 과장하거나 확장하지 말고, 정보 범위 내에서만 설명하라.
    - 사람에게 설명하듯 자연스럽게 작성하되, 사실만 전달하라.
    """
    
    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[{"role": "user", "content": prompt}]
    )

    answer = response.choices[0].message.content

    return {"answer": answer}

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