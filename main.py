import sys
import json
import os
import io

sys.stdout = io.TextIOWrapper(
    sys.stdout.buffer,
    encoding='utf-8'
)

import pdfplumber

from dotenv import load_dotenv
from openai import OpenAI

from pymongo import MongoClient
from datetime import datetime

def log(*args):
    print(*args, file=sys.stderr, flush=True)

log("현재 Python 경로:", sys.executable)

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
    [("email", 1), ("topics", 1)]
)

def load_prompt(name):

    with open(
        f"prompts/{name}",
        "r",
        encoding="utf-8"
    ) as f:

        return f.read()

def read_pdf(path):

    log("PDF 읽는 중...")

    text = ""

    with pdfplumber.open(path) as pdf:

        for page in pdf.pages:

            page_text = page.extract_text()

            if page_text:

                text += page_text + "\n"

    return text


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

    try:

        parsed = json.loads(result)

    except Exception:

        log("JSON 파싱 실패:", result)

        raise Exception(
            "GPT JSON 파싱 실패"
        )

    raw_topics = parsed.get(
        "topics",
        []
    )

    topics = clean_topics(
        raw_topics
    )

    log("정리된 topics:", topics)


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

def process_question(question, email):

    docs = list(mongo_collection.find({
        "email": email
    }))

    if not docs:

        return {
            "answer":
            "업로드된 학습 자료가 없습니다."
        }

    all_topics = []

    for doc in docs:

        for t in doc.get("topics", []):

            all_topics.append(t)

    topic_prompt = f"""
    다음은 학습 주제 목록이다.

    {all_topics}
    
    사용자 질문:
    {question}

    지시 사항:

    - 질문과 가장 관련 있는 topic 하나만 정확히 선택하라.
    - 몇 주차에 배웠는지도 말하여라.
    - 해당 topic이 몇 주차인지 함께 포함하라.
    - 반드시 JSON 형식으로만 출력하라.
    - JSON 외 다른 텍스트는 절대 출력하지 마라.

    출력 형식:

    {{
        "topic": "선택된 topic",
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

    found = mongo_collection.find_one({

        "email": email,

        "topics": selected_topic

    })

    if not found:

        return {
            "answer":
            "관련 내용을 찾지 못했습니다."
        }

    context = f"""
    주제: {', '.join(found['topics'])}

    내용:
    {found['content']}
    """
    
    answer_prompt = f"""
    다음 학습 정보를 참고하여 질문에 답하라.

    [정보]
    {context}

    [질문]
    {question}

    답변 규칙:

    - 질문에서 묻는 내용만 간결하게 답하라.
    - 해당 내용이 몇 주차에 학습되었는지도 함께 말하라.
    - 반드시 위 정보에 포함된 내용만 사용하라.
    - 정보에 없는 내용은 추가하지 마라.
    - 추측하거나 확장하지 마라.
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

try:

    mode = sys.argv[1]

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