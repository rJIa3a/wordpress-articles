import os
import json
from bs4 import BeautifulSoup
from markdownify import markdownify as md

input_folder = "articles"
output_file = "clean_articles.json"

result = []

for filename in os.listdir(input_folder):
    if filename.endswith(".json"):
        path = os.path.join(input_folder, filename)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        html = data["content"]["rendered"]
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["style", "script", "iframe", "svg"]):
            tag.decompose()

        clean_text = md(str(soup), strip=["a"])

        result.append({
            "title": data["title"]["rendered"],
            "url": data["link"],
            "text": clean_text
        })

with open(output_file, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
