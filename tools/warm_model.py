from fastembed import TextEmbedding
model=TextEmbedding('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2',cache_dir='local-data/models',threads=2)
v=list(model.embed(['Москва — столица России.','Санкт-Петербург расположен на Неве.']))
print('Neural embeddings ready:',len(v),len(v[0]),flush=True)
