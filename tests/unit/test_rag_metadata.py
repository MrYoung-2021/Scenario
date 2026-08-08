from langchain_core.documents import Document
import pytest

from rag.rag import RAG


class FakeVectorStore:
    def __init__(self):
        self.search_call = None

    async def asimilarity_search_with_relevance_scores(self, query, *, k, filter):
        self.search_call = (query, k, filter)
        return [
            (
                Document(
                    page_content="knowledge",
                    metadata={
                        "category": "formation",
                        "source": "manual",
                        "source_id": "source-1",
                        "verified": True,
                    },
                ),
                0.87,
            )
        ]


@pytest.mark.asyncio
async def test_rag_serializes_relevance_score_and_metadata_filter() -> None:
    vector_store = FakeVectorStore()
    rag = RAG(vector_store=vector_store, embeddings=object())

    result = await rag.asearch(
        "formation",
        k=5,
        metadata_filter={"category": "formation", "side": "red"},
    )

    assert vector_store.search_call == (
        "formation",
        5,
        {
            "$and": [
                {"category": "formation"},
                {"$or": [{"side": "red"}, {"side": "all"}]},
            ]
        },
    )
    assert result[0].score == 0.87
    assert result[0].source_id == "source-1"
    assert result[0].verified is True


def test_rag_uses_configured_text_splitter_for_long_content() -> None:
    class AddStore:
        def add_texts(self, texts, *, metadatas, ids):
            self.texts = texts
            return ids

    store = AddStore()
    rag = RAG(vector_store=store, embeddings=object())
    rag.text_splitter = type("Splitter", (), {"split_text": lambda self, text: ["one", "two"]})()

    ids = rag.add_text("x" * 2100, "expert")

    assert store.texts == ["one", "two"]
    assert len(set(ids)) == 2

