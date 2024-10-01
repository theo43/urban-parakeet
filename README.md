# urban-parakeet
This application allows sending PDF documents to be stored in a MongoDB database, its text extracted to be summarized by a LLM. Entities from the text are then extracted, all these information being stored in the same database.

# How to run
```
docker-compose up build
```

Then POST to `http://localhost:8000/documents` with a body containing a `file` key and your PDF file as a File with your favorite API Client tool.

It will generate a `file_id` that can be used to retrieve the summary and entities stored in the Mongo database with a GET call on `http://localhost:8000/summary/<file_id>`

