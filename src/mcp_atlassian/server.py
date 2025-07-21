import json
import logging
import os
from collections.abc import Sequence
from typing import Any

import uvicorn
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Resource, TextContent, Tool
from pydantic import AnyUrl
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Mount, Route

from confluence import ConfluenceFetcher
from jira import JiraFetcher

# Configure logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("mcp-atlassian")
logging.getLogger("mcp.server.lowlevel.server").setLevel(logging.WARNING)


def get_available_services():
    """Determine which services are available based on environment variables."""
    confluence_vars = all(
        [os.getenv("CONFLUENCE_URL"), os.getenv("CONFLUENCE_API_TOKEN")]
    )

    jira_vars = all([os.getenv("JIRA_URL"), os.getenv("JIRA_API_TOKEN")])

    return {"confluence": confluence_vars, "jira": jira_vars}


# Initialize services based on available credentials
services = get_available_services()
confluence_fetcher = ConfluenceFetcher() if services["confluence"] else None
jira_fetcher = JiraFetcher() if services["jira"] else None
mcp_server = Server("mcp-atlassian")
server_port = "8093"


@mcp_server.list_resources()
async def list_resources() -> list[Resource]:
    """List available Confluence spaces and Jira projects as resources."""
    resources = []

    # Add Confluence spaces
    if confluence_fetcher:
        spaces_response = confluence_fetcher.get_spaces()
        if isinstance(spaces_response, dict) and "results" in spaces_response:
            spaces = spaces_response["results"]
            resources.extend(
                [
                    Resource(
                        uri=AnyUrl(f"confluence://{space['key']}"),
                        name=f"Confluence Space: {space['name']}",
                        mimeType="text/plain",
                        description=space.get("description", {}).get("plain", {}).get("value", ""),
                    )
                    for space in spaces
                ]
            )

    # Add Jira projects
    if jira_fetcher:
        try:
            projects = jira_fetcher.jira.projects()
            resources.extend(
                [
                    Resource(
                        uri=AnyUrl(f"jira://{project['key']}"),
                        name=f"Jira Project: {project['name']}",
                        mimeType="text/plain",
                        description=project.get("description", ""),
                    )
                    for project in projects
                ]
            )
        except Exception as e:
            logger.error(f"Error fetching Jira projects: {str(e)}")

    return resources


@mcp_server.read_resource()
async def read_resource(uri: AnyUrl) -> str:
    """Read content from Confluence or Jira."""
    uri_str = str(uri)

    # Handle Confluence resources
    if uri_str.startswith("confluence://"):
        if not services["confluence"]:
            raise ValueError("Confluence is not configured. Please provide Confluence credentials.")
        parts = uri_str.replace("confluence://", "").split("/")

        # Handle space listing
        if len(parts) == 1:
            space_key = parts[0]
            documents = confluence_fetcher.get_space_pages(space_key)
            content = []
            for doc in documents:
                content.append(f"# {doc.metadata['title']}\n\n{doc.page_content}\n---")
            return "\n\n".join(content)

        # Handle specific page
        elif len(parts) >= 3 and parts[1] == "pages":
            space_key = parts[0]
            title = parts[2]
            doc = confluence_fetcher.get_page_by_title(space_key, title)

            if not doc:
                raise ValueError(f"Page not found: {title}")

            return doc.page_content

    # Handle Jira resources
    elif uri_str.startswith("jira://"):
        if not services["jira"]:
            raise ValueError("Jira is not configured. Please provide Jira credentials.")
        parts = uri_str.replace("jira://", "").split("/")

        # Handle project listing
        if len(parts) == 1:
            project_key = parts[0]
            issues = jira_fetcher.get_project_issues(project_key)
            content = []
            for issue in issues:
                content.append(f"# {issue.metadata['key']}: {issue.metadata['title']}\n\n{issue.page_content}\n---")
            return "\n\n".join(content)

        # Handle specific issue
        elif len(parts) >= 3 and parts[1] == "issues":
            issue_key = parts[2]
            issue = jira_fetcher.get_issue(issue_key)
            return issue.page_content

    raise ValueError(f"Invalid resource URI: {uri}")


