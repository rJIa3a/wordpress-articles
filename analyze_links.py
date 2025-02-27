import os
import json
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Папка со статьями
ARTICLES_DIR = "articles"
LINKS_FILE = "internal_links.json"

# Загружаем статьи
def load_articles():
    articles = {}
    for filename in os.listdir(ARTICLES_DIR):
        if filename.endswith(".json"):
            with open(os.path.join(ARTICLES_DIR, filename), "r", encoding="utf-8") as f:
                post = json.load(f)
                articles[post["id"]] = {
                    "title": post["title"]["rendered"],
                    "url": post["link"],
                    "content": post["content"]["rendered"]
                }
    return articles

# Вычисляем похожие статьи (по TF-IDF)
def find_similar_articles(articles, top_n=3):
    texts = [articles[a]["content"] for a in articles]
    vectorizer = TfidfVectorizer(stop_words="english")
    tfidf_matrix = vectorizer.fit_transform(texts)
    similarities = cosine_similarity(tfidf_matrix)

    links = {}
    ids = list(articles.keys())

    for i, article_id in enumerate(ids):
        similar_indices = np.argsort(similarities[i])[::-1][1:top_n+1]
        links[article_id] = [
            {
                "id": ids[j],
                "title": articles[ids[j]]["title"],
                "url": articles[ids[j]]["url"]
            } 
            for j in similar_indices
        ]
    return links

# Основной процесс
articles = load_articles()
internal_links = find_similar_articles(articles)

# Сохраняем в JSON
with open(LINKS_FILE, "w", encoding="utf-8") as f:
    json.dump(internal_links, f, ensure_ascii=False, indent=4)

print(f"Файл {LINKS_FILE} обновлён.")
