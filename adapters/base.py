from abc import ABC, abstractmethod

REQUIRED_CHUNK_FIELDS = {"text", "source_file", "wing", "room", "filed_at"}


class ChunkValidationError(Exception):
    pass


class AdapterBase(ABC):
    """
    Base class for all MindGraph source adapters.
    Subclasses implement fetch() to return a list of chunks
    conforming to the chunk schema in docs/adapter-contract.md.
    """

    @abstractmethod
    def fetch(self, config: dict) -> list[dict]:
        """
        Read from source and return a list of chunks.

        Each chunk must include: text, source_file, wing, room, filed_at.
        Optional fields: title, source_url, tags.
        """

    def fetch_and_validate(self, config: dict) -> list[dict]:
        chunks = self.fetch(config)
        for chunk in chunks:
            validate_chunk(chunk)
        return chunks


def validate_chunk(chunk: dict) -> None:
    missing = REQUIRED_CHUNK_FIELDS - set(chunk.keys())
    if missing:
        raise ChunkValidationError(
            f"Chunk missing required fields: {sorted(missing)}"
        )
    if not chunk.get("text", "").strip():
        raise ChunkValidationError("Chunk 'text' must not be empty")
