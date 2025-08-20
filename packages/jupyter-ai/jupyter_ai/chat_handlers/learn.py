import argparse
import json
import os
import time
from collections.abc import Coroutine
from glob import iglob
from typing import Any, Optional

from dask.distributed import Client as DaskClient
from jupyter_ai.document_loaders.directory import (
    EXCLUDE_DIRS,
    arxiv_to_text,
    get_embeddings,
    split,
)
from jupyter_ai.document_loaders.splitter import ExtensionSplitter, NotebookSplitter
from jupyter_ai.models import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    HumanChatMessage,
    IndexedDir,
    IndexMetadata,
)
from jupyter_core.paths import jupyter_data_dir
from jupyter_core.utils import ensure_dir_exists
from langchain.schema import BaseRetriever, Document
from langchain.text_splitter import (
    LatexTextSplitter,
    MarkdownTextSplitter,
    PythonCodeTextSplitter,
    RecursiveCharacterTextSplitter,
)
from langchain_community.vectorstores import FAISS

from .base import BaseChatHandler, SlashCommandRoutingType

# INDEX_SAVE_DIR = os.path.join(jupyter_data_dir(), "jupyter_ai", "indices")
INDEX_SAVE_DIR = os.path.join(os.path.dirname(__file__), "config", "indices")
METADATA_SAVE_PATH = os.path.join(INDEX_SAVE_DIR, "metadata.json")

