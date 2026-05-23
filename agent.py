import chromadb
from chromadb.utils import embedding_functions
from groq import Groq
import os
from dotenv import load_dotenv

# ROCKY: load environment variables
load_dotenv()

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

# ROCKY: groq client = fast cloud-based AI from Groq
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY not found in .env file")
groq_client = Groq(api_key=GROQ_API_KEY)

def expand_query(question: str) -> str:
    # ROCKY: query expansion adds related terms to improve vector search
    # example: "top scorer" → "top scorer goals scored most goals player"
    # we use groq to generate related terms
    
    prompt = f"""You are a football analyst. Expand this question with 2-3 related synonyms or related terms.
Return ONLY the expanded question as a single line. No explanation.

Question: {question}

Expanded question:"""
    
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200
    )
    
    expanded = response.choices[0].message.content.strip()
    # ROCKY: combine original + expanded for better search coverage
    return f"{question} {expanded}"

def rerank_chunks(question: str, chunks: list) -> list:
    # ROCKY: reranking scores each chunk 0-1 based on keyword overlap
    # chunks with more matching keywords score higher
    # this brings more relevant results to the top
    
    def fuzzy_match(q_word: str, chunk: str) -> bool:
        # ROCKY: fuzzy name matching for abbreviated player names
        # "bruno" matches "B. Fernandes" or "Fernandes"
        # "salah" matches "M. Salah" or "Salah"
        chunk_lower = chunk.lower()
        
        # ROCKY: exact substring match
        if q_word in chunk_lower:
            return True
        
        # ROCKY: check if word matches last name or first letter
        # e.g. "bruno" matches chunks with "fernandes" (last name)
        # or "b." (first initial)
        words_in_chunk = chunk_lower.split()
        for word in words_in_chunk:
            # ROCKY: match first initial (b., m., etc)
            if word.startswith(q_word[0] + "."):
                return True
            # ROCKY: match common last names if q_word could be first name
            if q_word in word:
                return True
        
        return False
    
    def calculate_relevance(q: str, chunk: str) -> float:
        # ROCKY: keyword overlap + fuzzy name matching
        q_words = set(q.lower().split())
        chunk_words = set(chunk.lower().split())
        
        # ROCKY: remove common words that don't add meaning
        stopwords = {"the", "a", "an", "is", "are", "in", "on", "at", "of", "or", "and"}
        q_words = q_words - stopwords
        chunk_words = chunk_words - stopwords
        
        # ROCKY: exact keyword matches
        if len(q_words) == 0 or len(chunk_words) == 0:
            return 0.0
            
        # ROCKY: count exact matches
        exact_intersection = len(q_words & chunk_words)
        
        # ROCKY: fuzzy matches for potential player names (longer words)
        fuzzy_matches = 0
        for q_word in q_words:
            if len(q_word) > 3:  # ROCKY: only fuzzy match words > 3 chars (likely names)
                if fuzzy_match(q_word, chunk):
                    fuzzy_matches += 1
        
        # ROCKY: combined score: exact matches weighted more than fuzzy
        union = len(q_words | chunk_words)
        jaccard = exact_intersection / union if union > 0 else 0.0
        fuzzy_bonus = fuzzy_matches * 0.1  # ROCKY: fuzzy adds small bonus
        
        return min(jaccard + fuzzy_bonus, 1.0)  # ROCKY: cap at 1.0
    
    # ROCKY: score each chunk and sort by relevance
    scored_chunks = [
        (chunk, calculate_relevance(question, chunk))
        for chunk in chunks
    ]
    
    # ROCKY: sort by score descending (highest first)
    scored_chunks.sort(key=lambda x: x[1], reverse=True)
    
    # ROCKY: return just the chunk text, reranked
    return [chunk for chunk, score in scored_chunks]

def ask(question: str) -> str:
    # ROCKY: ADVANCED RAG FLOW
    
    # ROCKY: step 0 → expand question with related terms
    expanded_question = expand_query(question)
    print(f"\n[DEBUG] expanded query: {expanded_question}")
    
    # ROCKY: step 1 → search chromadb for TOP 20 chunks
    # we get more results so reranking has good options
    results = collection.query(
        query_texts=[expanded_question],
        n_results=20
    )
    
    chunks = results["documents"][0]
    print(f"\n[DEBUG] raw search returned {len(chunks)} chunks")
    
    # ROCKY: step 2 → rerank chunks based on keyword overlap with ORIGINAL question
    reranked_chunks = rerank_chunks(question, chunks)
    
    # ROCKY: step 3 → pick top 5 after reranking
    top_5_chunks = reranked_chunks[:5]
    print(f"\n[DEBUG] after reranking, using top 5 chunks")
    
    # ROCKY: debug - show what chunks are being sent to groq
    print("\n[DEBUG] chunks being sent to groq:")
    for c in top_5_chunks:
        print(f"  → {c[:100]}")
    
    # ROCKY: step 4 → join chunks into context block
    context = "\n".join(top_5_chunks)
    
    # ROCKY: step 5 → build prompt
    # we give groq context + question
    # we tell it to ONLY answer from context. no making things up.
    prompt = f"""You are a Premier League football analyst assistant.
Use ONLY the context below to answer the question.
If the answer is not in the context, say "I don't have that information."

Note: Player names may be abbreviated. B. Fernandes means Bruno Fernandes. M. Salah means Mohamed Salah. Use context clues.

Context:
{context}

Question: {question}

Answer:"""
    
    # ROCKY: step 6 → send to groq and get answer
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1000
    )
    
    return response.choices[0].message.content


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