@mcp_server.list_tools()
async def list_tools() -> list[Tool]:
    """List available Confluence and Jira tools."""
    tools = []

    if confluence_fetcher:
        tools.extend(
            [
                Tool(
                    name="confluence_search",
                    description="Search Confluence content using CQL",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "CQL query string (e.g. 'type=page AND space=DEV')",
                            },
                            "limit": {
                                "type": "number",
                                "description": "Maximum number of results (1-50)",
                                "default": 10,
                                "minimum": 1,
                                "maximum": 50,
                            },
                        },
                        "required": ["query"],
                    },
                ),
                Tool(
                    name="confluence_get_page",
                    description="Read confluence page by ID",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "page_id": {"type": "string", "description": "Confluence page ID"},
                            "include_metadata": {
                                "type": "boolean",
                                "description": "Whether to include page metadata",
                                "default": True,
                            },
                        },
                        "required": ["page_id"],
                    },
                ),
                Tool(
                    name="split_page",
                    description="Split confluence page into parts",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "page_id": {"type": "string", "description": "Confluence page ID"},
                            "start": {
                                "type": "number",
                                "description": "Start index of results (1-100)",
                                "default": 0,
                                "minimum": 0
                            },
                            "limit": {
                                "type": "number",
                                "description": "Maximum number of results (1-100)",
                                "default": 10,
                                "minimum": 1,
                                "maximum": 100,
                            },
                        },
                        "required": ["page_id"],
                    },
                ),
                Tool(
                    name="confluence_get_comments",
                    description="Get comments for a specific Confluence page",
                    inputSchema={
                        "type": "object",
                        "properties": {"page_id": {"type": "string", "description": "Confluence page ID"}},
                        "required": ["page_id"],
                    },
                ),
                Tool(
                    name="get_page_by_title",
                    description="Read confluence page title",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "space_key": {"type": "string", "description": "Confluence space"},
                            "title": {"type": "string", "description": "Confluence title"},
                            "include_metadata": {
                                "type": "boolean",
                                "description": "Whether to include page metadata",
                                "default": True,
                            },
                        },
                        "required": ["space_key", "title"],
                    },
                ),
                Tool(
                    name="get_space_pages",
                    description="Get all pages from a specific space",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "space_key": {"type": "string", "description": "Confluence space"},
                            "start": {
                                "type": "number",
                                "description": "Start index of results",
                                "default": 0,
                                "minimum": 0
                            },
                            "limit": {
                                "type": "number",
                                "description": "Maximum number of results",
                                "default": 10,
                                "minimum": 1,
                                "maximum": 50,
                            },
                        },
                        "required": ["space_key"],
                    },
                ),
            ]
        )

    if jira_fetcher:
        tools.extend(
            [
                Tool(
                    name="jira_get_issue",
                    description="Get details of a specific Jira issue",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "issue_key": {"type": "string", "description": "Jira issue key (e.g., 'PROJ-123')"},
                            "expand": {"type": "string", "description": "Optional fields to expand", "default": None},
                        },
                        "required": ["issue_key"],
                    },
                ),
                Tool(
                    name="jira_search",
                    description="Search Jira issues using JQL",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "jql": {"type": "string", "description": "JQL query string"},
                            "fields": {
                                "type": "string",
                                "description": "Comma-separated fields to return",
                                "default": "*all",
                            },
                            "limit": {
                                "type": "number",
                                "description": "Maximum number of results (1-50)",
                                "default": 10,
                                "minimum": 1,
                                "maximum": 50,
                            },
                        },
                        "required": ["jql"],
                    },
                ),
                Tool(
                    name="jira_get_project_issues",
                    description="Get all issues for a specific Jira project",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "project_key": {"type": "string", "description": "The project key"},
                            "limit": {
                                "type": "number",
                                "description": "Maximum number of results (1-50)",
                                "default": 10,
                                "minimum": 1,
                                "maximum": 50,
                            },
                        },
                        "required": ["project_key"],
                    },
                ),
                Tool(
                    name="create_issue",
                    description="Create a new Jira issue",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "projectKey": {
                                "type": "string",
                                "description": "The project key where the issue will be created",
                            },
                            "issueType": {
                                "type": "string",
                                "description": "The type of issue to create (e.g., Bug, Story, Task)",
                            },
                            "summary": {
                                "type": "string",
                                "description": "The issue summary/title",
                            },
                            "descr": {
                                "type": "string",
                                "description": "The issue description",
                            },
                            "fields": {
                                "type": "string",
                                "description": "Additional fields to set on the issue",
                                "additionalProperties": True
                            },
                        },
                        "required": ["projectKey", "issueType", "summary", "descr"]
                    },
                ),
                Tool(
                    name="create_issue_link",
                    description="Create a link between 2 issues",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "linkType": {
                                "type": "string",
                                "description": "The type of link issues",
                            },
                            "inwardIssue": {
                                "type": "string",
                                "description": "Link from issue key",
                            },
                            "outwardIssue": {
                                "type": "string",
                                "description": "Link to issue key",
                            },
                            "comment": {
                                "type": "string",
                                "description": "Comment",
                            }
                        },
                        "required": ["linkType", "inwardIssue", "outwardIssue"]
                    },
                ),
                Tool(
                    name="get_issue_link_types",
                    description="Get issue link types",
                    inputSchema={"type": "object",
                                 "properties": {}},
                ),
            ]
        )

    return tools


