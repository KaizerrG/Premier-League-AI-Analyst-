import chromadb
from chromadb.utils import embedding_functions
from ollama import Client

# ROCKY: connect to chromadb where our PL data lives
client = chromadb.PersistentClient(path="./chroma_db")

# ROCKY: same embedding model we used in rag.py. must match.
embedding_fn = embedding_functions.OllamaEmbeddingFunction(
    url="http://localhost:11434",
    model_name="nomic-embed-text"
)

collection = client.get_or_create_collection(
    name="pl_data",
    embedding_function=embedding_fn
)

# ROCKY: ollama client = connection to local AI brain
ollama = Client(host="http://localhost:11434")

def ask(question: str) -> str:
    # ROCKY: step 1 → search chromadb for most relevant chunks
    # n_results=5 = give me top 5 most relevant pieces of data
    results = collection.query(
        query_texts=[question],
        n_results=5
    )
    
    # ROCKY: step 2 → join chunks into one context block
    chunks = results["documents"][0]
    context = "\n".join(chunks)
    
    # ROCKY: step 3 → build prompt
    # we give ollama context + question
    # we tell it to ONLY answer from context. no making things up.
    prompt = f"""You are a Premier League football analyst assistant.
Use ONLY the context below to answer the question.
If the answer is not in the context, say "I don't have that information."

Context:
{context}

Question: {question}

Answer:"""
    
    # ROCKY: step 4 → send to ollama and get answer
    response = ollama.chat(
        model="llama3",
        messages=[{"role": "user", "content": prompt}]
    )
    
    return response["message"]["content"]


def main():
    print("PL Football Analyst Agent")
    print("type 'quit' to exit")
    print("-" * 40)
    
    while True:
        # ROCKY: simple loop. ask question. get answer. repeat.
        question = input("\nAsk anything about PL 2024/25: ")
        
        if question.lower() == "quit":
            break
            
        print("\nthinking...")
        answer = ask(question)
        print(f"\n{answer}")

if __name__ == "__main__":
    main()