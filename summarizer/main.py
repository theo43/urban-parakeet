import os
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pymongo import MongoClient
from transformers import pipeline, AutoTokenizer
import logging
import datetime

app = FastAPI()

# Initialize logger
logger = logging.getLogger("uvicorn")
logger.setLevel(logging.INFO)

database_name = os.getenv("DATABASE_NAME", "up_db")
collection_name_documents = os.getenv("COLLECTION_NAME_DOCUMENTS", "documents")
collection_name_summaries = os.getenv("COLLECTION_NAME_SUMMARIES", "summaries")
mongo_uri = os.getenv("MONGO_URI")
client = MongoClient(mongo_uri)
db = client[database_name]
collection_documents = db[collection_name_documents]
collection_summaries = db[collection_name_summaries]

# Load the summarization pipeline
summarizer = pipeline("summarization", model="t5-small")
# Load tokenizer
tokenizer = AutoTokenizer.from_pretrained("t5-small")
# Load the NER pipeline
ner = pipeline("ner", model="dbmdz/bert-large-cased-finetuned-conll03-english")

class Document(BaseModel):
    id: str
    title: str
    content: bytes  # Change content to bytes to store binary data

class TextRequest(BaseModel):
    text: str
    file_id: str

def split_text(text, max_tokens):
    tokens = tokenizer.tokenize(text)
    len_tokens = len(tokens)
    len_tokens_chunks = []
    if len_tokens <= max_tokens:
        return [text], len_tokens, [len_tokens]
    
    chunks = []
    current_chunk = []
    current_length = 0
    
    for token in tokens:
        current_chunk.append(token)
        current_length += 1
        if current_length >= max_tokens:
            chunks.append(tokenizer.convert_tokens_to_string(current_chunk))
            current_chunk = []
            len_tokens_chunks.append(current_length)
            current_length = 0
    
    if current_chunk:
        chunks.append(tokenizer.convert_tokens_to_string(current_chunk))
    
    return chunks, len_tokens, len_tokens_chunks


@app.post("/infer/")
async def infer_text(request: TextRequest):
    file_id = request.file_id
    text = request.text
    logger.info(f"Received text to infer: {text} from file_id {file_id}")
    try:
        # Split the text if it exceeds the token limit
        max_tokens = 512  # Adjust this value as needed
        text_chunks, len_tokens, len_tokens_chunks = split_text(text, max_tokens)
        logger.info(
            f"Text of {len_tokens} tokens split into {len(text_chunks)} chunks of lengths {len_tokens_chunks}"
        )

        if len(text_chunks) == 1:
            logger.info(f"Text is {len_tokens} < {max_tokens}")
            final_summary = summarizer(
                text_chunks[0],
                max_length=150,
                min_length=30,
                do_sample=True
            )
        else:
            logger.info(f"Text is {len_tokens} > {max_tokens}")
            summaries = []
            for i, chunk in enumerate(text_chunks):
                logger.info(f"Processing chunk {i+1} of {len(text_chunks)}")
                summary = summarizer(
                    chunk,
                    max_length=150,
                    min_length=30,
                    do_sample=True
                )
                summaries.append(summary[0]['summary_text'])
            
            combined_summary = " ".join(summaries)
            logger.info(f"Generated combined summary: {combined_summary}")
            logger.info(f"Summarizing combined summary of length {len(combined_summary)}")
            final_summary = summarizer(
                combined_summary,
                max_length=150,
                min_length=30,
                do_sample=True
            )
        final_summary_text = final_summary[0]['summary_text']
        # Now extract entities using NER
        logger.info("Extracting entities from the summary")
        entities = ner(final_summary_text)
        entity_list = [
            {
                "entity": entity['entity'],
                "word": entity['word']
            } for entity in entities
        ]

        # Store the summary and its entities in MongoDB
        summary_doc = {
            "file_id": file_id,
            "summary": final_summary_text,
            "created_at": datetime.datetime.now(),
            "entities": entity_list
        }
        collection_summaries.insert_one(summary_doc)

        return {
            "summary": final_summary_text,
            "entities": entity_list
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
