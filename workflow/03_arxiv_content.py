import sys, os
from dotenv import load_dotenv
from langchain.document_loaders import ArxivLoader

load_dotenv()
sys.path.append(os.environ.get("PROJECT_PATH"))

import utils.paper_utils as pu

db_params = pu.db_params


def main():
    """Load summaries and add missing ones."""
    arxiv_code_map = pu.get_arxiv_title_dict()

    items_added = 0
    for k, v in arxiv_code_map.items():
        if os.path.exists(f"../data/arxiv/{k}.txt"):
            print(f"File {k} already exists.")
            continue
        docs = ArxivLoader(
            query=pu.preprocess(v), load_max_docs=3, doc_content_chars_max=int(1e10)
        ).load()
        docs = sorted(
            docs,
            key=lambda x: pu.tfidf_similarity(v, x.metadata["Title"]),
            reverse=True,
        )
        new_title = docs[0].metadata["Title"]
        title_sim = pu.tfidf_similarity(v, new_title)
        if title_sim < 0.7:
            print(f"No matching title found for {v}. Most similar: {new_title}")
            continue
        doc_content = docs[0].page_content
        with open(f"../data/arxiv/{k}.txt", "w") as f:
            f.write(doc_content)
        print(f"File {k} saved.")
        items_added += 1

    print(f"Process complete. Added {items_added} items in total.")


if __name__ == "__main__":
    main()