class LearnChatHandler(BaseChatHandler):
    id = "learn"
    name = "Learn Local Data"
    help = "Teach Jupyternaut about files on your system"
    routing_type = SlashCommandRoutingType(slash_id="learn")

    uses_llm = True
    
    # Flag to control if manual learning is allowed
    _manual_learning_disabled = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        excluded_dirs = ", ".join(EXCLUDE_DIRS)
        self.parser.prog = "/learn"
        self.parser.add_argument(
            "-a",
            "--all-files",
            action="store_true",
            help=f"Include hidden files, hidden directories, and excluded directories ({excluded_dirs})",
        )
        self.parser.add_argument(
            "-v", "--verbose", action="store_true", help="Increase verbosity"
        )
        self.parser.add_argument(
            "-d",
            "--delete",
            action="store_true",
            help="Delete everything previously learned",
        )
        self.parser.add_argument(
            "-l",
            "--list",
            action="store_true",
            help="List directories previously learned",
        )
        self.parser.add_argument(
            "-r",
            "--remote",
            action="store",
            default=None,
            type=str,
            help="Learn a remote document; currently only *arxiv* is supported",
        )
        self.parser.add_argument(
            "-c",
            "--chunk-size",
            action="store",
            default=DEFAULT_CHUNK_SIZE,
            type=int,
            help="Max number of characters in chunk",
        )
        self.parser.add_argument(
            "-o",
            "--chunk-overlap",
            action="store",
            default=DEFAULT_CHUNK_OVERLAP,
            type=int,
            help="Number of characters overlapping between chunks, helpful to ensure text is not split mid-word or mid-sentence",
        )
        self.parser.add_argument("path", nargs=argparse.REMAINDER)
        self.index_name = "default"
        self.index = None
        self.metadata = IndexMetadata(dirs=[])
        self.prev_em_id = None

        self._ensure_dirs()
        self._load()

    def _ensure_dirs(self):
        ensure_dir_exists(INDEX_SAVE_DIR, mode=0o700)

    def _load(self):
        """Loads the vector store."""
        if self.index is not None:
            return

        try:
            embeddings = self.get_embedding_model()
            if not embeddings:
                return

            index_path = os.path.join(INDEX_SAVE_DIR, self.index_name + ".faiss")
            if os.path.exists(index_path):
                self.index = FAISS.load_local(
                    INDEX_SAVE_DIR,
                    embeddings,
                    index_name=self.index_name,
                    allow_dangerous_deserialization=True,
                )
            else:
                self.log.info(
                    "No existing vector index found. You may create one using `/learn`."
                )
            self.load_metadata()
        except Exception as e:
            self.log.error(
                "Could not load vector index from disk. Full exception details printed below."
            )
            self.log.error(e)

    async def process_message(self, message: HumanChatMessage):
        # Check if manual learning is disabled
        if self._manual_learning_disabled:
            self.reply(
                "Manual learning is disabled. The system automatically learns from the project directory on startup."
            )
            return
            
        # If no embedding provider has been selected
        em_provider_cls, em_provider_args = self.get_embedding_provider()
        if not em_provider_cls:
            self.reply(
                "Sorry, please select an embedding provider before using the `/learn` command."
            )
            return

        args = self.parse_args(message)
        if args is None:
            return

        if args.delete:
            self.delete()
            self.reply(f"👍 I have deleted everything I previously learned.", message)
            return

        if args.list:
            self.reply(self._build_list_response())
            return

        if args.remote:
            remote_type = args.remote.lower()
            if remote_type == "arxiv":
                try:
                    id = args.path[0]
                    args.path = [arxiv_to_text(id, self.output_dir)]
                    self.reply(
                        f"Learning arxiv file with id **{id}**, saved in **{args.path[0]}**.",
                        message,
                    )
                except ModuleNotFoundError as e:
                    self.log.error(e)
                    self.reply(
                        "No `arxiv` package found. " "Install with `pip install arxiv`."
                    )
                    return
                except Exception as e:
                    self.log.error(e)
                    self.reply(
                        "An error occurred while processing the arXiv file. "
                        f"Please verify that the arxiv id {id} is correct."
                    )
                    return

        # Make sure the path exists.
        if not (len(args.path) == 1 and args.path[0]):
            no_path_arg_message = (
                "Please specify a directory or pattern you would like to "
                'learn on. "/learn" supports directories relative to '
                "the root (or preferred dir, if set) and Unix-style "
                "wildcard matching.\n\n"
                "Examples:\n"
                "- Learn on the root directory recursively: `/learn .`\n"
                "- Learn on files in the root directory: `/learn *`\n"
                "- Learn all python files under the root directory recursively: `/learn **/*.py`"
            )
            self.reply(f"{self.parser.format_usage()}\n\n {no_path_arg_message}")
            return
        short_path = args.path[0]
        load_path = os.path.join(self.output_dir, short_path)
        if not os.path.exists(load_path):
            try:
                # check if globbing the load path will return anything
                next(iglob(load_path))
            except StopIteration:
                response = f"Sorry, that path doesn't exist: {load_path}"
                self.reply(response, message)
                return

        # delete and relearn index if embedding model was changed
        await self.delete_and_relearn()

        with self.pending(f"Loading and splitting files for {load_path}", message):
            try:
                await self.learn_dir(
                    load_path, args.chunk_size, args.chunk_overlap, args.all_files
                )
            except Exception as e:
                response = """Learn documents in **{}** failed. {}.""".format(
                    load_path.replace("*", r"\*"),
                    str(e),
                )
            else:
                self.save()
                response = """🎉 I have learned documents at **%s** and I am ready to answer questions about them.
                    You can ask questions about these docs by prefixing your message with **/ask**.""" % (
                    load_path.replace("*", r"\*")
                )
        self.reply(response, message)

    def _build_list_response(self):
        if not self.metadata.dirs:
            return "There are no docs that have been learned yet."

        dirs = [dir.path for dir in self.metadata.dirs]
        dir_list = "\n- " + "\n- ".join(dirs) + "\n\n"
        message = f"""I can answer questions from docs in these directories:
        {dir_list}"""
        return message

    async def learn_dir(
        self, path: str, chunk_size: int, chunk_overlap: int, all_files: bool = False
    ):
        self.log.info(f"📁 Processing directory: {path}")
        
        dask_client: DaskClient = await self.dask_client_future
        splitter_kwargs = {"chunk_size": chunk_size, "chunk_overlap": chunk_overlap}
        splitters = {
            ".py": PythonCodeTextSplitter(**splitter_kwargs),
            ".md": MarkdownTextSplitter(**splitter_kwargs),
            ".tex": LatexTextSplitter(**splitter_kwargs),
            ".ipynb": NotebookSplitter(**splitter_kwargs),
        }
        splitter = ExtensionSplitter(
            splitters=splitters,
            default_splitter=RecursiveCharacterTextSplitter(
                **splitter_kwargs  # type:ignore[arg-type]
            ),
        )

        delayed = split(path, all_files, splitter=splitter)
        doc_chunks = await dask_client.compute(delayed)
        
        # Log file processing info
        self.log.info(f"📄 Created {len(doc_chunks)} document chunks")
        file_types = set()
        for chunk in doc_chunks:
            if hasattr(chunk, 'metadata') and 'source' in chunk.metadata:
                source_path = chunk.metadata['source']
                ext = os.path.splitext(source_path)[1]
                if ext:
                    file_types.add(ext)
                self.log.info(f"📑 Processing: {source_path}")
        
        if file_types:
            self.log.info(f"📋 File types: {', '.join(sorted(file_types))}")
        
        em_provider_cls, em_provider_args = self.get_embedding_provider()
        delayed = get_embeddings(doc_chunks, em_provider_cls, em_provider_args)
        embedding_results = await dask_client.compute(delayed)
        embedding_records, metadatas = embedding_results  # Extract both parts of tuple
        
        self.log.info(f"✨ Generated {len(embedding_records)} embeddings")
        
        if self.index:
            self.index.add_embeddings(text_embeddings=embedding_records, metadatas=metadatas)
        else:
            self.create(embedding_records, metadatas)  # Pass metadata to FAISS

        self._add_dir_to_metadata(path, chunk_size, chunk_overlap)
        self.prev_em_id = em_provider_cls.id + ":" + em_provider_args["model_id"]

    def _add_dir_to_metadata(self, path: str, chunk_size: int, chunk_overlap: int):
        dirs = self.metadata.dirs
        index = next((i for i, dir in enumerate(dirs) if dir.path == path), None)
        if not index:
            dirs.append(
                IndexedDir(
                    path=path, chunk_size=chunk_size, chunk_overlap=chunk_overlap
                )
            )
        self.metadata.dirs = dirs

    async def delete_and_relearn(self):
        """Delete the vector store and relearn all indexed directories if
        necessary. If the embedding model is unchanged, this method does
        nothing."""
        if not self.metadata.dirs:
            self.delete()
            return

        em_provider_cls, em_provider_args = self.get_embedding_provider()
        curr_em_id = em_provider_cls.id + ":" + em_provider_args["model_id"]
        prev_em_id = self.prev_em_id

        # TODO: Fix this condition to read the previous EM id from some
        # persistent source. Right now, we just skip this validation on server
        # init, meaning a user could switch embedding models in the config file
        # directly and break their instance.
        if (prev_em_id is None) or (prev_em_id == curr_em_id):
            return

        self.log.info(
            f"Switching embedding provider from {prev_em_id} to {curr_em_id}."
        )
        message = f"""🔔 Hi there, it seems like you have updated the embeddings
        model from `{prev_em_id}` to `{curr_em_id}`. I have to re-learn the
        documents you had previously submitted for learning. Please wait to use
        the **/ask** command until I am done with this task."""

        self.reply(message)

        metadata = self.metadata
        self.delete()
        await self.relearn(metadata)
        self.prev_em_id = curr_em_id

    def delete(self):
        self.index = None
        self.metadata = IndexMetadata(dirs=[])
        paths = [
            os.path.join(INDEX_SAVE_DIR, self.index_name + ext)
            for ext in [".pkl", ".faiss"]
        ]
        for path in paths:
            if os.path.isfile(path):
                os.remove(path)

    async def auto_learn_on_startup(self):
        """Auto-learn from root directory on startup using existing learn logic"""
        startup_start_time = time.time()
        
        try:
            # Check if embedding provider is configured
            em_provider_cls, em_provider_args = self.get_embedding_provider()
            if not em_provider_cls:
                self.log.warning("⚠️  No embedding provider configured. Skipping auto-learning.")
                return

            # Log model info
            model_info = f"{em_provider_cls.id}:{em_provider_args.get('model_id', 'unknown')}"
            self.log.info(f"🚀 AUTO-LEARNING STARTED 🚀")
            self.log.info(f"🔧 Embedding model: {model_info}")
            
            # Clear existing and learn from root
            self.delete()
            self.log.info(f"📚 Learning from: {self.root_dir}")
            
            # Use existing learn_dir method with logging
            await self.learn_dir(self.root_dir, DEFAULT_CHUNK_SIZE, DEFAULT_CHUNK_OVERLAP, all_files=False)
            self.save()
            
            # Calculate and log completion time
            elapsed_time = round(time.time() - startup_start_time, 2)
            self.log.info(f"🎯 AUTO-LEARNING COMPLETED! 🎯")
            self.log.info(f"⏱️  Total time: {elapsed_time} seconds")
            self.log.info(f"💾 Knowledge base ready for /ask queries!")
            
        except Exception as e:
            elapsed_time = round(time.time() - startup_start_time, 2)
            self.log.error(f"💥 AUTO-LEARNING FAILED! 💥")
            self.log.error(f"🔥 Error after {elapsed_time} seconds: {str(e)}")
            self.log.error(f"🔍 Check embedding provider configuration and file permissions")

    async def relearn(self, metadata: IndexMetadata):
        # Index all dirs in the metadata
        if not metadata.dirs:
            return

        for dir in metadata.dirs:
            # TODO: do not relearn directories in serial, but instead
            # concurrently or in parallel
            await self.learn_dir(
                dir.path, dir.chunk_size, dir.chunk_overlap, all_files=False
            )

        self.save()

        dir_list = (
            "\n- " + "\n- ".join([dir.path for dir in self.metadata.dirs]) + "\n\n"
        )
        message = f"""🎉 I am done learning docs in these directories:
        {dir_list} I am ready to answer questions about them.
        You can ask me about these documents by starting your message with **/ask**."""
        self.reply(message)

    def create(
        self,
        embedding_records: list[tuple[str, list[float]]],
        metadatas: Optional[list[dict]] = None,
    ):
        embeddings = self.get_embedding_model()
        if not embeddings:
            return
        self.index = FAISS.from_embeddings(
            text_embeddings=embedding_records, embedding=embeddings, metadatas=metadatas
        )
        self.save()

    def save(self):
        if self.index is not None:
            self.index.save_local(INDEX_SAVE_DIR, index_name=self.index_name)

        self.save_metadata()

    def save_metadata(self):
        with open(METADATA_SAVE_PATH, "w") as f:
            f.write(self.metadata.model_dump_json())

    def load_metadata(self):
        if not os.path.exists(METADATA_SAVE_PATH):
            return

        with open(METADATA_SAVE_PATH, encoding="utf-8") as f:
            j = json.loads(f.read())
            self.metadata = IndexMetadata(**j)

    async def aget_relevant_documents(
        self, query: str
    ) -> Coroutine[Any, Any, list[Document]]:
        if not self.index:
            return []  # type:ignore[return-value]

        await self.delete_and_relearn()
        docs = self.index.similarity_search(query)
        return docs

    def get_embedding_provider(self):
        return self.config_manager.em_provider, self.config_manager.em_provider_params

    def get_embedding_model(self):
        em_provider_cls, em_provider_args = self.get_embedding_provider()
        if em_provider_cls is None:
            return None

        return em_provider_cls(**em_provider_args)


class Retriever(BaseRetriever):
    learn_chat_handler: LearnChatHandler = None  # type:ignore[assignment]

    def _get_relevant_documents(  # type:ignore[override]
        self, query: str
    ) -> list[Document]:
        raise NotImplementedError()

    async def _aget_relevant_documents(  # type:ignore[override]
        self, query: str
    ) -> Coroutine[Any, Any, list[Document]]:
        docs = await self.learn_chat_handler.aget_relevant_documents(query)
        return docs
