import logging
import os
from typing import Optional

from atlassian import Confluence
from dotenv import load_dotenv
from langchain_text_splitters import MarkdownTextSplitter

from config import ConfluenceConfig
from document_types import Document
from preprocessing import TextPreprocessor

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger("mcp-atlassian")


def split_md_document(markdown_document: str):
    markdown_splitter = MarkdownTextSplitter()
    documents = markdown_splitter.create_documents(markdown_splitter.split_text(markdown_document))
    logger.info(f"Total documents: {len(documents)}")
    return documents


class ConfluenceFetcher:
    """Handles fetching and parsing content from Confluence."""

    def __init__(self):
        url = os.getenv("CONFLUENCE_URL")
        token = os.getenv("CONFLUENCE_API_TOKEN")

        if not all([url, token]):
            raise ValueError("Missing required Confluence environment variables")

        self.config = ConfluenceConfig(url=url, api_token=token)
        self.confluence = Confluence(
            url=self.config.url,
            token=self.config.api_token,  # API token is used as password
            cloud=False,
            verify_ssl=False
        )
        self.preprocessor = TextPreprocessor(self.config.url, self.confluence)

    def _process_html_content(self, html_content: str, space_key: str) -> tuple[str, str]:
        return self.preprocessor.process_html_content(html_content, space_key)

    def get_spaces(self, start: int = 0, limit: int = 10):
        """Get all available spaces."""
        return self.confluence.get_all_spaces(start=start, limit=limit)

    def get_page_content(self, page_id: str, clean_html: bool = True) -> Document:
        """Get content of a specific page."""
        page = self.confluence.get_page_by_id(page_id=page_id, expand="body.storage,version,space")
        space_key = page.get("space", {}).get("key", "")

        content = page["body"]["storage"]["value"]
        processed_html, processed_markdown = self._process_html_content(content, space_key)

        # Get author information from version
        version = page.get("version", {})
        author = version.get("by", {})

        metadata = {
            "page_id": page_id,
            "title": page["title"],
            "version": version.get("number"),
            "url": f"{self.config.url}/wiki/spaces/{space_key}/pages/{page_id}",
            "space_key": space_key,
            "author_name": author.get("displayName"),
            "space_name": page.get("space", {}).get("name", ""),
            "last_modified": version.get("when"),
        }

        return Document(page_content=processed_markdown if clean_html else processed_html, metadata=metadata)

    def split_page(
            self, page_id: str, clean_html: bool = True
    ) -> list[Document]:
        """Split a page into parts."""
        page = self.get_page_content(page_id=page_id, clean_html=clean_html)

        documents = split_md_document(page.page_content)

        return documents

    def get_page_by_title(self, space_key: str, title: str, clean_html: bool = True) -> Optional[Document]:
        """Get page content by space key and title."""
        try:
            page = self.confluence.get_page_by_title(space=space_key, title=title, expand="body.storage,version")

            if not page:
                return None

            content = page["body"]["storage"]["value"]
            if clean_html:
                content = self._clean_html_content(content)

            metadata = {
                "page_id": page["id"],
                "title": page["title"],
                "version": page.get("version", {}).get("number"),
                "space_key": space_key,
                "url": f"{self.config.url}/wiki/spaces/{space_key}/pages/{page['id']}",
            }

            return Document(page_content=content, metadata=metadata)

        except Exception as e:
            logger.error(f"Error fetching page: {str(e)}")
            return None

    def get_space_pages(
        self, space_key: str, start: int = 0, limit: int = 10, clean_html: bool = True
    ) -> list[Document]:
        """Get all pages from a specific space."""
        pages = self.confluence.get_all_pages_from_space(
            space=space_key, start=start, limit=limit, expand="body.storage"
        )

        documents = []
        for page in pages:
            content = page["body"]["storage"]["value"]
            if clean_html:
                content = self._clean_html_content(content)

            metadata = {
                "page_id": page["id"],
                "title": page["title"],
                "space_key": space_key,
                "version": page.get("version", {}).get("number"),
                "url": f"{self.config.url}/wiki/spaces/{space_key}/pages/{page['id']}",
            }

            documents.append(Document(page_content=content, metadata=metadata))

        return documents

    def get_page_comments(self, page_id: str, clean_html: bool = True) -> list[Document]:
        """Get all comments for a specific page."""
        page = self.confluence.get_page_by_id(page_id=page_id, expand="space")
        space_key = page.get("space", {}).get("key", "")
        space_name = page.get("space", {}).get("name", "")

        comments = self.confluence.get_page_comments(content_id=page_id, expand="body.view.value,version", depth="all")[
            "results"
        ]

        comment_documents = []
        for comment in comments:
            body = comment["body"]["view"]["value"]
            processed_html, processed_markdown = self._process_html_content(body, space_key)

            # Get author information from version.by instead of author
            author = comment.get("version", {}).get("by", {})

            metadata = {
                "page_id": page_id,
                "comment_id": comment["id"],
                "last_modified": comment.get("version", {}).get("when"),
                "type": "comment",
                "author_name": author.get("displayName"),
                "space_key": space_key,
                "space_name": space_name,
            }

            comment_documents.append(
                Document(page_content=processed_markdown if clean_html else processed_html, metadata=metadata)
            )

        return comment_documents

    def search(self, cql: str, limit: int = 10) -> list[Document]:
        """Search content using Confluence Query Language (CQL)."""
        try:
            results = self.confluence.cql(cql=cql, limit=limit)
            documents = []

            for result in results.get("results", []):
                content = result.get("content", {})
                if content.get("type") == "page":
                    metadata = {
                        "page_id": content["id"],
                        "title": result["title"],
                        "space": result.get("resultGlobalContainer", {}).get("title"),
                        "url": f"{self.config.url}{result['url']}",
                        "last_modified": result.get("lastModified"),
                        "type": content["type"],
                    }

                    # Use the excerpt as page_content since it's already a good summary
                    documents.append(Document(page_content=result.get("excerpt", ""), metadata=metadata))

            return documents
        except Exception as e:
            logger.error(f"Search failed with error: {str(e)}")
            return []