@mcp_server.call_tool()
async def call_tool(name: str, arguments: Any) -> Sequence[TextContent]:
    """Handle tool calls for Confluence and Jira operations."""
    try:
        logger.info(f"call_tool: {name}({arguments})")
        if name == "confluence_search":
            limit = min(int(arguments.get("limit", 10)), 50)
            documents = confluence_fetcher.search(arguments["query"], limit)
            search_results = [
                {
                    "page_id": doc.metadata["page_id"],
                    "title": doc.metadata["title"],
                    "space": doc.metadata["space"],
                    "url": doc.metadata["url"],
                    "last_modified": doc.metadata["last_modified"],
                    "type": doc.metadata["type"],
                    "excerpt": doc.page_content,
                }
                for doc in documents
            ]
            logger.info(f"{name}: {search_results})")

            return [TextContent(type="text", text=json.dumps(search_results, indent=2))]

        elif name == "confluence_get_page":
            doc = confluence_fetcher.get_page_content(arguments["page_id"])
            include_metadata = arguments.get("include_metadata", True)

            if include_metadata:
                result = {"content": doc.page_content, "metadata": doc.metadata}
            else:
                result = {"content": doc.page_content}

            logger.info(f"{name}: {result})")

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "confluence_get_comments":
            comments = confluence_fetcher.get_page_comments(arguments["page_id"])
            formatted_comments = [
                {
                    "author": comment.metadata["author_name"],
                    "created": comment.metadata["last_modified"],
                    "content": comment.page_content,
                }
                for comment in comments
            ]

            logger.info(f"{name}: {formatted_comments})")

            return [TextContent(type="text", text=json.dumps(formatted_comments, indent=2))]

        elif name == "split_page":

            start = int(arguments.get("start", 0))
            limit = int(arguments.get("limit", 10))
            page_id = arguments["page_id"]

            documents = confluence_fetcher.split_page(page_id)

            split_results = [
                {
                    "content": doc.page_content,
                    "metadata": doc.metadata,
                }
                for doc in documents[start:start + limit]
            ]

            result = {
                "page_id": page_id,
                "start": start,
                "limit": limit,
                "count": len(documents),
                "parts": split_results
            }

            logger.info(f"{name}: {documents}, {start}, {limit})")

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "get_page_by_title":
            doc = confluence_fetcher.get_page_by_title(arguments["space_key"], arguments["title"])
            include_metadata = arguments.get("include_metadata", True)

            if include_metadata:
                result = {"content": doc.page_content, "metadata": doc.metadata}
            else:
                result = {"content": doc.page_content}

            logger.info(f"{name}: {result})")

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "get_space_pages":
            start = int(arguments.get("start", 0))
            limit = min(int(arguments.get("limit", 10)), 50)
            documents = confluence_fetcher.get_space_pages(arguments["query"], start, limit)
            search_results = [
                {
                    "page_id": doc.metadata["page_id"],
                    "title": doc.metadata["title"],
                    "space": doc.metadata["space"],
                    "url": doc.metadata["url"],
                    "last_modified": doc.metadata["last_modified"],
                    "type": doc.metadata["type"],
                    "excerpt": doc.page_content,
                }
                for doc in documents
            ]
            logger.info(f"{name}: {search_results})")

            return [TextContent(type="text", text=json.dumps(search_results, indent=2))]

        elif name == "jira_get_issue":
            doc = jira_fetcher.get_issue(arguments["issue_key"], expand=arguments.get("expand"))
            result = {"content": doc.page_content, "metadata": doc.metadata}
            logger.info(f"{name}: {result})")
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "jira_search":
            limit = min(int(arguments.get("limit", 10)), 50)
            documents = jira_fetcher.search_issues(
                arguments["jql"], fields=arguments.get("fields", "*all"), limit=limit
            )
            search_results = [
                {
                    "key": doc.metadata["key"],
                    "title": doc.metadata["title"],
                    "type": doc.metadata["type"],
                    "status": doc.metadata["status"],
                    "created_date": doc.metadata["created_date"],
                    "priority": doc.metadata["priority"],
                    "link": doc.metadata["link"],
                    "excerpt": doc.page_content[:500] + "..." if len(doc.page_content) > 500 else doc.page_content,
                }
                for doc in documents
            ]
            logger.info(f"{name}: {search_results})")
            return [TextContent(type="text", text=json.dumps(search_results, indent=2))]

        elif name == "jira_get_project_issues":
            limit = min(int(arguments.get("limit", 10)), 50)
            documents = jira_fetcher.get_project_issues(arguments["project_key"], limit=limit)
            project_issues = [
                {
                    "key": doc.metadata["key"],
                    "title": doc.metadata["title"],
                    "type": doc.metadata["type"],
                    "status": doc.metadata["status"],
                    "created_date": doc.metadata["created_date"],
                    "link": doc.metadata["link"],
                }
                for doc in documents
            ]
            logger.info(f"{name}: {project_issues})")
            return [TextContent(type="text", text=json.dumps(project_issues, indent=2))]

        elif name == "create_issue":
            doc = jira_fetcher.create_issue(arguments["projectKey"], arguments["issueType"], arguments["summary"],
                                            arguments.get("descr"), fields=arguments.get("fields"))
            result = {"content": doc.page_content, "metadata": doc.metadata}
            logger.info(f"{name}: {result})")
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "create_issue_link":
            doc = jira_fetcher.create_issue_link(arguments["linkType"], arguments["inwardIssue"],
                                                 arguments["outwardIssue"],
                                                 arguments.get("comment"))
            result = {"content": doc.page_content, "metadata": doc.metadata}
            logger.info(f"{name}: {result})")
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "get_issue_link_types":
            doc = jira_fetcher.get_issue_link_types()
            result = {"content": doc.page_content, "metadata": doc.metadata}
            logger.info(f"{name}: {result})")
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        raise ValueError(f"Unknown tool: {name}")

    except Exception as e:
        logger.error(f"Tool execution error: {str(e)}")
        raise RuntimeError(f"Tool execution failed: {str(e)}")


def make_server_app() -> Starlette:
    """Create test Starlette app with SSE transport"""
    sse = SseServerTransport("/messages/")

    async def handle_sse(request: Request) -> Response:
        async with sse.connect_sse(
                request.scope, request.receive, request._send
        ) as streams:
            await mcp_server.run(
                streams[0], streams[1], mcp_server.create_initialization_options()
            )
        return Response()

    app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ]
    )

    return app


async def run_stdio():
    # Import here to avoid issues with event loops
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await mcp_server.run(read_stream, write_stream, mcp_server.create_initialization_options())


if __name__ == "__main__":
    app = make_server_app()
    server = uvicorn.Server(
        config=uvicorn.Config(
            app=app, host="127.0.0.1", port=server_port, log_level="info"
        )
    )
    print(f"starting server on {server_port}")
    server.run()
