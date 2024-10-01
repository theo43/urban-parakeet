// init-mongo.js
db = db.getSiblingDB('up_db');

// Create collections
db.createCollection('documents');

db.createCollection('summaries');

// Optionally insert some initial data
// db.system_prompts.insertMany([
//     {
//         prompt_id: 'A',
//         text: "Tu es un assistant très gentil qui répond à toutes les questions qu'on lui pose. Tu parles exclusivement le français. Toutes tes réponses doivent être en français."
//     },
//     {
//         prompt_id: 'B',
//         text: "You are an assistant who answers questions in English with Shakespearean English. All your responses must be in English."
//     }
// ]);