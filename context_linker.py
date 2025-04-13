import json
import numpy as np
from sentence_transformers import SentenceTransformer, util

# Загружаем очищенные статьи
with open("clean_articles.json", "r", encoding="utf-8") as f:
    articles = json.load(f)

titles = [a["title"] for a in articles]
texts = [a["text"] for a in articles]
urls = [a["url"] for a in articles]

# Загружаем модель
model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
embeddings = model.encode(texts, convert_to_tensor=True)

# Считаем близость и находим лучшие пары
links = []
for i, emb in enumerate(embeddings):
    cos_sim = util.cos_sim(emb, embeddings)[0]
    cos_sim[i] = -1  # не сравниваем статью саму с собой
    best_match = np.argmax(cos_sim)

    links.append({
        "source_url": urls[i],
        "anchor": titles[best_match],  # в качестве анкора используем заголовок
        "target_url": urls[best_match]
    })

# Сохраняем результат
with open("context_links.json", "w", encoding="utf-8") as f:
    json.dump(links, f, ensure_ascii=False, indent=2)
