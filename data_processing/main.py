import os
import json
import uuid
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pymongo import MongoClient
import pytesseract
import re
import logging
import datetime
from pdf2image import convert_from_bytes


# Configure the logger
logging.basicConfig(
    level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI()

database_name = os.getenv("DATABASE_NAME", "up_db")
collection_name_documents = os.getenv("COLLECTION_NAME_DOCUMENTS", "documents")
collection_name_summaries = os.getenv("COLLECTION_NAME_SUMMARIES", "summaries")
mongo_uri = os.getenv("MONGO_URI")
llm_service_url = os.getenv("LLM_SERVICE_URL")
summarizer_service_url = os.getenv("SUMMARIZER_SERVICE_URL")
client = MongoClient(mongo_uri)
db = client[database_name]
collection_documents = db[collection_name_documents]
collection_summaries = db[collection_name_summaries]

def clean_extracted_text(text):
    # Replace multiple newlines with a single newline
    text = re.sub(r'\n+', '\n', text)
    # Optionally, replace newlines with spaces
    text = text.replace('\n', ' ')
    # Remove special chars
    text = re.sub(r'[^a-zA-Z0-9\s.,!?\'"-]', '', text)
    # Trim leading and trailing whitespace
    text = text.strip()
    return text


@app.get("/process/{file_id}")
async def process_document(file_id: str):
    doc = collection_documents.find_one({"file_id": file_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    pdf_content = doc.get("content")
    logger.info(f"Received document with ID: {file_id}")
    if not pdf_content:
        raise HTTPException(status_code=400, detail="Invalid document content")

    # Convert PDF content to images
    images = convert_from_bytes(pdf_content)
    logger.info('PDF document converted into image')

    # Extract text from images using Tesseract
    extracted_text = ""
    for image in images:
        extracted_text += pytesseract.image_to_string(image)
    
    clean_text = clean_extracted_text(extracted_text)
    logger.info("Extracted text cleaned")

    try:
        response = requests.post(
            summarizer_service_url,
            json={'text': clean_text, "file_id": file_id},
            timeout=120
        )
        response.raise_for_status()
        summary = response.json().get("summary")
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="LLM service timed out")
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Failed to summarize text: {e}")


    return {
        "file_id": file_id,
        "extracted_text": extracted_text,
        "summary": summary,
        "entities": response.json().get("entities")
    }