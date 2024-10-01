import os
import json
import uuid
from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
from pymongo import MongoClient
import PyPDF2
from io import BytesIO
from fastapi.responses import StreamingResponse
import logging
import requests
import datetime


# Configure the logger
logging.basicConfig(
    level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI()

database_name = os.getenv("DATABASE_NAME", "up_db")
collection_name_documents = os.getenv(
    "COLLECTION_NAME_DOCUMENTS", "documents"
)
collection_name_summaries = os.getenv(
    "COLLECTION_NAME_SUMMARIES", "summaries"
)
mongo_uri = os.getenv("MONGO_URI")
client = MongoClient(mongo_uri)
db = client[database_name]
collection_documents = db[collection_name_documents]
collection_summaries = db[collection_name_summaries]


@app.post("/documents/")
async def create_document(file: UploadFile = File(...)):
    # Read the PDF file
    pdf_reader = PyPDF2.PdfFileReader(file.file)
    pdf_info = pdf_reader.getDocumentInfo()
    
    # Extract the title from the PDF metadata
    title = pdf_info.title if pdf_info.title else "Untitled Document"
    logger.info(f'Received document with title: {title}')
    # Read the file content
    file.file.seek(0)  # Reset file pointer to the beginning
    content = await file.read()
    
    # Generate a UUID for the document
    file_id = str(uuid.uuid4())
    
    # Create the document dictionary
    doc_dict = {
        "file_id": file_id,
        "title": title,
        "content": content,
        "created_at": datetime.datetime.now()
    }
    
    # Insert the document into the database
    result = collection_documents.insert_one(doc_dict)
    if result.inserted_id:

        # Send the document to the data preprocessing service
        logger.info(f"Sending file_id {file_id} to data preprocessing service")
        data_processing_service_url = os.getenv("DATA_PROCESSING_SERVICE_URL")
        if not data_processing_service_url:
            raise HTTPException(
                status_code=500, detail="Data preprocessing service URL not set"
            )
        
        logger.info(f"Data processing service URL: {data_processing_service_url}")
        response = requests.get(f"{data_processing_service_url}/{file_id}")
        if response.status_code != 200:
            raise HTTPException(
                status_code=500, detail="Failed to process document"
            )
        file_id = response.json().get("file_id")
        summary = response.json().get("summary")
        return {
            "file_id": file_id,
            "title": title,
            "summary": summary,
            "entities": response.json().get("entities")
        }
    
    raise HTTPException(status_code=500, detail="Document could not be created")


@app.get("/documents/{file_id}")
async def get_document(file_id: str):
    doc = collection_documents.find_one({"file_id": file_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    pdf_content = doc.get("content")
    if not pdf_content:
        raise HTTPException(status_code=400, detail="Invalid document content")

    return StreamingResponse(
        BytesIO(pdf_content),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={file_id}.pdf"}
    )

@app.get("/summary/{file_id}")
async def get_summary(file_id: str):
    res = collection_summaries.find_one({"file_id": file_id})
    logger.info(f'Retrieved summary for document: {file_id} and thats {res}')
    if not res:
        raise HTTPException(status_code=404, detail="Summary not found")

    return {
        'file_id': res['file_id'],
        'summary': res['summary'],
        'created_at': res['created_at'],
        'entities': res['entities']
    }

@app.get("/summaries/")
async def get_all_summaries():
    summaries = list(collection_summaries.find({}, {"_id": 0, "file_id": 1, "summary": 1}))
    return summaries

@app.delete("/clean/")
async def clean_collections():
    try:
        collection_documents.delete_many({})
        collection_summaries.delete_many({})
        return {"message": "Collections cleaned successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clean collections: {e}")